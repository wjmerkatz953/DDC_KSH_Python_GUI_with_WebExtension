# -*- coding: utf-8 -*-
# 파일명: import_alt_terms_stable.py
# 설명: (최종 안정화 버전) CSV 파일의 DDC altLabel 용어를 DB에 안전하게 추가합니다.
#       - 컬럼 순서에 상관없이 헤더 이름을 기준으로 동작합니다.
#       - 중복 데이터는 건너뛰고, 사용자 데이터('user')로 등록하여 보호합니다.

import pandas as pd
import time
import sqlite3
import os


def add_source_column_if_not_exists(cursor):
    """ddc_keyword 테이블에 'source' 컬럼이 없으면 자동으로 추가합니다."""
    cursor.execute("PRAGMA table_info(ddc_keyword)")
    columns = [col[1] for col in cursor.fetchall()]
    if "source" not in columns:
        print("INFO: 'ddc_keyword' 테이블에 'source' 컬럼을 추가합니다...")
        cursor.execute("ALTER TABLE ddc_keyword ADD COLUMN source TEXT DEFAULT 'auto'")
        conn.commit()
        print("INFO: 컬럼 추가 완료.")


def import_alt_terms_from_csv(csv_path: str = "new_alt_ddc_keyword.csv"):
    db_file = "dewey_cache.db"
    if not os.path.exists(db_file):
        print(f"❌ 오류: 데이터베이스 파일('{db_file}')을 찾을 수 없습니다.")
        return

    print("데이터베이스 연결 중...")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # [안전장치] 스크립트 호환성을 위해 'source' 컬럼 존재 여부를 항상 확인합니다.
    add_source_column_if_not_exists(cursor)

    print(f"\n📖 CSV 파일에서 데이터를 읽습니다: {csv_path}")
    try:
        df = pd.read_csv(csv_path, encoding="utf-8", keep_default_na=False)
        print(f"✅ 총 {len(df):,}개의 레코드를 읽었습니다.")

        print("\n🚀 데이터 업로드 시작...")
        start_time = time.time()

        cursor.execute("BEGIN TRANSACTION")

        inserted = 0
        ignored_duplicate = 0
        skipped_empty = 0

        for idx, row in df.iterrows():
            try:
                # ✅ [핵심] 컬럼 헤더 이름과 변수 이름을 일치시켜 순서가 바뀌어도 올바르게 동작합니다.
                iri = str(row["iri"]).strip()
                ddc = str(row["ddc"]).strip()
                keyword = str(row["keyword"]).strip()
                term_type = str(row["term_type"]).strip()

                if not iri or not ddc or not keyword:
                    skipped_empty += 1
                    continue

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO ddc_keyword (iri, ddc, keyword, term_type, source)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (iri, ddc, keyword, term_type, "user"),
                )

                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    ignored_duplicate += 1

            except KeyError as e:
                print(
                    f"   ❌ 오류: CSV 파일에 필수 헤더({e})가 없습니다. 트랜잭션을 롤백합니다."
                )
                conn.rollback()
                conn.close()
                return
            except Exception as e:
                print(f"   경고: {idx + 1}번째 행 처리 실패 - {e}")
                skipped_empty += 1
                continue

        conn.commit()
        end_time = time.time()
        elapsed = end_time - start_time

        print(f"\n✅ 업로드 완료!")
        print(f"   - 성공적으로 추가됨: {inserted:,}개")
        print(f"   - 중복되어 건너뜀: {ignored_duplicate:,}개")
        print(f"   - 빈 값이 있어 건너뜀: {skipped_empty:,}개")
        print(f"   - 소요 시간: {elapsed:.2f}초")

        cursor.execute("SELECT COUNT(*) FROM ddc_keyword WHERE source = 'user'")
        total_user = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM ddc_keyword WHERE source = 'auto'")
        total_auto = cursor.fetchone()[0]

        print(f"\n📊 최종 DB 통계:")
        print(f"   - 앱 자동 수집 키워드 (auto): {total_auto:,}개")
        print(f"   - 사용자 추가 키워드 (user): {total_user:,}개")
        print(f"   - 총계: {total_auto + total_user:,}개")

        conn.close()

    except FileNotFoundError:
        print(f"❌ 오류: 파일을 찾을 수 없습니다: {csv_path}")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    csv_file = "new_alt_ddc_keyword.csv"
    print("=" * 60)
    print("altLabel 용어 일괄 업로드 스크립트 (Stable - 안전 추가 버전)")
    print("=" * 60)
    import_alt_terms_from_csv(csv_file)
