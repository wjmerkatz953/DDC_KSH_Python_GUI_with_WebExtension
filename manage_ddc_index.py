# 파일명: manage_ddc_index.py (v3.1 - 권장 최종안)
#
# 변경점 요약:
# - 대량 삽입 후 FTS5 세그먼트 최적화: INSERT INTO ddc_keyword_fts('optimize')
# - DatabaseManager의 _get_dewey_connection()이 row_factory=sqlite3.Row를 이미 설정함
#   (별도 설정 불필요)  # see database_manager.py
#
# 사용법:
#   $ python manage_ddc_index.py
#
# 효과:
# - 인덱스 재구축 후 쿼리 성능/파일 단편화 개선

import json
import time
from database_manager import DatabaseManager


def build_ddc_english_keyword_index(db_manager: DatabaseManager):
    print("🚀 DDC 영어 키워드 FTS5 인덱스 구축을 시작합니다 (v3.1)...")
    conn = None
    try:
        conn = db_manager._get_dewey_connection()
        cursor = conn.cursor()

        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM ddc_keyword")
        print("... 기존 키워드 데이터를 초기화했습니다.")

        cursor.execute("SELECT raw_json FROM dewey_cache")
        all_cache = cursor.fetchall()
        print(f"... {len(all_cache):,}개의 원본 데이터를 불러왔습니다.")

        keyword_entries = []
        for row in all_cache:
            try:
                data = json.loads(row["raw_json"])
                iri = data.get("id")
                ddc_code = data.get("notation")
                if not ddc_code or not iri:
                    continue

                # prefLabel(en)
                if "prefLabel" in data and "en" in data["prefLabel"]:
                    keyword = data["prefLabel"]["en"].strip()
                    if keyword:
                        keyword_entries.append((iri, ddc_code, keyword, "pref"))

                # altLabel(en)
                if "altLabel" in data and "en" in data["altLabel"]:
                    labels = data["altLabel"]["en"]
                    alt_labels = labels if isinstance(labels, list) else [labels]
                    for label in alt_labels:
                        keyword = label.strip()
                        if keyword:
                            keyword_entries.append((iri, ddc_code, keyword, "alt"))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        # 유니크 처리(입력 안정화)
        unique_entries = list(dict.fromkeys(keyword_entries))
        print(f"... {len(unique_entries):,}개의 유니크한 영어 키워드를 추출했습니다.")

        # 대량 삽입
        inserted_count = 0
        if unique_entries:
            cursor.executemany(
                "INSERT OR IGNORE INTO ddc_keyword (iri, ddc, keyword, term_type) VALUES (?, ?, ?, ?)",
                unique_entries,
            )
            inserted_count = len(unique_entries)
            print(
                f"✅ 총 {inserted_count:,}개의 키워드를 ddc_keyword 테이블에 저장했습니다!"
            )

        # 🔧 FTS 세그먼트 최적화 (권장)
        cursor.execute(
            "INSERT INTO ddc_keyword_fts(ddc_keyword_fts) VALUES('optimize')"
        )
        print("... FTS5 optimize 수행 완료")

        conn.commit()
        return inserted_count

    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


# --- 스크립트 실행 부분 ---
if __name__ == "__main__":
    # 메인 앱과 동일한 DB 경로를 사용하도록 설정합니다.
    concepts_db_path = "nlk_concepts.sqlite"
    mapping_db_path = "kdc_ddc_mapping.db"

    print("데이터베이스 관리자 초기화 중...")
    db_manager_instance = DatabaseManager(
        concepts_db_path=concepts_db_path, kdc_ddc_mapping_db_path=mapping_db_path
    )

    start_time = time.time()

    # 인덱스 구축
    build_ddc_english_keyword_index(db_manager_instance)

    end_time = time.time()
    print(f"\n총 소요 시간: {end_time - start_time:.2f}초")
