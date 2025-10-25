# -*- coding: utf-8 -*-
# 파일명: Search_Google.py
# Version: v1.0.0
# 생성일시: 2025-08-14 KST
# 설명: Google Books API를 사용하여 도서 정보를 검색하는 Python 모듈. (Apps Script 포팅)

import requests
import re
from urllib.parse import urlencode
from qt_api_clients import translate_text_batch_async


# Google Books API도 설정탭의 번역 기능 통제를 받도록 추가
def _should_auto_translate(app_instance):
    """자동 번역 여부를 확인합니다."""
    if hasattr(app_instance, "foreign_auto_translation_var"):
        return app_instance.foreign_auto_translation_var.get()
    return _get_foreign_auto_translation_setting(app_instance)


def _get_foreign_auto_translation_setting(app_instance):
    """해외 도서관 자동 번역 설정을 가져옵니다."""
    if hasattr(app_instance, "db_manager") and app_instance.db_manager:
        value = app_instance.db_manager.get_setting("foreign_auto_translation")
        return value == "true" if value else True  # 기본값: 활성화
    return True


# Google Books API는 MARC XML이 아닌 JSON 응답을 사용하므로, 파서가 더 간단합니다.
def _parse_book_item(item, app_instance):
    """
    Google Books API의 JSON 응답 'item'에서 필요한 정보를 추출하여
    Tab_Google.py의 컬럼 구조에 맞는 딕셔너리로 반환합니다.
    """
    # Tab_Google.py에서 기대하는 최종 컬럼명과 일치시킵니다.
    record = {
        "제목": "없음",
        "저자": "없음",
        "출판지역": "없음",
        "출판사": "없음",
        "연도": "없음",
        "650 필드": "없음",
        "650 필드 (번역)": "없음",
        "ISBN": "없음",
        "상세 링크": "없음",
        "주제어_원문": [],  # 번역을 위해 임시 저장
    }

    try:
        volume_info = item.get("volumeInfo", {})
        if not volume_info:
            return None

        # 1. 제목
        record["제목"] = volume_info.get("title", "없음")
        subtitle = volume_info.get("subtitle")
        if subtitle:
            record["제목"] += f": {subtitle}"

        # 2. 저자
        authors = volume_info.get("authors", [])
        record["저자"] = ", ".join(authors) if authors else "없음"

        # 3. 출판사
        record["출판사"] = volume_info.get("publisher", "없음")

        # 4. 출판 연도 (YYYY-MM-DD 형식에서 YYYY만 추출)
        published_date = volume_info.get("publishedDate", "")
        if published_date:
            year_match = re.search(r"^\d{4}", published_date)
            if year_match:
                record["연도"] = year_match.group(0)
            else:
                record["연도"] = published_date  # YYYY 형식이 아닌 경우 원본 유지

        # 5. ISBN (13, 10 순으로 탐색)
        industry_identifiers = volume_info.get("industryIdentifiers", [])
        isbn13 = next(
            (i["identifier"] for i in industry_identifiers if i["type"] == "ISBN_13"),
            None,
        )
        isbn10 = next(
            (i["identifier"] for i in industry_identifiers if i["type"] == "ISBN_10"),
            None,
        )
        record["ISBN"] = isbn13 or isbn10 or "없음"

        # 6. 주제어 (categories 필드 사용)
        categories = volume_info.get("categories", [])
        record["주제어_원문"] = [cat.strip() for cat in categories if cat.strip()]

        # 7. 상세 정보 링크
        record["상세 링크"] = volume_info.get("infoLink", "없음")

        # 8. 출판 지역 (Google Books API에서 직접 제공하지 않음)
        # 이 필드는 "없음"으로 유지됩니다.

        return record

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"Google Books API 아이템 파싱 중 오류 발생: {e}", level="ERROR"
            )
        return None


