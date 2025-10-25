# -*- coding: utf-8 -*-
# 파일명: Search_MIT.py
# Version: v2.1.0
# 수정일시: 2025-09-19 KST
# 설명: MIT TIMDEX GraphQL API를 사용하여 도서 정보를 검색하는 Python 모듈. (ISBN 추출 개선 및 JSON 로깅 추가)
# -------------------
import requests
import re
import json  # 👈 JSON pretty-printing을 위해 추가
from qt_api_clients import translate_text_batch_async, extract_year


def _should_auto_translate(app_instance):
    """자동 번역 여부를 확인합니다."""
    if hasattr(app_instance, "foreign_auto_translation_var"):
        return app_instance.foreign_auto_translation_var.get()
    if hasattr(app_instance, "db_manager") and app_instance.db_manager:
        value = app_instance.db_manager.get_setting("foreign_auto_translation")
        return value == "true" if value else True
    return True


def _parse_timdex_record(record_json, app_instance):
    """TIMDEX GraphQL API의 JSON 응답에서 서지 정보를 추출합니다."""
    record = {
        "제목": record_json.get("title", ""),
        "저자": "",
        "출판사": "",
        "연도": "",
        "ISBN": "",
        "상세 링크": "",  # 👈 초기값은 비워둡니다.
        "주제어_원문": [],
        "082": "",
        "082 ind": "",
    }

    # -------------------
    # ✨ 상세 링크를 MARC 레코드 뷰 URL로 재구성
    source_link = record_json.get("sourceLink", "")
    if source_link:
        # sourceLink에서 Alma ID (alma99...) 부분을 추출
        match = re.search(r"(alma\d+)", source_link)
        if match:
            alma_doc_id = match.group(1)
            # MARC 레코드 뷰 URL 조립
            record["상세 링크"] = (
                f"https://mit.primo.exlibrisgroup.com/discovery/sourceRecord?"
                f"vid=01MIT_INST:MIT&docId={alma_doc_id}&recordOwner=01MIT_INST"
            )
        else:
            # Alma ID 추출에 실패하면 원본 링크를 그대로 사용 (폴백)
            record["상세 링크"] = source_link
    # -------------------

    # 저자
    contributors = record_json.get("contributors", [])
    if contributors:
        record["저자"] = " | ".join(
            [c.get("value", "") for c in contributors if c.get("value")]
        )

    # 출판사
    publishers = record_json.get("publishers", [])
    if publishers:
        record["출판사"] = " | ".join(
            [p.get("name", "") for p in publishers if p.get("name")]
        )

    # 출판 연도
    pub_date = record_json.get("publicationDate")
    if pub_date:
        record["연도"] = extract_year(pub_date)

    # -------------------
    # ✨ ISBN 추출 로직 개선
    isbns = set(record_json.get("isbns", []))  # 중복 제거를 위해 set 사용
    identifiers = record_json.get("identifiers", [])
    if identifiers:
        for identifier in identifiers:
            if (
                identifier
                and identifier.get("kind") == "ISBN"
                and identifier.get("value")
            ):
                isbns.add(identifier["value"])

    if isbns:
        record["ISBN"] = " | ".join(sorted(list(isbns)))
    # -------------------

    # 주제어
    subjects = record_json.get("subjects", [])
    if subjects:
        record["주제어_원문"] = [s for subj in subjects for s in subj.get("value", [])]

    # DDC (callNumbers 필드에서 추출 시도)
    call_numbers = record_json.get("callNumbers", [])
    ddc_values = []
    if call_numbers:
        for cn in call_numbers:
            # DDC는 보통 3자리 숫자 + 소수점으로 구성됨
            match = re.search(r"\b(\d{3}(?:\.\d+)?)\b", cn)
            if match:
                ddc_values.append(match.group(1))
    if ddc_values:
        record["082"] = " | ".join(ddc_values)

    return record


def search_mit_library(
    title_query=None,
    author_query=None,
    isbn_query=None,
    year_query=None,
    app_instance=None,
    db_manager=None,
):
    """MIT TIMDEX GraphQL API를 호출하고 결과를 파싱하여 반환합니다."""
    if not app_instance or not db_manager:
        return []

    base_url = "https://timdex.mit.edu/graphql"

    # -------------------
    # ✨ GraphQL 쿼리 수정: identifiers 필드 추가
    query = """
    query Search($title: String, $contributors: String, $identifiers: String, $searchterm: String) {
      search(title: $title, contributors: $contributors, identifiers: $identifiers, searchterm: $searchterm) {
        hits
        records {
          title
          contributors {
            value
            kind
          }
          publicationDate
          publishers {
            name
          }
          isbns
          identifiers {
            kind
            value
          }
          sourceLink
          subjects {
            value
            kind
          }
          callNumbers
        }
      }
    }
    """
    # -------------------

    # 검색어 조합
    variables = {}
    search_parts = []
    if title_query:
        variables["title"] = title_query
    if author_query:
        variables["contributors"] = author_query
    if isbn_query:
        variables["identifiers"] = isbn_query.replace("-", "").strip()

    if year_query:
        search_parts.append(year_query)

    if not variables and not search_parts:
        app_instance.log_message(
            "경고: MIT 검색을 위한 검색어가 없습니다.", level="WARNING"
        )
        return []

    if search_parts:
        variables["searchterm"] = " ".join(search_parts)

    try:
        app_instance.log_message(
            f"정보: MIT TIMDEX API 요청. URL: {base_url}, Variables: {variables}",
            level="INFO",
        )
        response = requests.post(
            base_url, json={"query": query, "variables": variables}, timeout=20
        )
        response.raise_for_status()

        response_json = response.json()

        # -------------------
        # ✨ Pretty-printed JSON 응답 전체를 로그에 기록
        # pretty_json = json.dumps(response_json, indent=2, ensure_ascii=False)
        # app_instance.log_message(
        #    f"정보: MIT TIMDEX API 전체 응답 (JSON):\n{pretty_json}", level="DEBUG"
        # )
        # -------------------

        if "errors" in response_json:
            raise Exception(f"GraphQL Error: {response_json['errors']}")

        records_json = (
            response_json.get("data", {}).get("search", {}).get("records", [])
        )
        if not records_json:
            app_instance.log_message(
                "정보: MIT TIMDEX 검색 결과가 없습니다.", level="INFO"
            )
            return []

        all_results = [
            parsed
            for record_data in records_json
            if (parsed := _parse_timdex_record(record_data, app_instance)) is not None
        ]

        # 주제어 번역 로직 (기존과 동일)
        if all_results and _should_auto_translate(app_instance):
            app_instance.log_message("정보: MIT 주제어 번역 시작...", level="INFO")
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
                    record["650 필드 (번역)"] = " | ".join(
                        [translation_map.get(s.strip(), s.strip()) for s in raw]
                    )
                    del record["주제어_원문"]
        elif all_results:
            for record in all_results:
                raw = record.get("주제어_원문", [])
                record["650 필드"] = " | ".join(raw)
                record["650 필드 (번역)"] = " | ".join(raw)
                del record["주제어_원문"]

        app_instance.log_message(
            f"정보: MIT TIMDEX 검색 결과 {len(all_results)}건 파싱 완료.", level="INFO"
        )
        return all_results

    except requests.exceptions.RequestException as e:
        app_instance.log_message(f"오류: MIT API 네트워크 오류: {e}", level="ERROR")
        return []
    except Exception as e:
        app_instance.log_message(
            f"오류: MIT API 처리 중 예기치 않은 오류: {e}", level="ERROR"
        )
        return []
