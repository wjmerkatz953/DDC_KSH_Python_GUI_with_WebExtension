# -*- coding: utf-8 -*-
"""
Search_Legal_deposit.py - 국립중앙도서관 납본 ID 검색 모듈
Version: v1.0.0
생성일: 2025-09-21 KST

국립중앙도서관의 ISBN 서지정보 API를 사용하여 납본 도서 정보를 검색합니다.
API 문서: https://www.nl.go.kr/seoji/SearchApi.do
"""

# ✅ [추가] PyInstaller 환경에서 SSL 인증서 경로 설정
from ssl_cert_utils import configure_ssl_certificates
configure_ssl_certificates()

import requests
import json
import time
import pandas as pd
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime


# ===== AFTER (urllib로 변환) =====
def search_legal_deposit_catalog(
    title_query="",
    author_query="",
    isbn_query="",
    year_query="",
    publisher_query="",
    app_instance=None,
    db_manager=None,
    page_size=20,
    max_pages=1,
):
    """
    국립중앙도서관 납본 ID 검색 API를 사용하여 도서 정보를 검색합니다.

    Args:
        title_query (str): 도서 제목 검색어
        author_query (str): 저자 검색어
        isbn_query (str): ISBN 검색어
        year_query (str): 출판연도 (YYYY 형식)
        publisher_query (str): 출판사 검색어
        app_instance: GUI 앱 인스턴스 (로그용)
        db_manager: 데이터베이스 매니저 (API 키 조회용)
        page_size (int): 페이지당 결과 수 (기본값: 50)
        max_pages (int): 최대 페이지 수 (기본값: 5)

    Returns:
        list: 검색 결과 리스트 (각 항목은 딕셔너리)
    """

    if app_instance:
        app_instance.log_message("납본 ID 검색을 시작합니다...")

    # API 키 가져오기 (NLK API 키 사용)
    if db_manager:
        api_key = db_manager.get_nlk_api_key()
        if not api_key:
            error_msg = "납본 ID 검색을 위한 API 키가 설정되지 않았습니다. API 설정을 확인해주세요."
            if app_instance:
                app_instance.log_message(f"오류: {error_msg}", level="ERROR")
            return []
    else:
        error_msg = "데이터베이스 매니저가 없어서 API 키를 가져올 수 없습니다."
        if app_instance:
            app_instance.log_message(f"오류: {error_msg}", level="ERROR")
        return []

    # 기본 API URL
    base_url = "https://www.nl.go.kr/seoji/SearchApi.do"

    all_results = []
    current_page = 1

    while current_page <= max_pages:
        try:
            # 필수 파라미터
            params = {
                "cert_key": api_key,
                "result_style": "json",
                "page_no": current_page,
                "page_size": page_size,
            }

            # 검색 조건이 있을 때만 정렬 추가
            has_search_params = any(
                [title_query, author_query, isbn_query, publisher_query, year_query]
            )
            if has_search_params:
                params["sort"] = "PUBLISH_PREDATE"
                params["order_by"] = "DESC"

            # 검색 조건 추가
            if title_query:
                params["title"] = title_query
            if author_query:
                params["author"] = author_query
            if isbn_query:
                clean_isbn = isbn_query.replace("-", "").replace(" ", "")
                params["isbn"] = clean_isbn
            if publisher_query:
                params["publisher"] = publisher_query
            if year_query:
                try:
                    year = int(year_query)
                    start_date = f"{year}0101"
                    end_date = f"{year}1231"
                    params["start_publish_date"] = start_date
                    params["end_publish_date"] = end_date
                except ValueError:
                    if app_instance:
                        app_instance.log_message(
                            f"경고: 올바르지 않은 연도 형식: {year_query}"
                        )

            # URL 인코딩
            query_string = urllib.parse.urlencode(params)
            full_url = f"{base_url}?{query_string}"

            if app_instance:
                app_instance.log_message(
                    f"납본 ID API 호출 중... (페이지 {current_page}/{max_pages}, URL: {full_url})"
                )

            # 요청 객체 생성 (헤더를 추가하지 않고 단순하게)
            req = urllib.request.Request(full_url)

            # API 호출
            with urllib.request.urlopen(req, timeout=60) as response:
                response_text = response.read().decode("utf-8")
                data = json.loads(response_text)

            # 에러 체크
            if "ERROR_CODE" in data:
                error_code = data.get("ERROR_CODE", "")
                error_message = data.get("MESSAGE", "알 수 없는 오류")
                error_msg = f"API 오류 ({error_code}): {error_message}"
                if app_instance:
                    app_instance.log_message(f"오류: {error_msg}", level="ERROR")
                return []

            if "docs" not in data:
                if app_instance:
                    app_instance.log_message("납본 ID 검색 결과가 없습니다.")
                break

            docs = data["docs"]
            total_count = data.get("TOTAL_COUNT", 0)

            if current_page == 1:
                if app_instance:
                    app_instance.log_message(
                        f"총 {total_count}건의 검색 결과를 찾았습니다."
                    )

            if not docs:
                break

            page_results = []
            for doc in docs:
                result = _process_legal_deposit_item(doc, app_instance)
                if result:
                    page_results.append(result)

            all_results.extend(page_results)

            if app_instance:
                app_instance.log_message(
                    f"페이지 {current_page}: {len(page_results)}건 처리 완료"
                )

            if len(docs) < page_size:
                break

            current_page += 1
            time.sleep(0.1)

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ) as e:
            error_msg = f"납본 ID API 요청 실패: {str(e)}"
            if app_instance:
                app_instance.log_message(f"오류: {error_msg}", level="ERROR")
            break
        except Exception as e:
            error_msg = f"납본 ID 검색 중 예상치 못한 오류: {str(e)}"
            if app_instance:
                app_instance.log_message(f"오류: {error_msg}", level="ERROR")
            break

    if app_instance:
        app_instance.log_message(f"납본 ID 검색 완료: 총 {len(all_results)}건의 결과")

    return all_results


