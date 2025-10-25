# -*- coding: utf-8 -*-
# 파일명: Search_BNF.py
# Version: v1.0.0
# 수정일시: 2025-08-08 KST (GAS BNF 로직 파이썬 포팅)

"""
Search_BNF.py - 프랑스 국립도서관(BNF) SRU 카탈로그를 검색하는 로직을 포함합니다.
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


# Search_BNF.py 파일 상단의 임포트 부분 다음에 추가
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


def _parse_unimarc_record(unimarc_record_element, namespaces, app_instance):
    """
    UNIMARC 레코드에서 필요한 정보를 추출하여 LC 탭과 유사한 딕셔너리로 반환합니다.
    """
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
        "출판사": "없음",  # 통일된 컬럼명 사용
        # BNF 전용 필드들 (필요 시 유지)
        "ISSN": "없음",
        "ISMN": "없음",
        "EAN": "없음",
        "언어": "없음",
        "물리적형태": "없음",
        "전자접근": "없음",
        "주제어_원문": [],
        "650 필드 (번역)": "없음",
    }

    def get_subfield_value(datafield_element, codes, separator=" "):
        """특정 서브필드 값들을 가져와 문자열로 결합"""
        values = []
        for subfield in datafield_element.findall("marc:subfield", namespaces):
            code = subfield.get("code")
            if code in codes and subfield.text:
                values.append(subfield.text.strip())
        result = separator.join(values).strip()
        # 끝의 구두점 제거 (대괄호는 중요한 서지정보이므로 보존!)
        return re.sub(r"[\/,;:]\s*$", "", result).strip()

    try:
        # Control Fields
        for field in unimarc_record_element.findall("marc:controlfield", namespaces):
            tag = field.get("tag")
            value = field.text or ""

            if tag == "001":  # BNF 고유 식별자
                record["LCCN"] = value.strip()
            elif tag == "003":  # 상세 페이지 링크
                if value.strip():
                    record["상세 링크"] = value.strip()

        # Data Fields
        data_fields = unimarc_record_element.findall("marc:datafield", namespaces)
        raw_subjects = []
        isbn_list = []  # 모든 ISBN을 수집할 리스트

        for field in data_fields:
            tag = field.get("tag")

            if tag == "010":  # ISBN (여러 개의 010 필드가 있을 수 있음)
                isbn_value = get_subfield_value(field, ["a"])
                if isbn_value:
                    isbn_list.append(isbn_value)  # 모든 ISBN을 리스트에 추가

            elif tag == "011":  # ISSN
                record["ISSN"] = get_subfield_value(field, ["a"])

            elif tag == "012":  # ISMN
                record["ISMN"] = get_subfield_value(field, ["a"])

            elif tag == "020":  # EAN
                record["EAN"] = get_subfield_value(field, ["a"])

            elif tag == "101":  # 언어
                record["언어"] = get_subfield_value(field, ["a"])

            elif tag == "200":  # 제목 및 책임 표시
                title_value = get_subfield_value(
                    field, ["a", "b", "c", "d", "e", "f", "g", "h", "i"], " : "
                )
                if title_value:
                    record["제목"] = title_value
                    record["245 필드"] = title_value

            elif tag == "205":  # 판차
                record["250"] = get_subfield_value(field, ["a"])

            elif tag in [
                "210",
                "214",
            ]:  # 발행, 배포 등 (210: 표준 UNIMARC, 214: BNF 특화)
                publication_place = get_subfield_value(field, ["a"])
                publisher = get_subfield_value(field, ["c"])
                year_value = get_subfield_value(field, ["d"])

                # 🎯 핵심 로직: 연도가 있는 필드만 처리하거나, 아직 설정되지 않은 경우만 처리
                has_year = year_value and re.search(r"\d{4}", year_value)

                # 출판지역 설정 (대괄호 등 원본 그대로 보존!!!)
                if publication_place and (has_year or record["출판지역"] == "없음"):
                    record["출판지역"] = publication_place  # 원본 그대로 저장

                # 출판사 설정 (원본 그대로 보존)
                if publisher and (has_year or record["출판사"] == "없음"):
                    record["출판사"] = publisher

                # 출판연도 설정 (연도가 있는 경우만)
                if has_year:
                    year_match = re.search(r"\d{4}", year_value)
                    record["연도"] = year_match.group(0)

            elif tag == "215":  # 물리적 형태
                record["물리적형태"] = get_subfield_value(field, ["a", "c"])

            elif tag in ["300", "327", "330"]:  # 주석, 내용, 요약
                note_content = get_subfield_value(
                    field,
                    [
                        "a",
                        "b",
                        "c",
                        "d",
                        "e",
                        "f",
                        "g",
                        "h",
                        "i",
                        "j",
                        "k",
                        "l",
                        "m",
                        "n",
                        "o",
                        "p",
                        "q",
                        "r",
                        "s",
                        "t",
                        "u",
                        "v",
                        "w",
                        "x",
                        "y",
                        "z",
                    ],
                )
                # 나중에 사용할 수 있도록 저장

            elif tag in ["606", "607", "608", "610", "611", "612"]:  # 주제어 필드들
                subject_parts = []
                for subfield in field.findall("marc:subfield", namespaces):
                    code = subfield.get("code")
                    if code in ["a", "x", "y", "z", "c"] and subfield.text:
                        subject_parts.append(subfield.text.strip())
                if subject_parts:
                    raw_subjects.append(" -- ".join(subject_parts))

            elif tag == "620":  # DDC (Dewey Decimal Classification)
                ddc_value = get_subfield_value(field, ["a"])
                if ddc_value and record["082"] == "없음":
                    record["082"] = ddc_value
                # 지시자 추출 (082 필드와 동일한 방식)
                if record["082 ind"] == "없음":
                    ind1 = field.get("ind1", " ").strip()
                    ind2 = field.get("ind2", " ").strip()
                    record["082 ind"] = f"{ind1}{ind2}".replace(" ", "#")

            elif tag == "676":  # 추가 DDC 필드 (620에서 찾지 못했을 경우)
                if record["082"] == "없음":
                    ddc_value = get_subfield_value(field, ["a"])
                    if ddc_value:
                        record["082"] = ddc_value
                    # 지시자 추출
                    if record["082 ind"] == "없음":
                        ind1 = field.get("ind1", " ").strip()
                        ind2 = field.get("ind2", " ").strip()
                        record["082 ind"] = f"{ind1}{ind2}".replace(" ", "#")

            elif tag in ["700", "701", "710"]:  # 저자 필드들
                if record["저자"] == "없음":
                    author_value = get_subfield_value(
                        field, ["a", "b", "c", "d", "f", "g"]
                    )
                    if author_value:
                        record["저자"] = author_value

            elif tag == "856":  # 전자 위치 및 접근
                electronic_link = get_subfield_value(field, ["u"])
                if electronic_link:
                    record["전자접근"] = electronic_link
                    # 상세 링크가 없으면 전자접근 링크를 상세 링크로 사용
                    if record["상세 링크"] == "없음":
                        record["상세 링크"] = electronic_link

        # ISBN 리스트를 문자열로 결합 (여러 ISBN 표시)
        if isbn_list:
            record["ISBN"] = " | ".join(isbn_list)  # 구분자로 연결

        # 주제어 처리
        record["주제어_원문"] = raw_subjects
        if raw_subjects:
            record["650 필드"] = " | ".join(raw_subjects)

        # 폴백 링크 생성
        if record["상세 링크"] == "없음" and record["LCCN"]:
            record["상세 링크"] = (
                f"https://catalogue.bnf.fr/ark:/12148/cb{record['LCCN']}"
            )

        return record

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"UNIMARC 레코드 파싱 중 오류 발생: {e}", level="ERROR"
            )
        return None


def search_bnf_catalog(
    title_query=None,
    author_query=None,
    isbn_query=None,
    ddc_query=None,
    year_query=None,  # ← 추가!
    app_instance=None,
    db_manager=None,
):
    """BNF SRU API를 호출하고 LC 탭과 호환되는 형식으로 결과를 파싱하여 반환합니다."""
    base_url = "https://catalogue.bnf.fr/api/SRU"

    # CQL 쿼리 구성 (5개 필드: 제목, 저자, ISBN, DDC, 연도)
    query_parts = []
    if title_query:
        query_parts.append(f'bib.title all "{title_query}"')
    if author_query:
        query_parts.append(f'bib.author all "{author_query}"')
    if isbn_query:
        clean_isbn = isbn_query.replace("-", "").replace(" ", "")
        query_parts.append(f'bib.isbn all "{clean_isbn}"')
    if ddc_query:
        query_parts.append(f'bib.dewey any "{ddc_query}"')
    if year_query:  # ← 추가!
        query_parts.append(f'bib.publicationdate="{year_query}"')

    if not query_parts:
        if app_instance:
            app_instance.log_message(
                "경고: BNF 검색을 위한 검색어가 없습니다.", level="WARNING"
            )
        return []

    cql_query = " and ".join(query_parts)

    params = {
        "operation": "searchRetrieve",
        "version": "1.2",
        "query": cql_query,
        "recordSchema": "unimarcXchange",
        "maximumRecords": "50",
    }

    try:
        if app_instance:
            app_instance.log_message(
                f"정보: BNF API 요청: {base_url} (쿼리: {cql_query})", level="INFO"
            )

        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()

        if app_instance:
            app_instance.log_message(
                f"정보: BNF API 응답 상태: {response.status_code}", level="INFO"
            )

        xml_content = response.text

        # XML 응답 파싱
        root = ET.fromstring(xml_content)

        # 네임스페이스 정의
        namespaces = {
            "srw": "http://www.loc.gov/zing/srw/",
            "marc": "info:lc/xmlns/marcxchange-v2",
        }

        # 검색 결과 레코드 추출
        records_element = root.find("srw:records", namespaces)
        if records_element is None:
            if app_instance:
                app_instance.log_message(
                    "정보: BNF 검색 결과가 없습니다.", level="INFO"
                )
            return []

        record_elements = records_element.findall("srw:record", namespaces)

        results = []
        for record_element in record_elements:
            if app_instance and app_instance.stop_search_flag.is_set():
                break

            record_data_element = record_element.find("srw:recordData", namespaces)
            if record_data_element is None:
                continue

            unimarc_record = record_data_element.find("marc:record", namespaces)
            if unimarc_record is None:
                continue

            parsed_record = _parse_unimarc_record(
                unimarc_record, namespaces, app_instance
            )
            if parsed_record:
                results.append(parsed_record)

        # 연도 기준으로 최신순 정렬
        results.sort(
            key=lambda x: int(x["연도"]) if x["연도"].isdigit() else 0,
            reverse=True,
        )

        # === 🚀 NDL 방식의 주제어 번역 로직 적용 ===
        # ===== 🆕 설정 확인 후 번역 실행 =====
        if results and app_instance and _should_auto_translate(app_instance):
            app_instance.log_message("정보: BNF 주제어 번역 시작...", level="INFO")

            # 1단계: 모든 고유 주제어 수집 및 중복 제거
            all_unique_subjects = set()
            total_subjects_count = 0

            for record in results:
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
                if total_subjects_count > len(all_unique_subjects):
                    app_instance.log_message(
                        f"⚡ 성능 개선: {total_subjects_count - len(all_unique_subjects)}번의 중복 번역 제거!",
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

            # 3단계: 번역 결과를 각 레코드에 적용 (NDL 방식)
            for record in results:
                raw_subjects = record.get("주제어_원문", [])
                if raw_subjects:
                    # 원문 주제어 설정
                    record["650 필드"] = " | ".join(raw_subjects)
                    # 번역된 주제어 설정 (중복 제거 적용)
                    translated_subjects = []
                    seen_translations = set()

                    for subject in raw_subjects:
                        subject = subject.strip()
                        if subject:
                            translated = translation_map.get(subject, subject)
                            if translated not in seen_translations:
                                translated_subjects.append(translated)
                                seen_translations.add(translated)

                    record["650 필드 (번역)"] = (
                        " | ".join(translated_subjects)
                        if translated_subjects
                        else "없음"
                    )
                else:
                    record["650 필드"] = "없음"
                    record["650 필드 (번역)"] = "없음"

                # 주제어_원문은 더 이상 필요 없으므로 제거 (NDL 방식)
                if "주제어_원문" in record:
                    del record["주제어_원문"]

            app_instance.log_message("정보: BNF 주제어 번역 완료.", level="INFO")

        elif results and app_instance:
            # 번역 비활성화 시 원문을 그대로 사용
            app_instance.log_message(
                "정보: 해외 도서관 자동 번역이 비활성화되어 원문 주제어를 사용합니다.",
                level="INFO",
            )

            for record in results:
                raw_subjects = record.get("주제어_원문", [])
                if raw_subjects:
                    record["650 필드"] = " | ".join(raw_subjects)
                    record["650 필드 (번역)"] = " | ".join(raw_subjects)  # 원문 그대로
                else:
                    record["650 필드"] = "없음"
                    record["650 필드 (번역)"] = "없음"

                # 주제어_원문은 더 이상 필요 없으므로 제거
                if "주제어_원문" in record:
                    del record["주제어_원문"]

            app_instance.log_message(
                "정보: BNF 주제어 처리 완료 (번역 비활성화).", level="INFO"
            )

        app_instance.log_message(
            f"정보: BNF 검색 완료. {len(results)}개 결과 반환.", level="INFO"
        )
        return results

    except requests.exceptions.RequestException as e:
        error_message = f"BNF API 요청 중 네트워크 오류 발생: {e}"
        if app_instance:
            app_instance.log_message(f"오류: {error_message}", level="ERROR")
        raise ConnectionError(error_message)

    except ET.ParseError as e:
        error_message = f"BNF API 응답 XML 파싱 오류: {e}"
        if app_instance:
            app_instance.log_message(f"오류: {error_message}", level="ERROR")
        raise ValueError(error_message)

    except Exception as e:
        error_message = f"BNF 검색 중 예기치 않은 오류 발생: {e}"
        if app_instance:
            app_instance.log_message(f"오류: {error_message}", level="ERROR")
        raise RuntimeError(error_message)
