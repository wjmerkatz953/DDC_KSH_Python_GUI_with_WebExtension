# -*- coding: utf-8 -*-
# Version: v1.0.0
# 생성일시: 2025-08-10 KST (GAS 네이버 API 로직을 파이썬으로 포팅)
# 수정일시: 2025-09-17 KST
"""
Search_Naver.py - 네이버 검색을 위한 하이브리드 도서 정보 수집 모듈

이 모듈은 네이버 책 API와 웹 스크레이핑을 결합하여 도서 정보를 검색하고 보강하는 로직을 포함합니다.
주요 기능은 다음과 같습니다:
1.  **하이브리드 검색**:
    - 네이버 책 API를 통해 ISBN, 제목, 저자 등 다양한 조건으로 기본 정보를 빠르게 조회합니다.
    - API 결과만으로는 부족한 상세 정보(저자 소개, 목차, 출판사 서평, 다른 작품 목록 등)를 얻기 위해, `requests`와 `BeautifulSoup`를 사용하여 Yes24와 교보문고의 도서 상세 페이지를 실시간으로 스크레이핑합니다.

2.  **데이터 보강 및 병합**:
    - ISBN 검색 시, 병렬 스레드(`threading`)를 이용해 Yes24와 교보문고 스크레이핑을 동시에 수행하여 응답 시간을 단축합니다.
    - 각 소스(Naver, Yes24, Kyobo)에서 수집된 정보를 바탕으로 'AI-Feed Merge', 'OtherWorks Merge' 등 여러 버전의 가공된 결과 레코드를 생성하여, 사용 목적에 맞는 풍부한 데이터를 제공합니다.

3.  **유틸리티 함수**:
    - 저자 소개 텍스트에서 다른 저작물 목록을 추출하고 정규화하는(`extract_other_works_grouped`) 기능을 포함합니다.

GAS(Google Apps Script)의 `fetchNaverBookInfo` 함수를 파이썬으로 포팅한 것을 시작으로, 현재는 훨씬 더 고도화된 데이터 수집 및 처리 기능을 수행하도록 확장되었습니다.
"""
import requests
import xml.etree.ElementTree as ET
import re
import time
import urllib.parse
import threading  # ✅ [추가] 병렬 처리를 위해 threading 모듈을 임포트합니다.
from bs4 import BeautifulSoup  # ✅ 새로 추가
from qt_api_clients import clean_text
from database_manager import DatabaseManager

import re as _re
import unicodedata as _ud

# ✅ [추가] PyInstaller 환경에서 SSL 인증서 경로 설정
from ssl_cert_utils import configure_ssl_certificates

configure_ssl_certificates()

_MEDIA_STOPWORDS = (
    "뉴욕 타임스",
    "뉴욕타임스",
    "워싱턴포스트",
    "로스앤젤레스 타임스",
    "허핑턴 포스트",
    "커커스 리뷰",
    "피플",
    "유에스 위클리",
    "타임",
    "LA 타임스",
    "Washington Post",
    "New York Times",
    "Huffington Post",
    "Kirkus Reviews",
    "People",
    "Us Weekly",
    "TIME",
    "조선일보",
    "중앙일보",
    "한겨레",
    "경향신문",
    "동아일보",
)

_EDGE_QUOTES_RE = _re.compile(r'^[《〈<«≪『「“"\']+|[》〉>»≫』」”"\']+$')
_TAIL_PAREN_RE = _re.compile(
    r"[\(\[\{（［｛〔【][^)\]\}）］｝〕】]*[\)\]\}）］｝〕】]\s*$"
)


def normalize_title_for_match(s: str) -> str:
    t = _ud.normalize("NFKC", (s or "").strip())
    # 양끝 인용/꺾쇠 제거 반복
    prev = None
    while prev != t:
        prev = t
        t = _EDGE_QUOTES_RE.sub("", t).strip()
    # 말미 괄호 꼬리 반복 제거
    while _TAIL_PAREN_RE.search(t):
        t = _TAIL_PAREN_RE.sub("", t).strip()
    # 공백 축소
    t = _re.sub(r"\s{2,}", " ", t)
    return t


def combine_author_bios(*bios: str) -> str:
    parts = [b.strip() for b in bios if b and b.strip()]
    return "\n\n".join(parts)


def extract_other_works_from_author_bio(
    author_bio: str, current_title: str
) -> list[str]:
    """
    - 예스24/교보 저자소개를 합친 본문에서 인용부호 내 서명만 추출
    - 매체/언론사명 필터링
    - 쉼표/중점 분해
    """
    if not author_bio:
        return []
    cur = normalize_title_for_match(current_title)

    # 인용부호 내부 캡처
    pat = _re.compile(r'[《〈<«≪『「“"\']\s*(.+?)\s*[》〉>»≫』」”"\']')
    cand = [m.group(1).strip() for m in pat.finditer(author_bio)]

    # 나열 분해
    spread = []
    for c in cand:
        if ("·" in c) or ("," in c) or ("，" in c):
            spread.extend([x.strip() for x in _re.split(r"[，,·]", c) if x.strip()])
        else:
            spread.append(c)

    # 정규화 + 필터
    seen, out = set(), []
    for t in spread:
        # 괄호 속 영문 원제 보존 (예: (The Seven Husbands of Evelyn Hugo))
        m = _re.search(r"[\(（]([^)）]+)[\)）]", t)
        original_eng = f"({m.group(1).strip()})" if m else ""

        n = normalize_title_for_match(t)
        if not n or len(n) < 2 or len(n) > 120:  # ← 80 → 120
            continue
        if n == cur:
            continue
        # 매체 필터는 '제목'에만 적용 (원서명 조각엔 적용 X)
        if any(sw in n for sw in _MEDIA_STOPWORDS):
            continue
        if _re.search(r"(리뷰|타임스|포스트|위클리)\s*$", n):
            continue

        # 표시용 제목: 정규화된 한글표제 + (원서명) 병기
        display_title = (
            f"{n}{original_eng}" if original_eng and original_eng not in n else n
        )

        if display_title not in seen:
            seen.add(display_title)
            out.append(display_title)

    return out  # ✅ 누락된 반환 추가


