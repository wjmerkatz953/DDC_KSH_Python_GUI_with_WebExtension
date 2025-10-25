# -*- coding: utf-8 -*-
# 파일명: Search_Princeton.py
# Version: v2.0.0 - Level 2 최적화 적용
# 수정일시: 2025-09-21 KST
# 설명: Princeton University Library API Level 2 최적화 - httpx HTTP/2, 재시도 로직, DNS 캐싱

import requests
import re
from qt_api_clients import translate_text_batch_async, extract_year
from bs4 import BeautifulSoup
import socket
import functools

# 🚀 Level 2 최적화: httpx 및 HTTP/2 지원
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# 🚀 MARC 페이지 캐싱을 위한 전역 딕셔너리
_marc_cache = {}

# 🚀 Level 2 최적화: DNS 캐싱 적용
socket.getaddrinfo = functools.lru_cache(maxsize=128)(socket.getaddrinfo)

# 🚀 Level 2 최적화: HTTP 클라이언트 최적화
_session = None
_httpx_client = None


def _get_optimized_client():
    """최적화된 HTTP 클라이언트를 반환합니다."""
    global _session, _httpx_client

    if HTTPX_AVAILABLE and _httpx_client is None:
        # httpx 사용 (HTTP/2 지원)
        _httpx_client = httpx.Client(
            http2=True,
            timeout=httpx.Timeout(5.0),  # 초기 타임아웃을 5초로 설정
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Cache-Control": "max-age=0",
            },
        )
        return _httpx_client

    elif _session is None:
        # requests fallback
        _session = requests.Session()

        # Connection Pooling 최적화
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=50,
            max_retries=0,  # 재시도는 직접 구현
            pool_block=False,
        )
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)

        _session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Cache-Control": "max-age=0",
            }
        )

    return _session


def _make_request_with_retry(url, params=None, max_retries=3, app_instance=None):
    """재시도 로직이 포함된 HTTP 요청 - 적응형 타임아웃"""
    client = _get_optimized_client()

    # 적응형 타임아웃: 첫 시도는 빠르게, 재시도할 때는 점진적으로 증가
    timeouts = [5, 8, 12]  # 5초 → 8초 → 12초

    for attempt in range(max_retries):
        current_timeout = timeouts[min(attempt, len(timeouts) - 1)]

        try:
            if HTTPX_AVAILABLE and isinstance(client, httpx.Client):
                # httpx 사용 - 동적 타임아웃 설정
                client.timeout = httpx.Timeout(current_timeout)
                if params:
                    response = client.get(url, params=params)
                else:
                    response = client.get(url)
                response.raise_for_status()

                if app_instance and attempt > 0:
                    app_instance.log_message(
                        f"Princeton API 성공 (시도 {attempt + 1}, {current_timeout}초)",
                        level="INFO",
                    )
                return response
            else:
                # requests 사용
                response = client.get(url, params=params, timeout=current_timeout)
                response.raise_for_status()

                if app_instance and attempt > 0:
                    app_instance.log_message(
                        f"Princeton API 성공 (시도 {attempt + 1}, {current_timeout}초)",
                        level="INFO",
                    )
                return response

        except (requests.Timeout, requests.ConnectionError, Exception) as e:
            # httpx 예외 처리
            is_timeout = (
                isinstance(e, requests.Timeout)
                or "timeout" in str(e).lower()
                or "timed out" in str(e).lower()
            )

            if attempt < max_retries - 1:
                if app_instance:
                    if is_timeout:
                        app_instance.log_message(
                            f"Princeton API 타임아웃 ({current_timeout}초) - 시도 {attempt + 2}/{max_retries} (다음: {timeouts[min(attempt + 1, len(timeouts) - 1)]}초)",
                            level="WARNING",
                        )
                    else:
                        app_instance.log_message(
                            f"Princeton API 연결 오류 - 시도 {attempt + 2}/{max_retries}: {type(e).__name__}",
                            level="WARNING",
                        )
                continue
            else:
                if app_instance:
                    if is_timeout:
                        app_instance.log_message(
                            f"Princeton API 최종 실패: 서버 응답이 너무 느립니다 (최대 {current_timeout}초 대기)",
                            level="ERROR",
                        )
                    else:
                        app_instance.log_message(
                            f"Princeton API 최종 실패: {e}", level="ERROR"
                        )
                raise
        except Exception as e:
            if app_instance:
                app_instance.log_message(
                    f"Princeton API 예상치 못한 오류: {e}", level="ERROR"
                )
            raise

    raise Exception("재시도 로직 오류")


