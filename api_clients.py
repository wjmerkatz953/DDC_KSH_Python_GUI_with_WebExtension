# -*- coding: utf-8 -*-
"""
api_clients.py - 외부 API (NLK SPARQL, ISNI 등)와 통신하고 데이터를 추출하는 함수들을 포함합니다.
버전: 2.1.1
생성일: 2025-07-19 12:05
수정일시: 2025-08-19 23:55 KST (concurrent.futures import 추가)
"""

import requests
import json
import re
import time
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor  # ✅ 추가
from urllib.parse import unquote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from deep_translator import GoogleTranslator
import hanja
from database_manager import DatabaseManager
import asyncio

# 글로벌 번역기 인스턴스
global_translator = GoogleTranslator(source="auto", target="ko")


def clean_text(text):
    """
    HTML 태그 제거, HTML 엔티티 변환, 공백 정리를 수행합니다.
    GAS cleanText() 함수 포팅
    Args:
        text (str): 정리할 텍스트.
    Returns:
        str: 정리된 텍스트.
    """
    if not isinstance(text, str) or not text:
        return ""

    text = re.sub(r"<[^>]*>", "", text)  # HTML 태그 제거
    text = text.replace("&nbsp;", " ")  # &nbsp;를 공백으로 변환
    text = text.replace("&amp;", "&")  # &amp; 변환
    text = text.replace("&lt;", "<")  # &lt; 변환
    text = text.replace("&gt;", ">")  # &gt; 변환
    text = text.replace("&quot;", '"')  # &quot; 변환
    text = re.sub(r"\s+", " ", text)  # 연속된 공백을 단일 공백으로 변환
    text = text.strip()  # 양 끝 공백 제거

    return text


def _create_session():
    """
    재시도 로직이 포함된 requests 세션을 생성합니다.
    """
    session = requests.Session()

    # 재시도 전략 설정
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"],
        backoff_factor=1,
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # 기본 헤더 설정
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )

    return session


def fetch_content(url, description, app_instance, accept_header="text/html"):
    """
    URL에서 HTML/XML 콘텐츠를 가져옵니다.
    GAS fetchContent() 함수 포팅
    Args:
        url (str): 가져올 URL.
        description (str): 로그에 사용할 URL 설명.
        app_instance: IntegratedSearchApp 클래스 인스턴스 (로그 메시지 출력을 위함).
        accept_header (str): Accept 헤더 값 (기본값: 'text/html').
    Returns:
        str or None: HTML/XML 콘텐츠 또는 오류 발생 시 None.
    """
    app_instance.log_message(f"정보: {description} URL: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": accept_header,
    }

    try:
        if app_instance.stop_search_flag.is_set():
            raise requests.exceptions.RequestException(
                "검색이 사용자 요청으로 중단되었습니다."
            )

        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        response.raise_for_status()
        return response.text

    except requests.exceptions.RequestException as e:
        if "검색이 사용자 요청으로 중단되었습니다." in str(e):
            app_instance.log_message(
                f"정보: {description} 검색이 중단되었습니다.", level="INFO"
            )
        else:
            app_instance.log_message(
                f"오류: {description} 접근 중 오류 발생: {e}", level="ERROR"
            )
            app_instance.show_messagebox(
                "네트워크 오류",
                f"국립중앙도서관 서버 접속이 불안정합니다. 잠시 후 다시 시도해주세요.\n\n오류: {e}",
                "error",
            )
        return None


def extract_isni_numbers(html_content):
    """
    HTML 문자열에서 ISNI 번호를 추출합니다.
    GAS extractIsniNumbers() 함수 포팅 - 더 정확한 패턴 매칭
    Args:
        html_content (str): HTML 문자열.
    Returns:
        list: 추출된 고유 ISNI 번호 배열.
    """
    isni_numbers = set()

    # 1. <span class="isni_number"> 태그에서 직접 추출
    isni_span_regex = (
        r'<span class="isni_number">(\d{4}\s\d{4}\s\d{4}\s\d{3}[\dX])\s*</span>'
    )
    for match in re.finditer(isni_span_regex, html_content):
        isni_numbers.add(match.group(1).replace(" ", ""))

    # 2. title 속성에서 추출 (대체)
    isni_title_regex = r'title="(\d{4}\s\d{4}\s\d{4}\s\d{3}[\dX])\s*"'
    for match in re.finditer(isni_title_regex, html_content):
        isni_numbers.add(match.group(1).replace(" ", ""))

    # 3. 일반적인 16자리 숫자 패턴 (공백 포함 또는 미포함, X 포함)
    general_isni_regex = r"\b(\d{4}\s?\d{4}\s?\d{4}\s?\d{3}[\dX]?)\b"
    for match in re.finditer(general_isni_regex, html_content):
        isni_numbers.add(match.group(1).replace(" ", ""))

    return list(isni_numbers)