def extract_other_works_grouped(
    author_bio_blocks: list[str], current_title: str
) -> list[dict]:
    """
    author_bio_blocks: 저자별 소개 텍스트 리스트 (예스24/교보 합본)
    return: [{"author_label": "저자1", "works": [{"title": "번역서명", "orig": "원서명 or ''"}, ...]}, ...]
    """
    groups = []
    for idx, bio in enumerate(author_bio_blocks or []):
        works = []
        # 기존 단일 추출 로직 재사용(원서명 병기 유지)
        # cand/spread 계산
        pat = _re.compile(r'[《〈<«≪『「“"\']\s*(.+?)\s*[》〉>»≫』」”"\']')
        cand = [m.group(1).strip() for m in pat.finditer(bio)]
        spread = []
        for c in cand:
            if ("·" in c) or ("," in c) or ("，" in c):
                spread.extend([x.strip() for x in _re.split(r"[，,·]", c) if x.strip()])
            else:
                spread.append(c)

        seen = set()
        for t in spread:
            # 괄호 속 원제(영문/기타) 추출 → 괄호 제거본을 orig로 사용
            m = _re.search(r"[\(（]([^)）]+)[\)）]", t)
            orig = m.group(1).strip() if m else ""
            normalized = normalize_title_for_match(t)
            if not normalized or len(normalized) < 2 or len(normalized) > 120:
                continue
            if normalized == normalize_title_for_match(current_title):
                continue
            if any(sw in normalized for sw in _MEDIA_STOPWORDS):
                continue
            if _re.search(r"(리뷰|타임스|포스트|위클리)\s*$", normalized):
                continue

            # 표시는 번역서명(정규화 결과)
            display_title = normalized
            key = (display_title, orig)
            if key in seen:
                continue
            seen.add(key)
            works.append({"title": display_title, "orig": orig})

        groups.append({"author_label": f"저자{idx+1}", "works": works})
    return groups


def render_other_works_grouped(
    groups: list[dict], author_names: list[str] | None = None
) -> str:
    """
    groups: extract_other_works_grouped() 결과
    author_names: 저자명 리스트(가능하면 사용), 없으면 groups의 author_label 사용
    """
    lines = ["4. 다른 작품", ""]
    for i, g in enumerate(groups):
        header = (
            author_names[i].strip()
            if author_names and i < len(author_names) and author_names[i].strip()
            else g.get("author_label", f"저자{i+1}")
        )
        if not g.get("works"):
            continue

        # ✅ 저자 헤더를 명확히 강조 (CTk TextBrowser용)
        lines.append(f"――――――――――――――――――――――――――――――――――――")
        lines.append(header)
        lines.append("")

        for w in g["works"]:
            lines.append(w["title"])
            if w.get("orig"):  # 원서 제목은 괄호 없이 바로 아래 행
                lines.append(w["orig"])

        # ✅ 저자 블록 사이에 구분용 빈 줄 2줄
        lines.extend(["", ""])

    # 마지막 공백 정리
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


def get_naver_api_credentials(db_manager):
    """
    데이터베이스에서 네이버 API 클라이언트 ID와 시크릿을 가져옵니다.
    GAS getNaverApiCredentialsInternal() 함수 포팅

    Args:
        db_manager (DatabaseManager): 데이터베이스 매니저 인스턴스

    Returns:
        tuple: (client_id, client_secret) 또는 (None, None) if not found
    """
    try:
        return db_manager.get_naver_api_credentials()
    except Exception as e:
        print(f"오류: 네이버 API 인증 정보 조회 실패: {e}")
        return None, None


