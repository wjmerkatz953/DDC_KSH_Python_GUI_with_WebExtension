# -*- coding: utf-8 -*-
# 파일명: Search_Author_Check.py
# 버전: v2.0.0
# 생성일: 2025-10-31
# 설명: nlk_biblio.sqlite 검색 래퍼 (search_common_manager 통합)

from search_common_manager import SearchCommonManager


def search_nlk_biblio(
    title_query=None,
    author_query=None,
    kac_query=None,
    year_query=None,
    app_instance=None,
    db_manager=None,
):
    """
    nlk_biblio.sqlite 데이터베이스에서 서지 정보를 검색합니다.

    ✅ 이 함수는 search_common_manager.SearchCommonManager의 래퍼입니다.
    ✅ 복수 검색 지원:
    - title_query에 여러 제목을 줄바꿈으로 구분하여 입력 가능
    - 단일 FTS5 쿼리로 일괄 검색

    Args:
        title_query (str): 제목 검색어 (줄바꿈으로 여러 개 가능)
        author_query (str): 저자 검색어
        kac_query (str): KAC 코드 검색어 (줄바꿈으로 여러 개 가능)
        year_query (str): 연도 검색어
        app_instance: 앱 인스턴스 (로깅용)
        db_manager: DB 관리자 (필수)

    Returns:
        list[dict]: 검색 결과 레코드 리스트
    """
    # 입력 검증
    if not db_manager:
        if app_instance:
            app_instance.log_message(
                "오류: db_manager가 제공되지 않았습니다.", "ERROR"
            )
        return []

    if not any([title_query, author_query, kac_query, year_query]):
        if app_instance:
            app_instance.log_message(
                "오류: 최소 하나의 검색어를 입력해야 합니다.", "ERROR"
            )
        return []

    try:
        # SearchCommonManager 인스턴스 생성
        search_manager = SearchCommonManager(db_manager)

        # 로깅 (옵션)
        if app_instance:
            search_terms = []
            if title_query:
                title_count = len(
                    [t for t in title_query.split("\n") if t.strip()]
                )
                search_terms.append(f"제목 {title_count}개")
            if author_query:
                search_terms.append(f"저자: {author_query}")
            if kac_query:
                kac_count = len([k for k in kac_query.split("\n") if k.strip()])
                search_terms.append(f"KAC {kac_count}개")
            if year_query:
                search_terms.append(f"연도: {year_query}")

            app_instance.log_message(
                f"정보: NLK Biblio 검색 시작 - {', '.join(search_terms)}", "INFO"
            )

        # 검색 실행
        results = search_manager.search_nlk_biblio(
            title_query=title_query,
            author_query=author_query,
            kac_query=kac_query,
            year_query=year_query,
        )

        # 결과 로깅
        if app_instance:
            app_instance.log_message(
                f"정보: 검색 완료. {len(results)}건 결과 반환.", "INFO"
            )

        return results

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 검색 중 예상치 못한 오류 발생: {e}", "ERROR"
            )
        import traceback
        traceback.print_exc()
        return []