def _should_auto_translate(app_instance):
    """자동 번역 여부를 확인합니다."""
    if hasattr(app_instance, "foreign_auto_translation_var"):
        return app_instance.foreign_auto_translation_var.get()
    if hasattr(app_instance, "db_manager") and app_instance.db_manager:
        value = app_instance.db_manager.get_setting("foreign_auto_translation")
        return value == "true" if value else True
    return True


def _parse_marc_fields_from_html(soup, skip_detailed_fields=False):
    """BeautifulSoup 객체에서 주요 MARC 태그와 내용을 한번에 파싱하여 딕셔너리로 반환합니다."""
    marc_data = {}
    try:
        fields = soup.find_all("div", class_="field")
        for field in fields:
            tag_span = field.find("span", class_="tag")
            if not tag_span:
                continue

            tag = tag_span.get_text(strip=True)

            # 🚀 필수 정보만 파싱 옵션 적용 (245는 JSON에서 이미 처리되므로 제외)
            if skip_detailed_fields:
                # 상세 정보 스킵 - 필수 필드만 파싱 (목차, 책소개, 245 제외)
                if tag not in ["250", "650", "082"]:
                    continue
            else:
                # 전체 정보 파싱 (245는 JSON에서 처리하므로 제외)
                if tag not in ["250", "505", "520", "650", "082"]:
                    continue

            ind1_div = field.find("div", class_="ind1")
            ind2_div = field.find("div", class_="ind2")
            ind1 = (
                ind1_div.get_text(strip=True).replace("\xa0", "#") if ind1_div else "#"
            )
            ind2 = (
                ind2_div.get_text(strip=True).replace("\xa0", "#") if ind2_div else "#"
            )
            # &nbsp; 문자를 #으로 변환
            ind1 = "#" if not ind1 else ind1
            ind2 = "#" if not ind2 else ind2
            indicators = f"{ind1}{ind2}"

            subfields_div = field.find("div", class_="subfields")
            if subfields_div:
                # 650 필드의 경우, $a와 $0를 조합
                if tag == "650":
                    sub_a_code = subfields_div.find(
                        "span", class_="sub_code", string=re.compile(r"a\|")
                    )
                    sub_0_code = subfields_div.find(
                        "span", class_="sub_code", string=re.compile(r"0\|")
                    )

                    text_a = (
                        sub_a_code.next_sibling.strip()
                        if sub_a_code and sub_a_code.next_sibling
                        else ""
                    )
                    link_0 = (
                        sub_0_code.next_sibling.strip()
                        if sub_0_code and sub_0_code.next_sibling
                        else ""
                    )

                    full_text = f"{text_a} {link_0}".strip()
                else:  # 다른 필드는 모든 텍스트를 조합
                    text_parts = [
                        part.strip()
                        for part in subfields_div.stripped_strings
                        if not part.endswith("|")
                    ]
                    full_text = " ".join(text_parts)

                if tag not in marc_data:
                    marc_data[tag] = []
                marc_data[tag].append({"text": full_text, "indicators": indicators})
    except Exception:
        return {}
    return marc_data