def search_naver_catalog(
    title_query, author_query, isbn_query, app_instance=None, db_manager=None
):
    """
    네이버 책 API를 사용하여 제목, 저자, ISBN으로 도서 정보를 검색합니다.
    GAS fetchNaverBookInfo() 함수를 파이썬으로 포팅하여 다중 검색 조건 지원

    Args:
        title_query (str): 검색할 책 제목
        author_query (str): 검색할 저자명
        isbn_query (str): 검색할 ISBN
        app_instance (object, optional): GUI 애플리케이션 인스턴스 (로그용)
        db_manager (DatabaseManager, optional): 데이터베이스 매니저 인스턴스

    Returns:
        list: 검색 결과 레코드 목록. 각 레코드는 딕셔너리 형태
    """
    # 검색어 유효성 검사
    if not any([title_query, author_query, isbn_query]):
        if app_instance:
            app_instance.log_message(
                "경고: 제목, 저자, ISBN 중 하나 이상을 입력해주세요.", level="WARNING"
            )
        return []

    if not db_manager:
        if app_instance:
            app_instance.log_message(
                "오류: DatabaseManager 인스턴스가 필요합니다.", level="ERROR"
            )
        return []

    if app_instance:
        search_info = (
            f"제목='{title_query}', 저자='{author_query}', ISBN='{isbn_query}'"
        )
        app_instance.log_message(f"정보: 네이버 책 API 검색 시작 ({search_info})")
        app_instance.update_progress(10)

    # 네이버 API 인증 정보 가져오기
    client_id, client_secret = get_naver_api_credentials(db_manager)
    if not client_id or not client_secret:
        if app_instance:
            app_instance.log_message(
                "오류: 네이버 API 클라이언트 ID 또는 시크릿이 설정되지 않았습니다. 설정 탭에서 API 키를 입력해주세요.",
                level="ERROR",
            )
        return []

    # 검색 쿼리 생성 (우선순위: ISBN > 제목+저자 > 제목 > 저자)
    if isbn_query:
        # ISBN 검색 (가장 정확함)
        api_url = (
            f"https://openapi.naver.com/v1/search/book_adv.xml?d_isbn={isbn_query}"
        )
        search_type = "ISBN 검색"
        primary_query = isbn_query
    elif title_query and author_query:
        # 제목 + 저자 조합 검색
        query = f"{title_query} {author_query}"
        api_url = f"https://openapi.naver.com/v1/search/book.xml?query={requests.utils.quote(query)}&display=100"
        search_type = "제목+저자 검색"
        primary_query = query
    elif title_query:
        # 제목만 검색
        api_url = f"https://openapi.naver.com/v1/search/book.xml?query={requests.utils.quote(title_query)}&display=100"
        search_type = "제목 검색"
        primary_query = title_query
    elif author_query:
        # 저자만 검색
        api_url = f"https://openapi.naver.com/v1/search/book.xml?query={requests.utils.quote(author_query)}&display=100"
        search_type = "저자 검색"
        primary_query = author_query
    else:
        return []

    if app_instance:
        app_instance.log_message(f"정보: 네이버 API 요청 URL: {api_url}")
        app_instance.update_progress(30)

    # API 요청 헤더 설정
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    # 기본값 설정
    results = []

    try:
        # API 호출
        response = requests.get(api_url, headers=headers, timeout=10)
        response_code = response.status_code
        response_text = response.text

        if app_instance:
            app_instance.log_message(f"정보: 네이버 API 응답 코드: {response_code}")
            app_instance.update_progress(60)

        if response_code == 200:
            try:
                # XML 파싱 (GAS 코드와 동일한 구조)
                root = ET.fromstring(response_text)
                channel = root.find("channel")

                if channel is not None:
                    items = channel.findall("item")

                    if items:
                        for item in items:
                            # 각 항목에서 정보 추출 (HTML 태그 제거)
                            title = clean_text(item.findtext("title", "정보 없음"))
                            author = clean_text(item.findtext("author", "정보 없음"))
                            publisher = clean_text(
                                item.findtext("publisher", "정보 없음")
                            )
                            pubdate = clean_text(item.findtext("pubdate", "정보 없음"))
                            isbn = clean_text(item.findtext("isbn", "정보 없음"))
                            price = clean_text(item.findtext("price", "정보 없음"))
                            description = clean_text(
                                item.findtext("description", "정보 없음")
                            )
                            link = item.findtext("link", "")

                            # 가격 포맷팅
                            if price and price != "정보 없음" and price.isdigit():
                                price = f"{int(price):,}원"

                            # 출간일 포맷팅 (YYYYMMDD → YYYY-MM-DD)
                            if (
                                pubdate
                                and pubdate != "정보 없음"
                                and len(pubdate) == 8
                                and pubdate.isdigit()
                            ):
                                pubdate = f"{pubdate[:4]}-{pubdate[4:6]}-{pubdate[6:8]}"

                            # ✅ 1. 네이버 API 기본 결과
                            naver_record = {
                                "검색소스": "Naver",
                                "서명": title,
                                "저자": author,
                                "분류 정보 취합": description,
                                "저자소개": "",  # 네이버 API는 제공 안함
                                "목차": "",  # 네이버 API는 제공 안함
                                "서평": description,
                                "ISBN": isbn,
                                "출판사": publisher,
                                "출간일": pubdate,
                                "가격": price,
                                "링크": link,
                            }
                            results.append(naver_record)
                            # ✅ 2. 예스24 및 교보문고 추가 정보
                            # -------------------
                            # ✅ 수정: ISBN으로 검색했을 때만 웹스크레이핑 로직 실행
                            if (
                                search_type == "ISBN 검색"
                                and isbn
                                and isbn != "정보 없음"
                            ):
                                clean_isbn = isbn.strip()
                                if clean_isbn:
                                    # 각 스크레이퍼의 결과를 저장할 딕셔너리
                                    scraping_results = {"yes24": {}, "kyobo": {}}

                                    # 스레드에서 실행할 함수 정의
                                    def run_scraper(site, isbn_code):
                                        if site == "yes24":
                                            scraping_results["yes24"] = (
                                                scrape_yes24_book_info(
                                                    isbn_code, app_instance
                                                )
                                            )
                                        elif site == "kyobo":
                                            scraping_results["kyobo"] = (
                                                scrape_kyobo_book_info(
                                                    isbn_code, app_instance
                                                )
                                            )

                                    # 스레드 생성 및 시작
                                    yes24_thread = threading.Thread(
                                        target=run_scraper, args=("yes24", clean_isbn)
                                    )
                                    kyobo_thread = threading.Thread(
                                        target=run_scraper, args=("kyobo", clean_isbn)
                                    )

                                    yes24_thread.start()
                                    kyobo_thread.start()

                                    # 두 스레드가 모두 끝날 때까지 대기
                                    yes24_thread.join(timeout=15)
                                    kyobo_thread.join(timeout=15)

                                    yes24_info = scraping_results["yes24"]
                                    kyobo_info = scraping_results["kyobo"]

                                    # -------------------
                                    # -------------------
                                    # ✅ [수정] 예스24: 저자소개, 목차, 서평 수집
                                    author_intro_y24 = yes24_info.get("저자소개", "")
                                    toc_y24 = yes24_info.get("목차", "")
                                    review_y24 = yes24_info.get("출판사서평", "")

                                    review_parts_y24 = []
                                    if author_intro_y24:
                                        review_parts_y24.append(
                                            f"1. 저자 소개\n{author_intro_y24}"
                                        )
                                    if toc_y24:
                                        review_parts_y24.append(f"2. 목차\n{toc_y24}")
                                    if review_y24:
                                        review_parts_y24.append(
                                            f"3. 서평\n{review_y24}"
                                        )

                                    # ✅ [핵심 추가] 예스24 행 생성 및 append (빠져있던 부분)
                                    yes24_record = {
                                        "검색소스": "Yes24",
                                        "서명": title,
                                        "저자": author,
                                        "분류 정보 취합": "\n\n".join(review_parts_y24),
                                        "저자소개": author_intro_y24,
                                        "목차": toc_y24,
                                        "서평": review_y24,
                                        "ISBN": isbn,
                                        "출판사": publisher,
                                        "출간일": pubdate,
                                        "가격": price,
                                        "링크": yes24_info.get("상품링크", link),
                                    }
                                    results.append(yes24_record)

                                    # ✅ 예스24 / 교보 저자소개 취합
                                    author_intro_kb = kyobo_info.get("저자소개", "")
                                    toc_kb = kyobo_info.get("목차", "")
                                    review_kb = kyobo_info.get("출판사서평", "")

                                    review_parts_kb = []
                                    if author_intro_kb:
                                        review_parts_kb.append(
                                            f"1. 저자 소개\n{author_intro_kb}"
                                        )
                                    if toc_kb:
                                        review_parts_kb.append(f"2. 목차\n{toc_kb}")
                                    if review_kb:
                                        review_parts_kb.append(f"3. 서평\n{review_kb}")

                                    kyobo_record = {
                                        "검색소스": "Kyobo Book",
                                        "서명": title,
                                        "저자": author,
                                        "분류 정보 취합": "\n\n".join(review_parts_kb),
                                        "저자소개": author_intro_kb,
                                        "목차": toc_kb,
                                        "서평": review_kb,
                                        "ISBN": isbn,
                                        "출판사": publisher,
                                        "출간일": pubdate,
                                        "가격": price,
                                        "링크": kyobo_info.get("상품링크", link),
                                    }
                                    results.append(kyobo_record)

                                    # ✅ 3-a) 길이 우선 병합(저자/목차/서평) 계산 추가
                                    def _longer(a: str, b: str) -> str:
                                        return (
                                            (a or "")
                                            if len(a or "") >= len(b or "")
                                            else (b or "")
                                        )

                                    merged_author = _longer(
                                        author_intro_y24, author_intro_kb
                                    )
                                    merged_toc = _longer(toc_y24, toc_kb)
                                    merged_review = _longer(review_y24, review_kb)

                                    merged_parts = []
                                    if merged_author:
                                        merged_parts.append(
                                            f"1. 저자 소개\n{merged_author}"
                                        )
                                    if merged_toc:
                                        merged_parts.append(f"2. 목차\n{merged_toc}")
                                    if merged_review:
                                        merged_parts.append(f"3. 서평\n{merged_review}")

                                    # ✅ 3-b) 저자별 블록 추출/렌더 (우선: 리스트 기반)
                                    author_blocks = []
                                    y24_blocks = yes24_info.get("저자소개_리스트") or []
                                    kb_blocks = kyobo_info.get("저자소개_리스트") or []
                                    author_blocks.extend(y24_blocks)
                                    author_blocks.extend(kb_blocks)

                                    # ✅ 3-c) 리스트가 비면 합본 텍스트로라도 그룹 생성 (fallback)
                                    if not author_blocks:
                                        combined_bio = combine_author_bios(
                                            author_intro_y24, author_intro_kb
                                        )
                                        author_blocks = (
                                            [combined_bio] if combined_bio else []
                                        )

                                    # 저자명 파싱
                                    author_names = []
                                    if author and isinstance(author, str):
                                        parts = [
                                            p.strip()
                                            for p in re.split(r"[|,／/]", author)
                                            if p.strip()
                                        ]
                                        if parts:
                                            author_names = parts

                                    groups = extract_other_works_grouped(
                                        author_blocks, title
                                    )
                                    pattern_text = render_other_works_grouped(
                                        groups, author_names or None
                                    )

                                    # 평탄화 리스트 (AI-Feed Merge용)
                                    other_works_flat = []
                                    for g in groups:
                                        for w in g["works"]:
                                            other_works_flat.append(
                                                f"{w['title']}({w['orig']})"
                                                if w["orig"]
                                                else w["title"]
                                            )

                                    # 4번째 행 — AI-Feed Merge
                                    merged_record = {
                                        "검색소스": "AI-Feed Merge",
                                        "서명": title,
                                        "저자": author,
                                        "분류 정보 취합": "\n\n".join(
                                            merged_parts
                                        ).strip(),
                                        "저자소개": merged_author,
                                        "목차": merged_toc,
                                        "서평": merged_review,
                                        "ISBN": isbn,
                                        "출판사": publisher,
                                        "출간일": pubdate,
                                        "가격": price,
                                        "링크": yes24_info.get("상품링크")
                                        or kyobo_info.get("상품링크")
                                        or link,
                                    }
                                    results.append(merged_record)

                                    # 5번째 행 — OtherWorks Merge (저자별 패턴)
                                    if groups:
                                        otherworks_record = {
                                            "검색소스": "OtherWorks Merge",
                                            "서명": title,
                                            "저자": author,
                                            "분류 정보 취합": pattern_text,  # 저자A/작품/원서명 형식
                                            "저자소개": "",
                                            "목차": "",
                                            "서평": "",
                                            "ISBN": isbn,
                                            "출판사": publisher,
                                            "출간일": pubdate,
                                            "가격": price,
                                            "링크": yes24_info.get("상품링크")
                                            or kyobo_info.get("상품링크")
                                            or link,
                                        }
                                        results.append(otherworks_record)

                            if app_instance:
                                app_instance.log_message(
                                    f"정보: 네이버 API 결과 - 서명: {title[:50]}{'...' if len(title) > 50 else ''}"
                                )

                    else:
                        # 검색 결과 없음
                        if app_instance:
                            app_instance.log_message(
                                "정보: 네이버 API 검색 결과가 없습니다."
                            )

                        results = [
                            {
                                "서명": "검색 결과 없음",
                                "저자": "",
                                "출판사": "",
                                "출간일": "",
                                "ISBN": primary_query if isbn_query else "",
                                "가격": "",
                                "서평": f"'{primary_query}'에 대한 검색 결과를 찾을 수 없습니다.",
                                "분류 정보 취합": "",
                                "저자소개": "",
                                "목차": "",
                                "검색소스": search_type,
                                "링크": "",
                            }
                        ]
                else:
                    # XML 구조 오류
                    error_msg = "네이버 API 응답에서 channel 태그를 찾을 수 없습니다."
                    if app_instance:
                        app_instance.log_message(f"오류: {error_msg}", level="ERROR")

                    results = [
                        {
                            "서명": "API 응답 오류",
                            "저자": "",
                            "출판사": "",
                            "출간일": "",
                            "ISBN": primary_query if isbn_query else "",
                            "가격": "",
                            "서평": error_msg,
                            "분류 정보 취합": "",
                            "저자소개": "",
                            "목차": "",
                            "검색소스": search_type,
                            "링크": "",
                        }
                    ]

            except ET.ParseError as e:
                # XML 파싱 오류
                error_msg = f"XML 파싱 실패: {str(e)}"
                if app_instance:
                    app_instance.log_message(
                        f"오류: 네이버 API 응답 XML 파싱 실패: {e}", level="ERROR"
                    )

                results = [
                    {
                        "서명": "XML 파싱 오류",
                        "저자": "",
                        "출판사": "",
                        "출간일": "",
                        "ISBN": primary_query if isbn_query else "",
                        "가격": "",
                        "서평": error_msg,
                        "분류 정보 취합": "",
                        "저자소개": "",
                        "목차": "",
                        "검색소스": search_type,
                        "링크": "",
                    }
                ]

        else:
            # API 오류 처리 (GAS 코드와 동일)
            error_msg = f"API 오류 ({response_code}): {response_text[:100]}..."
            if app_instance:
                app_instance.log_message(
                    f"오류: 네이버 API 호출 오류: 응답 코드 {response_code}, 응답 텍스트: {response_text[:100]}...",
                    level="ERROR",
                )

            results = [
                {
                    "서명": "API 호출 오류",
                    "저자": "",
                    "출판사": "",
                    "출간일": "",
                    "ISBN": primary_query if isbn_query else "",
                    "가격": "",
                    "서평": error_msg,
                    "분류 정보 취합": "",
                    "저자소개": "",
                    "목차": "",
                    "검색소스": search_type,
                    "링크": "",
                }
            ]

    except requests.exceptions.RequestException as e:
        # 네트워크 오류 처리
        error_msg = f"네트워크 오류: {str(e)}"
        if app_instance:
            app_instance.log_message(
                f"오류: 네이버 API 호출 중 네트워크 오류: {e}", level="ERROR"
            )

        results = [
            {
                "서명": "네트워크 오류",
                "저자": "",
                "출판사": "",
                "출간일": "",
                "ISBN": primary_query if isbn_query else "",
                "가격": "",
                "서평": error_msg,
                "분류 정보 취합": "",
                "저자소개": "",
                "목차": "",
                "검색소스": search_type,
                "링크": "",
            }
        ]

    except Exception as e:
        # 기타 예외 처리 (GAS 코드와 동일)
        error_msg = f"오류 발생: {str(e)}"
        if app_instance:
            app_instance.log_message(
                f"오류: 네이버 API 호출 중 예외 발생: {e}", level="ERROR"
            )

        results = [
            {
                "서명": "예외 오류",
                "저자": "",
                "출판사": "",
                "출간일": "",
                "ISBN": primary_query if isbn_query else "",
                "가격": "",
                "서평": error_msg,
                "분류 정보 취합": "",
                "저자소개": "",
                "목차": "",
                "검색소스": search_type,
                "링크": "",
            }
        ]

    if app_instance:
        app_instance.update_progress(100)
        app_instance.log_message(
            f"정보: 네이버 책 API 검색 완료. ({len(results)}개 결과)"
        )

    return results


