# -*- coding: utf-8 -*-
# Version: v2.0.1
# 수정일시: 2025-08-03 19:17 KST (NDL 검색 시 db_manager 인자 전달)

"""
search_orchestrator.py - 다양한 검색 로직 (ISBN/ISNI/KAC, LC, NDL)을 통합하고 조정합니다.
버전: 2.0.0 - GAS 로직 완전 포팅
생성일: 2025-07-19
수정일시: 2025-07-31 (GAS 우수 로직 완전 교체)
"""
import Search_Naver
import Search_CiNii
import time
import requests.exceptions
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)  # 👈 [추가] 병렬 처리용 임포트

# 새로운 저수준 API 클라이언트 함수 임포트
import qt_api_clients

# LC 및 NDL 검색 로직 모듈 임포트
import Search_LC
import Search_NDL
from Search_KAC_Authorities import run_full_extraction, run_multiple_kac_search

# ✅ [추가] Global 통합검색에 필요한 모든 검색 모듈을 임포트합니다.
from Search_DNB import search_dnb_catalog
from Search_BNF import search_bnf_catalog
from Search_BNE import search_bne_catalog
from Search_Google import search_google_books_api
from Search_Harvard import search_harvard_library
from Search_MIT import search_mit_library
from Search_Princeton import search_princeton_library
from Search_UPenn import search_upenn_library
import Search_CiNii
from Search_NLK import search_nlk_catalog
from Search_Cornell import search_cornell_library


def search_by_isbn(isbn_to_search, app_instance):
    """
    ISBN을 사용하여 저자의 ISNI 및 KAC 코드를 검색하고,
    국립중앙도서관 LOD에서 해당 저자의 저작 목록을 가져와 반환합니다.
    GAS 병렬처리 로직 적용
    Args:
        isbn_to_search (str): 검색할 ISBN.
        app_instance: IntegratedSearchApp 클래스 인스턴스 (로그 메시지 출력을 위함).
    Returns:
        list: 각 저자에 대한 정보 (이름, ISNI, KAC, 저작 목록) 딕셔너리 목록.
    """
    if not isbn_to_search:
        app_instance.log_message("오류: 검색할 ISBN이 비어있습니다.", level="ERROR")
        return []

    app_instance.log_message(
        f"정보: ISNI/KAC 및 저작 목록 검색 시작 (ISBN: {isbn_to_search})"
    )
    app_instance.update_progress(10)

    # GAS 로직 적용: NLK ISNI 검색 목록 페이지에서 ISNI 번호 추출
    nlk_isni_search_list_url = f"https://www.nl.go.kr/isni/search/searchIsniList?page=1&search_type=detail&person_job_list=&activity_list=&region_list=&org_type_list=&ac_type=0&detail_name=&detail_isni_num=&detail_isni=&detail_ac_control_no=&identiType=&identi_no=&detail_birth=&detail_death=&detail_activity=&PERSON_JOB=&detail_org_type=&detail_region=&detail_region_view=&detail_related_org=&detail_resource_name=&detail_identiType=ISBN&detail_identiNo={isbn_to_search}+&detail_keyword="

    isni_list_html_content = qt_api_clients.fetch_content(
        nlk_isni_search_list_url, "NLK ISNI 검색 목록", app_instance
    )

    if not isni_list_html_content:
        if app_instance.stop_search_flag.is_set():
            return []
        app_instance.log_message(
            "오류: ISNI 검색 오류: NLK ISNI 목록 페이지 접근 실패.", level="ERROR"
        )
        return []

    # GAS의 향상된 ISNI 추출 로직 사용
    unique_isnis = qt_api_clients.extract_isni_numbers(isni_list_html_content)

    if not unique_isnis:
        app_instance.log_message("정보: ISNI 번호를 찾을 수 없습니다.")
        return []

    app_instance.log_message(f"정보: 추출된 고유 ISNI 번호: {unique_isnis}")
    app_instance.update_progress(20)

    # 🚀 GAS 병렬처리 로직 적용: 모든 저자 데이터 동시 수집
    author_data_list = qt_api_clients._fetch_multiple_author_data_parallel(
        unique_isnis, app_instance
    )

    if app_instance.stop_search_flag.is_set():
        app_instance.log_message(
            "정보: ISBN 기반 ISNI/KAC 검색이 중단되었습니다. 현재까지의 결과 반환.",
            level="INFO",
        )
        return author_data_list

    app_instance.log_message("정보: ISNI/KAC 및 저작 목록 검색 완료.")
    app_instance.update_progress(100)
    return author_data_list


