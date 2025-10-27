# -*- coding: utf-8 -*-
# 파일명: Search_Cornell.py
# Version: v2.0.1
# 수정일시: 2025-10-27 KST
# 설명: Cornell University Library API의 내장 MARCXML을 직접 파싱하여 도서 정보를 검색하는 최적화된 모듈.
#      (Search_UPenn.py 구조를 모방하여 작성)
# 변경: 상세 링크에 /librarian_view 추가

import requests
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from qt_api_clients import translate_text_batch_async, extract_year


def _should_auto_translate(app_instance):
    """자동 번역 여부를 확인합니다."""
    if hasattr(app_instance, "foreign_auto_translation_var"):
        return app_instance.foreign_auto_translation_var.get()
    if hasattr(app_instance, "db_manager") and app_instance.db_manager:
        value = app_instance.db_manager.get_setting("foreign_auto_translation")
        return value == "true" if value else True
    return True


def _parse_embedded_marc_xml(marc_xml_string):
    """JSON에 포함된 MARCXML 문자열에서 필요한 데이터를 파싱합니다."""
    if not marc_xml_string:
        return {}

    def get_subfield_text(datafield, code):
        """서브필드에서 텍스트를 추출합니다."""
        # 네임스페이스 없이 먼저 찾기
        subfield = datafield.find(f"./subfield[@code='{code}']")
        if subfield is None:
            # 네임스페이스가 있는 경우 시도
            subfield = datafield.find(
                f".//{{http://www.loc.gov/MARC21/slim}}subfield[@code='{code}']"
            )
        return subfield.text.strip() if subfield is not None and subfield.text else ""

    def get_all_subfields(datafield):
        """모든 서브필드를 찾습니다 (네임스페이스 처리 포함)."""
        # 네임스페이스 없이 먼저 찾기
        subfields = datafield.findall("./subfield")
        if not subfields:
            # 네임스페이스가 있는 경우 시도
            subfields = datafield.findall(".//{http://www.loc.gov/MARC21/slim}subfield")
        return subfields

    marc_data = {}
    try:
        # XML 파싱
        root = ET.fromstring(marc_xml_string)

        # 모든 datafield 찾기 (네임스페이스 무관)
        datafields = root.findall(".//datafield")
        if not datafields:
            # 네임스페이스가 있는 경우 시도
            ns = {"marc": "http://www.loc.gov/MARC21/slim"}
            datafields = root.findall(".//marc:datafield", ns)

        for datafield in datafields:
            tag = datafield.get("tag")

            if tag in ["082", "245", "250", "264", "260", "505", "520", "650"]:
                indicators = f"{datafield.get('ind1', ' ')}{datafield.get('ind2', ' ')}"

                if tag not in marc_data:
                    marc_data[tag] = []

                if tag == "264" or tag == "260":
                    # 출판정보 필드
                    place = get_subfield_text(datafield, "a")
                    publisher = get_subfield_text(datafield, "b")
                    year = get_subfield_text(datafield, "c")

                    marc_data[tag].append(
                        {
                            "place": place.rstrip(" :,"),
                            "publisher": publisher.rstrip(" :,"),
                            "year": year.rstrip(" :,."),
                            "indicators": indicators,
                        }
                    )
                elif tag == "650":
                    # 주제어 필드
                    subfields = get_all_subfields(datafield)

                    subject_parts = []
                    for sf in subfields:
                        if sf.get("code") in ["a", "x", "y", "z", "v"]:
                            if sf.text:
                                subject_parts.append(sf.text.strip())

                    if subject_parts:
                        full_text = " -- ".join(subject_parts)
                        marc_data[tag].append(
                            {"text": full_text, "indicators": indicators}
                        )
                elif tag == "082":
                    # DDC 분류번호
                    a = get_subfield_text(datafield, "a")
                    if a:  # a 필드가 있을 때만 처리
                        # 슬래시 제거
                        a_clean = a.replace("/", "")
                        marc_data[tag].append(
                            {"text": a_clean, "indicators": indicators}
                        )
                elif tag == "245":
                    # 245 필드 특별 처리 (제목)
                    a = get_subfield_text(datafield, "a")
                    b = get_subfield_text(datafield, "b")
                    c = get_subfield_text(datafield, "c")
                    parts = []
                    if a:
                        parts.append(a.rstrip(" /:"))
                    if b:
                        parts.append(b.rstrip(" /:"))
                    if c:
                        parts.append(f"/ {c}")
                    full_text = " ".join(parts)
                    if full_text:
                        marc_data[tag].append(
                            {"text": full_text, "indicators": indicators}
                        )
                elif tag == "250":
                    # 250 필드 (판차사항)
                    a = get_subfield_text(datafield, "a")
                    if a:
                        marc_data[tag].append({"text": a, "indicators": indicators})
                elif tag == "505":
                    # 목차 필드 - 네임스페이스 처리 개선
                    subfields = get_all_subfields(datafield)

                    # 모든 서브필드의 텍스트를 수집
                    all_texts = []
                    for sf in subfields:
                        text = sf.text.strip() if sf.text else ""
                        if text:
                            all_texts.append(text)

                    if all_texts:
                        # 모든 텍스트를 " | "로 연결
                        full_text = " | ".join(all_texts)
                        marc_data[tag].append(
                            {"text": full_text, "indicators": indicators}
                        )
                elif tag == "520":
                    # 520 필드 (책소개) - 네임스페이스 처리 개선
                    subfields = get_all_subfields(datafield)

                    full_text = " ".join(sf.text.strip() for sf in subfields if sf.text)
                    if full_text:
                        marc_data[tag].append(
                            {"text": full_text, "indicators": indicators}
                        )

    except ET.ParseError as e:
        pass  # 조용히 실패
    except Exception as e:
        pass  # 조용히 실패

    return marc_data