def set_naver_api_credentials(client_id, client_secret, db_manager):
    """
    네이버 API 클라이언트 ID와 시크릿을 데이터베이스에 저장합니다.
    GAS setNaverApiCredentials() 함수 포팅

    Args:
        client_id (str): 네이버 개발자 센터에서 발급받은 클라이언트 ID
        client_secret (str): 네이버 개발자 센터에서 발급받은 클라이언트 시크릿
        db_manager (DatabaseManager): 데이터베이스 매니저 인스턴스

    Returns:
        bool: 성공 여부
    """
    try:
        return db_manager.set_naver_api_credentials(client_id, client_secret)
    except Exception as e:
        print(f"오류: 네이버 API 인증 정보 저장 실패: {e}")
        return False


def scrape_yes24_book_info(isbn, app_instance=None):
    """
    예스24에서 ISBN으로 도서의 저자소개, 목차, 출판사서평을 스크레이핑합니다.
    실제 HTML 구조 분석을 기반으로 작성됨.

    Args:
        isbn (str): 검색할 ISBN
        app_instance: 로그용 앱 인턴스

    Returns:
        dict: {"저자소개": str, "목차": str, "출판사서평": str}
    """
    result = {"저자소개": "", "목차": "", "출판사서평": "", "상품링크": ""}

    if not isbn:
        return result

    try:
        if app_instance:
            app_instance.log_message(
                f"정보: 예스24에서 ISBN {isbn} 정보 스크레이핑 시작"
            )

        search_url = f"https://www.yes24.com/product/search?domain=BOOK&query={isbn}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        session = requests.Session()
        session.headers.update(headers)

        try:
            session.get("https://www.yes24.com/", timeout=10)
            time.sleep(0.5)
            session.headers.update({"Referer": "https://www.yes24.com/"})
        except requests.exceptions.RequestException:
            if app_instance:
                app_instance.log_message(
                    "경고: 예스24 홈페이지 방문 실패 (쿠키 획득 실패)", level="WARNING"
                )

        search_response = session.get(search_url, timeout=15)
        search_response.raise_for_status()

        # -------------------
        # ✅ [수정 1] 검색 결과 페이지의 인코딩을 'euc-kr'로 명시하여 파싱 오류를 방지합니다.
        search_response.encoding = "utf-8"
        search_soup = BeautifulSoup(search_response.text, "html.parser")
        # -------------------

        product_link = None

        # -------------------
        # ✅ [수정 2] 불필요한 디버깅 코드를 정리하고, 가장 정확한 'data-goods-no' 속성을 직접 찾아 링크를 생성합니다.
        goods_item = search_soup.find(attrs={"data-goods-no": True})
        if goods_item and goods_item.get("data-goods-no"):
            goods_no = goods_item.get("data-goods-no").strip()
            if goods_no:
                product_link = f"https://www.yes24.com/product/goods/{goods_no}"
                # -------------------
                # ✅ [수정] 찾은 상품 링크를 결과 딕셔너리에 저장합니다.
                result["상품링크"] = product_link
                # -------------------
                if app_instance:
                    app_instance.log_message(
                        f"정보: 예스24 상품 링크 발견 (data-goods-no): {product_link}"
                    )
        # -------------------

        if not product_link:
            if app_instance:
                app_instance.log_message(
                    "경고: 예스24에서 상품 링크(data-goods-no)를 찾을 수 없습니다."
                )
            return result

        time.sleep(1)

        detail_response = session.get(product_link, timeout=15)
        detail_response.raise_for_status()

        # -------------------
        # ✅ [수정 3] 상세 페이지 역시 'euc-kr' 인코딩을 명시적으로 지정해야 문자가 깨지지 않습니다. (가장 핵심적인 수정)
        detail_response.encoding = "utf-8"
        detail_soup = BeautifulSoup(detail_response.text, "html.parser")
        # -------------------

        # 여러 기여자(지은이/옮긴이)가 있을 수 있으므로 모두 수집
        author_spans = detail_soup.find_all("span", class_="author_info info_origin")
        author_chunks = []
        for sp in author_spans:
            txt = sp.get_text(separator="\n", strip=True)
            if txt and len(txt) > 30:
                author_chunks.append(txt)
        if author_chunks:
            result["저자소개"] = "\n\n---\n\n".join(author_chunks)  # 구분선으로 연결
            result["저자소개_리스트"] = author_chunks  # ✅ 추가: 저자별 블록 그대로

        toc_section = detail_soup.find("div", id="infoset_toc")
        if toc_section:
            toc_textarea = toc_section.find("textarea", class_="txtContentText")
            if toc_textarea:
                toc_html = toc_textarea.get_text()
                toc_soup = BeautifulSoup(toc_html, "html.parser")
                toc_text = toc_soup.get_text(separator="\n", strip=True)
                if len(toc_text) > 20:
                    result["목차"] = toc_text

        # -------------------
        # ✅ [수정 4] '출판사 리뷰' 또는 '출판사 서평' 등 다양한 텍스트에 대응하도록 정규식을 사용합니다.
        publisher_review_heading = detail_soup.find(
            "h4", class_="tit_txt", string=re.compile(r"출판사\s*(리뷰|서평)")
        )
        # -------------------
        if publisher_review_heading:
            parent_section = publisher_review_heading.find_parent("div")
            if parent_section:
                next_div = parent_section.find_next_sibling(
                    "div", class_="infoSetCont_wrap"
                )
                if next_div:
                    review_textarea = next_div.find("textarea", class_="txtContentText")
                    if review_textarea:
                        review_html = review_textarea.get_text()
                        review_soup = BeautifulSoup(review_html, "html.parser")
                        review_text = review_soup.get_text(separator="\n", strip=True)
                        cleaned_review = (
                            review_text.replace("출판사 리뷰", "")
                            .replace("출판사 서평", "")
                            .strip()
                        )
                        if len(cleaned_review) > 20:
                            result["출판사서평"] = cleaned_review

        if app_instance:
            found_info = []
            if result["저자소개"]:
                found_info.append("저자소개")
            if result["목차"]:
                found_info.append("목차")
            if result["출판사서평"]:
                found_info.append("출판사서평")
            if found_info:
                app_instance.log_message(
                    f"정보: 예스24에서 추출 완료: {', '.join(found_info)}"
                )
            else:
                app_instance.log_message(
                    f"정보: 예스24에서 추가 정보를 찾을 수 없었습니다"
                )

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 예스24 스크레이핑 네트워크 오류: {e}", level="ERROR"
            )
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 예스24 스크레이핑 실패: {e}", level="ERROR"
            )

    return result


