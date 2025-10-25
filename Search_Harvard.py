# -*- coding: utf-8 -*-
# 파일명: Search_Harvard.py
# Version: v1.0.0
# 생성일시: 2025-09-18 KST
# 설명: Harvard LibraryCloud API를 사용하여 도서 정보를 검색하는 Python 모듈.

import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
import re
from qt_api_clients import translate_text_batch_async


# Search_Harvard.py 파일 상단의 임포트 부분 다음에 추가
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


def _parse_harvard_record(mods_record, ns, app_instance):
    """
    MODS XML에서 서지 정보를 추출합니다. (HOLLIS 영구 링크 사용)
    """
    record = {
        "제목": "",
        "저자": "",
        "출판사": "",
        "연도": "",
        "ISBN": "",
        "상세 링크": "",
        "주제어_원문": [],
        "082": "",
        "082 ind": "",
    }

    try:
        # 1. 제목 (부제 포함)
        title_main_element = mods_record.find(".//mods:titleInfo/mods:title", ns)
        title_main = title_main_element.text if title_main_element is not None else ""
        title_sub_element = mods_record.find(".//mods:titleInfo/mods:subTitle", ns)
        title_sub = title_sub_element.text if title_sub_element is not None else ""
        record["제목"] = f"{title_main}: {title_sub}" if title_sub else title_main

        # 2. 저자 (역할이 'creator'인 경우만)
        authors = []
        name_elements = mods_record.findall(".//mods:name", ns)
        for name_element in name_elements:
            role_term = name_element.find(".//mods:role/mods:roleTerm", ns)
            if role_term is not None and role_term.text == "creator":
                name_part = name_element.find(".//mods:namePart", ns)
                if name_part is not None and name_part.text:
                    authors.append(name_part.text.strip())
        record["저자"] = " | ".join(authors) if authors else "없음"

        # 3. 출판사
        publisher_element = mods_record.find(".//mods:originInfo/mods:publisher", ns)
        if publisher_element is not None:
            record["출판사"] = publisher_element.text or ""

        # 4. 출판 연도
        date_issued_element = mods_record.find(".//mods:originInfo/mods:dateIssued", ns)
        if date_issued_element is not None and date_issued_element.text:
            year_match = re.search(r"\d{4}", date_issued_element.text)
            if year_match:
                record["연도"] = year_match.group(0)

        # 5. ISBN
        isbn_element = mods_record.find('.//mods:identifier[@type="isbn"]', ns)
        if isbn_element is not None:
            record["ISBN"] = isbn_element.text or ""

        # 6. 주제어
        subject_elements = mods_record.findall(".//mods:subject/mods:topic", ns)
        subjects = [subj.text.strip() for subj in subject_elements if subj.text]
        record["주제어_원문"] = subjects

        # --- 🚀 7. 상세 링크 (사용자가 확인한 가장 안정적인 Alma 링크 사용) ---
        link_element = mods_record.find(
            './/mods:relatedItem[@otherType="HOLLIS record"]/mods:location/mods:url', ns
        )
        if link_element is not None and link_element.text:
            record["상세 링크"] = link_element.text.strip()

        # 8. DDC 및 지시자 - 복수 필드 지원
        ddc_elements = mods_record.findall(
            './/mods:classification[@authority="ddc"]', ns
        )
        ddc_values = []

        def is_valid_ddc(value):
            """DDC 분류번호가 유효한지 확인하는 함수"""
            if not value:
                return False
            # DDC는 숫자와 점(.)으로만 구성되어야 함
            import re

            pattern = r"^[0-9]+(\.[0-9]+)*$"
            return bool(re.match(pattern, value))

        for ddc_element in ddc_elements:
            if ddc_element is not None and ddc_element.text:
                ddc_value = ddc_element.text.strip().replace("/", "")

                # DDC 정규화: 유효한 DDC 번호만 수집
                if ddc_value and is_valid_ddc(ddc_value):
                    ddc_values.append(ddc_value)
                elif ddc_value and app_instance:
                    # 유효하지 않은 DDC 발견 시 로그
                    app_instance.log_message(
                        f"경고: Harvard에서 비DDC 텍스트 발견하여 제외: '{ddc_value}'",
                        level="WARNING",
                    )

        # 복수 DDC를 " | "로 구분하여 표시
        record["082"] = " | ".join(ddc_values) if ddc_values else ""
        record["082 ind"] = ""  # Harvard MODS는 지시자 없음 → Blank 처리

        if app_instance and ddc_values:
            app_instance.log_message(
                f"정보: Harvard에서 복수 DDC 추출: {len(ddc_values)}개 - {' | '.join(ddc_values)}",
                level="INFO",
            )

        return record

    except Exception as e:
        if app_instance:
            app_instance.log_message(f"Harvard 레코드 파싱 오류: {e}", level="ERROR")
        return None