def _decode_rawid_data(rawid_encoded_string, app_instance):
    """
    URL 인코딩된 rawid 문자열을 디코딩하고 JSON을 파싱하여 저자 정보를 추출합니다.
    GAS _decodeRawIdData() 함수 포팅
    Args:
        rawid_encoded_string (str): input 태그의 value 속성에서 추출한 rawid 문자열.
        app_instance: 로그 출력용
    Returns:
        dict|None: 저자 정보 객체 ({name, isni, kac}) 또는 파싱 실패 시 None.
    """
    app_instance.log_message(
        f"[_decode_rawid_data] rawid 디코딩 시작. 입력 길이: {len(rawid_encoded_string)}"
    )

    try:
        # 1단계: URL 디코딩
        decoded_value = unquote(rawid_encoded_string)
        app_instance.log_message(
            f"[_decode_rawid_data] URL 디코딩 완료. 내용 (처음 200자): {decoded_value[:200]}"
        )

        # 2단계: JSON 부분 추출 (마지막 { } 블록)
        json_part_match = re.search(r"(\{[\s\S]*\})$", decoded_value)

        if not json_part_match:
            app_instance.log_message(
                "[_decode_rawid_data] JSON 부분을 찾을 수 없습니다."
            )
            return None

        json_string = json_part_match.group(1)
        app_instance.log_message(
            f"[_decode_rawid_data] JSON 파트 추출 완료. 길이: {len(json_string)}"
        )

        # 3단계: JSON 파싱
        parsed_data = json.loads(json_string)
        app_instance.log_message(
            f"[_decode_rawid_data] JSON 파싱 완료. 이름: {parsed_data.get('name')}, ISNI: {parsed_data.get('isni_disp')}, KAC: {parsed_data.get('ac_control_no')}"
        )

        return {
            "name": parsed_data.get("name", "정보 없음"),
            # 공백과 + 기호 제거
            "isni": (parsed_data.get("isni_disp", "없음"))
            .replace(" ", "")
            .replace("+", ""),
            "kac": parsed_data.get("ac_control_no", "없음"),
        }

    except Exception as e:
        app_instance.log_message(
            f"[_decode_rawid_data] rawid 디코딩 또는 JSON 파싱 중 오류 발생: {e}"
        )
        return None


def extract_kac_code(html_content, app_instance):
    """
    ISNI 상세 페이지 HTML에서 KAC 코드를 추출합니다.
    GAS extractKacCode() 함수 포팅 - rawid 우선, LOD 링크 fallback
    Args:
        html_content (str): ISNI 상세 페이지 HTML 문자열.
        app_instance: 로그 출력용
    Returns:
        str: 추출된 KAC 코드 또는 "없음".
    """
    # 1. rawid에서 KAC 추출 시도 (우선)
    rawid_match = re.search(
        r'<input type="checkbox" id="rawid\d+" name="rawid" value="([^"]+)"',
        html_content,
    )
    if rawid_match and rawid_match.group(1):
        try:
            decoded_data = _decode_rawid_data(rawid_match.group(1), app_instance)
            if decoded_data and decoded_data["kac"] and decoded_data["kac"] != "없음":
                app_instance.log_message(
                    f"extract_kac_code: rawid에서 KAC 추출 성공: {decoded_data['kac']}"
                )
                return decoded_data["kac"]
        except Exception as e:
            app_instance.log_message(f"extract_kac_code: rawid 디코딩 실패: {e}")

    # 2. 기존 방식으로 fallback (LOD 링크에서 추출)
    kac_regex = r'href="https://lod\.nl\.go\.kr/resource/(KAC[0-9a-zA-Z]{9})"'
    kac_match = re.search(kac_regex, html_content, re.IGNORECASE)
    if kac_match and kac_match.group(1):
        app_instance.log_message(
            f"extract_kac_code: LOD 링크에서 KAC 추출 성공: {kac_match.group(1)}"
        )
        return kac_match.group(1)

    app_instance.log_message("extract_kac_code: KAC 코드를 찾을 수 없음")
    return "없음"


def get_author_name_from_kac_sparql(kac_code, app_instance):
    """
    KAC 코드를 사용하여 저자명을 추출합니다.
    GAS getAuthorNameFromKacLodPopup() 함수 포팅 - rawid 우선, LOD 팝업 fallback
    Args:
        kac_code (str): 검색할 KAC 코드.
        app_instance: IntegratedSearchApp 클래스 인스턴스 (로그 메시지 출력을 위함).
    Returns:
        str: 추출된 저자명 또는 "정보 없음".
    """
    app_instance.log_message(f"KAC LOD 팝업에서 저자 이름 추출 시도: {kac_code}")

    # 1. 먼저 librarian 사이트에서 rawid 추출 시도
    librarian_url = f"https://librarian.nl.go.kr/LI/contents/L20101000000.do?searchType=detail&page=1&pageSize=10&acType=0&val=&detailAcControlName=KAC&detailAcControlNo={kac_code}+&isni=&detailBirth=&detailDeath=&detailActivity=&detailJob=&detailOrgType=&detailRegion=&detailRegionView=&detailResourceName=&detailIdentiType=ISBN&detailIdentiNo=&detailKeyword="
    librarian_html = fetch_content(librarian_url, "Librarian KAC 페이지", app_instance)

    if librarian_html:
        rawid_match = re.search(
            r'<input type="checkbox" id="rawid\d+" name="rawid" value="([^"]+)"',
            librarian_html,
        )
        if rawid_match and rawid_match.group(1):
            try:
                decoded_data = _decode_rawid_data(rawid_match.group(1), app_instance)
                if (
                    decoded_data
                    and decoded_data["name"]
                    and decoded_data["name"] != "정보 없음"
                ):
                    app_instance.log_message(
                        f"저자 이름 추출 성공 (rawid): {decoded_data['name']}"
                    )
                    return decoded_data["name"]
            except Exception as e:
                app_instance.log_message(f"rawid 디코딩 실패: {e}")

    # 2. rawid 실패 시 기존 LOD 팝업 방식으로 fallback
    lod_popup_url = f"https://lod.nl.go.kr/home/include/lodpopup.jsp?uri=http://lod.nl.go.kr/resource/{kac_code}"
    html_content = fetch_content(
        lod_popup_url, "KAC LOD 팝업 페이지 (HTML)", app_instance
    )

    if not html_content:
        app_instance.log_message(
            f"KAC LOD 팝업 페이지에서 콘텐츠를 가져올 수 없음 (KAC: {kac_code})"
        )
        return "정보 없음"

    # 단순화: rdfs:label 패턴 하나만 사용 (가장 안정적)
    name_regex = r"<tr>\s*<td[^>]*>[\s\S]*?rdfs:label[\s\S]*?</td>\s*<td[^>]*>(?:<p>([\s\S]+?)</p>|([\s\S]+?))</td>\s*</tr>"
    name_match = re.search(name_regex, html_content, re.IGNORECASE)

    if name_match:
        raw_name = name_match.group(1) or name_match.group(2)
        if raw_name:
            cleaned_name = clean_text(raw_name)
            app_instance.log_message(
                f"저자 이름 추출 성공 (LOD fallback): {cleaned_name}"
            )
            return cleaned_name

    app_instance.log_message(
        f"KAC LOD 팝업 페이지에서 저자 이름을 찾을 수 없음 (KAC: {kac_code})"
    )
    return "정보 없음"


