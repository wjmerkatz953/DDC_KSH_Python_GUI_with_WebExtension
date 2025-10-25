# -*- coding: utf-8 -*-
# Version: v1.0.1
# search_ksh_lite.py
# 수정일시: 2025-08-07 01:15 KST (KSH Pro의 데이터 추출 및 포맷팅 로직 100% 복사 완료)
# 이번 기능 수정: 2025-08-08 KST (기능 오류 수정 및 원본 주석 완벽 복원)

import requests
import json
import re
import pandas as pd
from bs4 import BeautifulSoup
import urllib.parse
import time
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import search_single_word
from collections import Counter  # ← 추가
from search_query_manager import SearchQueryManager  # ← 추가


# 국립중앙도서관 KSH 상세 검색 URL
SEARCH_KSH_BASE_URL = "https://librarian.nl.go.kr/LI/contents/L20201000000.do"
KSH_BASE_URL = "https://librarian.nl.go.kr"  # 상세 페이지 접속을 위한 기본 URL

# User-Agent 헤더 (GAS 코드와 동일)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Language": "ko,en-US;q=0.9,en;q.8",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# 캐시를 위한 딕셔너리 (간단한 인메모리 캐시)
_cache = {}


def parse_qualifiers_from_title(title):
    """
    웹에서 추출한 관계어 제목에서 수식어들을 분리

    Args:
        title (str): 웹에서 추출한 원본 제목 (예: "눈(eye)", "문학[英語]")

    Returns:
        tuple: (pure_subject, parentheses, brackets)
    """
    pure_subject = title
    parentheses = None
    brackets = None

    # 원괄호 추출: (내용)
    parentheses_match = re.search(r"\((.*?)\)", title)
    if parentheses_match:
        parentheses = parentheses_match.group(1).strip()
        pure_subject = re.sub(r"\(.*?\)", "", pure_subject).strip()

    # 각괄호 추출: [내용]
    brackets_match = re.search(r"\[(.*?)\]", title)
    if brackets_match:
        brackets = brackets_match.group(1).strip()
        pure_subject = re.sub(r"\[.*?\]", "", pure_subject).strip()

    # -------------------
    # [재수정] DB 조회 키와 일치시키기 위해 'pure_subject' 내부 공백을 제거하지 않습니다.
    # 양 끝 공백만 제거합니다. (예: " 경제 학설 " -> "경제 학설")
    pure_subject = pure_subject.strip()
    # -------------------

    return pure_subject, parentheses, brackets


def clean_subject(text):
    """
    제목 문자열에서 괄호 안의 내용(대괄호/소괄호)만 제거하고, 단어 간 공백은 유지합니다.
    """
    if not text:
        return ""

    # KSH 마크업 처리 (기존과 동일)
    if "▼a" in text and "▼0" in text:
        ksh_match = re.search(r"▼a([^▼]+)▼0", text)
        if ksh_match:
            text = ksh_match.group(1)

    # 괄호 안 내용만 제거하고, 앞뒤 공백을 정리하여 반환
    cleaned_text = re.sub(r"\[.*?\]|\(.*?\)", "", text)
    return cleaned_text.strip()


def fetch_html(url, app_instance=None):
    """
    주어진 URL에서 HTML 콘텐츠를 가져옵니다.
    GAS fetchHtml() 함수 포팅
    Args:
        url (str): HTML을 가져올 URL.
        app_instance (object, optional): GUI 애플리케이션 인스턴스 (로그용).
    Returns:
        str: HTML 콘텐츠 문자열.
    """
    if app_instance:
        app_instance.log_message(f"정보: HTML 가져오는 중: {url}", level="INFO")
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
        time.sleep(0.5)  # 500ms 지연 추가 (서버 부하 방지)
        if app_instance:
            app_instance.log_message(
                f"정보: HTML 가져오기 성공. 내용 길이: {len(response.text)}",
                level="INFO",
            )
        return response.text
    except requests.exceptions.RequestException as e:
        error_message = f"오류: HTML 가져오기 실패. URL: {url}, 오류: {e}"
        if app_instance:
            app_instance.log_message(error_message, level="ERROR")
            app_instance.show_messagebox(
                "네트워크 오류",
                f"KSH Lite 검색 중 네트워크 오류가 발생했습니다.\n\n오류: {e}",
                "error",
            )
        raise ConnectionError(error_message)