def _parse_cornell_json_record(record_json, app_instance):
    """Cornell Blacklight API의 JSON 응답에서 서지 정보를 직접 추출합니다."""
    # Cornell은 attributes가 아닌 직접 필드 접근
    record_id = record_json.get("id", "")

    record = {
        "제목": "",
        "저자": "",
        "출판사": "",
        "연도": "",
        "ISBN": "",
        "상세 링크": (
            f"https://catalog.library.cornell.edu/catalog/{record_id}/librarian_view"
            if record_id
            else ""
        ),
        "주제어_원문": [],
        "082": "",
        "082 ind": "",
        "책소개": "",
        "목차": "",
        "245 필드": "",
        "250": "",
        "출판지역": "",
    }

    # 제목 추출
    title_display = record_json.get("title_display", "")
    if not title_display:
        fulltitle_display = record_json.get("fulltitle_display", "")
        title_display = fulltitle_display

    record["제목"] = re.sub(r"[{}\[\]]", "", title_display).strip()

    # 저자 추출
    author_display = record_json.get("author_display", "")
    if author_display:
        record["저자"] = author_display

    # ISBN 추출
    isbn_t = record_json.get("isbn_t", [])
    if isbn_t:
        record["ISBN"] = " | ".join(isbn_t)

    # MARC XML 파싱 (안전한 처리 + Cornell API 직접 필드 fallback)
    marc_display = record_json.get("marc_display", "")
    parsed_marc = {}

    if marc_display:
        try:
            parsed_marc = _parse_embedded_marc_xml(marc_display)

            if parsed_marc:  # 파싱 결과가 있는 경우에만 처리
                # 245 필드 (제목)
                if "245" in parsed_marc and parsed_marc["245"]:
                    p245 = parsed_marc["245"][0]
                    record["245 필드"] = p245.get("text", record["제목"])

                # 082 필드 (분류번호) - 복수의 DDC를 파이프로 구분
                if "082" in parsed_marc and parsed_marc["082"]:
                    ddc_list = parsed_marc["082"]
                    record["082"] = " | ".join([d.get("text", "") for d in ddc_list if d.get("text")])
                    record["082 ind"] = ddc_list[0].get("indicators", "")

                # 250 필드 (판차사항)
                if "250" in parsed_marc and parsed_marc["250"]:
                    record["250"] = parsed_marc["250"][0].get("text", "")

                # 520 필드 (책소개)
                if "520" in parsed_marc and parsed_marc["520"]:
                    record["책소개"] = parsed_marc["520"][0].get("text", "")

                # 505 필드 (목차)
                if "505" in parsed_marc and parsed_marc["505"]:
                    record["목차"] = parsed_marc["505"][0].get("text", "")

                # 650 필드 (주제어)
                if "650" in parsed_marc and parsed_marc["650"]:
                    subjects = [
                        field["text"]
                        for field in parsed_marc["650"]
                        if field.get("text")
                    ]
                    if subjects:
                        record["주제어_원문"] = subjects

                # 264 필드 (출판정보) - 260 필드도 확인
                if "264" in parsed_marc and parsed_marc["264"]:
                    p264 = parsed_marc["264"][0]
                    record["출판지역"] = p264.get("place", "")
                    record["출판사"] = p264.get("publisher", "")
                    record["연도"] = extract_year(p264.get("year", ""))
                elif "260" in parsed_marc and parsed_marc["260"]:
                    p260 = parsed_marc["260"][0]
                    record["출판지역"] = p260.get("place", "")
                    record["출판사"] = p260.get("publisher", "")
                    record["연도"] = extract_year(p260.get("year", ""))
        except Exception as e:
            if app_instance:
                app_instance.log_message(f"MARC XML 파싱 오류: {e}", level="WARNING")

    # Cornell API 직접 필드에서 추가 정보 추출 (fallback)
    if not record["책소개"]:
        # summary_display 또는 notes_display 확인
        summary_fields = record_json.get("summary_display", []) or record_json.get(
            "notes_display", []
        )
        if summary_fields:
            record["책소개"] = " | ".join(summary_fields)

    if not record["주제어_원문"]:
        # subject_topic_facet 또는 subject_display 확인
        subject_fields = record_json.get("subject_topic_facet", []) or record_json.get(
            "subject_display", []
        )
        if subject_fields:
            record["주제어_원문"] = subject_fields[:10]  # 너무 많으면 10개로 제한

    # DDC 정보 fallback
    if not record["082"]:
        # dewey_display, classification_display, call_number_display 등 확인
        dewey_fields = (
            record_json.get("dewey_display", [])
            or record_json.get("classification_display", [])
            or record_json.get("call_number_display", [])
        )
        if dewey_fields:
            record["082"] = dewey_fields[0]

    # 245 필드 fallback
    if not record["245 필드"]:
        # fulltitle_display 사용
        fulltitle_display = record_json.get("fulltitle_display", "")
        if fulltitle_display:
            record["245 필드"] = fulltitle_display

    # 출판정보가 MARC에서 추출되지 않은 경우 다른 필드에서 추출
    if not record["출판사"]:
        pub_info_display = record_json.get("pub_info_display", [])
        if pub_info_display:
            pub_string = pub_info_display[0]
            if pub_string:
                year = extract_year(pub_string)
                if year:
                    record["연도"] = year
                parts = pub_string.replace(year, "").strip(" .,:[]")
                if ":" in parts:
                    record["출판지역"], record["출판사"] = [
                        p.strip() for p in parts.split(":", 1)
                    ]
                else:
                    record["출판사"] = parts

    # 출판연도가 추출되지 않은 경우
    if not record["연도"]:
        pub_date_display = record_json.get("pub_date_display", [])
        if pub_date_display:
            record["연도"] = extract_year(pub_date_display[0])

    return record


