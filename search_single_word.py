# =====================================
# 파일: search_single_word.py
# 함수 순서 수정 (올바른 순서)
# =====================================

# -*- coding: utf-8 -*-
# Version: v1.0.0
# 수정일시: 2025-08-03 01:19 KST (한 글자 검색 로직 분리)

import requests
import re
import time
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# 상세 페이지 접속을 위한 기본 URL
SINGLE_WORD_BASE_URL = "https://librarian.nl.go.kr"


def scrape_nl_go_kr_ajax(search_term, app_instance=None):
    """
    ✅ 1. 먼저 기본 함수를 정의 (30초 타임아웃)

    librarian.nl.go.kr의 AJAX 엔드포인트에 POST 요청을 보내 데이터를 스크레이핑하는 함수입니다.
    이 함수는 먼저 메인 페이지에 GET 요청을 보내 유효한 쿠키를 획득한 후,
    requests 세션의 자동 쿠키 관리에 의존하여 AJAX POST 요청을 보냅니다.

    Args:
        search_term (str): 검색할 주제어 (예: "물", "레시피")
        app_instance: IntegratedSearchApp 클래스 인스턴스 (로그 메시지 출력을 위함).
    Returns:
        str or None: 서버로부터 받은 응답 텍스트 (일반적으로 HTML 또는 JSON) 또는 오류 발생 시 None.
    """
    main_page_url = "https://librarian.nl.go.kr/LI/contents/L20202000000.do"  # 주제명 브라우징 페이지
    ajax_url = "https://librarian.nl.go.kr/LI/module/isni/subjectList1depth.ajax"

    session = requests.Session()

    # 1. 메인 페이지에 GET 요청을 보내 쿠키 획득 (requests 세션이 내부적으로 쿠키를 관리하도록 함)
    try:
        if app_instance:
            app_instance.log_message(
                "  [scrape_nl_go_kr_ajax] 메인 페이지에 GET 요청을 보내 쿠키를 얻는 중 (자동 관리).."
            )
        main_page_response = session.get(
            main_page_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br, zstd",
            },
            timeout=30,
        )  # ✅ 30초 타임아웃
        if app_instance:
            app_instance.log_message(
                f"  [scrape_nl_go_kr_ajax] 메인 페이지 응답 코드: {main_page_response.status_code}"
            )
    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"  [scrape_nl_go_kr_ajax] 메인 페이지 요청 중 오류 발생 (쿠키 획득 시도): {e}",
                level="ERROR",
            )
        # 오류 발생해도 다음 단계 진행 (쿠키 없이 시도)

    if app_instance:
        app_instance.log_message(
            f'  [scrape_nl_go_kr_ajax] 실제 검색어: "{search_term}" (타입: {type(search_term)})'
        )

    # POST 요청 본문에 포함될 데이터 (kwd만 포함)
    payload = {"kwd": search_term}  # 실제 전달받은 search_term 사용

    # HTTP 헤더 설정
    headers = {
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://librarian.nl.go.kr",
        "Referer": "https://librarian.nl.go.kr/LI/contents/L20202000000.do",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Accept-Encoding": "gzip, deflate, br, zstd",
    }

    try:
        if app_instance:
            app_instance.log_message(
                f"  [scrape_nl_go_kr_ajax] AJAX POST 요청 URL: {ajax_url}"
            )
        response = session.post(
            ajax_url, data=payload, headers=headers, timeout=30
        )  # ✅ 30초 타임아웃
        response.raise_for_status()  # 200 이외의 응답 코드에 대해 예외 발생

        response_text = response.text

        if app_instance:
            app_instance.log_message(
                "  [scrape_nl_go_kr_ajax] AJAX POST 요청 성공. 응답 길이: "
                + str(len(response_text))
            )
        return response_text

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"  [scrape_nl_go_kr_ajax] 스크레이핑 중 오류 발생: {e}", level="ERROR"
            )
        raise e
    finally:
        session.close()


def scrape_nl_go_kr_ajax_with_retry(search_term, app_instance=None, max_retries=3):
    """
    재시도 로직이 포함된 AJAX 스크레이핑 함수

    Args:
        search_term (str): 검색할 주제어
        app_instance: 앱 인스턴스
        max_retries (int): 최대 재시도 횟수 (기본값: 3)

    Returns:
        str or None: 응답 텍스트 또는 None
    """
    for attempt in range(max_retries):
        try:
            # 기본 함수 호출
            return scrape_nl_go_kr_ajax(search_term, app_instance)
        except Exception as e:
            if attempt < max_retries - 1:
                if app_instance:
                    app_instance.log_message(
                        f"  [재시도 {attempt + 1}/{max_retries}] 오류: {e}",
                        level="WARNING",
                    )
                    app_instance.log_message(
                        f"  [재시도] 5초 후 다시 시도합니다...", level="INFO"
                    )
                time.sleep(5)
                continue
            else:
                raise e
    return None