def search_google_books_api(
    title_query=None,
    author_query=None,
    isbn_query=None,
    year_query=None,
    app_instance=None,
    db_manager=None,
):
    """
    Google Books API (v1)를 호출하고 결과를 파싱하여 반환합니다.
    """
    if not db_manager or not app_instance:
        print("오류: db_manager 또는 app_instance가 제공되지 않았습니다.")
        return []

    # 1. API 키 가져오기 (후속 조치로 DB에 추가 필요)
    api_key = db_manager.get_google_api_key()
    if not api_key:
        app_instance.log_message(
            "오류: Google Books API 키가 설정되지 않았습니다.", level="ERROR"
        )
        app_instance.show_messagebox(
            "API 키 오류",
            "Google Books API 키를 설정해야 합니다.\n[설정] 메뉴에서 API 키를 입력해주세요.",
            "error",
        )
        return []

    base_url = "https://www.googleapis.com/books/v1/volumes"
    query_parts = []

    # Apps Script 로직과 동일하게 쿼리 구성
    if title_query:
        query_parts.append(f"intitle:{title_query}")
    if author_query:
        query_parts.append(f"inauthor:{author_query}")
    if isbn_query:
        # ISBN 하이픈 제거
        query_parts.append(f'isbn:{isbn_query.replace("-", "").replace(" ", "")}')
    # year_query는 API 쿼리에 포함하지 않고, 결과를 받은 후 Python에서 필터링
    # (Google Books API가 출판 연도 전용 키워드를 지원하지 않으므로)
    if year_query:
        app_instance.log_message(
            f"정보: 출판 연도 '{year_query}'는 결과 수신 후 Python에서 필터링 예정",
            level="INFO",
        )

    if not query_parts:
        app_instance.log_message(
            "경고: Google Books API 검색을 위한 검색어가 없습니다.", level="WARNING"
        )
        return []

    # Google Books API는 띄어쓰기를 '+'로 연결합니다.
    final_query = "+".join(query_parts)

    params = {
        "q": final_query,
        "key": api_key,
        "maxResults": 40,  # API 최대치
        "orderBy": "newest",  # 최신순 정렬
        "country": "KR",  # 한국어 서적 우선 검색
        "printType": "books",  # 잡지가 아닌 책만 검색
    }

    try:
        url = f"{base_url}?{urlencode(params)}"
        app_instance.log_message(f"정보: Google Books API 요청: {url}", level="INFO")

        response = requests.get(
            url, timeout=20, headers={"User-Agent": "LibraryTool/1.0"}
        )
        response.raise_for_status()

        json_response = response.json()
        total_items = json_response.get("totalItems", 0)

        if total_items == 0:
            app_instance.log_message(
                "정보: Google Books API 검색 결과 없음.", level="INFO"
            )
            return []

        items = json_response.get("items", [])
        all_results = []
        for item in items:
            parsed = _parse_book_item(item, app_instance)
            if parsed:
                all_results.append(parsed)

        # ===== 🆕 Python 자체 연도 필터링 =====
        if year_query and all_results:
            year_cleaned = year_query.strip()
            filtered_results = []

            for record in all_results:
                published_year = record.get("연도", "")

                # 연도 매칭 로직
                if re.match(r"^\d{4}$", year_cleaned):
                    # 단일 연도 검색 (예: 2016)
                    if published_year == year_cleaned:
                        filtered_results.append(record)
                elif re.match(r"^\d{4}-\d{4}$", year_cleaned):
                    # 연도 범위 검색 (예: 2015-2017)
                    start_year, end_year = year_cleaned.split("-")
                    try:
                        pub_year_int = (
                            int(published_year) if published_year.isdigit() else 0
                        )
                        if int(start_year) <= pub_year_int <= int(end_year):
                            filtered_results.append(record)
                    except (ValueError, TypeError):
                        continue
                else:
                    # 부분 매칭 (예: "약 2016" 같은 경우)
                    if year_cleaned in published_year:
                        filtered_results.append(record)

            # 필터링 결과로 교체
            all_results = filtered_results
            app_instance.log_message(
                f"정보: 출판 연도 '{year_query}' 필터링 완료: {len(all_results)}건 매칭",
                level="INFO",
            )

        # ===== 🆕 설정 확인 후 번역 실행 (DNB, BNF, BNE와 동일) =====
        if (
            all_results
            and app_instance
            and db_manager
            and _should_auto_translate(app_instance)
        ):
            app_instance.log_message(
                "정보: Google Books 주제어 번역 시작...", level="INFO"
            )

            all_unique_subjects = set(
                s.strip()
                for record in all_results
                for s in record.get("주제어_원문", [])
                if s
            )

            if all_unique_subjects:
                custom_glossary = db_manager.get_all_custom_translations()
                translation_map = translate_text_batch_async(
                    all_unique_subjects, app_instance, custom_glossary, db_manager
                )

                for record in all_results:
                    raw_subjects = record.get("주제어_원문", [])
                    if raw_subjects:
                        record["650 필드"] = " | ".join(raw_subjects)
                        translated = [
                            translation_map.get(s.strip(), s.strip())
                            for s in raw_subjects
                        ]
                        record["650 필드 (번역)"] = " | ".join(translated)
                    else:
                        record["650 필드"] = "없음"
                        record["650 필드 (번역)"] = "없음"
                    del record["주제어_원문"]  # 임시 키 삭제

            app_instance.log_message(
                "정보: Google Books 주제어 번역 완료.", level="INFO"
            )

        elif all_results and app_instance:
            # 번역 비활성화 시 원문을 그대로 사용
            app_instance.log_message(
                "정보: 해외 도서관 자동 번역이 비활성화되어 원문 주제어를 사용합니다.",
                level="INFO",
            )

            for record in all_results:
                raw_subjects = record.get("주제어_원문", [])
                if raw_subjects:
                    record["650 필드"] = " | ".join(raw_subjects)
                    record["650 필드 (번역)"] = " | ".join(raw_subjects)  # 원문 그대로
                else:
                    record["650 필드"] = "없음"
                    record["650 필드 (번역)"] = "없음"
                del record["주제어_원문"]

            app_instance.log_message(
                "정보: Google Books 주제어 처리 완료 (번역 비활성화).", level="INFO"
            )

        # 출판 연도 기준으로 내림차순 정렬 (기존 모듈과 동일)
        all_results.sort(key=lambda x: str(x.get("연도", "0")), reverse=True)

        app_instance.log_message(
            f"정보: Google Books 검색 결과 {len(all_results)}건 파싱 완료.",
            level="INFO",
        )
        return all_results

    except requests.exceptions.RequestException as e:
        app_instance.log_message(
            f"오류: Google Books API 검색 중 네트워크 오류: {e}", level="ERROR"
        )
        app_instance.show_messagebox(
            "Google 서버 연결 오류",
            f"Google 서버 접속이 불안정합니다.\n\n오류: {e}",
            "error",
        )
        return []
    except Exception as e:
        error_message = str(e)
        if "API key not valid" in error_message:
            app_instance.log_message(
                "오류: Google Books API 키가 유효하지 않습니다.", level="ERROR"
            )
            app_instance.show_messagebox(
                "API 키 오류",
                "Google Books API 키가 유효하지 않습니다. [설정]에서 올바른 키를 입력해주세요.",
                "error",
            )
        else:
            app_instance.log_message(
                f"오류: Google Books API 검색 중 예기치 않은 오류: {e}", level="ERROR"
            )
        return []
