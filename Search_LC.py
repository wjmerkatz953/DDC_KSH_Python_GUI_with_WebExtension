# -*- coding: utf-8 -*-
# Version: v1.0.65
# 수정일시: 2025-08-09 19:30 KST (발행지, 출판 연도, 출판사 파싱 로직 추가)

"""
Search_LC.py - LC(Library of Congress) SRU 카탈로그를 검색하는 로직을 포함합니다.
"""

# ✅ [추가] PyInstaller 환경에서 SSL 인증서 경로 설정
from ssl_cert_utils import configure_ssl_certificates
configure_ssl_certificates()

import requests
import xml.etree.ElementTree as ET
import re
from urllib.parse import quote_plus


def search_lc_catalog(
    isbn_query=None,
    title_query=None,
    author_query=None,
    year_query=None,
    app_instance=None,
):
    """
    LC SRU 카탈로그를 검색하고 결과를 파싱합니다.
    """
    base_url = "http://lx2.loc.gov:210/LCDB"
    query_parts = []

    # 특수 문자를 이스케이프하는 헬퍼 함수
    def escape_sru_query_term(term):
        # SRU 쿼리에서 특별한 의미를 가질 수 있는 문자들을 이스케이프합니다.
        # 여기서는 큰따옴표(")를 이스케이프하여 구문 검색 내에서 리터럴 큰따옴표를 사용할 수 있게 합니다.
        chars_to_escape = r"*!^\"<>=/\#@$%&{}|~"
        escaped_term = ""
        for char in term:
            if char in chars_to_escape:
                escaped_term += "\\" + char
            else:
                escaped_term += char
        return escaped_term

    if isbn_query:
        query_parts.append(f"bath.isbn={escape_sru_query_term(isbn_query)}")

    if title_query:
        original_title_query = title_query
        # 제목 쿼리에서 물음표만 제거합니다. 다른 구두점은 유지합니다.
        title_query_cleaned = title_query.replace("?", "").strip()

        # 처리된 제목 쿼리를 큰따옴표로 묶어 구문 검색을 수행하도록 합니다.
        processed_title_query = escape_sru_query_term(title_query_cleaned)
        query_parts.append(f'bath.title="{processed_title_query}"')

        if original_title_query != title_query_cleaned and app_instance:
            app_instance.log_message(
                f"정보: LC 제목 검색어에서 물음표가 제거되고 구문 검색을 위해 처리되었습니다: '{original_title_query}' -> '\"{processed_title_query}\"'",
                level="INFO",
            )

    if author_query:
        query_parts.append(f"bath.author={escape_sru_query_term(author_query)}")

    # -------------------
    # year_query는 SRU 쿼리에 포함하지 않고, 결과를 받은 후 Python에서 필터링
    # (LC SRU가 출판 연도 검색을 제대로 지원하지 않으므로)
    if year_query:
        if app_instance:
            app_instance.log_message(
                f"정보: 출판 연도 '{year_query}'는 결과 수신 후 Python에서 필터링 예정",
                level="INFO",
            )
    # -------------------

    if not query_parts:
        if app_instance:
            app_instance.log_message(
                "경고: LC 검색을 위한 쿼리 조건이 없습니다.", level="WARNING"
            )
        return []

    query_string = " and ".join(query_parts)
    params = {
        "operation": "searchRetrieve",
        "version": "1.1",
        "query": query_string,
        "maximumRecords": 50,  # 최대 50개 레코드 요청
        "recordSchema": "marcxml",  # MARCXML 형식으로 요청
    }

    try:
        if app_instance:
            app_instance.log_message(
                f"정보: LC SRU API 요청: {base_url}?{requests.compat.urlencode(params)}",
                level="INFO",
            )

        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 발생

        if app_instance:
            app_instance.log_message("정보: LC SRU API 응답 수신 완료.", level="INFO")

        root = ET.fromstring(response.content)

        # 네임스페이스 정의
        namespaces = {
            "zs": "http://www.loc.gov/zing/srw/",
            "marc": "http://www.loc.gov/MARC21/slim",
        }

        records = []
        for record_element in root.findall(".//marc:record", namespaces):
            record_data = {}

            # 008 필드에서 발행 연도 추출 (예: 008/07-10)
            field_008 = record_element.find(
                ".//marc:controlfield[@tag='008']", namespaces
            )
            if field_008 is not None and field_008.text and len(field_008.text) >= 11:
                record_data["연도"] = field_008.text[7:11].strip()
            else:
                record_data["연도"] = "없음"

            # 245 필드 (제목)
            field_245 = record_element.find(".//marc:datafield[@tag='245']", namespaces)
            if field_245 is not None:
                # GAS 로직을 참고하여 제목($a, $b) 및 245필드(전체)를 별도로 처리

                # $a, $b 하위 필드 텍스트 추출
                subfield_a_element = field_245.find(
                    "marc:subfield[@code='a']", namespaces
                )
                a_content = (
                    subfield_a_element.text.strip()
                    if subfield_a_element is not None and subfield_a_element.text
                    else ""
                )

                subfield_b_element = field_245.find(
                    "marc:subfield[@code='b']", namespaces
                )
                b_content = (
                    subfield_b_element.text.strip()
                    if subfield_b_element is not None and subfield_b_element.text
                    else ""
                )

                # GAS 로직과 동일하게 제목 가공
                main_title = ""
                sub_title = ""

                # $a 내용 자체에 콜론이 있는 경우, 부제로 분리
                if ":" in a_content:
                    parts = a_content.split(":", 1)
                    main_title = parts[0].strip()
                    sub_title = parts[1].strip()
                else:
                    main_title = a_content.strip()

                # $b 내용을 부제에 추가
                if b_content:
                    if not sub_title:
                        sub_title = b_content.strip()
                    else:
                        sub_title += " " + b_content.strip()

                # ✨ 수정: 후행 구두점(슬래시 등) 제거 로직 추가
                main_title = re.sub(r"\s*[/:]\s*$", "", main_title).strip()
                sub_title = re.sub(r"\s*[/:]\s*$", "", sub_title).strip()

                # 최종 '제목' 컬럼 포맷 생성
                formatted_title = f"▼a{main_title}"
                if sub_title:
                    formatted_title += f" :▼b{sub_title}"
                formatted_title += "▲"

                record_data["제목"] = formatted_title

                # '245 필드' 컬럼은 기존 로직을 유지하여 전체 내용을 보여줍니다.
                all_subfields_245_raw = []
                for subfield in field_245.findall("marc:subfield", namespaces):
                    if subfield.text:
                        all_subfields_245_raw.append(subfield.text.strip())

                raw_245_content = " ".join(all_subfields_245_raw).strip()
                raw_245_content = re.sub(r"\s+", " ", raw_245_content)
                record_data["245 필드"] = raw_245_content if raw_245_content else "없음"

            else:
                record_data["제목"] = "없음"
                record_data["245 필드"] = "없음"

            # 100, 110, 700, 710 필드 (저자)
            author_names = []
            for tag in ["100", "110", "700", "710"]:
                fields = record_element.findall(
                    f".//marc:datafield[@tag='{tag}']", namespaces
                )
                for field in fields:
                    subfield_a = field.find("marc:subfield[@code='a']", namespaces)
                    if subfield_a is not None and subfield_a.text:
                        author_names.append(subfield_a.text.strip())
            record_data["저자"] = ", ".join(author_names) if author_names else "없음"

            # 010 필드 (LCCN) 추출 및 상세 링크 생성
            lccn_link = "없음"
            lccn_value = "없음"

            # 010 필드에서 LCCN 추출 시도 (가장 정확)
            field_010 = record_element.find(".//marc:datafield[@tag='010']", namespaces)
            if field_010 is not None:
                subfield_a_lccn = field_010.find("marc:subfield[@code='a']", namespaces)
                if subfield_a_lccn is not None and subfield_a_lccn.text:
                    lccn = subfield_a_lccn.text.strip()
                    # GAS 버전과 동일하게 공백만 제거
                    cleaned_lccn = lccn.replace(" ", "")
                    lccn_value = cleaned_lccn
                    # 변경된 부분: search.catalog.loc.gov 형식으로 상세 링크 생성
                    lccn_link = f"https://search.catalog.loc.gov/search?option=lccn&query={lccn_value}"
                    if app_instance:
                        app_instance.log_message(
                            f"정보: LCCN (010 필드) 추출 및 상세 링크 생성 성공: {lccn_link}",
                            level="INFO",
                        )

            # 010 필드에서 유효한 LCCN을 찾지 못했을 경우 001 필드 확인 (폴백)
            if lccn_value == "없음":
                field_001 = record_element.find(
                    ".//marc:controlfield[@tag='001']", namespaces
                )
                if field_001 is not None and field_001.text:
                    lccn = field_001.text.strip()
                    # GAS 버전과 동일하게 공백만 제거
                    cleaned_lccn = lccn.replace(" ", "")
                    lccn_value = cleaned_lccn
                    # 변경된 부분: search.catalog.loc.gov 형식으로 상세 링크 생성
                    lccn_link = f"https://search.catalog.loc.gov/search?option=lccn&query={lccn_value}"
                    if app_instance:
                        app_instance.log_message(
                            f"정보: LCCN (001 필드) 추출 및 상세 링크 생성 성공: {lccn_link}",
                            level="INFO",
                        )

            record_data["LCCN"] = lccn_value  # LCCN 값을 별도로 저장
            record_data["상세 링크"] = lccn_link  # 상세 링크는 LCCN 기반 링크로 설정

            # 020 필드 (ISBN) 추출 - 모든 020 필드에서 ISBN 수집
            isbn_list = []
            fields_020 = record_element.findall(
                ".//marc:datafield[@tag='020']", namespaces
            )
            for field_020 in fields_020:
                # 각 020 필드의 모든 subfield 'a' 처리
                subfields_a = field_020.findall("marc:subfield[@code='a']", namespaces)
                for subfield_a_isbn in subfields_a:
                    if subfield_a_isbn is not None and subfield_a_isbn.text:
                        isbn_raw = subfield_a_isbn.text.strip()
                        # ISBN에서 괄호 안의 내용 (적격자) 제거 및 공백/하이픈 제거
                        isbn_cleaned = re.sub(r"\s*\(.*?\)", "", isbn_raw)
                        isbn_cleaned = re.sub(r"[\s\-]", "", isbn_cleaned)
                        # 유효한 ISBN만 추가 (숫자와 X로만 구성되고 10자리 또는 13자리)
                        if re.match(
                            r"^[\dX]{10}$|^[\dX]{13}$", isbn_cleaned, re.IGNORECASE
                        ):
                            isbn_list.append(isbn_cleaned)
                            if app_instance:
                                app_instance.log_message(
                                    f"정보: ISBN (020 필드) 추출 성공: {isbn_cleaned}",
                                    level="INFO",
                                )

            # ISBN 목록을 파이프(|)로 구분하여 저장
            if isbn_list:
                # 중복 제거 (순서 유지)
                unique_isbns = []
                seen = set()
                for isbn in isbn_list:
                    if isbn not in seen:
                        unique_isbns.append(isbn)
                        seen.add(isbn)

                record_data["ISBN"] = " | ".join(unique_isbns)
                if app_instance:
                    app_instance.log_message(
                        f"정보: 총 {len(unique_isbns)}개의 고유 ISBN 추출 완료: {record_data['ISBN']}",
                        level="INFO",
                    )
            else:
                record_data["ISBN"] = "없음"
                if app_instance:
                    app_instance.log_message(
                        "정보: 020 필드에서 유효한 ISBN을 찾을 수 없습니다.",
                        level="INFO",
                    )

            # 082 필드 (DDC)
            field_082 = record_element.find(".//marc:datafield[@tag='082']", namespaces)
            if field_082 is not None:
                subfield_a = field_082.find("marc:subfield[@code='a']", namespaces)
                if subfield_a is not None:
                    # ❗ 수정: 슬래시 제거
                    record_data["082"] = subfield_a.text.strip().replace("/", "")
                else:
                    record_data["082"] = "없음"
            else:
                record_data["082"] = "없음"

            # 082 필드의 지시자 추출 (첫 번째 지시자, 두 번째 지시자)
            if field_082 is not None:
                ind1 = field_082.get("ind1", " ").strip()
                ind2 = field_082.get("ind2", " ").strip()
                record_data["082 ind"] = f"{ind1}{ind2}".replace(
                    " ", "#"
                )  # 공백은 #으로 표시
            else:
                record_data["082 ind"] = "없음"

            # 250 필드 (판차 정보)
            field_250 = record_element.find(".//marc:datafield[@tag='250']", namespaces)
            if field_250 is not None:
                subfield_a = field_250.find("marc:subfield[@code='a']", namespaces)
                if subfield_a is not None:
                    record_data["250"] = subfield_a.text.strip()
                else:
                    record_data["250"] = "없음"
            else:
                record_data["250"] = "없음"

            # ✨ 추가: 발행지, 출판사, 출판 연도 정보 추출
            # 발행지 (260$a, 264$a)
            field_260 = record_element.find(".//marc:datafield[@tag='260']", namespaces)
            field_264 = record_element.find(".//marc:datafield[@tag='264']", namespaces)

            # 발행지 추출 (260$a 또는 264$a)
            place_of_publication = "없음"
            if field_260 is not None:
                subfield_a_260 = field_260.find("marc:subfield[@code='a']", namespaces)
                if subfield_a_260 is not None and subfield_a_260.text:
                    place_of_publication = subfield_a_260.text.strip().rstrip(":")
            if place_of_publication == "없음" and field_264 is not None:
                subfield_a_264 = field_264.find("marc:subfield[@code='a']", namespaces)
                if subfield_a_264 is not None and subfield_a_264.text:
                    place_of_publication = subfield_a_264.text.strip().rstrip(":")
            record_data["발행지"] = place_of_publication

            # 출판사 추출 (260$b 또는 264$b)
            publisher = "없음"
            if field_260 is not None:
                subfield_b_260 = field_260.find("marc:subfield[@code='b']", namespaces)
                if subfield_b_260 is not None and subfield_b_260.text:
                    publisher = subfield_b_260.text.strip().rstrip(",")
            if publisher == "없음" and field_264 is not None:
                subfield_b_264 = field_264.find("marc:subfield[@code='b']", namespaces)
                if subfield_b_264 is not None and subfield_b_264.text:
                    publisher = subfield_b_264.text.strip().rstrip(",")
            record_data["출판사"] = publisher

            # 650 필드 (주제어)
            field_650_list = record_element.findall(
                ".//marc:datafield[@tag='650']", namespaces
            )
            subjects = []
            for field_650 in field_650_list:
                subfield_a = field_650.find("marc:subfield[@code='a']", namespaces)
                if subfield_a is not None:
                    subjects.append(subfield_a.text.strip())
            record_data["650 필드"] = ", ".join(subjects) if subjects else "없음"

            records.append(record_data)

        # ===== 🆕 Python 자체 연도 필터링 (Google Books와 동일) =====
        if year_query and records:
            year_cleaned = year_query.strip()
            filtered_records = []

            for record in records:
                published_year = record.get("연도", "")

                # 연도 매칭 로직
                if re.match(r"^\d{4}$", year_cleaned):
                    # 단일 연도 검색 (예: 2016)
                    if published_year == year_cleaned:
                        filtered_records.append(record)
                elif re.match(r"^\d{4}-\d{4}$", year_cleaned):
                    # 연도 범위 검색 (예: 2015-2017)
                    start_year, end_year = year_cleaned.split("-")
                    try:
                        pub_year_int = (
                            int(published_year) if published_year.isdigit() else 0
                        )
                        if int(start_year) <= pub_year_int <= int(end_year):
                            filtered_records.append(record)
                    except (ValueError, TypeError):
                        continue
                else:
                    # 부분 매칭 (예: "약 2016" 같은 경우)
                    if year_cleaned in published_year:
                        filtered_records.append(record)

            # 필터링 결과로 교체
            records = filtered_records
            if app_instance:
                app_instance.log_message(
                    f"정보: 출판 연도 '{year_query}' 필터링 완료: {len(records)}건 매칭",
                    level="INFO",
                )

        if app_instance:
            app_instance.log_message(
                f"정보: LC 검색 결과 {len(records)}개 레코드 파싱 완료.",
                level="INFO",
            )
        return records

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"오류: LC 검색 중 네트워크 오류 발생: {e}", level="ERROR"
            )
            app_instance.show_messagebox(
                "LC 서버 연결 오류",
                f"LC 서버 접속이 불안정합니다. 잠시 후 다시 시도해주세요.\n\n오류: {e}",
                "error",
            )
        return []
    except ET.ParseError as e:
        if app_instance:
            app_instance.log_message(
                f"오류: LC 검색 응답 XML 파싱 오류: {e}", level="ERROR"
            )
            app_instance.show_messagebox(
                "LC 서버 응답 형식 오류",
                f"LC 서버에서 비정상적인 응답을 받았습니다. 잠시 후 다시 시도해주세요.\n\n오류: {e}",
                "error",
            )
        return []
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: LC 검색 중 예기치 않은 오류 발생: {e}", level="ERROR"
            )
            app_instance.show_messagebox(
                "LC 검색 오류",
                f"LC 검색 중 예기치 않은 오류가 발생했습니다.\n\n오류: {e}",
                "error",
            )
        return []