def extract_work_ids_from_kac_lod_page(html_content):
    """
    KAC LOD 페이지 HTML에서 저작물 ID를 추출합니다.
    GAS extractWorkIdsFromKacLodPage() 함수 포팅
    Args:
        html_content (str): KAC LOD 페이지 HTML 문자열
    Returns:
        list: 추출된 고유 저작물 ID 배열
    """
    # href="lodpopup.jsp?uri=..." 패턴을 찾아 uri= 뒤의 값을 추출합니다.
    work_id_regex = r'href=[\'"]lodpopup\.jsp\?uri=http://lod\.nl\.go\.kr/resource/(KMO\d+|CNTS-\d+|KDM\d+|KJU\d+)[\'"]'
    work_id_matches = re.findall(work_id_regex, html_content)
    return list(set(work_id_matches))  # 중복 제거


def extract_year(date_string):
    """
    날짜 문자열에서 4자리 연도를 추출합니다.
    GAS extractYear() 함수 포팅
    Args:
        date_string (str): 날짜를 포함하는 문자열.
    Returns:
        str: 추출된 4자리 연도 (예: "2023"), 또는 찾을 수 없는 경우 "연도 불명".
    """
    if not isinstance(date_string, str):
        return "연도 불명"

    # YYYY-MM-DDTHH:MM:SS 형식, YYYYMMDD 형식, [YYYY] 또는 YYYY 패턴 처리
    match = re.search(
        r"(\d{4})-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|(\d{4})\d{2}\d{2}|\b(\d{4})\b",
        date_string,
    )
    if match:
        return match.group(1) or match.group(2) or match.group(3)
    return "연도 불명"


