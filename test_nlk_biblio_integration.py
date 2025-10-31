# -*- coding: utf-8 -*-
"""
NLK Biblio 검색 통합 테스트

database_manager + search_common_manager 아키텍처 검증
"""

import sys
from database_manager import DatabaseManager
from Search_Author_Check import search_nlk_biblio


def main():
    print("=" * 60)
    print("NLK Biblio 검색 통합 테스트")
    print("=" * 60)
    print()

    # DatabaseManager 초기화
    print("1. DatabaseManager 초기화...")
    db_manager = DatabaseManager(
        concepts_db_path="nlk_concepts.sqlite",
        kdc_ddc_mapping_db_path="kdc_ddc_mapping.db",
    )
    print("   ✅ 초기화 완료")
    print()

    # 테스트 케이스
    test_cases = [
        {
            "name": "단일 제목 검색",
            "params": {"title_query": "도서관", "db_manager": db_manager},
        },
        {
            "name": "복수 제목 검색",
            "params": {
                "title_query": "도서관\n목록\n분류",
                "db_manager": db_manager,
            },
        },
        {
            "name": "저자 검색",
            "params": {"author_query": "황전후", "db_manager": db_manager},
        },
        {
            "name": "KAC 코드 검색 (nlk: 프리픽스 포함)",
            "params": {"kac_query": "nlk:KAC200702805", "db_manager": db_manager},
        },
        {
            "name": "KAC 코드 검색 (프리픽스 없이)",
            "params": {"kac_query": "KAC200702805", "db_manager": db_manager},
        },
        {
            "name": "연도 검색",
            "params": {"year_query": "2020", "db_manager": db_manager},
        },
    ]

    # 테스트 실행
    for i, test in enumerate(test_cases, 1):
        print(f"{i}. {test['name']}:")
        try:
            results = search_nlk_biblio(**test["params"])
            print(f"   ✅ 결과: {len(results)}건")

            # 첫 번째 결과 샘플 출력
            if results:
                first = results[0]
                print(f"   📄 샘플:")
                print(f"      제목: {first.get('제목', '')[:50]}")
                print(f"      저자: {first.get('저자', '')[:30]}")
                print(f"      KAC: {first.get('KAC 코드', '')[:30]}")
                print(f"      연도: {first.get('연도', '')}")

        except Exception as e:
            print(f"   ❌ 오류: {e}")
            import traceback

            traceback.print_exc()

        print()

    print("=" * 60)
    print("테스트 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