def search_cornell_library(
    title_query=None,
    author_query=None,
    isbn_query=None,
    year_query=None,
    app_instance=None,
    db_manager=None,
    skip_detailed_fields=False,
):
    """Cornell University Library API를 호출하고 결과를 파싱합니다."""
    if not any([title_query, author_query, isbn_query, year_query]):
        if app_instance:
            app_instance.log_message(
                "경고: Cornell 검색어가 없습니다.", level="WARNING"
            )
        return []

    base_url = "https://catalog.library.cornell.edu/catalog.json"

    params = {}

    if isbn_query:
        # ISBN 검색시에는 ISBN만 검색
        params["q"] = isbn_query.replace("-", "").strip()
    else:
        # 필드별 검색 파라미터 구성
        query_parts = []

        if title_query:
            # 제목 필드 검색
            query_parts.append(f'title_t:"{title_query}"')

        if author_query:
            # 저자 필드 검색
            query_parts.append(f'author_t:"{author_query}"')

        if year_query:
            # 발행연도 검색
            query_parts.append(f'pub_date_display:"{year_query}"')

        if query_parts:
            # AND 조건으로 연결
            params["q"] = " AND ".join(query_parts)
        else:
            params["q"] = "*:*"  # 모든 결과 반환

    try:
        if app_instance:
            app_instance.log_message(
                f"정보: Cornell API 요청: {base_url} with params {params}", level="INFO"
            )

        response = requests.get(base_url, params=params, timeout=20)
        response.raise_for_status()
        response_json = response.json()
        records_json = response_json.get("response", {}).get("document", [])

        if not records_json:
            if app_instance:
                app_instance.log_message(
                    "정보: Cornell 검색 결과가 없습니다.", level="INFO"
                )
            return []

        # 병렬 처리 대신 순차 처리 (단일 요청이므로 병렬 불필요)
        all_results = [
            _parse_cornell_json_record(rec, app_instance) for rec in records_json
        ]

        # 자동 번역 처리
        if all_results and _should_auto_translate(app_instance):
            all_unique_subjects = set(
                s.strip() for r in all_results for s in r.get("주제어_원문", []) if s
            )
            if all_unique_subjects:
                custom_glossary = db_manager.get_all_custom_translations()
                translation_map = translate_text_batch_async(
                    list(all_unique_subjects), app_instance, custom_glossary, db_manager
                )
                for record in all_results:
                    raw = record.get("주제어_원문", [])
                    record["650 필드"] = " | ".join(raw)
                    translated = [
                        translation_map.get(s.strip(), s.strip()) for s in raw
                    ]
                    record["650 필드 (번역)"] = " | ".join(translated)
                    if "주제어_원문" in record:
                        del record["주제어_원문"]
        elif all_results:
            for record in all_results:
                raw = record.get("주제어_원문", [])
                record["650 필드"] = " | ".join(raw)
                record["650 필드 (번역)"] = " | ".join(raw)
                if "주제어_원문" in record:
                    del record["주제어_원문"]

        if app_instance:
            app_instance.log_message(
                f"정보: Cornell 검색 결과 {len(all_results)}건 파싱 완료.", level="INFO"
            )
        return all_results

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"오류: Cornell API 네트워크 오류: {e}", level="ERROR"
            )
        return []
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: Cornell API 처리 중 예기치 않은 오류: {e}", level="ERROR"
            )
        return []
