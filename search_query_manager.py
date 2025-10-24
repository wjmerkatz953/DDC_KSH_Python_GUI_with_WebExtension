# 파일명: search_query_manager.py
# 설명: 통합 검색 관리자 (하위 호환성 유지를 위한 래퍼 클래스)
"""search_query_manager.py
버전: v3.0.0
업데이트: 2025-10-20

[2025-10-20 업데이트 내역 - v3.0.0]
🔧 파일 분할 리팩토링
- 3,432줄 단일 파일을 3개 모듈로 분할
  * search_common_manager.py: 공용 베이스 클래스 (1,057줄)
  * search_dewey_manager.py: 듀이탭 전용 (1,063줄)
  * search_ksh_manager.py: KSH탭 전용 (1,416줄)

- SearchQueryManager는 3개 클래스를 통합하는 래퍼로 변경
- 기존 코드와 100% 하위 호환성 유지

[이전 버전 - v2.2.0]
⚡ 검색 성능 최적화 (20초 → 1초!)
- FTS5 전문 검색 인덱스 도입 (ksh_korean 컬럼)
- DDC 검색 최적화 (INDEXED BY idx_ddc_ksh)
- SELECT 쿼리 최적화 (SELECT * → 필요한 컬럼만 조회)
"""

from database_manager import DatabaseManager
from search_dewey_manager import SearchDeweyManager
from search_ksh_manager import SearchKshManager


class SearchQueryManager(SearchDeweyManager, SearchKshManager):
    """
    통합 검색 관리자 클래스

    다중 상속으로 Dewey와 KSH 기능을 모두 제공:
    - SearchDeweyManager: DDC 검색, 캐시 관리
    - SearchKshManager: KSH 개념 검색, 한글 주제명 검색
    - SearchCommonManager: 공용 서지 검색, 전처리 (상위 클래스)

    하위 호환성:
    - 기존 코드에서 `SearchQueryManager`를 그대로 사용 가능
    - 모든 메서드 시그니처 동일
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        초기화

        Args:
            db_manager: DatabaseManager 인스턴스
        """
        # 다중 상속이지만 __init__은 SearchCommonManager 것만 호출
        # (SearchDeweyManager와 SearchKshManager는 모두 SearchCommonManager를 상속)
        super().__init__(db_manager)


# 하위 호환성을 위한 별칭
SearchManager = SearchQueryManager