def get_works_from_nl_ajax_api(kac_code, app_instance):
    """
    KAC 코드를 사용하여 NLK AJAX API에서 저작물 목록을 가져옵니다.
    offline과 online 자료를 병렬로 수집하여 합칩니다.
    Args:
        kac_code (str): 저작물을 가져올 KAC 코드.
        app_instance: 로그 출력용
    Returns:
        list: 저작물 객체 배열 (title, author, year, link 포함).
    """
    start_time = time.time()
    app_instance.log_message(
        f"[get_works_from_nl_ajax_api] KAC({kac_code})에 대한 offline/online 저작물 병렬 수집 시작."
    )

    base_url = "https://librarian.nl.go.kr/LI/module/isni/subjectNlSearch.ajax"
    page_size = 1000  # 1000개씩 한 번에 수집

    def fetch_category_works(category):
        """특정 카테고리(offline/online)의 저작물을 수집"""
        url = f"{base_url}?acControlNo={kac_code}&pageNum=1&pageSize={page_size}&category={category}&sort=&fLanguage=&publishYear=&field="

        app_instance.log_message(f"  🔍 {category} 검색 URL: {url}")

        # 실제 브라우저와 동일한 헤더 설정으로 차단 방지
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Referer": f"https://librarian.nl.go.kr/LI/contents/L20101000000.do?id={kac_code}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch_ua_mobile": "?0",
            "sec-ch_ua_platform": '"Windows"',
        }

        try:
            if app_instance.stop_search_flag.is_set():
                return []

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                app_instance.log_message(
                    f"[get_works_from_nl_ajax_api] 오류: {category} 자료 가져오기 실패. 응답 코드: {response.status_code}"
                )
                return []

            html_content = response.text
            current_works = []

            # HTML 파싱 로직
            work_blocks = html_content.split('<div class="table_bd">')[
                1:
            ]  # 첫 번째는 제외

            if len(work_blocks) == 0:
                return []

            for i, block in enumerate(work_blocks):
                # 새로운 HTML 구조에 맞는 제목과 링크 추출
                title_match = re.search(
                    r'<a\s+href="([^"]+)"[^>]*class="link"[^>]*>([^<]+)</a>',
                    block,
                    re.IGNORECASE,
                )

                if not title_match:
                    continue

                relative_link = title_match.group(1)
                title = title_match.group(2).strip()

                # 새로운 구조에 맞는 저자 정보 추출
                author_match = re.search(
                    r'<span class="remark">저자</span>\s*<span class="cont"[^>]*>([^<]+)</span>',
                    block,
                    re.DOTALL,
                )
                author = "정보 없음"
                if author_match:
                    author = author_match.group(1).strip()

                # 새로운 구조에 맞는 발행연도 추출
                year_match = re.search(
                    r'<span class="remark">발행년도</span>\s*<span class="cont"[^>]*>([^<]+)</span>',
                    block,
                    re.DOTALL,
                )
                year = year_match.group(1).strip() if year_match else "연도 불명"

                # 상대 링크를 절대 링크로 변환
                if relative_link.startswith("/"):
                    absolute_link = f"https://librarian.nl.go.kr/LI/contents/L20101000000.do{relative_link}"
                else:
                    absolute_link = f"https://librarian.nl.go.kr/LI/contents/L20101000000.do{relative_link}"

                current_works.append(
                    {
                        "title": title,
                        "author": author,
                        "year": year,
                        "link": absolute_link,
                    }
                )

            return current_works

        except requests.exceptions.RequestException as e:
            app_instance.log_message(
                f"[get_works_from_nl_ajax_api] {category} 요청 중 오류 발생: {e}"
            )
            return []

    # 병렬로 offline과 online 자료 수집
    all_works = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # offline과 online을 동시에 실행
        future_offline = executor.submit(fetch_category_works, "offline")
        future_online = executor.submit(fetch_category_works, "online")

        # 결과 수집
        offline_works = future_offline.result()
        online_works = future_online.result()

        # 결과 합치기
        all_works.extend(offline_works)
        all_works.extend(online_works)

    # 발행년도 기준으로 최신순 정렬
    all_works.sort(
        key=lambda x: int(x["year"]) if x["year"].isdigit() else 0, reverse=True
    )

    end_time = time.time()
    elapsed_time = end_time - start_time

    app_instance.log_message(
        f"[get_works_from_nl_ajax_api] 총 {len(all_works)}개의 저작물 수집 완료 (offline: {len(offline_works)}, online: {len(online_works)}) - ⏱️ 소요시간: {elapsed_time:.2f}초"
    )
    return all_works


def get_work_details_from_work_sparql_optimized(work_ids, app_instance):
    """
    기존 함수명 유지 - 내부적으로 AJAX API 사용
    SPARQL 대신 AJAX API를 사용하여 저작물 상세 정보를 가져옵니다.
    Args:
        work_ids (list): 저작물 ID 목록 (실제로는 사용하지 않음).
        app_instance: IntegratedSearchApp 클래스 인스턴스.
    Returns:
        list: 저작물 상세 정보 딕셔너리 목록.
    """
    # 이 함수는 기존 호출 방식과의 호환성을 위해 남겨두지만,
    # 실제로는 get_works_from_nl_ajax_api()를 사용하도록 권장
    app_instance.log_message(
        "경고: get_work_details_from_work_sparql_optimized는 더 이상 사용되지 않습니다. get_works_from_nl_ajax_api를 사용하세요."
    )
    return []


