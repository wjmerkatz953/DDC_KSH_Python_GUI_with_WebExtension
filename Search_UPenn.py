# -*- coding: utf-8 -*-
# 파일명: Search_UPenn.py
# Version: v2.0.0
# 수정일시: 2025-09-20 KST
# 설명: University of Pennsylvania Library API의 내장 MARCXML을 직접 파싱하여 도서 정보를 검색하는 최적화된 모듈.
#      (불필요한 staff_view 웹 요청 제거)

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
    marc_data = {}
    try:
        root = ET.fromstring(marc_xml_string)

        def get_subfield_text(datafield, code):
            subfield = datafield.find(f"./subfield[@code='{code}']")
            return (
                subfield.text.strip() if subfield is not None and subfield.text else ""
            )

        for datafield in root.findall(".//datafield"):
            tag = datafield.get("tag")
            if tag in ["245", "250", "264", "505", "520", "650", "082"]:
                if tag not in marc_data:
                    marc_data[tag] = []

                indicators = (
                    f"{datafield.get('ind1', ' ')}{datafield.get('ind2', ' ')}".replace(
                        " ", "#"
                    )
                )

                # -------------------
                # ✨ FIX: 245 필드 파싱 로직 수정
                if tag == "245":
                    # 모든 서브필드를 순서대로 조합
                    subfields = datafield.findall("./subfield")
                    full_text = " ".join(sf.text.strip() for sf in subfields if sf.text)
                    # 불필요한 공백 정리
                    full_text = re.sub(r"\s+/\s*", " / ", full_text).strip(" .,/:")
                    marc_data[tag].append({"text": full_text, "indicators": indicators})
                # -------------------
                elif tag == "264":  # Publication info
                    a = get_subfield_text(datafield, "a")
                    b = get_subfield_text(datafield, "b")
                    c = get_subfield_text(datafield, "c")
                    marc_data[tag].append(
                        {
                            "place": a.strip(" :[]"),
                            "publisher": b.strip(" ,;"),
                            "year": c,
                        }
                    )
                # -------------------
                # ✨ FIX: 650 필드 파싱 로직 수정
                elif tag == "650":
                    a = get_subfield_text(datafield, "a")
                    zero = get_subfield_text(datafield, "0")
                    # $a와 $0를 조합하여 "주제어 http://..." 형식 생성
                    full_text = f"{a.strip(' .')} {zero}".strip()
                    marc_data[tag].append({"text": full_text, "indicators": indicators})
                # -------------------
                elif tag == "082":
                    a = get_subfield_text(datafield, "a").replace("/", "")
                    if a:
                        marc_data[tag].append({"text": a, "indicators": indicators})
                else:  # 250, 505, 520
                    subfields = datafield.findall("./subfield")
                    full_text = " ".join(sf.text.strip() for sf in subfields if sf.text)
                    marc_data[tag].append({"text": full_text, "indicators": indicators})

    except ET.ParseError:
        pass
    return marc_data


def _parse_upenn_json_record(record_json, app_instance):
    """UPenn Blacklight API의 JSON 응답에서 서지 정보를 직접 추출합니다."""
    attributes = record_json.get("attributes", {})
    record_id = record_json.get("id", "")

    record = {
        "제목": "",
        "저자": "",
        "출판사": "",
        "연도": "",
        "ISBN": "",
        "상세 링크": (
            f"https://find.library.upenn.edu/catalog/{record_id}/staff_view"
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

    raw_title = (attributes.get("title") or [""])[0]
    record["제목"] = re.sub(r"[{}\[\]]", "", raw_title).strip()

    creator_ss = attributes.get("creator_ss", {})
    if creator_ss and isinstance(creator_ss, dict):
        record["저자"] = " | ".join(creator_ss.get("attributes", {}).get("value", []))

    isbn_ss = attributes.get("isbn_ss", {})
    if isbn_ss and isinstance(isbn_ss, dict):
        record["ISBN"] = " | ".join(isbn_ss.get("attributes", {}).get("value", []))

    marc_xml_str = (
        attributes.get("marcxml_marcxml", {}).get("attributes", {}).get("value")
        or [None]
    )[0]
    if marc_xml_str:
        parsed_marc = _parse_embedded_marc_xml(marc_xml_str)

        p245 = parsed_marc.get("245", [{}])[0]
        record["245 필드"] = p245.get("text", record["제목"])

        # 복수의 082 필드를 파이프로 구분
        ddc_list = parsed_marc.get("082", [])
        if ddc_list:
            record["082"] = " | ".join([d.get("text", "") for d in ddc_list if d.get("text")])
            record["082 ind"] = ddc_list[0].get("indicators", "")

        record["250"] = parsed_marc.get("250", [{}])[0].get("text", "")
        record["책소개"] = parsed_marc.get("520", [{}])[0].get("text", "")
        record["목차"] = parsed_marc.get("505", [{}])[0].get("text", "")

        subjects = [field["text"] for field in parsed_marc.get("650", [])]
        if subjects:
            record["주제어_원문"] = subjects

        p264 = parsed_marc.get("264", [{}])[0]
        if p264:
            record["출판지역"] = p264.get("place", "")
            record["출판사"] = p264.get("publisher", "")
            record["연도"] = extract_year(p264.get("year", ""))

    if not record["출판사"]:
        pub_ss = attributes.get("publication_ss", {})
        if pub_ss and isinstance(pub_ss, dict):
            pub_string = (pub_ss.get("attributes", {}).get("value") or [""])[0]
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

    return record


def search_upenn_library(
    title_query=None,
    author_query=None,
    isbn_query=None,
    year_query=None,
    app_instance=None,
    db_manager=None,
    skip_detailed_fields=False,
):
    """University of Pennsylvania Library API를 호출하고 결과를 파싱합니다."""
    if not any([title_query, author_query, isbn_query, year_query]):
        if app_instance:
            app_instance.log_message("경고: UPenn 검색어가 없습니다.", level="WARNING")
        return []

    base_url = "https://find.library.upenn.edu/catalog.json"

    query_parts = []
    if title_query:
        query_parts.append(title_query)
    if author_query:
        query_parts.append(author_query)
    if year_query:
        query_parts.append(year_query)
    search_term = " ".join(query_parts)

    params = {"search_field": "all_fields"}
    if isbn_query:
        params["q"] = isbn_query.replace("-", "").strip()
    else:
        params["q"] = search_term

    try:
        if app_instance:
            app_instance.log_message(
                f"정보: UPenn API 요청: {base_url} with params {params}", level="INFO"
            )

        response = requests.get(base_url, params=params, timeout=20)
        response.raise_for_status()
        response_json = response.json()
        records_json = response_json.get("data", [])

        if not records_json:
            if app_instance:
                app_instance.log_message(
                    "정보: UPenn 검색 결과가 없습니다.", level="INFO"
                )
            return []

        # 병렬 처리 대신 순차 처리 (단일 요청이므로 병렬 불필요)
        all_results = [
            _parse_upenn_json_record(rec, app_instance) for rec in records_json
        ]

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
                f"정보: UPenn 검색 결과 {len(all_results)}건 파싱 완료.", level="INFO"
            )
        return all_results

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"오류: UPenn API 네트워크 오류: {e}", level="ERROR"
            )
        return []
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: UPenn API 처리 중 예기치 않은 오류: {e}", level="ERROR"
            )
        return []
