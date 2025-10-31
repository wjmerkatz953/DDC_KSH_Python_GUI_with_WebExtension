#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KAC 코드가 비어있는 레코드 삭제 스크립트

사용법:
    python cleanup_empty_kac.py --dry-run  # 삭제 전 확인만
    python cleanup_empty_kac.py --execute  # 실제 삭제
"""

import sqlite3
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="KAC 코드 비어있는 레코드 삭제")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="삭제하지 않고 확인만 합니다",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제로 삭제를 실행합니다",
    )
    parser.add_argument(
        "--db",
        default="nlk_biblio.sqlite",
        help="데이터베이스 파일 경로 (기본: nlk_biblio.sqlite)",
    )

    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        parser.print_help()
        sys.exit(1)

    print(f"데이터베이스: {args.db}")
    print("-" * 60)

    try:
        conn = sqlite3.connect(args.db)
        cursor = conn.cursor()

        # 1. 삭제 대상 확인
        cursor.execute(
            """
            SELECT COUNT(*) FROM biblio
            WHERE kac_codes IS NULL OR kac_codes = ''
        """
        )
        count_to_delete = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM biblio")
        total_count = cursor.fetchone()[0]

        print(f"전체 레코드: {total_count:,}건")
        print(f"삭제 대상 (KAC 비어있음): {count_to_delete:,}건")
        print(f"삭제 후 남을 레코드: {total_count - count_to_delete:,}건")
        print(f"삭제 비율: {count_to_delete / total_count * 100:.2f}%")
        print()

        if args.dry_run:
            print("✅ [DRY-RUN] 확인만 수행. 삭제하지 않습니다.")

            # 샘플 레코드 출력
            print("\n삭제될 샘플 레코드 (처음 5개):")
            cursor.execute(
                """
                SELECT nlk_id, title, author_names, year
                FROM biblio
                WHERE kac_codes IS NULL OR kac_codes = ''
                LIMIT 5
            """
            )
            for i, row in enumerate(cursor.fetchall(), 1):
                nlk_id, title, author, year = row
                print(f"  {i}. [{nlk_id}] {title[:50]} - {author} ({year})")

        elif args.execute:
            print("⚠️  [WARNING] 실제 삭제를 수행합니다!")
            response = input("계속하시겠습니까? (yes/no): ")

            if response.lower() != "yes":
                print("❌ 취소되었습니다.")
                sys.exit(0)

            print()
            print("🗑️  레코드 삭제 중...")
            cursor.execute(
                """
                DELETE FROM biblio
                WHERE kac_codes IS NULL OR kac_codes = ''
            """
            )
            conn.commit()
            print(f"✅ {count_to_delete:,}건 삭제 완료")

            print()
            print("🔄 FTS5 인덱스 재구축 중...")
            cursor.execute(
                "INSERT INTO biblio_title_fts(biblio_title_fts) VALUES('rebuild')"
            )
            conn.commit()
            print("✅ FTS5 인덱스 재구축 완료")

            print()
            print("🗜️  VACUUM 실행 중 (디스크 공간 회수)...")
            conn.execute("VACUUM")
            print("✅ VACUUM 완료")

            # 최종 확인
            cursor.execute("SELECT COUNT(*) FROM biblio")
            final_count = cursor.fetchone()[0]
            print()
            print(f"최종 레코드 수: {final_count:,}건")

        conn.close()
        print()
        print("=" * 60)
        print("완료")

    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