def _process_legal_deposit_item(doc, app_instance=None):
    """
    납본 ID API 응답의 개별 아이템을 처리하여 표준화된 형태로 변환합니다.

    Args:
        doc (dict): API 응답의 개별 문서 데이터
        app_instance: GUI 앱 인스턴스 (로그용)

    Returns:
        dict: 처리된 도서 정보 딕셔너리
    """
    try:
        # 기본 정보 추출
        title = doc.get("TITLE", "").strip()
        author = doc.get("AUTHOR", "").strip()
        publisher = doc.get("PUBLISHER", "").strip()
        isbn = doc.get("EA_ISBN", "").strip()

        # 권차 정보가 있으면 제목에 추가
        vol = doc.get("VOL", "").strip()
        if vol and vol != title:
            title = f"{title} {vol}".strip()

        # 총서 정보 처리
        series_title = doc.get("SERIES_TITLE", "").strip()
        series_no = doc.get("SERIES_NO", "").strip()
        if series_title:
            series_info = series_title
            if series_no:
                series_info += f" ; {series_no}"
            title = f"{title} ({series_info})".strip()

        # 출판연도 추출 (PUBLISH_PREDATE에서)
        publish_date = doc.get("PUBLISH_PREDATE", "")
        year = ""
        if publish_date and len(publish_date) >= 4:
            year = publish_date[:4]

        # DDC 분류번호
        ddc = doc.get("DDC", "").strip()

        # 가격 정보
        price = doc.get("PRE_PRICE", "").strip()

        # 형태사항
        form = doc.get("FORM", "").strip()
        page = doc.get("PAGE", "").strip()
        book_size = doc.get("BOOK_SIZE", "").strip()

        # 전자책 여부
        ebook_yn = doc.get("EBOOK_YN", "N")
        is_ebook = "전자책" if ebook_yn == "Y" else "인쇄책"

        # CIP 정보
        cip_yn = doc.get("CIP_YN", "N")
        control_no = doc.get("CONTROL_NO", "").strip()

        # URL 정보
        title_url = doc.get("TITLE_URL", "").strip()  # 표지이미지
        book_intro_url = doc.get("BOOK_INTRODUCTION_URL", "").strip()  # 책소개
        publisher_url = doc.get("PUBLISHER_URL", "").strip()  # 출판사 홈페이지

        # 상세 링크 생성 (국립중앙도서관 상세페이지)
        detail_link = ""
        if isbn:
            detail_link = f"https://www.nl.go.kr/seoji/contents/S80100000000.do?schM=intgr_detail_view_isbn&isbn13={isbn}"

        # 020 필드 생성 로직
        ea_isbn = isbn  # isbn 변수는 이미 EA_ISBN 값을 담고 있음
        ea_add_code = doc.get("EA_ADD_CODE", "").strip()
        set_isbn = doc.get("SET_ISBN", "").strip()
        set_add_code = doc.get("SET_ADD_CODE", "").strip()

        field_020 = ""
        if ea_isbn:  # EA_ISBN이 있는 경우
            field_020 = f"▼a{ea_isbn}▼g{ea_add_code} :▼c\\{price}▲"
        elif set_isbn:  # EA_ISBN이 없고 SET_ISBN만 있는 경우
            field_020 = f"▼a{set_isbn}▼g{set_add_code} :▼c\\{price}▲"

        # 결과 딕셔너리 구성 (API에서 제공하는 모든 항목 포함)
        result = {
            # API 원본 필드명 (GUI 표시용)
            "TITLE": title,
            "AUTHOR": author,
            "020 필드": field_020,
            "EA_ISBN": isbn,
            "EA_ADD_CODE": doc.get("EA_ADD_CODE", "").strip(),
            "SET_ISBN": doc.get("SET_ISBN", "").strip(),
            "SET_ADD_CODE": doc.get("SET_ADD_CODE", "").strip(),
            "SET_EXPRESSION": doc.get("SET_EXPRESSION", "").strip(),
            "PRE_PRICE": price,
            "PUBLISHER": publisher,
            "EDITION_STMT": doc.get("EDITION_STMT", "").strip(),
            "KDC": doc.get("KDC", "").strip(),
            "DDC": ddc,
            "PAGE": page,
            "BOOK_SIZE": book_size,
            "FORM": form,
            "PUBLISH_PREDATE": doc.get("PUBLISH_PREDATE", "").strip(),
            "SUBJECT": doc.get("SUBJECT", "").strip(),
            "EBOOK_YN": ebook_yn,
            "CIP_YN": cip_yn,
            "PUBLISHER_URL": publisher_url,
            "INPUT_DATE": doc.get("INPUT_DATE", "").strip(),
            "UPDATE_DATE": doc.get("UPDATE_DATE", "").strip(),
            # 기본 서지정보 (한글명 - 호환성용)
            "제목": title,
            "권차": vol,
            "020 필드": field_020,
            "총서명": series_title,
            "총서편차": doc.get("SERIES_NO", "").strip(),
            "저자": author,
            "ISBN": isbn,
            "ISBN부가기호": doc.get("EA_ADD_CODE", "").strip(),
            "세트ISBN": doc.get("SET_ISBN", "").strip(),
            "세트ISBN부가기호": doc.get("SET_ADD_CODE", "").strip(),
            "세트표현": doc.get("SET_EXPRESSION", "").strip(),
            "출판사": publisher,
            "판사항": doc.get("EDITION_STMT", "").strip(),
            "예정가격": price,
            # 분류정보
            "주제": doc.get("SUBJECT", "").strip(),
            # 형태정보
            "페이지": page,
            "책크기": book_size,
            "발행제본형태": form,
            "출판예정일": doc.get("PUBLISH_PREDATE", "").strip(),
            "출판 연도": year,
            # 상태정보
            "전자책여부": ebook_yn,
            "자료유형": is_ebook,
            "CIP신청여부": cip_yn,
            "CIP": "Y" if cip_yn == "Y" else "N",
            "CIP제어번호": control_no,
            # URL 정보
            "표지이미지URL": title_url,
            "목차URL": doc.get("BOOK_TB_CNT_URL", "").strip(),
            "책소개URL": book_intro_url,
            "책요약URL": doc.get("BOOK_SUMMARY_URL", "").strip(),
            "출판사홈페이지URL": publisher_url,
            # 시스템 정보
            "등록날짜": doc.get("INPUT_DATE", "").strip(),
            "수정날짜": doc.get("UPDATE_DATE", "").strip(),
            "페이지번호": doc.get("PAGE_NO", "").strip(),
            "전체출력수": doc.get("TOTAL_COUNT", "").strip(),
            # 표시용 정리된 정보 (호환성용)
            "가격": price,
            "형태": form,
            "크기": book_size,
            "CIP번호": control_no,
            "표지이미지": title_url,
            "책소개": book_intro_url,
            "출판사홈페이지": publisher_url,
            "상세 링크": detail_link,
        }

        # 빈 값 정리
        for key, value in result.items():
            if not value or value == "None":
                result[key] = ""

        return result

    except Exception as e:
        if app_instance:
            app_instance.log_message(f"경고: 납본 ID 항목 처리 중 오류: {str(e)}")
        return None