def _fetch_and_process_single_author_data(
    input_isni=None, input_kac=None, app_instance=None
):
    """
    저자 데이터 (ISNI, KAC, 저작물 목록)를 가져오는 핵심 로직입니다.
    GAS _fetchAndProcessSingleAuthorData() 함수 포팅
    Args:
        input_isni (str|None): 검색할 ISNI (없으면 None).
        input_kac (str|None): 검색할 KAC (없으면 None).
        app_instance: 로그 출력용
    Returns:
        dict|None: 단일 저자 데이터 객체 또는 찾을 수 없을 때 None.
    """
    author_isni = input_isni
    author_kac = input_kac
    author_name = "정보 없음"
    works_list = []

    # 공통 로직: librarian 사이트에서 rawid 우선 추출
    librarian_url = ""
    if author_kac and author_kac != "없음":
        if author_kac and author_kac != "없음":
            librarian_url = f"https://librarian.nl.go.kr/LI/contents/L20101000000.do?searchType=detail&page=1&pageSize=10&acType=0&val=&detailAcControlName=KAC&detailAcControlNo={author_kac}+&isni=&detailBirth=&detailDeath=&detailActivity=&detailJob=&detailOrgType=&detailRegion=&detailRegionView=&detailResourceName=&detailIdentiType=ISBN&detailIdentiNo=&detailKeyword="
    elif author_isni and author_isni != "없음":
        librarian_url = f"https://librarian.nl.go.kr/LI/contents/L20101000000.do?searchType=detail&page=1&pageSize=10&acType=0&val=&detailAcControlName=KAC&detailAcControlNo=&isni={author_isni}+&detailBirth=&detailDeath=&detailActivity=&detailJob=&detailOrgType=&detailRegion=&detailRegionView=&detailResourceName=&detailIdentiType=ISBN&detailIdentiNo=&detailKeyword="
    else:
        app_instance.log_message("ERROR: 유효한 ISNI 또는 KAC가 필요합니다.")
        return None

    # rawid에서 모든 정보 한 번에 추출 시도
    librarian_html = fetch_content(librarian_url, "Librarian 페이지", app_instance)
    if librarian_html:
        rawid_match = re.search(
            r'<input type="checkbox" id="rawid\d+" name="rawid" value="([^"]+)"',
            librarian_html,
        )
        if rawid_match and rawid_match.group(1):
            try:
                decoded_data = _decode_rawid_data(rawid_match.group(1), app_instance)
                if (
                    decoded_data
                    and decoded_data["name"] != "정보 없음"
                    and decoded_data["kac"] != "없음"
                ):
                    # rawid에서 모든 정보 추출 성공! 바로 사용
                    author_name = decoded_data["name"]
                    author_isni = decoded_data["isni"]
                    author_kac = decoded_data["kac"]
                    app_instance.log_message(
                        f"rawid에서 모든 정보 추출 성공: 이름={author_name}, ISNI={author_isni}, KAC={author_kac}"
                    )
                else:
                    app_instance.log_message("rawid 추출 실패, fallback 로직 실행")
                    # fallback 로직 실행
                    if input_kac:
                        author_name = get_author_name_from_kac_sparql(
                            author_kac, app_instance
                        )
                        author_isni = "없음"
                    elif input_isni:
                        author_kac = extract_kac_code(librarian_html, app_instance)
                        if author_kac != "없음":
                            author_name = get_author_name_from_kac_sparql(
                                author_kac, app_instance
                            )
            except Exception as e:
                app_instance.log_message(f"rawid 디코딩 실패: {e}, fallback 실행")
                # fallback 로직 실행 (기존과 동일)
                if input_kac:
                    author_name = get_author_name_from_kac_sparql(
                        author_kac, app_instance
                    )
                    author_isni = "없음"
                elif input_isni:
                    author_kac = extract_kac_code(librarian_html, app_instance)
                    if author_kac != "없음":
                        author_name = get_author_name_from_kac_sparql(
                            author_kac, app_instance
                        )

    # 저작물 목록 추출 (AJAX API 사용으로 변경)
    if author_kac and author_kac != "없음":
        app_instance.log_message(
            f'_fetch_and_process_single_author_data: KAC "{author_kac}"로 저작물 목록 가져오기 시도.'
        )

        # 기존 LOD 방식 대신 AJAX API 사용
        all_works_from_ajax = get_works_from_nl_ajax_api(author_kac, app_instance)

        if all_works_from_ajax and len(all_works_from_ajax) > 0:
            works_list = []
            for work in all_works_from_ajax:
                works_list.append(
                    {
                        # ✅ GAS와 동일한 형태
                        "display": f"{work['title']} ({work['year']})",
                        "url": work["link"],
                        "creators": [work["author"]],  # ✅ GAS와 동일한 키명
                    }
                )
            app_instance.log_message(
                f"_fetch_and_process_single_author_data: AJAX API를 통해 저작물 {len(works_list)}개 가져옴."
            )
        else:
            app_instance.log_message(
                f"_fetch_and_process_single_author_data: AJAX API를 통해 저작물을 추출하지 못했습니다 (KAC: {author_kac})."
            )
    else:
        app_instance.log_message(
            "_fetch_and_process_single_author_data: 유효한 KAC 코드를 찾을 수 없어 저작물 목록을 추출할 수 없습니다."
        )

    return {
        "authorName": author_name,
        "isni": author_isni,
        "kac": author_kac,
        "works": works_list,
    }


