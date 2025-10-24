# -*- coding: utf-8 -*-
# 파일명: Search_BNE.py
# Version: v1.1.0
# 수정일시: 2025-08-12 KST
# 설명: 스페인 국립도서관(BNE) SRU 카탈로그 검색 로직 (BNE GAS.txt 기반 최종 수정)

import requests
import xml.etree.ElementTree as ET
import re
from qt_api_clients import translate_text_batch_async


# Search_BNE.py 파일 상단의 임포트 부분 다음에 추가
def _should_auto_translate(app_instance):
    """자동 번역 여부를 확인합니다."""
    if hasattr(app_instance, "foreign_auto_translation_var"):
        return app_instance.foreign_auto_translation_var.get()
    return _get_foreign_auto_translation_setting(app_instance)


def _get_foreign_auto_translation_setting(app_instance):
    """해외 도서관 자동 번역 설정을 가져옵니다."""
    if hasattr(app_instance, "db_manager") and app_instance.db_manager:
        value = app_instance.db_manager.get_setting("foreign_auto_translation")
        return value == "true" if value else True  # 기본값: 활성화
    return True


def _parse_marc_record(marc_record_element, namespaces, app_instance):
    """
    BNE의 MARC21-xml 레코드에서 필요한 정보를 추출하여 딕셔너리로 반환합니다.
    (BNE GAS.txt 로직 기반)
    """
    record = {
        "제목": "없음",
        "저자": "없음",
        "출판지역": "없음",
        "출판사": "없음",
        "연도": "없음",
        "650 필드": "없음",
        "650 필드 (번역)": "없음",
        "ISBN": "없음",
        "상세 링크": "없음",
        "주제어_원문": [],
    }

    try:
        control_number = ""
        for field in marc_record_element.findall("marc:controlfield", namespaces):
            tag = field.get("tag")
            value = field.text or ""
            if tag == "001":
                control_number = value
                # ✅ [수정] GAS 로직에 따라 안정적인 영구 링크 생성
                record["상세 링크"] = (
                    f"https://catalogo.bne.es/permalink/34BNE_INST/f0qo1i/alma{value}"
                )
            elif tag == "008" and len(value) >= 11:
                year_str = value[7:11]
                if re.match(r"^\d{4}$", year_str):
                    record["연도"] = year_str

        data_fields = marc_record_element.findall("marc:datafield", namespaces)

        author_field = next(
            (f for f in data_fields if f.get("tag") in ["100", "110"]), None
        )
        if author_field:
            sub_a = author_field.find("marc:subfield[@code='a']", namespaces)
            if sub_a is not None and sub_a.text:
                record["저자"] = sub_a.text.strip().rstrip(",")

        title_field = next((f for f in data_fields if f.get("tag") == "245"), None)
        if title_field:
            # ✅ [수정] GAS 로직에 따라 subfield 'c'까지 포함
            title_parts = [
                sf.text.strip()
                for sf in title_field.findall("marc:subfield", namespaces)
                if sf.get("code") in ["a", "b", "c"] and sf.text
            ]
            record["제목"] = re.sub(r"[,\s/;:]+$", "", " : ".join(title_parts))

        pub_field = next(
            (f for f in data_fields if f.get("tag") in ["260", "264"]), None
        )
        if pub_field:
            # ❗ [유지] GAS에 없지만 UI에 필요한 '출판지역'($a) 정보 추출 로직은 유지
            sub_a = pub_field.find("marc:subfield[@code='a']", namespaces)
            if sub_a is not None and sub_a.text:
                record["출판지역"] = sub_a.text.strip().rstrip(" :")

            sub_b = pub_field.find("marc:subfield[@code='b']", namespaces)
            if sub_b is not None and sub_b.text:
                record["출판사"] = sub_b.text.strip().rstrip(" ,")

            if record["연도"] == "없음":
                sub_c = pub_field.find("marc:subfield[@code='c']", namespaces)
                if sub_c is not None and sub_c.text:
                    year_match = re.search(r"\d{4}", sub_c.text)
                    if year_match:
                        record["연도"] = year_match.group(0)

        isbn_field = next((f for f in data_fields if f.get("tag") == "020"), None)
        if isbn_field:
            sub_a = isbn_field.find("marc:subfield[@code='a']", namespaces)
            if sub_a is not None and sub_a.text:
                record["ISBN"] = re.sub(r"\s*\(.*?\)", "", sub_a.text).strip()

        # ✅ [수정] GAS 로직에 따라 주제어 태그 확장 (600, 610, 650, 651)
        raw_subjects = []
        for field in data_fields:
            if field.get("tag") in ["600", "610", "650", "651"]:
                parts = [
                    sf.text.strip()
                    for sf in field.findall("marc:subfield", namespaces)
                    if sf.get("code") in ["a", "x", "y", "z"] and sf.text
                ]
                if parts:
                    raw_subjects.append(" -- ".join(parts))
        record["주제어_원문"] = raw_subjects

        return record
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"BNE MARC 레코드 파싱 중 오류 발생: {e}", level="ERROR"
            )
        return None


