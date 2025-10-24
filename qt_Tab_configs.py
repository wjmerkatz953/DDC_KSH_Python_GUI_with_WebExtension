# qt_Tab_configs.py
# -*- coding: utf-8 -*-
"""
모든 검색 탭의 설정을 중앙에서 관리하는 파일
"""
# 각 탭이 사용할 검색 함수들을 임포트합니다.
# (앞으로 추가될 모든 탭의 검색 함수를 이곳으로 가져옵니다)

from Search_NLK import search_nlk_catalog
from search_orchestrator import (
    search_lc_orchestrated,
    search_ndl_cinii_integrated,  # 👈 [수정] 임포트 경로 명확화
    search_global_integrated,
    search_western_integrated,
)
from Search_Legal_deposit import search_legal_deposit_catalog
from Search_Naver import search_naver_catalog  # 👈 [추가] 네이버 검색 함수 임포트
from search_orchestrator import search_kac_authorities_orchestrated  # 👈 [추가]
from search_orchestrator import search_brief_works_orchestrated  # 👈 [추가]
from Search_KSH_Lite import (
    run_ksh_lite_extraction,
)  # ✅ [핵심 수정] KSH Lite 검색 함수 임포트
from Search_ISNI_Detailed import scrape_isni_detailed_full_data
from Search_KSH_Local import search_ksh_local_orchestrated
from search_query_manager import SearchQueryManager
import re

# ✅ [핵심 수정] Mock/실제 서버 선택 로직을 tab_configs에도 적용
USE_MOCK_DATA = False  # qt_TabView_Example.py와 동일하게 설정

if USE_MOCK_DATA:
    from mock_backend import search_lc_orchestrated_mock as search_lc_orchestrated
else:
    from search_orchestrator import search_lc_orchestrated


# ========================================
# DDC Label 추가 래퍼 함수들
# ========================================


def _add_ddc_labels_to_results(results, ddc_column_name, db_manager):
    """
    검색 결과 리스트에 DDC Label을 추가하는 헬퍼 함수

    Args:
        results: 검색 결과 리스트 (딕셔너리 리스트)
        ddc_column_name: DDC 번호가 있는 컬럼명 (예: "082", "DDC")
        db_manager: DatabaseManager 인스턴스

    Returns:
        DDC Label이 추가된 결과 리스트
    """
    if not results or not db_manager:
        return results

    sqm = SearchQueryManager(db_manager)

    for result in results:
        ddc_value = result.get(ddc_column_name, "")

        # DDC 값에서 실제 DDC 번호 추출 (MARC 형식 처리)
        if ddc_value and str(ddc_value).strip():
            # "$a 320.011 $2 23" 같은 MARC 형식에서 DDC 번호만 추출
            ddc_numbers = []

            # $a 서브필드에서 DDC 번호 추출
            if "$a" in str(ddc_value):
                matches = re.findall(r"\$a\s*([0-9.]+)", str(ddc_value))
                ddc_numbers.extend(matches)
            # 순수 DDC 번호 형식
            elif re.match(r"^[0-9.| ]+$", str(ddc_value)):
                # 파이프 또는 공백으로 구분된 여러 DDC 처리
                ddc_numbers = [
                    num.strip()
                    for num in re.split(r"[|\s]+", str(ddc_value))
                    if num.strip()
                ]

            # DDC 번호가 추출되었으면 레이블 조회
            if ddc_numbers:
                ddc_string = " | ".join(ddc_numbers)
                result["DDC Label"] = sqm.get_ddc_labels(ddc_string)
            else:
                result["DDC Label"] = ""
        else:
            result["DDC Label"] = ""

    return results


def search_nlk_catalog_with_labels(*args, **kwargs):
    """NLK 검색 결과에 DDC Label을 추가하는 래퍼"""
    results = search_nlk_catalog(*args, **kwargs)
    db_manager = kwargs.get("db_manager")
    return _add_ddc_labels_to_results(results, "082", db_manager)