def _fetch_multiple_author_data_parallel(isni_list, app_instance):
    """
    병렬처리로 여러 ISNI의 저자 데이터를 동시에 수집합니다.
    GAS _fetchMultipleAuthorDataParallel() 함수 포팅
    Args:
        isni_list (list): ISNI 번호 배열
        app_instance: 로그 출력용
    Returns:
        list: 저자 데이터 객체 배열
    """
    if not isni_list or len(isni_list) == 0:
        return []

    app_instance.log_message(f"병렬처리로 {len(isni_list)}명의 저자 데이터 수집 시작")

    # 1단계: 모든 ISNI에 대한 Librarian 페이지 요청을 동시에 준비
    librarian_urls = []
    for isni in isni_list:
        url = f"https://librarian.nl.go.kr/LI/contents/L20101000000.do?searchType=detail&page=1&pageSize=10&acType=0&val=&detailAcControlName=KAC&detailAcControlNo=&isni={isni}+&detailBirth=&detailDeath=&detailActivity=&detailJob=&detailOrgType=&detailRegion=&detailRegionView=&detailResourceName=&detailIdentiType=ISBN&detailIdentiNo=&detailKeyword="
        librarian_urls.append(url)

    app_instance.log_message(
        f"1단계: {len(librarian_urls)}개 Librarian 페이지 동시 요청"
    )

    # 2단계: 병렬로 모든 Librarian 페이지를 가져오기
    author_info_list = []
    ajax_requests_to_make = []  # AJAX 요청할 것들

    def fetch_librarian_page(url_and_isni):
        url, original_isni = url_and_isni
        try:
            if app_instance.stop_search_flag.is_set():
                return None

            response = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=10,
            )

            if response.status_code != 200:
                app_instance.log_message(
                    f"저자 (ISNI: {original_isni}) Librarian 페이지 접근 실패: {response.status_code}"
                )
                return None

            html_content = response.text
            rawid_match = re.search(
                r'<input type="checkbox" id="rawid\d+" name="rawid" value="([^"]+)"',
                html_content,
            )

            if rawid_match and rawid_match.group(1):
                try:
                    decoded_data = _decode_rawid_data(
                        rawid_match.group(1), app_instance
                    )
                    if (
                        decoded_data
                        and decoded_data["name"] != "정보 없음"
                        and decoded_data["kac"] != "없음"
                    ):
                        app_instance.log_message(
                            f"저자 rawid 추출 성공: {decoded_data['name']} (KAC: {decoded_data['kac']})"
                        )
                        return {
                            "authorName": decoded_data["name"],
                            "isni": decoded_data["isni"],
                            "kac": decoded_data["kac"],
                            "works": [],  # 나중에 채울 예정
                        }
                    else:
                        app_instance.log_message(
                            f"저자 rawid 디코딩 실패 또는 불완전한 데이터"
                        )
                except Exception as e:
                    app_instance.log_message(f"저자 rawid 파싱 오류: {e}")
            else:
                app_instance.log_message(f"저자 rawid를 찾을 수 없음")

        except Exception as e:
            app_instance.log_message(f"저자 정보 수집 중 오류: {e}")

        return None

    # ThreadPoolExecutor를 사용한 병렬 처리
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        url_isni_pairs = [(url, isni) for url, isni in zip(librarian_urls, isni_list)]
        future_to_isni = {
            executor.submit(fetch_librarian_page, pair): pair[1]
            for pair in url_isni_pairs
        }

        for future in concurrent.futures.as_completed(future_to_isni):
            if app_instance.stop_search_flag.is_set():
                app_instance.log_message("정보: 병렬 저자 정보 수집이 중단되었습니다.")
                break

            result = future.result()
            if result:
                author_info_list.append(result)
                ajax_requests_to_make.append(
                    {
                        "author_index": len(author_info_list) - 1,
                        "kac_code": result["kac"],
                    }
                )

    app_instance.log_message(f"1단계 완료: {len(author_info_list)}개 저자 정보 수집됨")

    # 3단계: 모든 저작물 AJAX 요청을 병렬로 수행
    if len(ajax_requests_to_make) == 0:
        app_instance.log_message("AJAX 요청할 저자가 없음")
        return author_info_list

    app_instance.log_message(
        f"2단계: {len(ajax_requests_to_make)}명의 저작물 목록 동시 수집 시작"
    )

    def fetch_works_ajax(request_info):
        """
        병렬처리용 저작물 수집 함수 - GAS와 동일하게 기존 함수 재사용
        """
        try:
            if app_instance.stop_search_flag.is_set():
                return None

            kac_code = request_info["kac_code"]

            # ✅ GAS처럼 기존 함수 재사용 - 중복 코드 완전 제거!
            works_from_ajax = get_works_from_nl_ajax_api(kac_code, app_instance)

            # ✅ GAS와 동일한 형태로 변환 (display, url, creators)
            formatted_works = []
            for work in works_from_ajax:
                formatted_works.append(
                    {
                        "display": f"{work['title']} ({work['year']})",
                        "url": work["link"],
                        "creators": [work["author"]],
                    }
                )

            # 발행년도 기준 최신순 정렬 (GAS와 동일)
            formatted_works.sort(
                key=lambda x: _extract_year_from_display(x["display"]), reverse=True
            )

            return {
                "author_index": request_info["author_index"],
                "works": formatted_works,
            }

        except Exception as e:
            app_instance.log_message(f"병렬 저작물 수집 중 오류: {e}")
            return None

    def _extract_year_from_display(display_text):
        """display 텍스트에서 연도 추출 (정렬용)"""
        match = re.search(r"\((\d{4}|\연도 불명)\)$", display_text)
        if match and match.group(1) != "연도 불명":
            return int(match.group(1))
        return 0

    # 저작물 정보 병렬 수집
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_request = {
            executor.submit(fetch_works_ajax, req): req for req in ajax_requests_to_make
        }

        for future in concurrent.futures.as_completed(future_to_request):
            if app_instance.stop_search_flag.is_set():
                app_instance.log_message("정보: 병렬 저작물 수집이 중단되었습니다.")
                break

            result = future.result()
            if result:
                author_index = result["author_index"]
                works = result["works"]
                author_info_list[author_index]["works"] = works
                app_instance.log_message(
                    f"저자 {author_index+1} ({author_info_list[author_index]['authorName']}): {len(works)}개 저작물 수집 완료"
                )

    app_instance.log_message(
        f"병렬처리 완료: 총 {len(author_info_list)}명의 저자 데이터 수집 완료"
    )
    return author_info_list


# 기존 함수명 유지하되 내부 로직을 새로운 방식으로 교체하는 함수들


def execute_sparql_query(sparql_query, app_instance):
    """
    기존 함수명 유지 - 실제로는 사용하지 않음
    SPARQL 쿼리 대신 새로운 방식을 사용하므로 빈 결과 반환
    """
    app_instance.log_message(
        "경고: SPARQL 쿼리는 더 이상 사용되지 않습니다. 새로운 AJAX API를 사용합니다."
    )
    return []