def search_by_isni(isni_code, app_instance):
    """
    ISNI 번호를 사용하여 저자 정보를 검색하고 저작 목록을 가져옵니다.
    GAS 개선 로직 적용
    Args:
        isni_code (str): 검색할 ISNI 번호.
        app_instance: IntegratedSearchApp 클래스 인스턴스 (로그 메시지 출력을 위함).
    Returns:
        list: 각 저자에 대한 정보 (이름, ISNI, KAC, 저작 목록) 딕셔너리 목록.
    """
    app_instance.update_progress(10)

    if app_instance.stop_search_flag.is_set():
        return []

    # GAS 로직 적용: 단일 저자 데이터 수집
    author_data = qt_api_clients._fetch_and_process_single_author_data(
        input_isni=isni_code, input_kac=None, app_instance=app_instance
    )

    if app_instance.stop_search_flag.is_set():
        app_instance.log_message("정보: ISNI 기반 검색이 중단되었습니다.", level="INFO")
        return [] if not author_data else [author_data]

    app_instance.update_progress(100)
    return [author_data] if author_data else []


def search_by_kac(kac_code, app_instance, isni_code="없음"):
    """
    KAC 코드를 사용하여 저자 정보를 검색하고 저작 목록을 가져옵니다.
    GAS 개선 로직 적용
    Args:
        kac_code (str): 검색할 KAC 코드.
        app_instance: IntegratedSearchApp 클래스 인스턴스 (로그 메시지 출력을 위함).
        isni_code (str): (선택 사항) 이미 알고 있는 ISNI 번호.
    Returns:
        list: 각 저자에 대한 정보 (이름, ISNI, KAC, 저작 목록) 딕셔너리 목록.
    """
    app_instance.update_progress(10)

    if app_instance.stop_search_flag.is_set():
        return []

    # GAS 로직 적용: 단일 저자 데이터 수집
    author_data = qt_api_clients._fetch_and_process_single_author_data(
        input_isni=isni_code if isni_code != "없음" else None,
        input_kac=kac_code,
        app_instance=app_instance,
    )

    if app_instance.stop_search_flag.is_set():
        app_instance.log_message("정보: KAC 기반 검색이 중단되었습니다.", level="INFO")
        return [] if not author_data else [author_data]

    app_instance.update_progress(100)
    return [author_data] if author_data else []


def search_lc_orchestrated(
    title_query, author_query, isbn_query, year_query=None, app_instance=None
):
    """
    LC 검색을 오케스트레이션합니다.
    Args:
        title_query (str): 검색할 제목 쿼리.
        author_query (str): 검색할 저자 쿼리.
        isbn_query (str): 검색할 ISBN 쿼리.
        year_query (str, optional): 검색할 출판연도 쿼리. 기본값: None
        app_instance (object, optional): GUI 애플리케이션 인스턴스.
    Returns:
        list: LC 검색 결과 레코드 목록.
    """
    app_instance.log_message("정보: LC 검색 오케스트레이션 시작.")
    results = Search_LC.search_lc_catalog(
        isbn_query, title_query, author_query, year_query, app_instance
    )
    if app_instance.stop_search_flag.is_set():
        app_instance.log_message(
            "정보: LC 검색 오케스트레이션이 중단되었습니다. 현재까지의 결과 반환.",
            level="INFO",
        )
        return results
    app_instance.log_message("정보: LC 검색 오케스트레이션 완료.")
    return results


def search_ndl_orchestrated(
    title_query, author_query, isbn_query, year_query, app_instance, db_manager
):
    """
    NDL 검색을 오케스트레이션합니다.
    Args:
        title_query (str): 검색할 제목 쿼리.
        author_query (str): 검색할 저자 쿼리.
        isbn_query (str): 검색할 ISBN 쿼리.
        year_query (str): 검색할 발행연도 쿼리.
        app_instance (object): GUI 애플리케이션 인스턴스.
        db_manager (DatabaseManager): DatabaseManager 인스턴스.
    Returns:
        list: NDL 검색 결과 레코드 목록.
    """
    app_instance.log_message("정보: NDL 검색 오케스트레이션 시작.")
    # ❗ 수정: db_manager와 year_query를 search_ndl_catalog 함수에 전달
    results = Search_NDL.search_ndl_catalog(
        title_query, author_query, isbn_query, year_query, app_instance, db_manager
    )
    if app_instance.stop_search_flag.is_set():
        app_instance.log_message(
            "정보: NDL 검색 오케스트레이션이 중단되었습니다. 현재까지의 결과 반환.",
            level="INFO",
        )
        return results
    app_instance.log_message("정보: NDL 검색 오케스트레이션 완료.")
    return results