def _parse_princeton_json_record(record_json, app_instance, skip_detailed_fields=False):
    """Princeton Blacklight API의 JSON 응답 및 staff_view 페이지에서 서지 정보를 추출합니다."""
    attributes = record_json.get("attributes", {})
    links = record_json.get("links", {})

    record = {
        "제목": attributes.get("title", ""),
        "저자": "",
        "출판사": "",
        "연도": "",
        "ISBN": "",
        "상세 링크": "",
        "주제어_원문": [],
        "082": "",
        "082 ind": "",
        "책소개": "",
        "목차": "",
        "250": "",
        "출판지역": "",
    }

    # 기본 정보 파싱 (JSON)
    author_display = attributes.get("author_display", {})
    if author_display:
        author_list = author_display.get("attributes", {}).get("value", [])
        record["저자"] = " | ".join(author_list)

    pub_display = attributes.get("pub_created_display", {})
    if pub_display:
        pub_string = pub_display.get("attributes", {}).get("value", [""])[0]
        if pub_string:
            year = extract_year(pub_string)
            if year:
                record["연도"] = year
                # 출판지역 추출: 콜론(:) 이전 부분
                parts_before_year = pub_string.split(year)[0].strip(" :,")
                if ":" in parts_before_year:
                    place_parts = parts_before_year.split(":")
                    record["출판지역"] = place_parts[0].strip()  # 출판지역
                    if len(place_parts) > 1:
                        record["출판사"] = place_parts[1].strip()  # 출판사
                else:
                    record["출판사"] = parts_before_year

    isbn_display = attributes.get("isbn_s", {})
    if isbn_display:
        isbn_list = isbn_display.get("attributes", {}).get("value", [])
        record["ISBN"] = " | ".join(isbn_list)

    # LC Call Number (082 필드 대신 사용할 수 있음)
    lc_call_number = ""
    lc_display = attributes.get("lc_1letter_s", {})
    if lc_display:
        lc_list = lc_display.get("attributes", {}).get("value", [])
        lcc_call_number = " | ".join(lc_list)

    # MARC 상세 정보 파싱 (staff_view 페이지)
    self_link = links.get("self", "")
    if self_link:
        marc_link = f"{self_link}/staff_view"
        record["상세 링크"] = marc_link

        try:
            # 🚀 Level 2 최적화: 캐시 키에 skip_detailed_fields 포함
            cache_key = f"{marc_link}_{skip_detailed_fields}"

            if cache_key in _marc_cache:
                parsed_marc = _marc_cache[cache_key]
            else:
                # 🚀 Level 2 최적화: 개선된 HTTP 요청
                response = _make_request_with_retry(
                    marc_link, app_instance=app_instance
                )

                # 응답 텍스트 추출 (httpx/requests 호환)
                if hasattr(response, "text"):
                    html_content = response.text
                else:
                    html_content = response.content.decode("utf-8")

                # 🚀 BeautifulSoup 파서를 lxml로 변경 (html.parser보다 빠름)
                try:
                    soup = BeautifulSoup(html_content, "lxml")
                except:
                    soup = BeautifulSoup(html_content, "html.parser")

                parsed_marc = _parse_marc_fields_from_html(soup, skip_detailed_fields)

                # 🚀 캐시에 저장 (메모리 절약을 위해 최대 500개까지만)
                if len(_marc_cache) >= 500:
                    # 가장 오래된 항목 제거 (FIFO)
                    oldest_key = next(iter(_marc_cache))
                    del _marc_cache[oldest_key]
                _marc_cache[cache_key] = parsed_marc

            # 파싱된 MARC 데이터로 record 딕셔너리 최종 완성
            record["250"] = parsed_marc.get("250", [{}])[0].get("text", "")

            # 🚀 선택적 파싱: skip_detailed_fields가 False일 때만 목차, 책소개 파싱
            if not skip_detailed_fields:
                record["목차"] = parsed_marc.get("505", [{}])[0].get("text", "")
                record["책소개"] = parsed_marc.get("520", [{}])[0].get("text", "")
            else:
                record["목차"] = ""
                record["책소개"] = ""

            # 주제어 추출
            subjects = [field["text"] for field in parsed_marc.get("650", [])]
            if subjects:
                record["주제어_원문"] = subjects

            # DDC 082 필드 추출 및 정규화
            ddc_field = parsed_marc.get("082", [{}])[0]
            if ddc_field.get("text"):
                ddc_raw = ddc_field["text"]
                # 공백 전까지만 추출 후 슬래시 제거
                ddc_before_space = ddc_raw.split()[0] if ddc_raw.split() else ddc_raw
                ddc_clean = ddc_before_space.replace("/", "")
                record["082"] = ddc_clean
                record["082 ind"] = ddc_field["indicators"]
            else:
                record["082"] = ""
                record["082 ind"] = ""

        except Exception as e:
            if app_instance:
                app_instance.log_message(
                    f"경고: Princeton MARC 페이지({marc_link}) 파싱 실패: {e}",
                    level="WARNING",
                )
            # 실패 시 LC Call Number를 082 필드로 사용
            record["082"] = lcc_call_number

    return record