def translate_text(text, custom_glossary_map=None, db_manager: DatabaseManager = None):
    """
    텍스트를 번역하고, 사용자 정의 용어집을 적용하며, 한자를 한글로 변환합니다.
    Args:
        text (str): 번역할 텍스트.
        custom_glossary_map (dict, optional): 미리 로드된 사용자 정의 용어집.
        db_manager (DatabaseManager, optional): DB 용어집 조회를 위한 DatabaseManager 인스턴스.
    Returns:
        str: 번역 및 변환된 텍스트.
    """
    if not text or not isinstance(text, str):
        return ""

    try:
        # 1. DB에서 용어집 조회 (캐싱된 결과가 없거나 DB 매니저가 제공될 때)
        if db_manager:
            # 먼저 전체 텍스트가 용어집에 있는지 확인
            cached_translation = db_manager.get_translation(text)
            if cached_translation:
                return cached_translation  # 캐시된 번역 반환

        # 2. 사용자 정의 용어집 적용 (미리 로드된 맵 사용)
        if custom_glossary_map and text in custom_glossary_map:
            return custom_glossary_map[text]

        # 3. 구글 번역 API 호출
        translated_text = GoogleTranslator(source="auto", target="ko").translate(text)

        # 4. 한자 -> 한글 변환
        # 번역 결과가 None이 아닐 경우에만 변환 시도
        if translated_text:
            final_text = hanja.translate(translated_text, "substitution")
        else:
            final_text = text  # 번역 실패 시 원본 텍스트 사용

        # 5. 번역 결과를 DB에 저장 (성공적인 번역이고 DB 매니저가 있을 때)
        if db_manager and translated_text:
            db_manager.add_translation(text, final_text)

        return final_text

    except Exception as e:
        # 오류 발생 시 원본 텍스트 반환
        # app_instance가 없으므로 로그는 호출하는 쪽에서 처리
        return f"{text} (번역 오류: {e})"


# === 🔥 비동기 배치 번역 시스템 (DNB, BNF 전용) ===


async def translate_batch_async_safe(
    subjects_batch,
    batch_size=15,
    max_concurrent=3,
    app_instance=None,
    custom_glossary_map=None,
    db_manager=None,
):
    """
    요청 제한이 있는 안전한 비동기 배치 번역 (DNB, BNF 전용)
    Args:
        subjects_batch (set): 번역할 고유 주제어 집합
        batch_size (int): 한 배치당 주제어 개수 (15개)
        max_concurrent (int): 동시 실행할 최대 배치 수 (3개)
        app_instance: 로깅용 앱 인스턴스
        custom_glossary_map: 용어집
        db_manager: DB 매니저
    Returns:
        dict: {원문: 번역} 매핑 딕셔너리
    """
    if not subjects_batch:
        return {}

    if app_instance:
        app_instance.log_message(
            f"🚀 안전한 비동기 배치 번역 시작! {len(subjects_batch)}개 주제어를 {batch_size}개씩 분할",
            level="INFO",
        )

    # 주제어를 여러 배치로 분할
    subjects_list = list(subjects_batch)
    batches = [
        subjects_list[i : i + batch_size]
        for i in range(0, len(subjects_list), batch_size)
    ]

    if app_instance:
        app_instance.log_message(
            f"📦 {len(batches)}개 배치로 분할 완료! 동시 최대 {max_concurrent}개씩 처리",
            level="INFO",
        )

    # 🛡️ 세마포어로 동시 실행 제한
    semaphore = asyncio.Semaphore(max_concurrent)
    final_translation_map = {}

    async def process_batch_with_limit(batch_idx, batch):
        """세마포어로 제한된 배치 처리"""
        async with semaphore:
            if app_instance and app_instance.stop_search_flag.is_set():
                return {}

            try:
                # 배치 간 짧은 딜레이 (API 친화적)
                if batch_idx > 0:
                    await asyncio.sleep(0.3)  # 300ms 대기

                result = await translate_single_batch_async_safe(
                    batch, batch_idx, app_instance, custom_glossary_map, db_manager
                )
                return result

            except Exception as e:
                if app_instance:
                    app_instance.log_message(
                        f"⚠️ 배치 {batch_idx} 처리 실패: {e}", level="WARNING"
                    )
                return {}

    try:
        # 🚀 제한된 동시 실행으로 모든 배치 처리
        tasks = [
            process_batch_with_limit(batch_idx, batch)
            for batch_idx, batch in enumerate(batches)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 병합
        successful_batches = 0

        for batch_idx, result in enumerate(results):
            if isinstance(result, dict) and result:
                final_translation_map.update(result)
                successful_batches += 1
            elif isinstance(result, Exception):
                if app_instance:
                    app_instance.log_message(
                        f"⚠️ 배치 {batch_idx} 예외 발생: {result}", level="WARNING"
                    )

        if app_instance:
            app_instance.log_message(
                f"✅ 안전한 비동기 배치 번역 완료! {successful_batches}/{len(batches)} 배치 성공",
                level="INFO",
            )

        return final_translation_map

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"❌ 안전한 비동기 배치 번역 전체 실패: {e}", level="ERROR"
            )
        return {}