def search_western_integrated_with_labels(*args, **kwargs):
    """Western 검색 결과에 DDC Label을 추가하는 래퍼"""
    results = search_western_integrated(*args, **kwargs)
    db_manager = kwargs.get("db_manager")
    return _add_ddc_labels_to_results(results, "082", db_manager)


def search_global_integrated_with_labels(*args, **kwargs):
    """Global 검색 결과에 DDC Label을 추가하는 래퍼"""
    results = search_global_integrated(*args, **kwargs)
    db_manager = kwargs.get("db_manager")
    return _add_ddc_labels_to_results(results, "082", db_manager)


# 탭들의 '설계도'를 정의하는 중앙 딕셔너리
TAB_CONFIGURATIONS = {
    # ✅ [추가] MARC 추출 및 편집 탭 설정
    "MARC_EXTRACTOR": {
        "tab_name": "MARC 추출",
    },
    "MARC_EDITOR": {
        "tab_name": "MARC 로직 편집",
    },
    # 'XX_SEARCH'는 각 설정을 구분하기 위한 고유 키(key)입니다.
    # ✅ [추가] NLK 검색 탭 설정
    "NLK_SEARCH": {
        "tab_name": "NLK 검색",
        "tab_key": "nlk",  # ✅ 설정용 키 추가
        "column_map": [
            ("제목", "제목"),
            ("저자", "저자"),
            ("650 필드", "650 필드"),
            ("KDC", "KDC"),
            ("082", "082"),
            ("DDC Label", "DDC Label"),  # ✅ [신규] DDC Label 컬럼 추가
            ("출판사", "출판사"),
            ("연도", "연도"),
            ("ISBN", "ISBN"),
            ("상세 링크", "상세 링크"),
        ],
        "search_function": search_nlk_catalog_with_labels,  # ✅ [수정] 래퍼 함수 사용
    },
    # ✅ [추가] 납본 ID 검색 탭 설정
    "LEGAL_DEPOSIT_SEARCH": {
        "tab_name": "납본 ID 검색",
        "tab_key": "legal_deposit",  # ✅ 설정용 키 추가
        "column_map": [
            # 기존 UI의 컬럼명을 그대로 가져옵니다.
            ("TITLE", "TITLE"),
            ("AUTHOR", "AUTHOR"),
            ("020 필드", "020 필드"),
            ("EA_ISBN", "EA_ISBN"),
            ("EA_ADD_CODE", "EA_ADD_CODE"),
            ("SET_ISBN", "SET_ISBN"),
            ("SET_ADD_CODE", "SET_ADD_CODE"),
            ("SET_EXPRESSION", "SET_EXPRESSION"),
            ("PRE_PRICE", "PRE_PRICE"),
            ("PUBLISHER", "PUBLISHER"),
            ("EDITION_STMT", "EDITION_STMT"),
            ("KDC", "KDC"),
            ("DDC", "DDC"),
            ("PAGE", "PAGE"),
            ("BOOK_SIZE", "BOOK_SIZE"),
            ("FORM", "FORM"),
            ("PUBLISH_PREDATE", "PUBLISH_PREDATE"),
            ("SUBJECT", "SUBJECT"),
            ("EBOOK_YN", "EBOOK_YN"),
            ("CIP_YN", "CIP_YN"),
            ("PUBLISHER_URL", "PUBLISHER_URL"),
            ("INPUT_DATE", "INPUT_DATE"),
            ("UPDATE_DATE", "UPDATE_DATE"),
        ],
        "search_function": search_legal_deposit_catalog,
    },
    # ✅ [추가] NDL + CiNii 통합 검색 탭 설정
    "NDL_SEARCH": {
        "tab_name": "NDL + CiNii 검색",
        "tab_key": "ndl",  # ✅ 설정용 키 추가
        "column_map": [
            ("출처", "출처"),  # NDL vs CiNii 구분
            ("제목", "제목"),
            ("저자", "저자"),
            ("제목 번역", "제목 번역"),
            ("출판사", "출판사"),
            ("연도", "연도"),
            ("650 필드", "650 필드"),
            ("650 필드 (번역)", "650 필드 (번역)"),
            ("ISBN", "ISBN"),
            ("상세 링크", "상세 링크"),
        ],
        "search_function": search_ndl_cinii_integrated,
    },
    # ✅ [추가] Western 검색 탭 설정
    "WESTERN_SEARCH": {
        "tab_name": "Western 검색",
        "tab_key": "western",  # ✅ 설정용 키 추가
        "column_map": [
            ("출처", "출처"),
            ("제목", "제목"),
            ("저자", "저자"),
            ("082", "082"),
            ("DDC Label", "DDC Label"),  # ✅ [신규] DDC Label 컬럼 추가
            ("082 ind", "082 ind"),
            ("245 필드", "245 필드"),
            ("250", "250"),
            ("연도", "연도"),
            ("출판사", "출판사"),
            ("발행지", "발행지"),
            ("650 필드", "650 필드"),
            ("650 필드 (번역)", "650 필드 (번역)"),
            ("책소개", "책소개"),
            ("목차", "목차"),
            ("ISBN", "ISBN"),
            ("상세 링크", "상세 링크"),
        ],
        "search_function": search_western_integrated_with_labels,  # ✅ [수정] 래퍼 함수 사용
    },
    # ✅ [추가] Global 통합 검색 탭 설정
    "GLOBAL_SEARCH": {
        "tab_name": "Global 통합검색",
        "tab_key": "global",  # ✅ 설정용 키 추가
        "column_map": [
            ("출처", "출처"),
            ("제목", "제목"),
            ("저자", "저자"),
            ("082", "082"),
            ("DDC Label", "DDC Label"),  # ✅ [신규] DDC Label 컬럼 추가
            ("082 ind", "082 ind"),
            ("245 필드", "245 필드"),
            ("250", "250"),
            ("연도", "연도"),
            ("출판사", "출판사"),
            ("발행지", "발행지"),  # '출판지역' -> '발행지'로 용어 통일
            ("650 필드", "650 필드"),
            ("650 필드 (번역)", "650 필드 (번역)"),
            ("책소개", "책소개"),
            ("목차", "목차"),
            ("ISBN", "ISBN"),
            ("KDC", "KDC"),
            ("상세 링크", "상세 링크"),
        ],
        "search_function": search_global_integrated_with_labels,  # ✅ [수정] 래퍼 함수 사용
    },
    # ✅ [추가] AI 피드 검색 탭 설정
    "AI_FEED_SEARCH": {
        "tab_name": "AI 피드",
        "tab_key": "ai_feed",  # ✅ 설정용 키 추가
        "column_map": [
            ("서명", "서명"),
            ("저자", "저자"),
            ("분류 정보 취합", "분류 정보 취합"),
            ("저자소개", "저자소개"),
            ("목차", "목차"),
            ("서평", "서평"),
            ("검색소스", "검색소스"),
            ("ISBN", "ISBN"),
            ("출판사", "출판사"),
            ("출간일", "출간일"),
            ("링크", "링크"),
        ],
        "search_function": search_naver_catalog,
    },
    # ✅ [추가] Gemini DDC 분류 탭 설정
    "GEMINI_DDC_SEARCH": {
        "tab_name": "Gemini DDC 분류",
        "intermediate_column_map": [
            ("level", "검색층위"),
            ("language", "언어"),
            ("keyword", "키워드"),
            ("search_keyword", "검색어"),
            ("rank", "순위"),
            ("ddc", "DDC"),
            ("ddc_count", "DDC등장"),
            ("ddc_label", "DDC레이블"),
            ("title", "제목"),
            ("ksh", "KSH"),
            ("term_type", "용어유형"),
        ],
        # -------------------
        # ✅ [수정] 키 이름을 'column_map'으로 변경하여 BaseSearchTab과 호환되도록 수정
        "column_map": [
            # -------------------
            ("순위", "순위"),
            ("DDC 분류번호", "DDC 분류번호"),
            ("분류 해설", "분류 해설"),
            ("DDC실제의미", "DDC실제의미"),
            ("LC Catalog Links", "LC Catalog Links"),
        ],
    },
    # ✅ [추가] Dewey 분류 검색 탭 설정
    "DEWEY_SEARCH": {"tab_name": "Dewey 분류 검색"},
    "KAC_AUTHORITIES_SEARCH": {
        "tab_name": "저자전거 검색",
        "tab_key": "dewey",  # ✅ 설정용 키 추가
        "column_map": [
            ("이름", "이름"),
            ("ISNI", "ISNI"),
            ("제어번호", "제어번호"),
            ("직업", "직업"),
            ("생몰년", "생몰년"),
            ("활동분야", "활동분야"),
            ("전체 저작물", "전체 저작물"),
            ("NLK 리소스", "NLK 리소스"),
            ("관련 기관", "관련 기관"),
            ("최근 저작물", "최근 저작물"),
            ("지역", "지역"),
            ("기관명", "기관명"),
            ("상세페이지 링크", "상세 링크"),
            ("저작물 목록 링크", "저작물 목록 링크"),
            ("성별", "성별"),
            ("국가", "국가"),
            ("기관 코드", "기관 코드"),
            ("로마자 이름", "로마자 이름"),
            ("한자 이름", "한자 이름"),
            ("조직 제어번호", "조직 제어번호"),
            ("등록 상태", "등록 상태"),
            ("ISNI 리소스", "ISNI 리소스"),
            ("ISNI 발급일", "ISNI 발급일"),
        ],
        "search_function": search_kac_authorities_orchestrated,
    },
    # ✅ [추가] 간략 저작물 정보 탭 설정
    "BRIEF_WORKS_SEARCH": {
        "tab_name": "간략 저작물 정보",
        "column_map": [
            # ✅ [핵심 수정] CTk 스타일의 키 매핑으로 변경: Data Key를 Display Name과 동일하게 설정
            ("저자명", "저자명"),
            ("KAC", "KAC"),
            ("ISNI", "ISNI"),
            ("저작물 제목", "저작물 제목"),
            ("연도", "연도"),
            ("링크", "링크"),
        ],
        "search_function": search_brief_works_orchestrated,
    },
    # ✅ [추가] 상세 저작물 정보 검색 탭 설정
    "ISNI_DETAILED_SEARCH": {
        "tab_name": "상세 저작물 정보",
        "column_map": [
            ("TITLE", "TITLE"),
            ("PUBLISH_YEAR", "PUBLISH_YEAR"),
            ("PUBLISHER", "PUBLISHER"),
            ("AUTHOR (Main)", "AUTHOR (Main)"),
            (
                "OFF_AUTHOR_LIST (공저자명 (KAC코드))",
                "OFF_AUTHOR_LIST (공저자명 (KAC코드))",
            ),
            ("SUBJECT_INFO", "SUBJECT_INFO"),
            ("KDC", "KDC"),
            ("KDC_CLASS_NO", "KDC_CLASS_NO"),
            ("LANGUAGE", "LANGUAGE"),
            ("IMAGE_URL", "IMAGE_URL"),
            ("링크", "링크"),
        ],
        "search_function": scrape_isni_detailed_full_data,
    },
    # ✅ [추가] KSH Hybrid 검색 탭 설정
    "KSH_HYBRID_SEARCH": {
        "tab_name": "KSH Hybrid",
        "column_map": [
            # (데이터 키, 화면에 표시될 이름)
            ("전체 목록 검색 결과", "전체 목록 검색 결과"),
            ("KSH 코드", "KSH 코드"),
            ("우선어", "우선어"),
            ("동의어/유사어(UF)", "동의어/유사어(UF)"),
            ("UF (로컬)", "UF (로컬)"),
            ("상위어", "상위어"),
            ("BT (로컬)", "BT (로컬)"),
            ("하위어", "하위어"),
            ("NT (로컬)", "NT (로컬)"),
            ("관련어", "관련어"),
            ("RT (로컬)", "RT (로컬)"),
            ("외국어", "외국어"),
            ("FOREIGN (로컬)", "FOREIGN (로컬)"),
            ("_url_data", "_url_data"),
            ("_url_uf", "_url_uf"),
            ("_url_bt", "_url_bt"),
            ("_url_nt", "_url_nt"),
            ("_url_rt", "_url_rt"),
            ("_url_foreign", "_url_foreign"),
        ],
        "search_function": run_ksh_lite_extraction,  # Search_KSH_Lite.py의 메인 함수
    },
    "KSH_LOCAL_SEARCH": {
        "tab_name": "KSH Local",
        # [핵심] BaseSearchTab이 인식할 수 있는 표준 키를 사용합니다.
        "search_function": search_ksh_local_orchestrated,
        "column_map": [
            ("주제명", "주제명"),
            ("Matched", "Matched"),
            ("주제모음", "주제모음"),
            ("DDC", "DDC"),
            ("KDC-Like", "KDC-Like"),
            ("관련어", "관련어"),
            ("상위어", "상위어"),
            ("하위어", "하위어"),
            ("동의어", "동의어"),
            ("KSH 링크", "KSH 링크"),
        ],
        # 하단(서지) 테이블 컬럼 맵
        "column_map_bottom": [
            # ✅ [수정] (DataFrame 컬럼명, UI에 표시될 이름) 형식으로 변경
            ("ksh_labeled", "KSH 라벨"),
            ("ddc", "DDC"),
            ("ddc_count", "DDC 출현 카운트"),
            ("ddc_label", "DDC Label"),  # ✅ [신규] DDC Label 컬럼 추가
            ("ddc_edition", "DDC판"),
            ("kdc", "KDC"),
            ("kdc_edition", "KDC판"),
            ("title", "서명"),
            ("publication_year", "발행년"),
            ("data_type", "자료유형"),
            ("source_file", "소스파일"),
            ("identifier", "식별자"),
            ("nlk_link", "NLK 링크"),
            # -------------------
        ],
        # 상단 편집 가능 컬럼 (엑셀 스타일 인라인 편집)
        "editable_columns_top": ["주제모음", "DDC", "KDC-Like"],
    },
    # ✅ [추가] Python 코드 실행 탭 설정
    "PYTHON_TAB": {
        "tab_name": "🐍 Python",
    },
    # ✅ [추가] Settings 탭 설정
    "SETTINGS": {
        "tab_name": "설정",
    },
}


# ----------------------------------------
# (선택) column_map 유효성 간단 검사
# ----------------------------------------
def _validate_column_maps(tab_configs: dict):
    for key, cfg in tab_configs.items():
        cmap = cfg.get("column_map")
        if not cmap:
            continue
        if not isinstance(cmap, list):
            raise ValueError(f"[{key}] column_map은 list여야 합니다.")
        for i, pair in enumerate(cmap):
            if (not isinstance(pair, (list, tuple))) or len(pair) != 2:
                raise ValueError(
                    f"[{key}] column_map[{i}]는 (data_key, header) 2-튜플이어야 합니다: {pair}"
                )
            data_key, header = pair
            if not isinstance(data_key, str) or not isinstance(header, str):
                raise ValueError(
                    f"[{key}] column_map[{i}]의 원소는 문자열이어야 합니다: {pair}"
                )


# 앱 초기화 시 한 번 호출
_validate_column_maps(TAB_CONFIGURATIONS)