def perform_search(search_keyword, app_instance=None):
    total_start = time.time()

    processed_search_keyword = search_keyword.strip()
    if "▼a" in processed_search_keyword and "▼0" in processed_search_keyword:
        ksh_match = re.search(r"▼a([^▼]+)▼0", processed_search_keyword)
        if ksh_match:
            processed_search_keyword = ksh_match.group(1)
            if app_instance:
                app_instance.log_message(
                    f"🔍 KSH 마크업에서 순수 검색어 추출: {search_keyword} → {processed_search_keyword}",
                    level="INFO",
                )

    encoded_search_keyword = urllib.parse.quote_plus(processed_search_keyword)
    search_url = (
        f"{SEARCH_KSH_BASE_URL}?pageSize=1000&pageNum=1&kwd={encoded_search_keyword}"
    )

    if app_instance:
        app_instance.log_message(
            f'정보: 검색 페이지 가져오는 중: "{processed_search_keyword}"', level="INFO"
        )

    cleaned_search_keyword = clean_subject(processed_search_keyword)

    download_start = time.time()
    html = fetch_html(search_url, app_instance)
    if app_instance:
        app_instance.log_message(
            f"⏱️ HTML 다운로드 시간: {time.time() - download_start:.2f}초", level="INFO"
        )

    parse_start = time.time()
    soup = BeautifulSoup(html, "html.parser")

    all_results = []
    best_match = {"targetTermId": "", "mainSubjectFromList": ""}
    current_best_priority = -1

    # 집계용
    raw_block_count = len(soup.find_all("div", class_="table_bd"))
    kept_blocks = 0
    ksh_attached_count = 0
    dropped_blocks = []

    # 결과 카드 블록(보임/숨김 무관)의 termId 링크 기준으로 수집
    table_bds = soup.find_all("div", class_="table_bd")

    for block_soup in table_bds:
        try:
            # 1) 제목 행
            title_row = block_soup.find("div", class_=re.compile(r"\btit_table_row\b"))

            # 2) 링크 탐색 우선순위: 보임(post_not) → 숨김(list_not) → 블록 내 임의의 링크
            link_tag = None
            if title_row:
                link_tag = title_row.select_one(
                    'span.cont.post_not a[href*="termId="]'
                ) or title_row.select_one('span.cont.list_not a[href*="termId="]')
            if not link_tag:
                link_tag = block_soup.select_one('a[href*="termId="]')
            if not link_tag:
                dropped_blocks.append("no_link_in_block")
                continue

            href = link_tag.get("href", "")

            # 3) termId 추출 + 보정(동일 블록 내 다른 링크에서 보정 시도)
            term_id_match = re.search(r"termId=(\d+)", href)
            if not term_id_match:
                for a2 in block_soup.select('a[href*="termId="]'):
                    m2 = re.search(r"termId=(\d+)", a2.get("href", ""))
                    if m2:
                        link_tag = a2
                        term_id_match = m2
                        href = a2.get("href", "")
                        break
            term_id = term_id_match.group(1) if term_id_match else ""

            # 4) 제목(subject) 추출 폴백
            def _tx(a):
                return (a.get("title") or a.get_text(strip=True) or "").strip()

            subject = _tx(link_tag)
            if not subject and title_row:
                vis_a = title_row.select_one("span.cont.post_not a[href*='termId=']")
                if vis_a:
                    subject = _tx(vis_a)
            if not subject and title_row:
                hid_a = title_row.select_one("span.cont.list_not a[href*='termId=']")
                if hid_a:
                    subject = _tx(hid_a)
            if not subject:
                subject = f"termId={term_id or '∅'}"

            # 5) KSH 코드(숨김(list_not)에서만 부여됨)
            ksh_code = ""
            if title_row:
                for sp in title_row.select("span.cont.list_not"):
                    m = re.search(r"(KSH[0-9A-Z]+)", sp.get_text(" ", strip=True))
                    if m:
                        ksh_code = m.group(1)
                        ksh_attached_count += 1
                        break

            # 6) 우선어
            preferred_term = ""
            for row in block_soup.find_all("div", class_="post_not"):
                rmk = row.find("span", class_="remark")
                if rmk and "우선어" in rmk.get_text(strip=True):
                    cont_span = row.find("span", class_="cont")
                    if cont_span:
                        preferred_term = cont_span.get_text(strip=True)
                    break

            # 7) URL: termId가 있으면 표준 URL, 없으면 원 href를 절대경로로
            item_url = (
                f"{KSH_BASE_URL}/LI/contents/L20201000000.do?termId={term_id}"
                if term_id
                else urllib.parse.urljoin(KSH_BASE_URL, href)
            )

            all_results.append(
                {
                    "subject": subject,
                    "termId": term_id,  # 비어있을 수 있음(목록 유지 목적)
                    "url": item_url,
                    "preferredTerm": preferred_term,
                    "kshCode": ksh_code,
                    "cleanedLength": len(clean_subject(subject)),
                }
            )
            kept_blocks += 1

            # 8) best match는 상세 페이지 조회 안전성을 위해 termId 있는 항목만 참여
            cleaned_subject = clean_subject(subject)
            priority = -1
            if subject == search_keyword:
                priority = 0
            elif (
                cleaned_subject.replace(" ", "").lower()
                == cleaned_search_keyword.replace(" ", "").lower()
            ):
                priority = 1
            elif subject.startswith(search_keyword):
                priority = 2

            if priority != -1 and term_id:
                current_best_cleaned_length = (
                    len(clean_subject(best_match["mainSubjectFromList"]))
                    if best_match["mainSubjectFromList"]
                    else float("inf")
                )
                if (
                    current_best_priority == -1
                    or priority < current_best_priority
                    or (
                        priority == current_best_priority
                        and len(cleaned_subject) < current_best_cleaned_length
                    )
                ):
                    best_match = {
                        "targetTermId": term_id,
                        "mainSubjectFromList": subject,
                    }
                    current_best_priority = priority

        except Exception as e:
            dropped_blocks.append(f"exception:{e.__class__.__name__}")
            continue

    # 정렬 (기존 기준 유지)
    all_results.sort(
        key=lambda a: (
            not clean_subject(a["subject"])
            .replace(" ", "")
            .lower()
            .startswith(cleaned_search_keyword.replace(" ", "").lower()),
            len(clean_subject(a["subject"]).replace(" ", "")),
            clean_subject(a["subject"]).replace(" ", "").lower(),
        )
    )

    # ✅ 베스트매치가 비었으면 termId 있는 첫 항목으로 폴백
    if not best_match["targetTermId"]:
        first = next((r for r in all_results if r.get("termId")), None)
        if first:
            best_match = {
                "targetTermId": first["termId"],
                "mainSubjectFromList": first["subject"],
            }
    # 로그
    if app_instance:
        if kept_blocks != raw_block_count:
            app_instance.log_message(
                f"경고: kept({kept_blocks}) != raw({raw_block_count}) — 드롭 사유 점검 권장",
                level="WARNING",
            )

    if app_instance:
        app_instance.log_message(
            f"⏱️ 파싱 시간: {time.time() - parse_start:.2f}초 "
            f"(raw table_bd={raw_block_count}, kept={kept_blocks}, KSH부착={ksh_attached_count})",
            level="INFO",
        )
        if dropped_blocks:
            top3 = ", ".join(
                f"{r}×{c}" for r, c in Counter(dropped_blocks).most_common(3)
            )
            app_instance.log_message(f"디버그: 누락 사유 TOP3 → {top3}", level="DEBUG")

        app_instance.log_message(
            f"정보: 총 {len(all_results)}개의 전체 검색 결과 찾음.", level="INFO"
        )

    if app_instance:
        ksh_lite_sanity_check(html, all_results, app_instance)

    return {"allResults": all_results, "bestMatch": best_match}


