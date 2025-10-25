# -*- coding: utf-8 -*-
"""
최종 성능 테스트: 전체 검색 파이프라인 (Concept DB + 서지 DB)
"""
import sys
import io
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 실제 앱 환경 재현
from database_manager import DatabaseManager
from search_query_manager import SearchQueryManager

print("="*70)
print("통합 검색 성능 테스트 (Concept DB FTS5 + 서지 DB FTS5)")
print("="*70)

# DB 초기화
db_manager = DatabaseManager(
    concepts_db_path="nlk_concepts.sqlite",
    kdc_ddc_mapping_db_path="kdc_ddc_mapping.db"
)

query_manager = SearchQueryManager(db_manager)

# 테스트 키워드
test_cases = [
    ("한국", "대량 결과 (600+ concepts)"),
    ("경제", "중간 결과 (1500+ concepts)"),
    ("미술", "소량 결과 (289 concepts)"),
    ("물리학", "소량 결과 (165 concepts)"),
]

print(f"\n{'키워드':<15} {'시간':<10} {'Concept':<12} {'서지':<10} {'설명'}")
print("-"*70)

for keyword, description in test_cases:
    start_time = time.time()

    df_concept, df_biblio, search_type = query_manager.search_integrated_ksh(keyword)

    elapsed = time.time() - start_time

    print(f"{keyword:<15} {elapsed:>6.2f}s    {len(df_concept):>6}개    {len(df_biblio):>6}개   {description}")

print("\n" + "="*70)
print("테스트 완료!")
print("="*70)