def format_legal_deposit_results_for_display(results):
    """
    납본 ID 검색 결과를 GUI 표시용으로 포맷팅합니다.

    Args:
        results (list): 검색 결과 리스트

    Returns:
        pandas.DataFrame: 표시용 데이터프레임
    """
    if not results:
        return pd.DataFrame()

    try:
        # DataFrame 생성
        df = pd.DataFrame(results)

        # 표시할 컬럼 순서 정의 (API 원본 필드명 사용)
        display_columns = [
            "TITLE",
            "AUTHOR",
            "020 필드",
            "EA_ISBN",
            "EA_ADD_CODE",
            "SET_ISBN",
            "SET_ADD_CODE",
            "SET_EXPRESSION",
            "PRE_PRICE",
            "PUBLISHER",
            "EDITION_STMT",
            "KDC",
            "DDC",
            "PAGE",
            "BOOK_SIZE",
            "FORM",
            "PUBLISH_PREDATE",
            "SUBJECT",
            "EBOOK_YN",
            "CIP_YN",
            "PUBLISHER_URL",
            "INPUT_DATE",
            "UPDATE_DATE",
        ]

        # 존재하는 컬럼만 선택
        available_columns = [col for col in display_columns if col in df.columns]
        df = df[available_columns]

        # 데이터 타입 정리
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace("nan", "")
            df[col] = df[col].replace("None", "")

        return df

    except Exception as e:
        print(f"오류: 납본 ID 결과 포맷팅 실패: {str(e)}")
        return pd.DataFrame()