async def translate_single_batch_async_safe(
    batch, batch_idx, app_instance=None, custom_glossary_map=None, db_manager=None
):
    """
    안전한 단일 배치 비동기 번역 - 재시도 로직 포함
    """
    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            if app_instance:
                retry_msg = f" (재시도 {attempt})" if attempt > 0 else ""
                app_instance.log_message(
                    f"🔄 배치 {batch_idx}: {len(batch)}개 주제어 번역 중...{retry_msg}",
                    level="DEBUG",
                )

            # 더 안전한 구분자 사용
            safe_delimiter = " || "
            batch_text = safe_delimiter.join(batch)

            # 동기 번역기를 ThreadPoolExecutor로 비동기 실행
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                translated_text = await loop.run_in_executor(
                    executor, global_translator.translate, batch_text
                )

            # 번역 결과 분리
            translated_batch = translated_text.split(safe_delimiter)

            # 결과 검증 및 매핑
            if len(translated_batch) == len(batch):
                result = dict(zip(batch, [t.strip() for t in translated_batch]))
                if app_instance:
                    success_msg = f" (재시도 후 성공)" if attempt > 0 else ""
                    app_instance.log_message(
                        f"✅ 배치 {batch_idx} 완료: {len(result)}개 번역{success_msg}",
                        level="DEBUG",
                    )
                return result
            else:
                if attempt < max_retries:
                    if app_instance:
                        app_instance.log_message(
                            f"⚠️ 배치 {batch_idx} 개수 불일치, 재시도 중...",
                            level="DEBUG",
                        )
                    await asyncio.sleep(0.5)  # 재시도 전 대기
                    continue
                else:
                    # 최종 실패시 개별 번역으로 폴백
                    if app_instance:
                        app_instance.log_message(
                            f"⚠️ 배치 {batch_idx} 최종 실패, 개별 번역으로 폴백",
                            level="WARNING",
                        )
                    return await translate_batch_individually_async_safe(
                        batch, batch_idx, app_instance, custom_glossary_map, db_manager
                    )

        except Exception as e:
            if attempt < max_retries:
                if app_instance:
                    app_instance.log_message(
                        f"⚠️ 배치 {batch_idx} 오류 발생, 재시도 중: {e}", level="DEBUG"
                    )
                await asyncio.sleep(1.0)  # 오류시 더 긴 대기
                continue
            else:
                if app_instance:
                    app_instance.log_message(
                        f"❌ 배치 {batch_idx} 최종 실패: {e}", level="ERROR"
                    )
                # 최종 실패시 개별 번역 시도
                return await translate_batch_individually_async_safe(
                    batch, batch_idx, app_instance, custom_glossary_map, db_manager
                )

    return {}


async def translate_batch_individually_async_safe(
    batch, batch_idx, app_instance=None, custom_glossary_map=None, db_manager=None
):
    """
    안전한 개별 번역 폴백 - 기존 translate_text 로직 사용 (DB 캐시, 용어집, 한자변환 포함)
    """
    result = {}
    loop = asyncio.get_event_loop()

    # 개별 번역은 더 보수적으로 (동시 2개까지만)
    semaphore = asyncio.Semaphore(2)

    async def translate_single_subject_safe(subject):
        async with semaphore:
            try:
                # 개별 번역간 딜레이
                await asyncio.sleep(0.1)

                # 🔥 기존 translate_text 로직 사용 (DB 캐시, 용어집, 한자변환 모두 포함)
                with ThreadPoolExecutor(max_workers=1) as executor:
                    translated = await loop.run_in_executor(
                        executor,
                        translate_text,
                        subject,
                        custom_glossary_map,
                        db_manager,
                    )
                return subject, translated.strip()
            except Exception as e:
                if app_instance:
                    app_instance.log_message(
                        f"개별 번역 실패: {subject} - {e}", level="WARNING"
                    )
                return subject, f"{subject} (번역 오류)"

    # 모든 개별 번역을 제한된 병렬로 실행
    tasks = [translate_single_subject_safe(subject) for subject in batch]
    individual_results = await asyncio.gather(*tasks, return_exceptions=True)

    for item in individual_results:
        if isinstance(item, tuple):
            subject, translation = item
            result[subject] = translation
        elif isinstance(item, Exception):
            if app_instance:
                app_instance.log_message(f"개별 번역 예외: {item}", level="WARNING")

    if app_instance:
        app_instance.log_message(
            f"✅ 배치 {batch_idx} 안전한 개별 번역 완료: {len(result)}개 (기존 로직 사용)",
            level="DEBUG",
        )

    return result


def translate_text_batch_async(
    subjects_batch, app_instance=None, custom_glossary_map=None, db_manager=None
):
    """
    비동기 배치 번역을 동기 환경에서 실행하는 래퍼 함수 (DNB, BNF 전용)

    Args:
        subjects_batch (set): 번역할 고유 주제어 집합
        app_instance: 로깅용 앱 인스턴스
        custom_glossary_map: 용어집 딕셔너리
        db_manager: DB 매니저 인스턴스

    Returns:
        dict: {원문: 번역} 매핑 딕셔너리
    """
    try:
        # 새로운 이벤트 루프 생성 및 실행
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                translate_batch_async_safe(
                    subjects_batch,
                    app_instance=app_instance,
                    custom_glossary_map=custom_glossary_map,
                    db_manager=db_manager,
                )
            )
        finally:
            loop.close()
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"❌ 비동기 배치 번역 실행 실패: {e}", level="ERROR"
            )
        return {}