def parse_detail_page(html, app_instance=None):
    """
    상세 페이지 HTML을 파싱하여 메인 KSH 코드와 우선어 제목, 그리고 관계 정보(유형, 제목, Term ID)를 추출합니다.
    GAS parseDetailPage() 함수 포팅
    Args:
        html (str): 상세 페이지의 HTML 콘텐츠.
        app_instance (object, optional): GUI 애플리케이션 인스턴스 (로그용).
    Returns:
        object: mainKSH, priorityTermTitle, relatedTerms를 포함하는 객체.
    """
    if app_instance:
        app_instance.log_message(
            "정보: 상세 페이지 HTML에서 메인 KSH, 우선어, 원시 관계어 파싱 중.",
            level="INFO",
        )
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "mainKSH": None,
        "priorityTermTitle": None,
        "relatedTerms": [],  # [type, title, termId] 형태의 배열로 저장
    }

    # title_wrap에서 표제어(우선어)와 KSH 코드 추출
    title_wrap = soup.find("div", class_="title_wrap")
    if title_wrap:
        h6_tag = title_wrap.find("h6")
        span_ksh_tag = title_wrap.find("span", string=re.compile(r"KSH[0-9A-Z]{10}"))

        if h6_tag:
            extracted_title = h6_tag.get_text(strip=True)
            if extracted_title:
                result["priorityTermTitle"] = extracted_title
            else:
                result["priorityTermTitle"] = None

        if span_ksh_tag:
            result["mainKSH"] = span_ksh_tag.get_text(strip=True)

        if app_instance:
            app_instance.log_message(
                f"정보: title_wrap에서 추출됨: 제목=\"{result['priorityTermTitle']}\", KSH=\"{result['mainKSH']}\"",
                level="INFO",
            )
    else:
        if app_instance:
            app_instance.log_message(
                "경고: title_wrap 패턴을 찾을 수 없거나 KSH가 title_wrap에 없습니다. priorityTermTitle은 null이 됩니다.",
                level="WARNING",
            )

    # 관계 정보 추출 (table_bd 블록 반복)
    relation_blocks = soup.find_all("div", class_="table_bd")
    if app_instance:
        app_instance.log_message(
            f"정보: 상세 HTML을 {len(relation_blocks)}개의 관계 블록으로 분할함.",
            level="INFO",
        )

    for block in relation_blocks:
        relation_type_span = block.find("span", class_="cont")
        relation_type = (
            relation_type_span.get_text(strip=True) if relation_type_span else ""
        )

        title_link_tag = block.find("a", href=re.compile(r"termId=\d+"))
        rel_term_id = ""
        rel_subject = ""
        if title_link_tag:
            term_id_match = re.search(r"termId=(\d+)", title_link_tag["href"])
            rel_term_id = term_id_match.group(1) if term_id_match else ""
            rel_subject = title_link_tag.get_text(strip=True)

        if relation_type and rel_term_id and rel_subject:
            result["relatedTerms"].append([relation_type, rel_subject, rel_term_id])

    if app_instance:
        app_instance.log_message(
            f"정보: 총 {len(result['relatedTerms'])}개의 원시 관계어 추출됨.",
            level="INFO",
        )
    return result