def search_bne_catalog(
    title_query=None,
    author_query=None,
    isbn_query=None,
    year_query=None,
    app_instance=None,
    db_manager=None,
):
    """BNE SRU API를 호출하고 결과를 파싱하여 반환합니다."""
    base_url = "https://catalogo.bne.es/view/sru/34BNE_INST"
    cql_parts = []

    if title_query:
        cql_parts.append(f'alma.title="{title_query}"')
    if author_query:
        cql_parts.append(f'alma.creator="{author_query}"')
    if isbn_query:
        cql_parts.append(f'alma.isbn="{isbn_query.replace("-", "").replace(" ", "")}"')
    if year_query:
        # ✅ [수정] GAS 로직에 따라 정확한 연도 검색 키 'main_pub_date' 사용
        cql_parts.append(f'main_pub_date="{year_query}"')

    if not cql_parts:
        if app_instance:
            app_instance.log_message(
                "경고: BNE 검색을 위한 검색어가 없습니다.", level="WARNING"
            )
        return []

    cql_query = " and ".join(cql_parts)
    params = {
        "version": "1.2",
        "operation": "searchRetrieve",
        "query": cql_query,
        "recordSchema": "marcxml",
        "maximumRecords": "50",
    }

    try:
        # ... (이하 요청, 응답 처리 및 번역 로직은 이전과 동일하게 유지) ...
        if app_instance:
            app_instance.log_message(
                f"정보: BNE API 요청: {base_url}?{requests.compat.urlencode(params)}",
                level="INFO",
            )
        response = requests.get(
            base_url,
            params=params,
            timeout=20,
            headers={"User-Agent": "LibraryTool/1.0"},
        )
        response.raise_for_status()

        namespaces = {
            "zs": "http://www.loc.gov/zing/srw/",
            "marc": "http://www.loc.gov/MARC21/slim",
        }
        root = ET.fromstring(response.content)

        all_results = []
        records_element = root.find("zs:records", namespaces)
        if records_element is None:
            return []

        for record_element in records_element.findall("zs:record", namespaces):
            record_data = record_element.find("zs:recordData", namespaces)
            if record_data is not None:
                marc_record = record_data.find("marc:record", namespaces)
                if marc_record is not None:
                    parsed = _parse_marc_record(marc_record, namespaces, app_instance)
                    if parsed:
                        all_results.append(parsed)

        # ===== 🆕 설정 확인 후 번역 실행 =====
        if (
            all_results
            and app_instance
            and db_manager
            and _should_auto_translate(app_instance)
        ):
            app_instance.log_message("정보: BNE 주제어 번역 시작...", level="INFO")
            all_unique_subjects = set(
                s.strip()
                for record in all_results
                for s in record.get("주제어_원문", [])
                if s and s.strip()
            )

            if all_unique_subjects:
                custom_glossary = (
                    db_manager.get_all_custom_translations() if db_manager else {}
                )
                translation_map = translate_text_batch_async(
                    all_unique_subjects, app_instance, custom_glossary, db_manager
                )

                for record in all_results:
                    raw_subjects = record.get("주제어_원문", [])
                    if raw_subjects:
                        record["650 필드"] = " | ".join(raw_subjects)
                        translated_subjects = [
                            translation_map.get(s.strip(), s.strip())
                            for s in raw_subjects
                            if s and s.strip()
                        ]
                        record["650 필드 (번역)"] = " | ".join(translated_subjects)
                    else:
                        record["650 필드"] = "없음"
                        record["650 필드 (번역)"] = "없음"
                    del record["주제어_원문"]

            app_instance.log_message("정보: BNE 주제어 번역 완료.", level="INFO")

        elif all_results and app_instance:
            # 번역 비활성화 시 원문을 그대로 사용
            app_instance.log_message(
                "정보: 해외 도서관 자동 번역이 비활성화되어 원문 주제어를 사용합니다.",
                level="INFO",
            )

            for record in all_results:
                raw_subjects = record.get("주제어_원문", [])
                if raw_subjects:
                    record["650 필드"] = " | ".join(raw_subjects)
                    record["650 필드 (번역)"] = " | ".join(raw_subjects)  # 원문 그대로
                else:
                    record["650 필드"] = "없음"
                    record["650 필드 (번역)"] = "없음"
                del record["주제어_원문"]

            app_instance.log_message(
                "정보: BNE 주제어 처리 완료 (번역 비활성화).", level="INFO"
            )

        # 출판 연도 기준으로 최신순 정렬
        all_results.sort(key=lambda x: str(x.get("연도", "0")), reverse=True)

        if app_instance:
            app_instance.log_message(
                f"정보: BNE 검색 결과 {len(all_results)}개 레코드 파싱 완료.",
                level="INFO",
            )
        return all_results

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"오류: BNE 검색 중 네트워크 오류: {e}", level="ERROR"
            )
            app_instance.show_messagebox(
                "BNE 서버 연결 오류",
                f"BNE 서버 접속이 불안정합니다.\n\n오류: {e}",
                "error",
            )
        return []
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: BNE 검색 중 예기치 않은 오류: {e}", level="ERROR"
            )
        return []