# search_orchestrator.py 파일 끝에 추가할 함수
def search_naver_orchestrated(title_query, author_query, isbn_query, app_instance):
    """
    네이버 책 API 검색을 오케스트레이션합니다.
    Args:
        title_query (str): 검색할 제목 쿼리.
        author_query (str): 검색할 저자 쿼리.
        isbn_query (str): 검색할 ISBN 쿼리.
        app_instance (object): GUI 애플리케이션 인스턴스.
    Returns:
        list: 네이버 검색 결과 레코드 목록.
    """
    app_instance.log_message("정보: 네이버 책 API 검색 오케스트레이션 시작.")

    # DatabaseManager 인스턴스 가져오기
    db_manager = app_instance.db_manager

    results = Search_Naver.search_naver_catalog(
        title_query, author_query, isbn_query, app_instance, db_manager
    )

    if app_instance.stop_search_flag.is_set():
        app_instance.log_message(
            "정보: 네이버 검색 오케스트레이션이 중단되었습니다. 현재까지의 결과 반환.",
            level="INFO",
        )
        return results

    app_instance.log_message("정보: 네이버 책 API 검색 오케스트레이션 완료.")
    return results


# ✅ [새로운 통합 검색 함수 추가]
def search_ndl_cinii_integrated(
    title_query, author_query, isbn_query, year_query, app_instance, db_manager
):
    """NDL과 CiNii 검색을 병렬로 실행하고 결과를 통합하여 반환하는 오케스트레이터"""
    if (
        hasattr(app_instance, "stop_search_flag")
        and app_instance.stop_search_flag.is_set()
    ):
        return []

    all_results = []

    def create_search_task(search_func, source_name, **kwargs):
        """검색 실행 및 출처 추가를 위한 래퍼 함수"""
        try:
            app_instance.log_message(f"정보: {source_name} 검색 시작 (병렬)")
            results = search_func(**kwargs)
            for result in results:
                result["출처"] = source_name
            return results
        except Exception as e:
            app_instance.log_message(
                f"오류: {source_name} 검색 실패: {e}", level="ERROR"
            )
            return []

    # 각 검색에 필요한 파라미터 정의
    base_params = {
        "title_query": title_query,
        "author_query": author_query,
        "isbn_query": isbn_query,
        "year_query": year_query,
        "app_instance": app_instance,
    }

    ndl_params = {**base_params, "db_manager": db_manager}
    cinii_params = base_params

    tasks = {
        "NDL": (Search_NDL.search_ndl_catalog, ndl_params),
        "CiNii": (Search_CiNii.search_cinii_books, cinii_params),
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_source = {
            executor.submit(create_search_task, func, source, **params): source
            for source, (func, params) in tasks.items()
        }

        for future in as_completed(future_to_source):
            if (
                hasattr(app_instance, "stop_search_flag")
                and app_instance.stop_search_flag.is_set()
            ):
                break
            try:
                all_results.extend(future.result())
            except Exception as e:
                source_name = future_to_source[future]
                app_instance.log_message(
                    f"오류: {source_name} 결과 수집 실패: {e}", level="ERROR"
                )

    if (
        hasattr(app_instance, "stop_search_flag")
        and app_instance.stop_search_flag.is_set()
    ):
        return []

    # 출처 우선순위 및 연도별 정렬
    def get_source_priority(source):
        return {"NDL": 1, "CiNii": 2}.get(source, 999)

    all_results.sort(
        key=lambda x: (
            get_source_priority(x.get("출처", "")),
            -(int(x.get("연도", "0")) if str(x.get("연도", "0")).isdigit() else 0),
        )
    )

    app_instance.log_message(
        f"정보: NDL + CiNii 통합 검색 완료! 총 {len(all_results)}개 결과"
    )
    return all_results


# ✅ [새로운 Global 통합 검색 함수 추가]
def search_global_integrated(
    title_query,
    author_query,
    isbn_query,
    year_query,
    ddc_query,
    app_instance,
    db_manager,
):
    """13개 이상의 국내외 도서관 DB를 병렬로 검색하고 결과를 통합하여 반환하는 오케스트레이터"""
    if (
        hasattr(app_instance, "stop_search_flag")
        and app_instance.stop_search_flag.is_set()
    ):
        return []

    all_results = []

    def create_search_task(search_func, source_name, **kwargs):
        """검색 실행 및 출처 추가를 위한 래퍼 함수"""
        try:
            if (
                hasattr(app_instance, "stop_search_flag")
                and app_instance.stop_search_flag.is_set()
            ):
                return []
            app_instance.log_message(f"정보: {source_name} 검색 시작 (병렬)")
            results = search_func(**kwargs)
            for result in results:
                result["출처"] = source_name
            return results
        except Exception as e:
            app_instance.log_message(
                f"오류: {source_name} 검색 실패: {e}", level="ERROR"
            )
            return []

    search_params = {
        "title_query": title_query,
        "author_query": author_query,
        "isbn_query": isbn_query,
        "year_query": year_query,
        "ddc_query": ddc_query,
        "app_instance": app_instance,
        "db_manager": db_manager,
    }

    # 각 검색 API가 요구하는 파라미터에 맞춰 작업을 구성합니다.
    tasks = {
        "NLK": (
            search_nlk_catalog,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "LC": (
            search_lc_orchestrated,
            {
                k: v
                for k, v in search_params.items()
                if k not in ["ddc_query", "db_manager"]
            },
        ),
        "Princeton": (
            search_princeton_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "Harvard": (
            search_harvard_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "MIT": (
            search_mit_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "Cornell": (
            search_cornell_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "DNB": (search_dnb_catalog, search_params),
        "NDL": (
            search_ndl_orchestrated,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "CiNii": (
            Search_CiNii.search_cinii_books,
            {
                k: v
                for k, v in search_params.items()
                if k not in ["ddc_query", "db_manager"]
            },
        ),
        "BNF": (search_bnf_catalog, search_params),
        "BNE": (
            search_bne_catalog,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "Google": (
            search_google_books_api,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "UPenn": (
            search_upenn_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
    }

    with ThreadPoolExecutor(max_workers=13) as executor:
        future_to_source = {
            executor.submit(create_search_task, func, source, **params): source
            for source, (func, params) in tasks.items()
        }
        for future in as_completed(future_to_source):
            if (
                hasattr(app_instance, "stop_search_flag")
                and app_instance.stop_search_flag.is_set()
            ):
                break
            try:
                all_results.extend(future.result())
            except Exception as e:
                source_name = future_to_source[future]
                app_instance.log_message(
                    f"오류: {source_name} 결과 수집 실패: {e}", level="ERROR"
                )

    if (
        hasattr(app_instance, "stop_search_flag")
        and app_instance.stop_search_flag.is_set()
    ):
        return all_results

    def get_source_priority(source):
        priority_map = {
            "NLK": 1,
            "LC": 2,
            "Harvard": 3,
            "Princeton": 4,
            "UPenn": 5,
            "Cornell": 6,
            "MIT": 7,
            "DNB": 8,
            "NDL": 9,
            "CiNii": 10,
            "BNF": 11,
            "BNE": 12,
            "Google": 13,
        }
        return priority_map.get(source, 999)

    all_results.sort(
        key=lambda x: (
            get_source_priority(x.get("출처", "")),
            -(int(x.get("연도", "0")) if str(x.get("연도", "0")).isdigit() else 0),
        )
    )

    app_instance.log_message(
        f"정보: Global 통합검색 완료! 총 {len(all_results)}개 결과"
    )
    return all_results


# ✅ [새로운 Western 통합 검색 함수 추가]
def search_western_integrated(
    title_query,
    author_query,
    isbn_query,
    year_query,
    ddc_query,
    app_instance,
    db_manager,
):
    """서양권 주요 도서관 DB를 병렬로 검색하고 결과를 통합하여 반환하는 오케스트레이터"""
    if (
        hasattr(app_instance, "stop_search_flag")
        and app_instance.stop_search_flag.is_set()
    ):
        return []

    all_results = []

    # create_search_task 래퍼 함수는 재사용
    def create_search_task(search_func, source_name, **kwargs):
        try:
            if (
                hasattr(app_instance, "stop_search_flag")
                and app_instance.stop_search_flag.is_set()
            ):
                return []
            app_instance.log_message(f"정보: {source_name} 검색 시작 (병렬)")
            results = search_func(**kwargs)
            for result in results:
                result["출처"] = source_name
            return results
        except Exception as e:
            app_instance.log_message(
                f"오류: {source_name} 검색 실패: {e}", level="ERROR"
            )
            return []

    search_params = {
        "title_query": title_query,
        "author_query": author_query,
        "isbn_query": isbn_query,
        "year_query": year_query,
        "ddc_query": ddc_query,
        "app_instance": app_instance,
        "db_manager": db_manager,
    }

    # 서양권 소스만 포함하여 작업 구성
    tasks = {
        "LC": (
            search_lc_orchestrated,
            {
                k: v
                for k, v in search_params.items()
                if k not in ["ddc_query", "db_manager"]
            },
        ),
        "Harvard": (
            search_harvard_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "MIT": (
            search_mit_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "Cornell": (
            search_cornell_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "Princeton": (
            search_princeton_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "UPenn": (
            search_upenn_library,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "DNB": (search_dnb_catalog, search_params),
        "BNF": (search_bnf_catalog, search_params),
        "BNE": (
            search_bne_catalog,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
        "Google": (
            search_google_books_api,
            {k: v for k, v in search_params.items() if k not in ["ddc_query"]},
        ),
    }

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_source = {
            executor.submit(create_search_task, func, source, **params): source
            for source, (func, params) in tasks.items()
        }
        for future in as_completed(future_to_source):
            if (
                hasattr(app_instance, "stop_search_flag")
                and app_instance.stop_search_flag.is_set()
            ):
                break
            try:
                all_results.extend(future.result())
            except Exception as e:
                source_name = future_to_source[future]
                app_instance.log_message(
                    f"오류: {source_name} 결과 수집 실패: {e}", level="ERROR"
                )

    if (
        hasattr(app_instance, "stop_search_flag")
        and app_instance.stop_search_flag.is_set()
    ):
        return all_results

    def get_source_priority(source):
        priority_map = {
            "LC": 1,
            "Harvard": 2,
            "MIT": 3,
            "Cornell": 4,
            "Princeton": 5,
            "UPenn": 6,
            "DNB": 7,
            "BNF": 8,
            "BNE": 9,
            "Google": 10,
        }
        return priority_map.get(source, 999)

    all_results.sort(
        key=lambda x: (
            get_source_priority(x.get("출처", "")),
            -(int(x.get("연도", "0")) if str(x.get("연도", "0")).isdigit() else 0),
        )
    )

    app_instance.log_message(
        f"정보: Western 통합검색 완료! 총 {len(all_results)}개 결과"
    )
    return all_results


# ✅ [새로운 저자전거 검색 오케스트레이터 함수 추가]
def search_kac_authorities_orchestrated(search_term, app_instance, db_manager):
    """입력된 검색어에 따라 단일 또는 복수 KAC 검색을 실행합니다."""
    search_term = search_term.strip()
    if not search_term:
        return []

    # 쉼표나 세미콜론으로 구분된 복수 검색어 감지
    if "," in search_term or ";" in search_term:
        search_terms = [
            term.strip() for term in re.split(r"[,;]", search_term) if term.strip()
        ]
        if len(search_terms) > 1:
            if app_instance:
                app_instance.log_message(
                    f"정보: KAC 복수 검색 감지 - {len(search_terms)}개", level="INFO"
                )
            return run_multiple_kac_search(search_terms, app_instance)

    # 단일 검색어 처리
    return run_full_extraction(search_term, app_instance)


# ✅ [새로운 간략 저작물 정보 오케스트레이터 함수 추가]
def search_brief_works_orchestrated(
    search_type, query_value, app_instance, db_manager=None
):
    """검색 유형에 따라 적절한 검색 함수를 호출하는 중계기 역할을 합니다."""
    if search_type == "ISBN":
        return search_by_isbn(query_value, app_instance)
    elif search_type == "ISNI":
        return search_by_isni(query_value, app_instance)
    elif search_type == "KAC":
        return search_by_kac(query_value, app_instance)
    else:
        if app_instance:
            app_instance.log_message(
                f"오류: 알 수 없는 검색 유형입니다: {search_type}", level="ERROR"
            )
        return []