def run_ksh_lite_extraction(search_term, search_mode, app_instance=None):
    """
    주어진 검색어로 KSH 데이터를 추출합니다. (Pro/Lite 모드 및 한 글자 검색 통합)
    """
    # 1. 검색어 유효성 검사
    if not search_term or not isinstance(search_term, str) or search_term.strip() == "":
        if app_instance:
            app_instance.log_message("오류: 유효한 검색어가 없습니다.", level="ERROR")
            return pd.DataFrame()

    # 2. 한 글자 검색 처리
    if len(search_term) == 1:
        # ... (한 글자 처리 로직 - 변경 없음) ...
        if app_instance:
            app_instance.log_message(
                f"정보: '{search_term}' (한 글자)에 대한 특수 검색을 시작합니다.",
                level="INFO",
            )
        try:
            response_text = search_single_word.scrape_nl_go_kr_ajax_with_retry(
                search_term, app_instance, max_retries=3
            )
            subjects = search_single_word.parse_ajax_response_for_subjects(
                response_text, search_term
            )
            if not subjects:
                if app_instance:
                    app_instance.log_message(
                        "오류: 한 글자 검색에서 결과를 찾을 수 없습니다.", level="ERROR"
                    )
                    return pd.DataFrame()
            df = format_single_word_results_for_lite(
                subjects, app_instance, max_results=50
            )  # 50개 제한
            return df
        except Exception as e:
            if app_instance:
                app_instance.log_message(
                    f"오류: 한 글자 특수 검색 중 오류 발생: {e}", level="ERROR"
                )
                return pd.DataFrame()

    # 3. 두 글자 이상 검색 처리
    total_start_time = time.time()
    cache_key = f"KSH_SEARCH_{search_term}"
    if cache_key in _cache:
        if app_instance:
            app_instance.log_message(
                f"정보: '{search_term}'에 대한 데이터가 캐시에서 로드되었습니다.",
                level="INFO",
            )
            return _cache[cache_key]
    if app_instance:
        app_instance.update_progress(0)
        app_instance.log_message(
            f"정보: KSH 검색을 '{search_mode}' 모드로 시작합니다.", level="INFO"
        )

    # target_term_id 찾기
    target_term_id = ""
    main_subject_from_list = ""
    found_term_id = False
    global_search_results = []
    potential_keywords = [search_term]
    if " " in search_term:
        potential_keywords.append(search_term.replace(" ", ""))
    unique_potential_keywords = list(dict.fromkeys(potential_keywords))

    for p_keyword in unique_potential_keywords:
        if app_instance and app_instance.stop_search_flag.is_set():
            break
        try:
            search_result = perform_search(
                p_keyword, app_instance
            )  # HTML 목록 가져오기 및 파싱 (global_search_results 생성)
            if search_result["bestMatch"]["targetTermId"]:
                target_term_id = search_result["bestMatch"]["targetTermId"]
                main_subject_from_list = search_result["bestMatch"][
                    "mainSubjectFromList"
                ]
                found_term_id = True
                global_search_results = search_result["allResults"]
                break
        except ConnectionError:
            return pd.DataFrame()
    if not found_term_id:
        if app_instance:
            app_instance.show_messagebox(
                "검색 실패",
                f"'{search_term}'에 대한 정확히 일치하는 항목을 찾을 수 없습니다.",
                "error",
            )
            return pd.DataFrame()

    # 상세 페이지 처리 및 관계어 처리
    try:
        if app_instance:
            app_instance.update_progress(20)
        detail_url = (
            f"{KSH_BASE_URL}/LI/contents/L20201000000.do?termId={target_term_id}"
        )
        detail_html = fetch_html(detail_url, app_instance)  # 상세 HTML 가져오기
        detail_parsed = parse_detail_page(
            detail_html, app_instance
        )  # 상세 HTML 파싱 (메인 우선어/KSH/관계어 추출)
        raw_related_terms = detail_parsed["relatedTerms"]

        # 관계어 처리 (Pro/Lite 분기)
        categorized_relations_details = {}  # 초기화
        if search_mode == "Pro":
            # ... (Pro 모드 로직 - 변경 없음) ...
            app_instance.log_message(
                "정보: [Pro 모드] 로컬 DB 조회 및 웹 스크레이핑을 시작합니다.",
                level="INFO",
            )
            db_cache_start_time = time.time()
            categorized_relations_details, fetch_requests, url_to_term_data_map = (
                process_related_terms_with_db_cache(raw_related_terms, app_instance)
            )
            if app_instance:
                app_instance.log_message(
                    f"⏱️ 로컬 DB 캐시 처리 총 시간: {time.time() - db_cache_start_time:.2f}초",
                    level="INFO",
                )
            if fetch_requests:
                app_instance.log_message(
                    f"정보: [Pro 모드] {len(fetch_requests)}개 관계어 상세 정보 동시 요청 중...",
                    level="INFO",
                )
                web_fetch_start_time = time.time()
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {
                        executor.submit(fetch_html, url, app_instance): url
                        for url in fetch_requests
                    }
                    categorized_relations_details = process_web_fetched_ksh_codes(
                        futures,
                        url_to_term_data_map,
                        categorized_relations_details,
                        app_instance,
                    )
                if app_instance:
                    app_instance.log_message(
                        f"⏱️ 웹 스크레이핑 총 시간: {time.time() - web_fetch_start_time:.2f}초",
                        level="INFO",
                    )

        else:  # Lite 모드
            app_instance.log_message(
                "정보: [Lite 모드] 로컬 DB 조회만 실행합니다.", level="INFO"
            )
            db_cache_start_time = time.time()
            categorized_relations_details, _, _ = process_related_terms_with_db_cache(
                raw_related_terms, app_instance
            )  # 관계어 KSH 코드 등 조회
            if app_instance:
                app_instance.log_message(
                    f"⏱️ 로컬 DB 캐시 처리 총 시간: {time.time() - db_cache_start_time:.2f}초",
                    level="INFO",
                )

        main_priority_title = detail_parsed.get(
            "priorityTermTitle"
        )  # 메인 검색어의 우선어 (첫 행용)
        main_ksh_code = detail_parsed.get("mainKSH")  # 메인 검색어의 KSH (첫 행용)
        if app_instance:
            app_instance.update_progress(80)

        # DataFrame 생성
        headers = [
            "",
            "전체 목록 검색 결과",
            "KSH 코드",
            "우선어",
            "동의어/유사어(UF)",
            "UF (로컬)",
            "상위어",
            "BT (로컬)",
            "하위어",
            "NT (로컬)",
            "관련어",
            "RT (로컬)",
            "외국어",
            "FOREIGN (로컬)",
            "_url_data",
            "_url_uf",
            "_url_bt",
            "_url_nt",
            "_url_rt",
            "_url_foreign",
        ]

        uf_list = categorized_relations_details.get("synonyms", [])
        bt_list = categorized_relations_details.get("broader", [])
        nt_list = categorized_relations_details.get("narrower", [])
        rt_list = categorized_relations_details.get("related", [])
        foreign_list = categorized_relations_details.get("foreign", [])
        max_rows = max(
            len(global_search_results),
            len(uf_list),
            len(bt_list),
            len(nt_list),
            len(rt_list),
            len(foreign_list),
            1,
        )

        # 목록 KSH 코드 일괄 조회 (DataFrame 채우기 전 준비)
        list_subjects_with_qualifiers = []
        subject_map_for_list = {}
        preferred_terms_set = set()  # ✅ 우선어 저장용

        for item in global_search_results:
            subject = item["subject"]
            pure, paren, bracket = parse_qualifiers_from_title(subject)
            # 💡 [핵심 수정] DB 조회용 튜플과 맵핑용 튜플의 형식을 (str, str, str)로 통일합니다.
            list_subjects_with_qualifiers.append((pure, paren or "", bracket or ""))
            subject_map_for_list[subject] = (pure, paren or "", bracket or "")

            # ✅ 우선어도 조회 대상에 포함
            preferred_term = item.get("preferredTerm")
            if preferred_term and preferred_term.strip():
                preferred_terms_set.add(preferred_term)
                pure_pref, paren_pref, bracket_pref = parse_qualifiers_from_title(
                    preferred_term
                )
                # 💡 [핵심 수정] DB 조회용 튜플과 맵핑용 튜플의 형식을 (str, str, str)로 통일합니다.
                list_subjects_with_qualifiers.append(
                    (pure_pref, paren_pref or "", bracket_pref or "")
                )
                subject_map_for_list[preferred_term] = (
                    pure_pref,
                    paren_pref or "",
                    bracket_pref or "",
                )

        list_ksh_code_map = {}
        sqm = None  # SearchQueryManager 인스턴스 (아래 루프에서도 사용 가능하도록 여기서 선언)
        if hasattr(app_instance, "db_manager"):
            sqm = SearchQueryManager(app_instance.db_manager)  # 여기서 미리 생성

        if list_subjects_with_qualifiers and sqm:
            try:
                batch_results_df = sqm.get_ksh_entries_batch_exact(
                    list_subjects_with_qualifiers
                )  # 수정된 정확한 조회 함수 사용
                # -------------------
                # [로그 제거] 디버깅용 로그 삭제
                # -------------------
                if not batch_results_df.empty:
                    temp_map = {}
                    for _, row_db in batch_results_df.iterrows():
                        db_pure = row_db["pure_subject_name"]
                        db_paren = row_db["qualifier_parentheses"] or ""
                        db_bracket = row_db["qualifier_square_brackets"] or ""
                        ksh_code = row_db["ksh_code"]
                        # 💡 [핵심 수정] DB에서 반환된 'pref_label'을 사용합니다.
                        # (폴백으로 공백 제거된 db_pure 사용)
                        db_label = row_db.get("pref_label", db_pure)
                        if ksh_code:
                            markup = f"▼a{db_label}▼0{ksh_code}▲"
                        else:
                            markup = f"▼a{db_label}▲"

                        # -------------------
                        # [로그 제거] 디버깅용 로그 삭제
                        log_key = (db_pure, db_paren, db_bracket)
                        # -------------------

                        temp_map[log_key] = markup

                    for original_subject, qualifiers in subject_map_for_list.items():
                        if qualifiers in temp_map:
                            list_ksh_code_map[original_subject] = temp_map[qualifiers]
                        # -------------------
                        # [로그 제거] 디버깅용 로그 삭제
                        # -------------------
            except Exception as e:
                if app_instance:
                    app_instance.log_message(
                        f"⚠️ 목록 KSH 코드 일괄 조회 실패: {e}", level="WARNING"
                    )
        # -------------------
        # [로그 제거] 디버깅용 로그 삭제
        # -------------------
        # DataFrame 채우기 최적화: 열 단위 데이터 준비
        data_dict = {h: [""] * max_rows for h in headers}  # 모든 컬럼 초기화

        # 1. global_search_results (목록 검색 결과) 처리
        list_subjects = [item["subject"] for item in global_search_results]
        list_preferred = [item.get("preferredTerm") for item in global_search_results]
        list_urls = [item["url"] for item in global_search_results]
        num_list_results = len(list_subjects)

        data_dict["전체 목록 검색 결과"][:num_list_results] = list_subjects
        data_dict["_url_data"][:num_list_results] = list_urls

        # 2. KSH 코드 및 우선어 컬럼 채우기 (최적화된 방식)
        ksh_codes_col = [""] * max_rows
        preferred_col = [""] * max_rows

        for i in range(num_list_results):
            original_subject = list_subjects[i]
            preferred_term = list_preferred[i]
            term_for_ksh_code = preferred_term if preferred_term else original_subject

            # KSH 코드 결정
            if term_for_ksh_code in list_ksh_code_map:
                ksh_codes_col[i] = list_ksh_code_map[term_for_ksh_code]
            elif global_search_results[i].get("kshCode") and not preferred_term:
                ksh_codes_col[i] = (
                    f"▼a{original_subject}▼0{global_search_results[i]['kshCode']}▲"
                )
            else:
                ksh_codes_col[i] = f"▼a{term_for_ksh_code}▲"

            # 우선어 결정
            if i == 0:
                if main_priority_title and main_ksh_code:
                    preferred_col[i] = f"▼a{main_priority_title}▼0{main_ksh_code}▲"
                elif main_priority_title:
                    preferred_col[i] = main_priority_title
                else:
                    preferred_col[i] = ksh_codes_col[i]  # 폴백
            elif preferred_term:
                preferred_col[i] = list_ksh_code_map.get(
                    preferred_term, f"▼a{preferred_term}▲"
                )
            # else: 기본값 "" 유지

        data_dict["KSH 코드"] = ksh_codes_col
        data_dict["우선어"] = preferred_col

        # 3. 관계어 컬럼 채우기 (UF, BT, NT, RT, FOREIGN) - 리스트 슬라이싱 활용
        def fill_relation_columns(relation_list, col_web, col_local, col_url):
            count = len(relation_list)
            if count > 0:
                data_dict[col_web][:count] = [item[0] for item in relation_list]
                data_dict[col_local][:count] = [item[1] for item in relation_list]
                data_dict[col_url][:count] = [item[2] for item in relation_list]

        fill_relation_columns(uf_list, "동의어/유사어(UF)", "UF (로컬)", "_url_uf")
        fill_relation_columns(bt_list, "상위어", "BT (로컬)", "_url_bt")
        fill_relation_columns(nt_list, "하위어", "NT (로컬)", "_url_nt")
        fill_relation_columns(rt_list, "관련어", "RT (로컬)", "_url_rt")
        fill_relation_columns(foreign_list, "외국어", "FOREIGN (로컬)", "_url_foreign")

        # 4. 최종 DataFrame 생성
        df = pd.DataFrame(data_dict)
        # 로그, 캐시 저장, 반환
        if app_instance:
            app_instance.log_message(
                f"🎯 KSH '{search_mode}' 모드 전체 실행 시간: {time.time() - total_start_time:.2f}초",
                level="INFO",
            )
        _cache[cache_key] = df
        if app_instance:
            app_instance.log_message(
                f"정보: 총 {len(df)}개 항목의 KSH 데이터를 추출했습니다.", level="INFO"
            )
            app_instance.update_progress(100)
        return df

    # 예외 처리
    except Exception as e:
        error_message = f"KSH 검색 중 예기치 않은 오류 발생: {e}"
        if app_instance:
            app_instance.log_message(f"오류: {error_message}", level="ERROR")
        raise  # 상위로 예외 전달