def search_princeton_library(
    title_query=None,
    author_query=None,
    isbn_query=None,
    year_query=None,
    app_instance=None,
    db_manager=None,
    skip_detailed_fields=False,
):
    """Princeton University Library API를 호출하고 결과를 파싱하여 반환합니다."""
    if not any([title_query, author_query, isbn_query, year_query]):
        if app_instance:
            app_instance.log_message(
                "경고: 프린스턴 검색을 위한 검색어가 없습니다.", level="WARNING"
            )
        return []

    base_url = "https://catalog.princeton.edu/catalog.json"
    params = {}

    if isbn_query:
        params["q"] = isbn_query.replace("-", "").strip()
    else:
        # === 🔧 정확한 Princeton 필드명으로 수정 ===
        if author_query and not title_query and not year_query:
            # 저자만 검색할 때
            params["q"] = author_query
            params["search_field"] = "browse_name"  # Author (browse) 사용
        elif title_query and author_query:
            # 제목 + 저자 복합 검색 (기존 방식 유지하되 더 정확한 쿼리)
            params["q"] = f'title:"{title_query}" AND author:"{author_query}"'
        elif title_query and not author_query:
            # 제목만 검색
            params["q"] = f'title:"{title_query}"'
        else:
            # 기타 복합 검색 (년도 포함)
            query_parts = []
            if title_query:
                query_parts.append(f'title:"{title_query}"')
            if author_query:
                query_parts.append(f'author:"{author_query}"')
            if year_query:
                query_parts.append(f'date:"{year_query}"')

            if query_parts:
                params["q"] = " AND ".join(query_parts)
    try:
        # 🚀 Level 2 최적화: 개선된 API 요청 (재시도 로직 포함)
        if app_instance:
            client_type = "httpx (HTTP/2)" if HTTPX_AVAILABLE else "requests"
            app_instance.log_message(
                f"정보: Princeton API 요청 시작 ({client_type}): {params}", level="INFO"
            )

        response = _make_request_with_retry(
            base_url, params=params, app_instance=app_instance
        )

        # 응답 처리 (httpx/requests 호환)
        if hasattr(response, "json"):
            response_json = response.json()
        else:
            import json

            response_json = json.loads(response.text)

        records_json = response_json.get("data", [])

        if not records_json:
            if app_instance:
                app_instance.log_message(
                    "정보: Princeton 검색 결과가 없습니다.", level="INFO"
                )
            return []

        # 🚀 Level 2 최적화: ThreadPoolExecutor 워커 수 추가 증가 (12 → 15)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if app_instance:
            app_instance.log_message(
                f"정보: Princeton {len(records_json)}건의 레코드를 병렬 파싱 시작 (워커 15개, {client_type})",
                level="INFO",
            )

        all_results = []

        # 🚀 병렬 처리 워커 수 (15)
        with ThreadPoolExecutor(max_workers=15) as executor:
            future_to_record = {
                executor.submit(
                    _parse_princeton_json_record,
                    record_data,
                    app_instance,
                    skip_detailed_fields,
                ): record_data
                for record_data in records_json
            }

            for future in as_completed(future_to_record):
                try:
                    parsed = future.result()
                    if parsed is not None:
                        all_results.append(parsed)
                except Exception as e:
                    if app_instance:
                        app_instance.log_message(
                            f"경고: Princeton 레코드 파싱 실패: {e}", level="WARNING"
                        )

        # 주제어 번역 로직
        if all_results and _should_auto_translate(app_instance):
            if app_instance:
                app_instance.log_message(
                    "정보: Princeton 주제어 번역 시작...", level="INFO"
                )

            all_unique_subjects = set(
                s.strip() for r in all_results for s in r.get("주제어_원문", []) if s
            )

            if all_unique_subjects:
                custom_glossary = db_manager.get_all_custom_translations()
                translation_map = translate_text_batch_async(
                    list(all_unique_subjects), app_instance, custom_glossary, db_manager
                )
                for record in all_results:
                    raw_subjects = record.get("주제어_원문", [])
                    record["650 필드"] = " | ".join(raw_subjects)  # 원문 필드
                    translated = [
                        translation_map.get(s.strip(), s.strip()) for s in raw_subjects
                    ]
                    record["650 필드 (번역)"] = " | ".join(translated)  # 번역 필드
                    del record["주제어_원문"]

        elif all_results:
            for record in all_results:
                raw_subjects = record.get("주제어_원문", [])
                record["650 필드"] = " | ".join(raw_subjects)
                record["650 필드 (번역)"] = " | ".join(raw_subjects)
                del record["주제어_원문"]

        if app_instance:
            app_instance.log_message(
                f"정보: Princeton 검색 결과 {len(all_results)}건 파싱 완료.",
                level="INFO",
            )
        return all_results

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: Princeton API 처리 중 오류: {e}", level="ERROR"
            )
        return []
