# -*- coding: utf-8 -*-
# 파일명: migrate_schema_final.py
# 설명: FTS5 호환성과 검색 품질을 개선한 최종 마이그레이션 스크립트
#
# 변경점 요약:
# - ddc_keyword PK를 (iri, keyword, term_type)로 확장 → pref/alt 공존 보장
# - FTS5 토크나이저/프리픽스 설정 추가: unicode61 + tokenchars=.-_ + prefix 2/3/4
# - 백업/복원 로직 유지 (term_type은 'unknown'으로 복원)
#
# 주의: dewey_cache.db에 ddc_keyword_fts가 content 테이블 모드로 연결됩니다.

import sqlite3

DB_PATH = "dewey_cache.db"


def migrate_schema_final():
    """ddc_keyword 스키마를 최종 버전으로 재구성하고 FTS5를 재생성합니다."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        print("[START] 최종 스키마 마이그레이션을 시작합니다 (Final)...")
        cursor.execute("BEGIN TRANSACTION")

        # 1) 기존 데이터 백업 (테이블 미존재 시 안전 처리)
        try:
            cursor.execute("SELECT iri, ddc, keyword FROM ddc_keyword")
            backup_data = cursor.fetchall()
            print(f"... 기존 데이터 {len(backup_data)}건 백업 완료")
        except sqlite3.OperationalError:
            backup_data = []
            print("... 기존 ddc_keyword 테이블이 없어 백업을 건너뜁니다.")

        # 2) 의존 객체 드롭
        cursor.execute("DROP TRIGGER IF EXISTS ddc_keyword_ai")
        cursor.execute("DROP TRIGGER IF EXISTS ddc_keyword_ad")
        cursor.execute("DROP TRIGGER IF EXISTS ddc_keyword_au")
        cursor.execute("DROP TABLE IF EXISTS ddc_keyword_fts")
        cursor.execute("DROP TABLE IF EXISTS ddc_keyword")
        print("... 기존 테이블 및 트리거 삭제 완료")

        # 3) ddc_keyword 테이블 재생성 (핵심 변경: PK 확장)
        cursor.execute(
            """
            CREATE TABLE ddc_keyword (
                iri       TEXT NOT NULL,
                ddc       TEXT NOT NULL,
                keyword   TEXT NOT NULL,
                term_type TEXT NOT NULL,
                PRIMARY KEY (iri, keyword, term_type)
            )
            """
        )
        print("... 최종 ddc_keyword 테이블 재생성 완료")

        # 4) FTS5 가상 테이블 + 트리거 재생성
        #    - tokenizer: unicode61 remove_diacritics=2 tokenchars=.-_
        #    - prefix: 2 3 4 (전방매칭 성능/품질 향상)
        cursor.execute(
            """
            CREATE VIRTUAL TABLE ddc_keyword_fts USING fts5(
                ddc,
                keyword,
                term_type,
                content='ddc_keyword',
                content_rowid='rowid',
                tokenize='porter unicode61'
            )
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER ddc_keyword_ai AFTER INSERT ON ddc_keyword BEGIN
                INSERT INTO ddc_keyword_fts(rowid, ddc, keyword, term_type)
                VALUES (new.rowid, new.ddc, new.keyword, new.term_type);
            END
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER ddc_keyword_ad AFTER DELETE ON ddc_keyword BEGIN
                INSERT INTO ddc_keyword_fts(ddc_keyword_fts, rowid, ddc, keyword, term_type)
                VALUES ('delete', old.rowid, old.ddc, old.keyword, old.term_type);
            END
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER ddc_keyword_au AFTER UPDATE ON ddc_keyword BEGIN
                INSERT INTO ddc_keyword_fts(ddc_keyword_fts, rowid, ddc, keyword, term_type)
                VALUES ('delete', old.rowid, old.ddc, old.keyword, old.term_type);
                INSERT INTO ddc_keyword_fts(rowid, ddc, keyword, term_type)
                VALUES (new.rowid, new.ddc, new.keyword, new.term_type);
            END
            """
        )
        print("... FTS 테이블 및 트리거 재생성 완료")

        # 5) 백업 데이터 복원 (term_type은 알 수 없으므로 'unknown'으로 기록)
        if backup_data:
            restore_list = [
                (row["iri"], row["ddc"], row["keyword"]) for row in backup_data
            ]
            cursor.executemany(
                "INSERT OR IGNORE INTO ddc_keyword (iri, ddc, keyword, term_type) VALUES (?, ?, ?, 'unknown')",
                restore_list,
            )
            print(f"... 기존 데이터 {len(restore_list)}건 복원 완료")

        conn.commit()
        print("[SUCCESS] 스키마 마이그레이션 성공!")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[ERROR] 마이그레이션 실패: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    migrate_schema_final()