# 파일: Search_KSH_Lite.py
def process_related_terms_with_db_cache(raw_related_terms, app_instance=None):
    """
    관계어들의 KSH 코드를 처리합니다. (DB 일괄 조회 최적화 적용)
    1. 메모리 캐시에서 먼저 확인합니다.
    2. 캐시에 없는 항목들을 모아 DB에서 '단 한 번' 일괄 조회합니다.
    """
    categorized_relations_details = {
        "synonyms": [],
        "broader": [],
        "narrower": [],
        "related": [],
        "foreign": [],
    }

    if app_instance:
        app_instance.log_message(
            "정보: 관계어 처리 중 (메모리 캐시 확인 및 DB 일괄 조회 준비)...",
            level="INFO",
        )

    # 1단계: 메모리 캐시에서 확인하고, DB 조회가 필요한 항목만 수집
    terms_to_query_db = []
    term_title_to_id_map = {}
    for term_type, title, term_id in raw_related_terms:
        # ✅ 디버깅: 모든 관계어 타입 로그 출력
        # if app_instance:
        #    app_instance.log_message(
        #        f"🔍 관계어 체크: '{title}' → 타입: '{term_type}'", level="INFO"
        #    )

        # 외국어는 DB 조회가 불필요하므로 바로 처리
        if any(
            foreign_type in term_type
            for foreign_type in [
                "영어(ENG)",
                "독일어(GER)",
                "ESP(ESP)",
                "프랑스어(FRA)",
                "일본어(JPN)",
                "중국어(CHI)",
            ]
        ):
            if app_instance:
                app_instance.log_message(
                    f"✅ 외국어 인식: '{title}' → DB 조회 제외", level="INFO"
                )
            _cache[f"KSH_CODE_{term_id}"] = None  # '없음'으로 캐시
            continue

        # 외국어가 아닌 경우 로그
        # if app_instance:
        #    app_instance.log_message(
        #        f"🔍 일반 관계어: '{title}' → DB 조회 대상", level="INFO"
        #    )

        # 캐시에 없는 항목만 DB 조회 대상으로 추가
        if f"KSH_CODE_{term_id}" not in _cache:
            if title not in term_title_to_id_map:
                terms_to_query_db.append(title)
                term_title_to_id_map[title] = term_id

    # 2단계: DB 조회가 필요한 항목들을 일괄(batch) 조회하여 성능 최적화
    if terms_to_query_db and app_instance and hasattr(app_instance, "db_manager"):
        db_manager = app_instance.db_manager

        # -------------------
        # ✅ [핵심 성능 개선] N+1 쿼리 문제를 해결하기 위해,
        # get_ksh_entries_batch_exact()를 한 번만 호출하여 모든 용어를 일괄 조회합니다.
        # 이 함수는 (pure_subject, parentheses, brackets) 튜플 리스트를 인자로 받습니다.
        # 여기서는 수식어가 없으므로 (title, None, None) 형태로 변환합니다.
        batch_query_terms = [(title, None, None) for title in terms_to_query_db]

        # ✅ [핵심 수정] SearchQueryManager를 임포트하고 인스턴스를 생성하여 메서드를 호출합니다.
        from search_query_manager import SearchQueryManager

        sqm = SearchQueryManager(db_manager)
        df_batch_results = sqm.get_ksh_entries_batch_exact(batch_query_terms)

        # 결과를 빠르게 조회할 수 있도록 {주제명: KSH코드} 맵을 생성합니다.
        # 'pure_subject_name' 컬럼이 실제 주제명을 담고 있습니다.
        if not df_batch_results.empty:
            result_map = {
                row["pure_subject_name"]: row["ksh_code"]
                for index, row in df_batch_results.iterrows()
                if "pure_subject_name" in row and "ksh_code" in row
            }
        else:
            result_map = {}

        # 일괄 조회 결과를 바탕으로 메모리 캐시(_cache)를 채웁니다.
        for title in terms_to_query_db:
            term_id = term_title_to_id_map.get(title)
            if term_id is None:
                continue

            # result_map에서 KSH 코드를 찾고, 없으면 None으로 캐시하여 불필요한 재조회를 방지합니다.
            ksh_code = result_map.get(title)
            _cache[f"KSH_CODE_{term_id}"] = ksh_code

    # 3단계: 모든 관계어를 다시 순회하며 최종 결과 생성
    for term_type, title, term_id in raw_related_terms:
        hyperlink_url = f"{KSH_BASE_URL}/LI/contents/L20201000000.do?termId={term_id}"

        # 캐시에서 KSH 코드 조회 (DB 조회 결과가 반영된 상태)
        cached_ksh_code = _cache.get(f"KSH_CODE_{term_id}")

        # 포맷팅
        if any(
            t in term_type
            for t in [
                "영어(ENG)",
                "독일어(GER)",
                "ESP(ESP)",
                "프랑스어(FRA)",
                "일본어(JPN)",
                "중국어(CHI)",
                "동의어(UF)",
            ]
        ):
            formatted_ksh_string = title
        elif cached_ksh_code:
            formatted_ksh_string = f"▼a{title}▼0{cached_ksh_code}▲"
        else:
            formatted_ksh_string = f"▼a{title}▲"

        term_details = (title, formatted_ksh_string, hyperlink_url)

        # 최종 데이터 분류
        if "동의어(UF)" in term_type:
            categorized_relations_details["synonyms"].append(term_details)
        elif "상위어(BT)" in term_type:
            categorized_relations_details["broader"].append(term_details)
        elif "하위어(NT)" in term_type:
            categorized_relations_details["narrower"].append(term_details)
        elif "관련어(RT)" in term_type:
            categorized_relations_details["related"].append(term_details)
        else:
            categorized_relations_details["foreign"].append(term_details)

    # Lite 모드이므로 fetch_requests(웹 요청 목록)는 항상 비어있음
    return categorized_relations_details, [], {}