def scrape_kyobo_book_info(isbn, app_instance=None):
    """
    교보문고에서 ISBN으로 도서의 저자소개, 목차, 출판사서평을 스크레이핑합니다.
    실제 HTML 구조 분석을 기반으로 작성됨.

    Args:
        isbn (str): 검색할 ISBN
        app_instance: 로그용 앱 인스턴스

    Returns:
        dict: {"저자소개": str, "목차": str, "출판사서평": str}
    """
    result = {"저자소개": "", "목차": "", "출판사서평": "", "상품링크": ""}

    if not isbn:
        return result

    try:
        if app_instance:
            app_instance.log_message(
                f"정보: 교보문고에서 ISBN {isbn} 정보 스크레이핑 시작"
            )

        # 교보문고 검색 URL (ISBN으로 검색)
        search_url = f"https://search.kyobobook.co.kr/search?keyword={isbn}&gbCode=TOT&target=total"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        # 검색 페이지에서 상품 링크 찾기
        search_response = requests.get(search_url, headers=headers, timeout=10)
        search_response.raise_for_status()

        search_soup = BeautifulSoup(search_response.content, "html.parser")

        # ✅ 교보문고 실제 구조: data-pid="S000217279197" data-bid="9788901296883"
        product_link = None

        # 1차 시도: ISBN으로 정확한 매칭
        checkbox_input = search_soup.find(
            "input", {"class": "result_checkbox", "data-pid": True, "data-bid": isbn}
        )

        if checkbox_input:
            product_id = checkbox_input.get("data-pid")
            if product_id:
                product_link = f"https://product.kyobobook.co.kr/detail/{product_id}"
                # -------------------
                # ✅ [수정] 찾은 상품 링크를 결과 딕셔너리에 저장합니다.
                result["상품링크"] = product_link
                # -------------------
                if app_instance:
                    app_instance.log_message(
                        f"정보: 교보문고 상품 페이지 발견: {product_link}"
                    )

        # 2차 시도: data-pid만으로 찾기 (백업)
        if not product_link:
            checkbox_input = search_soup.find("input", {"data-pid": True})
            if checkbox_input:
                product_id = checkbox_input.get("data-pid")
                if product_id:
                    product_link = (
                        f"https://product.kyobobook.co.kr/detail/{product_id}"
                    )

        if not product_link:
            if app_instance:
                app_instance.log_message(
                    "경고: 교보문고에서 상품 링크를 찾을 수 없습니다."
                )
            return result

        # 요청 간격 조절
        time.sleep(1)

        # 상품 상세 페이지 접근
        detail_response = requests.get(product_link, headers=headers, timeout=10)
        detail_response.raise_for_status()

        detail_soup = BeautifulSoup(detail_response.content, "html.parser")

        # ✅ 저자소개 추출: `writer_info_box`를 먼저 찾고, 그 안에서 `info_text` 클래스의 `p` 태그를 찾습니다.
        # -------------------
        # [수정] .find()는 첫 번째 저자(앨리슨 우드 브룩스)만 찾습니다.
        #       .find_all()로 변경하여 저자, 번역자 등 모든 'writer_info_box'를 순회해야 합니다.
        author_boxes = detail_soup.find_all("div", class_="writer_info_box")
        author_chunks = []  # 모든 저자/번역자의 소개 블록을 담을 리스트

        if author_boxes:
            for box in author_boxes:  # 👈 [수정] 발견된 모든 박스를 순회
                # writer_info_box 안에 여러 명의 info_text 단락이 존재 가능
                author_ps = box.find_all("p", class_="info_text")
                for p in author_ps:  # 👈 [수정] 각 박스 안의 p 태그 순회
                    t = p.get_text(separator="\n", strip=True)
                    if t and len(t) > 30:
                        author_chunks.append(t)  # 👈 [수정] 단일 리스트에 모두 추가

            if author_chunks:
                result["저자소개"] = "\n\n---\n\n".join(author_chunks)
                result["저자소개_리스트"] = author_chunks  # ✅ 수정: 저자/번역자 블록이 모두 포함됨
        # -------------------

        # ✅ 목차 추출: <h2 class="title_heading">목차</h2> → <ul class="book_contents_list">
        toc_heading = detail_soup.find("h2", class_="title_heading", string="목차")
        if toc_heading:
            # 목차 헤딩 다음의 auto_overflow_wrap 찾기
            toc_container = toc_heading.find_next("div", class_="auto_overflow_wrap")
            if toc_container:
                # book_contents_list 찾기
                contents_list = toc_container.find("ul", class_="book_contents_list")
                if contents_list:
                    # 모든 목차 항목 추출
                    content_items = contents_list.find_all(
                        "li", class_="book_contents_item"
                    )
                    toc_texts = []
                    for item in content_items:
                        item_text = item.get_text(separator="\n", strip=True)
                        if item_text:
                            toc_texts.append(item_text)

                    if toc_texts:
                        toc_content = "\n".join(toc_texts)
                        if len(toc_content) > 20:
                            result["목차"] = toc_content

        # ✅ 출판사서평 추출: <h2 class="title_heading">출판사 서평</h2> → <p class="info_text">
        publisher_review_heading = detail_soup.find(
            "h2", class_="title_heading", string="출판사 서평"
        )
        if publisher_review_heading:
            # 출판사 서평 헤딩 다음의 auto_overflow_wrap 찾기
            review_container = publisher_review_heading.find_next(
                "div", class_="auto_overflow_wrap"
            )
            if review_container:
                # info_text 단락들 추출
                review_paragraphs = review_container.find_all("p", class_="info_text")
                review_texts = []
                for p in review_paragraphs:
                    p_text = p.get_text(separator="\n", strip=True)
                    if p_text:
                        review_texts.append(p_text)

                if review_texts:
                    review_content = "\n".join(review_texts)
                    cleaned_review = (
                        review_content.replace("출판사 서평", "")
                        .replace("출판사 리뷰", "")
                        .strip()
                    )
                    if len(cleaned_review) > 20:
                        result["출판사서평"] = cleaned_review

        if app_instance:
            found_info = []
            if result["저자소개"]:
                found_info.append("저자소개")
            if result["목차"]:
                found_info.append("목차")
            if result["출판사서평"]:
                found_info.append("출판사서평")
            if found_info:
                app_instance.log_message(
                    f"정보: 교보문고에서 추출 완료: {', '.join(found_info)}"
                )
            else:
                app_instance.log_message(
                    f"정보: 교보문고에서 추가 정보를 찾을 수 없었습니다"
                )

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 교보문고 스크레이핑 네트워크 오류: {e}", level="ERROR"
            )
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 교보문고 스크레이핑 실패: {e}", level="ERROR"
            )

    return result