def search_harvard_library(
    title_query=None,
    author_query=None,
    isbn_query=None,
    year_query=None,  # ← 추가!
    app_instance=None,
    db_manager=None,
):
    """
    Harvard LibraryCloud API를 호출하고 결과를 파싱하여 반환합니다. (URL 로깅 추가)
    """
    if not app_instance or not db_manager:
        return []
    base_url = "https://api.lib.harvard.edu/v2/items.xml"
    params = {"limit": 50}
    # 쿼리 구성 (기존과 동일)
    if isbn_query:
        # Harvard API 문서에 따른 올바른 ISBN 검색 방법
        cleaned_isbn = isbn_query.replace("-", "").replace(" ", "").strip()
        params["q"] = cleaned_isbn
        # -------------------
        # ISBN 검색 시에도 연도 필터 적용
        if year_query:
            params["dateIssued"] = year_query
        # -------------------
    elif title_query or author_query:
        if title_query:
            params["title"] = title_query
        if author_query:
            params["name"] = author_query
        # -------------------
        # 제목/저자 검색 시 연도 필터 적용
        if year_query:
            params["dateIssued"] = year_query
        # -------------------
    # -------------------
    elif year_query:
        # 연도만 검색하는 경우
        params["dateIssued"] = year_query
    # -------------------
    else:
        app_instance.log_message(
            "경고: Harvard 검색을 위한 검색어가 없습니다.", level="WARNING"
        )
        return []

    try:
        # --- 🚀 최종 요청 URL 생성 및 로그 기록 ---
        request_url = f"{base_url}?{urlencode(params)}"
        app_instance.log_message(
            f"정보: Harvard LibraryCloud API 최종 요청 URL:\n{request_url}",
            level="INFO",
        )

        response = requests.get(request_url, timeout=20)
        response.raise_for_status()

        # 응답이 비어있는 경우 처리
        if not response.content:
            app_instance.log_message(
                "정보: Harvard API에서 비어있는 응답을 받았습니다.", level="INFO"
            )
            return []

        root = ET.fromstring(response.content)
        ns = {"mods": "http://www.loc.gov/mods/v3"}

        mods_records = root.findall(".//mods:mods", ns)
        if not mods_records:
            app_instance.log_message(
                "정보: Harvard 검색 결과가 없습니다 (mods 레코드 없음).", level="INFO"
            )
            return []

        all_results = []
        for record_xml in mods_records:
            parsed = _parse_harvard_record(record_xml, ns, app_instance)
            if parsed:
                all_results.append(parsed)

        # 주제어 일괄 번역
        # ===== 🆕 설정 확인 후 번역 실행 =====
        if all_results and app_instance and _should_auto_translate(app_instance):
            app_instance.log_message("정보: Harvard 주제어 번역 시작...", level="INFO")

            all_unique_subjects = set(
                s.strip()
                for record in all_results
                for s in record.get("주제어_원문", [])
                if s
            )
            if all_unique_subjects:
                custom_glossary = db_manager.get_all_custom_translations()
                translation_map = translate_text_batch_async(
                    list(all_unique_subjects), app_instance, custom_glossary, db_manager
                )
                for record in all_results:
                    raw_subjects = record.get("주제어_원문", [])
                    record["650 필드"] = " | ".join(raw_subjects)
                    translated = [
                        translation_map.get(s.strip(), s.strip()) for s in raw_subjects
                    ]
                    record["650 필드 (번역)"] = " | ".join(translated)
                    del record["주제어_원문"]

            app_instance.log_message("정보: Harvard 주제어 번역 완료.", level="INFO")

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
                "정보: Harvard 주제어 처리 완료 (번역 비활성화).", level="INFO"
            )

        app_instance.log_message(
            f"정보: Harvard 검색 결과 {len(all_results)}건 파싱 완료.", level="INFO"
        )
        return all_results

    except requests.exceptions.RequestException as e:
        app_instance.log_message(f"오류: Harvard API 네트워크 오류: {e}", level="ERROR")
        return []
    except Exception as e:
        app_instance.log_message(
            f"오류: Harvard API 처리 중 예기치 않은 오류: {e}", level="ERROR"
        )
        return []