def process_web_fetched_ksh_codes(
    futures, url_to_term_data_map, categorized_formatted_relations, app_instance=None
):
    """
    웹에서 가져온 KSH 코드들을 처리하고 로컬 DB에 저장합니다.
    (기능 수정: KSH Lite에서는 웹 스크레이핑을 수행하지 않으므로 이 함수는 비워둡니다.)
    """
    # KSH Lite에서는 관계어에 대한 웹 스크레이핑을 하지 않으므로, 이 함수의 로직은 실행되지 않습니다.
    # 기존 코드 구조를 유지하기 위해 함수 선언은 남겨두고, 적절한 반환값을 제공합니다
    return categorized_formatted_relations


def get_max_results_for_char(search_char):
    """
    특정 글자에 따른 최대 결과 개수 설정

    Args:
        search_char (str): 검색할 한 글자

    Returns:
        int: 해당 글자의 최대 결과 개수
    """
    # 매우 고빈도 글자들 (결과가 특히 많은 글자들)
    very_high_frequency = ["시", "물", "사", "문", "학", "정", "국", "대", "인", "자"]

    # 고빈도 글자들
    high_frequency = ["눈", "촉", "음", "식", "생", "경", "공", "기", "동", "서"]

    if search_char in very_high_frequency:
        return 500  # 매우 고빈도는 200개로 더 제한
    elif search_char in high_frequency:
        return 500  # 고빈도는 300개 제한
    else:
        return 500  # 일반 글자는 500개까지 허용


# Search_KSH_Lite.py 파일 하단(기존 if __name__ == "__main__": 구문 위)에 추가할 함수들:
def format_single_word_results_for_lite(subjects, app_instance=None, max_results=50):
    """
    한 글자 검색 결과를 KSH Lite와 동일한 20컬럼 구조로 변환, 로컬 DB 조회 건 수 제한 50건
    """
    if not subjects:
        return pd.DataFrame()

    # 🎯 상위 지정 개수로 제한
    if len(subjects) > max_results:
        if app_instance:
            app_instance.log_message(
                f"정보: 한 글자 검색 결과 {len(subjects)}개를 상위 {max_results}개로 제한합니다.",
                level="INFO",
            )
        subjects = subjects[:max_results]

    if app_instance:
        app_instance.log_message(
            f"정보: 한 글자 검색 결과 {len(subjects)}개를 20컬럼 구조로 변환 시작...",
            level="INFO",
        )

    # 최고 매칭 주제어 찾기 (첫 번째 항목)
    best_match = subjects[0] if subjects else None
    relations_data = {}

    if best_match and app_instance:
        try:
            # 최고 매칭 주제어의 관계어 추출
            relations_data = extract_relations_for_best_match(best_match, app_instance)
        except Exception as e:
            if app_instance:
                app_instance.log_message(
                    f"경고: 관계어 추출 중 오류: {e}", level="WARNING"
                )

    # 로컬 DB에서 KSH 코드 조회
    ksh_code_mapping = get_ksh_codes_for_single_word_subjects(subjects, app_instance)

    # ✅ KSH Lite와 동일한 컬럼 구조 사용
    headers = [
        "",
        "전체 목록 검색 결과",
        "KSH 코드",
        "우선어",
        "동의어/유사어(UF)",
        "UF (로컬)",
        "상위어",
        "BT (로컬)",
        "하위어",
        "NT (로컬)",
        "관련어",
        "RT (로컬)",
        "외국어",
        "FOREIGN (로컬)",
        "_url_data",
        "_url_uf",
        "_url_bt",
        "_url_nt",
        "_url_rt",
        "_url_foreign",
    ]

    # ✅ 관계어 리스트 추출 (올바른 형식)
    uf_list = relations_data.get("synonyms", [])
    bt_list = relations_data.get("broader", [])
    nt_list = relations_data.get("narrower", [])
    rt_list = relations_data.get("related", [])
    foreign_list = relations_data.get("foreign", [])

    # ✅ 최대 행 수 계산 (KSH Lite와 동일한 로직)
    max_rows = max(
        len(subjects),
        len(uf_list),
        len(bt_list),
        len(nt_list),
        len(rt_list),
        len(foreign_list),
        1,
    )

    if app_instance:
        app_instance.log_message(
            f"정보: {max_rows}행의 DataFrame 생성 중...", level="INFO"
        )

    output_data = []
    for i in range(max_rows):
        row = [""] * len(headers)

        # 전체 목록 검색 결과 (한 글자 검색의 주제명들)
        if i < len(subjects):
            subject_name = subjects[i]["subject"]

            # ✨ 수정: subject_url 변수를 여기서 초기화
            # .get() 메서드를 사용해 Key가 없을 경우를 방어
            subject_url = subjects[i].get("url", "")

            row[1] = subject_name  # 전체 목록 검색 결과
            # row[14] = subjects[i]['url']  # 기존 URL(ksh_code 기반)

            # ✨ 수정: termId 기반의 올바른 URL로 변경
            term_id = extract_term_id_from_single_word_url(subject_url)
            if term_id:
                # KSH 상세 페이지 URL 형식에 맞게 수정
                row[14] = f"{KSH_BASE_URL}/LI/contents/L20201000000.do?termId={term_id}"
            else:
                row[14] = subject_url  # 폴백 (기존 URL)

            # KSH 코드 (로컬 DB 조회 결과)
            if subject_name in ksh_code_mapping:
                ksh_code = ksh_code_mapping[subject_name]
                row[2] = f"▼a{subject_name}▼0{ksh_code}▲"

        # 우선어 (첫 번째 주제어만)
        if i == 0 and subjects:
            row[3] = subjects[0]["subject"]  # 첫 번째 주제어를 우선어로

        # ✅ 관계어 컬럼들 (KSH Lite와 동일한 분할 방식)
        if i < len(uf_list):
            row[4], row[5] = uf_list[i][0], uf_list[i][1]  # UF, UF (로컬)
            row[15] = uf_list[i][2]  # _url_uf
        if i < len(bt_list):
            row[6], row[7] = bt_list[i][0], bt_list[i][1]  # BT, BT (로컬)
            row[16] = bt_list[i][2]  # _url_bt
        if i < len(nt_list):
            row[8], row[9] = nt_list[i][0], nt_list[i][1]  # NT, NT (로컬)
            row[17] = nt_list[i][2]  # _url_nt
        if i < len(rt_list):
            row[10], row[11] = rt_list[i][0], rt_list[i][1]  # RT, RT (로컬)
            row[18] = rt_list[i][2]  # _url_rt
        if i < len(foreign_list):
            # FOREIGN, FOREIGN (로컬)
            row[12], row[13] = foreign_list[i][0], foreign_list[i][1]
            row[19] = foreign_list[i][2]  # _url_foreign

        output_data.append(row)

    df = pd.DataFrame(output_data, columns=headers)

    if app_instance:
        app_instance.log_message(
            f"✅ 한 글자 검색 결과 20컬럼 DataFrame 생성 완료: {len(df)}행",
            level="INFO",
        )

    return df