def get_additional_book_info(isbn, app_instance=None):
    """
    예스24와 교보문고에서 추가 도서 정보를 수집합니다.

    Args:
        isbn (str): 검색할 ISBN
        app_instance: 로그용 앱 인스턴스

    Returns:
        dict: {"저자소개": str, "목차": str, "출판사서평": str}
    """
    result = {"저자소개": "", "목차": "", "출판사서평": ""}

    if not isbn:
        return result

    # 예스24에서 먼저 시도
    yes24_info = scrape_yes24_book_info(isbn, app_instance)

    # 교보문고에서 시도 (예스24에서 못 찾은 정보가 있을 경우)
    need_kyobo = (
        not yes24_info["저자소개"]
        or not yes24_info["목차"]
        or not yes24_info["출판사서평"]
    )

    if need_kyobo:
        kyobo_info = scrape_kyobo_book_info(isbn, app_instance)

        # 정보 병합 (예스24 우선, 없으면 교보문고)
        if not yes24_info["저자소개"] and kyobo_info["저자소개"]:
            result["저자소개"] = kyobo_info["저자소개"]
        else:
            result["저자소개"] = yes24_info["저자소개"]

        if not yes24_info["목차"] and kyobo_info["목차"]:
            result["목차"] = kyobo_info["목차"]
        else:
            result["목차"] = yes24_info["목차"]

        if not yes24_info["출판사서평"] and kyobo_info["출판사서평"]:
            result["출판사서평"] = kyobo_info["출판사서평"]
        else:
            result["출판사서평"] = yes24_info["출판사서평"]
    else:
        result = yes24_info

    return result


# 테스트용 메인 함수
if __name__ == "__main__":
    print("Search_Naver.py 테스트 실행")

    # 테스트 ISBN
    test_isbn = "9788960773417"

    # 간단한 테스트 (실제 API 키 없이)
    print(f"테스트 ISBN: {test_isbn}")

    # DatabaseManager 없이 테스트
    results = search_naver_catalog(test_isbn, app_instance=None, db_manager=None)
    print("테스트 결과:", results)
