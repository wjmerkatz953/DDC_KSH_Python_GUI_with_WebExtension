# -*- coding: utf-8 -*-
# 파일명: Search_DNB.py
# Version: v1.0.7
# 수정일시: 2025-08-09 KST (사용자 피드백 반영: 번역 병렬 처리 강화)

"""
Search_DNB.py - 독일 국립도서관(DNB) SRU 카탈로그를 검색하는 로직을 포함합니다.
Google Apps Script 버전의 로직을 Python으로 포팅했으며, Tab_LC.py와 호환되는 형식으로 결과를 반환합니다.
"""

# ✅ [추가] PyInstaller 환경에서 SSL 인증서 경로 설정
from ssl_cert_utils import configure_ssl_certificates
configure_ssl_certificates()

import requests
import xml.etree.ElementTree as ET
import re
from concurrent.futures import ThreadPoolExecutor
from qt_api_clients import translate_text
from qt_api_clients import translate_text_batch_async


# Search_DNB.py 파일 상단의 임포트 부분 다음에 추가
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
    MARC 레코드에서 필요한 정보를 추출하여 LC 탭과 유사한 딕셔너리로 반환합니다.
    """
    # ✅ 수정: 새로운 컬럼(출판지역, 출판사) 추가
    record = {
        "제목": "없음",
        "저자": "없음",
        "연도": "없음",
        "상세 링크": "없음",
        "ISBN": "없음",
        "LCCN": "없음",
        "082": "없음",
        "082 ind": "없음",
        "245 필드": "없음",
        "250": "없음",
        "650 필드": "없음",
        "출판지역": "없음",
        "출판사": "없음",
        "주제어_원문": [],
        "650 필드 (번역)": "없음",
    }

    try:
        # Control Fields
        for field in marc_record_element.findall("marc:controlfield", namespaces):
            tag = field.get("tag")
            value = field.text or ""
            if tag == "001":
                record["LCCN"] = value  # DNB 고유 식별자를 LCCN 필드에 저장
            elif tag == "008" and len(value) >= 11:
                year_str = value[7:11]
                if re.match(r"^\d{4}$", year_str):
                    record["연도"] = year_str

        # Data Fields
        data_fields = marc_record_element.findall("marc:datafield", namespaces)

        # 저자 (100, 110, 700, 710)
        author_names = []
        for tag in ["100", "110", "700", "710"]:
            for field in data_fields:
                if field.get("tag") == tag:
                    subfield_a = field.find("marc:subfield[@code='a']", namespaces)
                    if subfield_a is not None and subfield_a.text:
                        author_names.append(subfield_a.text.strip())
        record["저자"] = ", ".join(author_names) if author_names else "없음"

        # 제목 (245)
        field_245 = next((f for f in data_fields if f.get("tag") == "245"), None)
        if field_245 is not None:
            sub_a = field_245.find("marc:subfield[@code='a']", namespaces)
            sub_b = field_245.find("marc:subfield[@code='b']", namespaces)
            title_a = sub_a.text.strip() if sub_a is not None and sub_a.text else ""
            title_b = sub_b.text.strip() if sub_b is not None and sub_b.text else ""
            record["제목"] = f"{title_a} : {title_b}".strip(" :")

            all_subfields_245 = [
                sf.text.strip()
                for sf in field_245.findall("marc:subfield", namespaces)
                if sf.text
            ]
            record["245 필드"] = " ".join(all_subfields_245)

        # DDC (082)
        field_082 = next((f for f in data_fields if f.get("tag") == "082"), None)
        if field_082 is not None:
            ind1 = field_082.get("ind1", " ").strip()
            ind2 = field_082.get("ind2", " ").strip()
            record["082 ind"] = f"{ind1}{ind2}".replace(" ", "#")
            sub_a_082 = field_082.find("marc:subfield[@code='a']", namespaces)
            if sub_a_082 is not None and sub_a_082.text:
                record["082"] = sub_a_082.text.strip().replace("/", "")

        # ✅ 추가: 출판 정보 (260, 264)
        publication_field = next(
            (f for f in data_fields if f.get("tag") in ["260", "264"]), None
        )
        if publication_field is not None:
            place_subfield = publication_field.find(
                "marc:subfield[@code='a']", namespaces
            )
            publisher_subfield = publication_field.find(
                "marc:subfield[@code='b']", namespaces
            )
            if place_subfield is not None and place_subfield.text:
                record["출판지역"] = place_subfield.text.strip().rstrip(" :")
            if publisher_subfield is not None and publisher_subfield.text:
                record["출판사"] = publisher_subfield.text.strip().rstrip(" ,")
            # 008 필드에서 연도를 못찾았을 경우 여기서 다시 시도
            if record["연도"] == "없음":
                date_subfield = publication_field.find(
                    "marc:subfield[@code='c']", namespaces
                )
                if date_subfield is not None and date_subfield.text:
                    year_match = re.search(r"\d{4}", date_subfield.text)
                    if year_match:
                        record["연도"] = year_match.group(0)

        # 기타 필드
        raw_subjects = []
        for field in data_fields:
            tag = field.get("tag")

            if tag.startswith("6"):
                subject_parts = [
                    sf.text.strip()
                    for sf in field.findall("marc:subfield", namespaces)
                    if sf.get("code") in ["a", "x", "y", "z"] and sf.text
                ]
                if subject_parts:
                    raw_subjects.append(" -- ".join(subject_parts))
                continue

            sub_a = field.find("marc:subfield[@code='a']", namespaces)
            if sub_a is None or not sub_a.text:
                continue

            if tag == "020" and record["ISBN"] == "없음":
                record["ISBN"] = re.sub(r"\s*\(.*?\)", "", sub_a.text).strip()
            elif tag == "250":
                record["250"] = sub_a.text.strip()
            elif tag == "856":
                sub_u = field.find("marc:subfield[@code='u']", namespaces)
                if sub_u is not None and sub_u.text:
                    record["상세 링크"] = sub_u.text.strip()

        record["주제어_원문"] = raw_subjects

        if record["상세 링크"] == "없음" and record["LCCN"]:
            record["상세 링크"] = f"https://d-nb.info/{record['LCCN']}"

        return record

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"MARC 레코드 파싱 중 오류 발생: {e}", level="ERROR"
            )
        return None


def search_dnb_catalog(
    title_query=None,
    author_query=None,
    isbn_query=None,
    ddc_query=None,
    year_query=None,  # ← 추가!    
    app_instance=None,
    db_manager=None,
):
    """DNB SRU API를 호출하고 LC 탭과 호환되는 형식으로 결과를 파싱하여 반환합니다."""
    base_url = "https://services.dnb.de/sru/dnb"
    cql_parts = []
    if isbn_query:
        cql_parts.append(f"dnb.num=\"{isbn_query.replace('-', '').replace(' ', '')}\"")
    if title_query:
        cql_parts.append(f'dnb.tit="{title_query}"')
    if author_query:
        cql_parts.append(f'dnb.per="{author_query}"')
    if ddc_query:
        cql_parts.append(f'dnb.ddc="{ddc_query}"')
    if year_query:
        cql_parts.append(f'dnb.jhr="{year_query}"')        

    if not cql_parts:
        if app_instance:
            app_instance.log_message(
                "경고: DNB 검색을 위한 검색어가 없습니다.", level="WARNING"
            )
        return []

    cql_query = " and ".join(cql_parts)
    params = {
        "version": "1.1",
        "operation": "searchRetrieve",
        "query": cql_query,
        "recordSchema": "MARC21-xml",
        "maximumRecords": "50",
    }

    try:
        if app_instance:
            app_instance.log_message(
                f"정보: DNB API 요청: {base_url}?{requests.compat.urlencode(params)}",
                level="INFO",
            )
        response = requests.get(
            base_url,
            params=params,
            timeout=15,
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

        # ✅ 수정: BNF 방식의 번역 로직 적용 (병렬 처리 강화)
        # ===== 🆕 설정 확인 후 번역 실행 =====
        if (
            all_results
            and app_instance
            and db_manager
            and _should_auto_translate(app_instance)
        ):
            app_instance.log_message("정보: DNB 주제어 번역 시작...", level="INFO")

            all_unique_subjects = set()
            total_subjects_count = 0
            for record in all_results:
                raw_subjects = record.get("주제어_원문", [])
                total_subjects_count += len(raw_subjects)
                for subject in raw_subjects:
                    if subject and subject.strip():
                        all_unique_subjects.add(subject.strip())

            if app_instance:
                app_instance.log_message(
                    f"📊 통계: 전체 주제어 {total_subjects_count}개 → 고유 주제어 {len(all_unique_subjects)}개",
                    level="INFO",
                )

            # 2단계:
            translation_map = {}
            if all_unique_subjects:
                app_instance.log_message(
                    "🚀🚀 중앙집중 비동기 배치 번역 시스템 시작!", level="INFO"
                )

                # 용어집 가져오기
                custom_glossary_map = {}
                if db_manager:
                    custom_glossary_map = db_manager.get_all_custom_translations()

                # 🚀 중앙집중 비동기 번역 실행!
                translation_map = translate_text_batch_async(
                    all_unique_subjects, app_instance, custom_glossary_map, db_manager
                )

                if not translation_map:
                    # 실패시 기존 동기 방식으로 폴백
                    if app_instance:
                        app_instance.log_message(
                            "⚠️ 비동기 번역 실패, 기존 동기 방식으로 폴백",
                            level="WARNING",
                        )

                    with ThreadPoolExecutor(max_workers=15) as executor:
                        future_to_subject = {
                            executor.submit(
                                translate_text, subject, custom_glossary_map, db_manager
                            ): subject
                            for subject in all_unique_subjects
                        }

                        for future in future_to_subject:
                            subject = future_to_subject[future]
                            try:
                                translation_map[subject] = future.result()
                            except Exception as exc:
                                translation_map[subject] = f"{subject} (번역 오류)"
                                if app_instance:
                                    app_instance.log_message(
                                        f"오류: 주제어 '{subject}' 번역 실패: {exc}",
                                        level="ERROR",
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
                    record["650 필드 (번역)"] = (
                        " | ".join(translated_subjects)
                        if translated_subjects
                        else "없음"
                    )
                else:
                    record["650 필드"] = "없음"
                    record["650 필드 (번역)"] = "없음"

                if "주제어_원문" in record:
                    del record["주제어_원문"]

            app_instance.log_message("정보: DNB 주제어 번역 완료.", level="INFO")

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

                if "주제어_원문" in record:
                    del record["주제어_원문"]

            app_instance.log_message(
                "정보: DNB 주제어 처리 완료 (번역 비활성화).", level="INFO"
            )

        all_results.sort(
            key=lambda x: (
                int(x.get("연도", 0))
                if str(x.get("연도", 0)).isdigit()
                else 0
            ),
            reverse=True,
        )

        if app_instance:
            app_instance.log_message(
                f"정보: DNB 검색 결과 {len(all_results)}개 레코드 파싱 완료.",
                level="INFO",
            )
        return all_results

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"오류: DNB 검색 중 네트워크 오류: {e}", level="ERROR"
            )
            app_instance.show_messagebox(
                "DNB 서버 연결 오류",
                f"DNB 서버 접속이 불안정합니다.\n\n오류: {e}",
                "error",
            )
        return []
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: DNB 검색 중 예기치 않은 오류: {e}", level="ERROR"
            )
        return []