def extract_relations_for_best_match(best_match, app_instance=None):
    """
    첫 번째 주제어의 상세 페이지에서 관계어 추출
    KSH Lite의 기존 관계어 추출 로직 재사용

    Args:
        best_match (dict): 최고 매칭 주제어 데이터 {'subject': '', 'url': '', ...}
        app_instance: GUI 애플리케이션 인스턴스

    Returns:
        dict: 관계어 데이터 {'synonyms': [], 'broader': [], ...}
    """
    try:
        # URL에서 termId 추출
        term_id = extract_term_id_from_single_word_url(best_match["url"])
        if not term_id:
            if app_instance:
                app_instance.log_message(
                    f"경고: URL에서 termId를 추출할 수 없습니다: {best_match['url']}",
                    level="WARNING",
                )
            return initialize_empty_relations()

        # 상세 페이지 HTML 가져오기 (기존 함수 재사용)
        detail_url = f"{KSH_BASE_URL}/LI/contents/L20201000000.do?termId={term_id}"
        if app_instance:
            app_instance.log_message(
                f"정보: 상세 페이지 접근: {detail_url}", level="INFO"
            )

        detail_html = fetch_html(detail_url, app_instance)
        if not detail_html:
            return initialize_empty_relations()

        # 관계어 파싱 (기존 함수 재사용)
        detail_parsed = parse_detail_page(detail_html, app_instance)
        raw_related_terms = detail_parsed["relatedTerms"]

        if app_instance:
            app_instance.log_message(
                f"정보: {len(raw_related_terms)}개의 관계어를 발견했습니다.",
                level="INFO",
            )

        # Lite 모드로 관계어 처리 (기존 함수 재사용)
        categorized_relations_details, _, _ = process_related_terms_with_db_cache(
            raw_related_terms, app_instance
        )

        return categorized_relations_details

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 관계어 추출 중 오류 발생: {e}", level="ERROR"
            )
        return initialize_empty_relations()


def get_ksh_codes_for_single_word_subjects(subjects, app_instance=None):
    """
    한 글자 검색 결과의 모든 주제어에 대해 로컬 DB에서 KSH 코드 조회
    KSH Lite의 복합 인덱스 조회 로직을 완전히 재사용

    Args:
        subjects (list): 한 글자 검색 주제어 리스트
        app_instance: GUI 애플리케이션 인스턴스

    Returns:
        dict: {subject_name: ksh_code} 매핑
    """
    if not subjects or not app_instance or not hasattr(app_instance, "db_manager"):
        return {}

    # 1. 수식어 분리 (기존 함수 재사용)
    terms_with_qualifiers = []
    subject_to_qualifiers_map = {}

    for subject_data in subjects:
        subject_name = subject_data["subject"]  # "물리학", "물리학(교육)" 등
        pure, paren, bracket = parse_qualifiers_from_title(subject_name)
        terms_with_qualifiers.append((pure, paren, bracket))
        subject_to_qualifiers_map[subject_name] = (pure, paren, bracket)

    if app_instance:
        app_instance.log_message(
            f"정보: {len(terms_with_qualifiers)}개 주제어의 로컬 DB KSH 코드 조회 시작...",
            level="INFO",
        )

    # 2. 일괄 로컬 DB 조회 (기존 함수 완전 재사용)
    sqm = SearchQueryManager(app_instance.db_manager)
    db_results_df = sqm.get_ksh_entries_batch_exact(terms_with_qualifiers)

    # 3. 결과 매핑 생성
    ksh_codes_mapping = {}
    for _, row in db_results_df.iterrows():
        db_pure = row["pure_subject_name"]
        db_parentheses = row.get("qualifier_parentheses", "") or ""
        db_brackets = row.get("qualifier_square_brackets", "") or ""

        # 원본 subject와 매칭되는 항목 찾기
        for subject_name, (pure, paren, bracket) in subject_to_qualifiers_map.items():
            if (
                db_pure == pure
                and (db_parentheses or "") == (paren or "")
                and (db_brackets or "") == (bracket or "")
            ):

                ksh_codes_mapping[subject_name] = row["ksh_code"]
                if app_instance:
                    qualifier_info = ""
                    if paren:
                        qualifier_info += f"({paren})"
                    if bracket:
                        qualifier_info += f"[{bracket}]"
                    app_instance.log_message(
                        f"✅ KSH 코드 매칭: {pure}{qualifier_info} → {row['ksh_code']}",
                        level="INFO",
                    )
                break

    if app_instance:
        app_instance.log_message(
            f"정보: 로컬 DB에서 {len(ksh_codes_mapping)}개의 KSH 코드를 찾았습니다.",
            level="INFO",
        )

    return ksh_codes_mapping