def test_api_connection_urllib(api_key, app_instance=None):
    """
    urllib를 사용한 API 연결 테스트 (requests 대안)
    """
    if app_instance:
        app_instance.log_message("urllib로 API 연결 테스트를 시작합니다...")

    test_url = f"https://www.nl.go.kr/seoji/SearchApi.do?cert_key={api_key}&result_style=json&page_no=1&page_size=10&sort=PUBLISH_PREDATE&order_by=DESC"

    try:
        # urllib 요청 생성
        req = urllib.request.Request(test_url)

        # 브라우저 헤더 추가
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        req.add_header("Accept", "application/json, text/javascript, */*; q=0.01")
        req.add_header("Accept-Language", "ko-KR,ko;q=0.9,en;q=0.8")
        req.add_header("Referer", "https://www.nl.go.kr/")

        # 요청 실행
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read().decode("utf-8")
            json_data = json.loads(data)

            if app_instance:
                app_instance.log_message(
                    f"urllib 연결 테스트 성공! 상태코드: {response.status}"
                )
                app_instance.log_message(f"응답 데이터 키: {list(json_data.keys())}")
                if "docs" in json_data:
                    app_instance.log_message(f"결과 개수: {len(json_data['docs'])}건")

            return True

    except urllib.error.HTTPError as e:
        if app_instance:
            app_instance.log_message(f"HTTP 오류: {e.code} - {e.reason}")
        return False
    except urllib.error.URLError as e:
        if app_instance:
            app_instance.log_message(f"URL 오류: {e.reason}")
        return False
    except Exception as e:
        if app_instance:
            app_instance.log_message(f"urllib 테스트 실패: {e}")
        return False


def test_api_connection(api_key, app_instance=None):
    """
    search-addon.js와 동일한 방식으로 API 연결 테스트 (urllib, 헤더 없음)
    """
    if app_instance:
        app_instance.log_message(
            "search-addon.js 방식으로 API 연결 테스트를 시작합니다..."
        )

    # search-addon.js와 정확히 동일한 요청 (헤더 완전 제거)
    test_url = f"https://www.nl.go.kr/seoji/SearchApi.do?cert_key={api_key}&result_style=json&page_no=1&page_size=10&sort=PUBLISH_PREDATE&order_by=DESC"

    try:
        if app_instance:
            app_instance.log_message(f"테스트 URL: {test_url}")

        # search-addon.js처럼 아무 헤더 없이 요청
        req = urllib.request.Request(test_url)
        # User-Agent도 제거! (fetch()는 기본 브라우저 User-Agent 사용)

        # 요청 실행
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read().decode("utf-8")
            json_data = json.loads(data)

            if app_instance:
                app_instance.log_message(
                    f"연결 테스트 성공! 상태코드: {response.status}"
                )
                app_instance.log_message(f"응답 데이터 키: {list(json_data.keys())}")
                if "docs" in json_data:
                    app_instance.log_message(f"결과 개수: {len(json_data['docs'])}건")

            return True

    except Exception as e:
        if app_instance:
            app_instance.log_message(f"테스트 실패: {e}")
        return False


# 테스트용 메인 함수 수정
if __name__ == "__main__":
    print("Search_Legal_deposit.py - 납본 ID 검색 모듈")

    # API 연결 테스트
    test_api_key = "8f2ab95929df06a19f2f7d1b4cf4996118cce50914577c007ae6c78704ab2383"

    class DummyApp:
        def log_message(self, msg, level="INFO"):
            print(f"[{level}] {msg}")

    dummy_app = DummyApp()

    # 연결 테스트 실행 (urllib 사용)
    print("=== urllib 라이브러리 테스트 ===")
    connection_ok = test_api_connection(test_api_key, dummy_app)

    if connection_ok:
        print("연결 성공! 실제 검색을 시도합니다...")
        # 간단한 테스트 검색
        test_results = search_legal_deposit_catalog(
            isbn_query="9788936434267",  # 간단한 ISBN으로 테스트
            app_instance=dummy_app,
            page_size=5,
            max_pages=1,
        )
        print(f"테스트 검색 결과: {len(test_results)}건")
    else:
        print("연결 실패 - 네트워크 환경을 확인해주세요")