def strip_html_tags_and_trim(html_string):
    """
    HTML 내용에서 태그를 제거하고 공백을 정리하는 헬퍼 함수.
    Args:
        html_string (str): HTML 문자열
    Returns:
        str: 정리된 텍스트
    """
    if not html_string:
        return ""
    # 정규식을 사용하여 HTML 태그 제거
    text = re.sub(r"<[^>]*>", "", html_string)
    # 연속된 공백을 단일 공백으로 변환하고 앞뒤 공백 제거
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_ajax_response_for_subjects(html, search_term=""):
    """
    AJAX 응답 HTML에서 주제어 목록과 해당 URL을 파싱합니다.
    이 함수는 librarian.nl.go.kr/LI/module/isni/subjectList1depth.ajax 응답 구조에 맞춰져 있습니다.

    Args:
        html (str): AJAX 응답으로 받은 HTML 문자열.
        search_term (str): 검색어 (정렬 우선순위 결정용)
    Returns:
        list: 각 객체는 { subject: str, url: str, sort_key: str, sort_length: int, is_empty: bool, relevance_score: int } 형태입니다.
    """
    subjects = []

    # onclick 방식의 링크를 파싱하는 정규식
    # <a href="#none" onclick="goSubject2depthList(this,'173522');return false;">가는눈</a>
    regex = re.compile(
        r'<a href="#none" onclick="goSubject2depthList\(this,\'(\d+)\'\);return false;">([^<]+)</a>'
    )

    for match in regex.finditer(html):
        term_id = match.group(1)  # 예: 173522
        original_subject = match.group(2)  # 원본 주제어 (괄호 포함)

        # 정렬용: 괄호 안의 내용 제거 (원괄호, 각괄호 모두)
        cleaned_for_sort = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", original_subject).strip()

        # 상세 페이지 URL 구성 (termId 기반)
        # KSH 뒤에 0을 10자리로 채워야 함.
        # 예: KSH0000000001
        full_url = f"{SINGLE_WORD_BASE_URL}/LI/contents/L20201000000.do?termId=KSH{term_id.zfill(10)}"

        # 괄호만 있고 실제 내용이 없는 항목인지 확인
        is_empty = cleaned_for_sort == ""

        # 검색어 관련도 계산 (검색어가 있을 때만)
        relevance_score = 5  # 기본값: 관련 없음 (가장 낮은 우선순위)
        if search_term and not is_empty:
            if cleaned_for_sort == search_term:
                relevance_score = 1  # 최우선: 완전 일치
            elif cleaned_for_sort.startswith(search_term):
                relevance_score = 2  # 2순위: 검색어로 시작
            elif search_term in cleaned_for_sort:
                relevance_score = 3  # 3순위: 검색어 포함
            elif search_term in original_subject:
                relevance_score = 4  # 4순위: 괄호 안에만 검색어 있음

        subjects.append(
            {
                "subject": original_subject,  # 실제 출력용: 원본 그대로 (괄호 포함)
                "url": full_url,
                "sort_key": cleaned_for_sort,  # 정렬용: 괄호 제거
                "sort_length": len(cleaned_for_sort),  # 정렬을 위한 글자수
                "is_empty": is_empty,  # 빈 항목 여부
                "relevance_score": relevance_score,  # 검색어 관련도 점수
            }
        )

    # 정렬: 빈 항목 → 관련도 → 글자수 → 가나다순
    subjects.sort(
        key=lambda x: (
            x["is_empty"],  # True (빈 항목)가 뒤로
            x["relevance_score"],  # 점수가 낮을수록 우선 (1이 최고)
            x["sort_length"],  # 글자수 비교 (짧은 것이 먼저)
            x["sort_key"],  # 가나다순
        )
    )

    return subjects


def run_single_word_search(search_term, app_instance=None):
    """
    주어진 검색어로 국립중앙도서관 웹사이트에서 한 글자 주제명 데이터를 추출합니다.
    Args:
        search_term (str): 검색할 한 글자 주제명.
        app_instance (object, optional): GUI 애플리케이션 인스턴스 (로그 및 진행도 업데이트용).
    Returns:
        pd.DataFrame: 추출된 주제명 데이터가 담긴 DataFrame.
    """
    if not search_term or not isinstance(search_term, str) or search_term.strip() == "":
        if app_instance:
            app_instance.log_message("오류: 유효한 검색어가 없습니다.", level="ERROR")
        return pd.DataFrame()

    if app_instance:
        app_instance.log_message(
            f"정보: 검색어 '{search_term}'로 한 글자 주제명 데이터 추출 시작...",
            level="INFO",
        )
        app_instance.update_progress(0)

    try:
        html_response = scrape_nl_go_kr_ajax(search_term, app_instance)
        if not html_response:
            return pd.DataFrame()

        subjects = parse_ajax_response_for_subjects(html_response, search_term)

        if subjects:
            df = pd.DataFrame(subjects)
            if app_instance:
                app_instance.log_message(
                    f"정보: 총 {len(df)}개의 한 글자 주제명 데이터를 추출했습니다.",
                    level="INFO",
                )
                app_instance.update_progress(100)
            return df
        else:
            if app_instance:
                app_instance.log_message(
                    f"정보: '{search_term}'에 대한 한 글자 주제명 검색 결과가 없습니다.",
                    level="INFO",
                )
            return pd.DataFrame()

    except Exception as e:
        error_message = f"한 글자 주제명 검색 중 예기치 않은 오류 발생: {e}"
        if app_instance:
            app_instance.log_message(f"오류: {error_message}", level="ERROR")
            app_instance.show_messagebox(
                "한 글자 주제명 검색 오류",
                f"한 글자 주제명 검색 중 예기치 않은 오류가 발생했습니다.\n\n오류: {e}",
                "error",
            )
        return pd.DataFrame()
    finally:
        if app_instance:
            app_instance.update_progress(100)