def build_single_word_20_column_dataframe(
    subjects, ksh_codes_mapping, relation_data, app_instance=None
):
    """
    한 글자 검색 결과를 KSH Lite와 동일한 20컬럼 구조로 DataFrame 생성

    Args:
        subjects (list): 한 글자 검색 주제어 리스트
        ksh_codes_mapping (dict): {subject_name: ksh_code} 매핑
        relation_data (dict): 관계어 데이터
        app_instance: GUI 애플리케이션 인스턴스

    Returns:
        pd.DataFrame: 20컬럼 구조의 DataFrame
    """
    # KSH Lite와 동일한 컬럼 구조
    headers = [
        "",
        "전체 목록 검색 결과",
        "KSH 코드",
        "우선어",
        "동의어/유사어(UF)",
        "UF (로컬)",
        "상위어",
        "BT (로컬)",
        "하위어",
        "NT (로컬)",
        "관련어",
        "RT (로컬)",
        "외국어",
        "FOREIGN (로컬)",
        "_url_data",
        "_url_uf",
        "_url_bt",
        "_url_nt",
        "_url_rt",
        "_url_foreign",
    ]

    # 관계어 리스트 추출
    uf_list = relation_data.get("synonyms", [])
    bt_list = relation_data.get("broader", [])
    nt_list = relation_data.get("narrower", [])
    rt_list = relation_data.get("related", [])
    foreign_list = relation_data.get("foreign", [])

    # 최대 행 수 계산
    max_rows = max(
        len(subjects),
        len(uf_list),
        len(bt_list),
        len(nt_list),
        len(rt_list),
        len(foreign_list),
        1,
    )

    if app_instance:
        app_instance.log_message(
            f"정보: {max_rows}행의 DataFrame 생성 중...", level="INFO"
        )

    output_data = []
    for i in range(max_rows):
        row = [""] * len(headers)

        # 전체 목록 검색 결과 (한 글자 검색의 주제명들)
        if i < len(subjects):
            subject_name = subjects[i]["subject"]
            row[1] = subject_name  # 전체 목록 검색 결과
            row[14] = subjects[i]["url"]  # _url_data

            # KSH 코드 (로컬 DB 조회 결과)
            if subject_name in ksh_codes_mapping:
                ksh_code = ksh_codes_mapping[subject_name]
                row[2] = f"▼a{subject_name}▼0{ksh_code}▲"

        # 우선어 (첫 번째 주제어만)
        if i == 0 and subjects:
            row[3] = subjects[0]["subject"]  # 첫 번째 주제어를 우선어로

        # 관계어 컬럼들 (첫 번째 주제어의 관계어만)
        if i < len(uf_list):
            row[4], row[5] = uf_list[i][0], uf_list[i][1]  # UF, UF (로컬)
            row[15] = uf_list[i][2]  # _url_uf
        if i < len(bt_list):
            row[6], row[7] = bt_list[i][0], bt_list[i][1]  # BT, BT (로컬)
            row[16] = bt_list[i][2]  # _url_bt
        if i < len(nt_list):
            row[8], row[9] = nt_list[i][0], nt_list[i][1]  # NT, NT (로컬)
            row[17] = nt_list[i][2]  # _url_nt
        if i < len(rt_list):
            row[10], row[11] = rt_list[i][0], rt_list[i][1]  # RT, RT (로컬)
            row[18] = rt_list[i][2]  # _url_rt
        if i < len(foreign_list):
            # FOREIGN, FOREIGN (로컬)
            row[12], row[13] = foreign_list[i][0], foreign_list[i][1]
            row[19] = foreign_list[i][2]  # _url_foreign

        output_data.append(row)

    df = pd.DataFrame(output_data, columns=headers)

    if app_instance:
        app_instance.log_message(
            f"✅ 한 글자 검색 결과 20컬럼 DataFrame 생성 완료: {len(df)}행",
            level="INFO",
        )

    return df


def extract_term_id_from_single_word_url(url):
    """
    한 글자 검색 URL에서 termId 추출
    예: "https://librarian.nl.go.kr/LI/contents/L20201000000.do?termId=KSH0000173522" → "173522"

    Args:
        url (str): 한 글자 검색 결과 URL

    Returns:
        str: 추출된 termId (숫자만) 또는 None
    """
    if not url or "termId=" not in url:
        return None

    try:
        # termId=KSH0000173522 형태에서 숫자 부분만 추출
        term_id_part = url.split("termId=")[-1]
        # KSH 부분 제거하고 숫자만 추출
        numeric_id = "".join(filter(str.isdigit, term_id_part))
        return numeric_id if numeric_id else None
    except Exception:
        return None


def initialize_empty_relations():
    """
    빈 관계어 데이터 구조 초기화

    Returns:
        dict: 빈 관계어 딕셔너리
    """
    return {"synonyms": [], "broader": [], "narrower": [], "related": [], "foreign": []}


def ksh_lite_sanity_check(html, results, app_instance=None):
    from bs4 import BeautifulSoup
    import re

    soup = BeautifulSoup(html, "html.parser")
    all_a = soup.select('a[href*="termId="]')
    # table_bd 내의 가시 링크만 카운트(= 우리가 실제로 쓰는 기준)
    visible_links = soup.select('span.cont.post_not a[href*="termId="]')
    parsed_subjects = {r["subject"] for r in results}
    page_subjects = set()
    for a in visible_links:
        t = (a.get("title") or a.get_text(strip=True) or "").strip()
        page_subjects.add(t)

    missing = sorted(list(page_subjects - parsed_subjects))
    extra = sorted(list(parsed_subjects - page_subjects))

    if app_instance:
        app_instance.log_message(
            f"[검증] 페이지 내 termId 링크: 전체 {len(all_a)} / 가시 {len(visible_links)} / 파싱 {len(results)}",
            level="INFO",
        )
        if missing:
            app_instance.log_message(
                f"[검증] 파싱 누락 {len(missing)}개 → {missing[:5]}...", level="WARNING"
            )
        if extra:
            app_instance.log_message(
                f"[검증] 페이지에 없는데 파싱됨 {len(extra)}개 → {extra[:5]}...",
                level="WARNING",
            )
        if not missing and not extra:
            app_instance.log_message(
                "[검증] 파싱 결과와 페이지가 완벽 일치 ✅", level="INFO"
            )


if __name__ == "__main__":
    print("KSH Lite Search Logic Module")
    # 예시: '양초'
    # df = run_ksh_lite_extraction("양초")
    # if not df.empty:
    #     print(df.head())
    # else:
    #     print("데이터를 찾을 수 없거나 오류가 발생했습니다.")
