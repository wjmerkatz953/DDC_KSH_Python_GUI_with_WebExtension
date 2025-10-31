#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KAC 코드가 있는 레코드만 복사하여 새 DB 생성 (빠른 방법)

DELETE보다 INSERT가 훨씬 빠릅니다!
- DELETE: 2천만 건 삭제 (느림)
- INSERT: 700만 건 복사 (빠름)

예상 소요 시간: 약 15-30분
"""

import sqlite3
import time
from pathlib import Path


def main():
    print("=" * 70)
    print("KAC 코드가 있는 레코드만 새 DB로 복사")
    print("=" * 70)
    print()

    db_path = Path("nlk_biblio.sqlite")
    new_db_path = Path("nlk_biblio_kac_only.sqlite")
    backup_path = Path("nlk_biblio_backup.sqlite")

    if not db_path.exists():
        print(f"[ERROR] 파일을 찾을 수 없습니다: {db_path}")
        return

    if new_db_path.exists():
        print(f"[WARNING] 파일이 이미 존재합니다: {new_db_path}")
        response = input("덮어쓰시겠습니까? (yes/no): ")
        if response.lower() != "yes":
            print("[CANCELED] 취소되었습니다.")
            return
        new_db_path.unlink()

    print(f"원본 DB: {db_path}")
    print(f"새 DB: {new_db_path}")
    print()

    try:
        # 원본 DB 연결
        print("[1/6] 원본 DB 연결 중...")
        source_conn = sqlite3.connect(str(db_path))
        source_cursor = source_conn.cursor()

        # 통계 확인
        source_cursor.execute("SELECT COUNT(*) FROM biblio")
        total_count = source_cursor.fetchone()[0]

        source_cursor.execute(
            """
            SELECT COUNT(*) FROM biblio
            WHERE kac_codes IS NOT NULL AND kac_codes != ''
        """
        )
        kac_count = source_cursor.fetchone()[0]

        print(f"   전체 레코드: {total_count:,}건")
        print(f"   KAC 있는 레코드: {kac_count:,}건")
        print(f"   복사 비율: {kac_count / total_count * 100:.2f}%")
        print()

        # 새 DB 생성
        print("2[OK]  새 DB 생성 중...")
        new_conn = sqlite3.connect(str(new_db_path))
        new_cursor = new_conn.cursor()

        # 테이블 스키마 복사
        print("   - 테이블 스키마 복사 중...")
        source_cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='biblio'"
        )
        schema = source_cursor.fetchone()[0]
        new_cursor.execute(schema)
        print("   [OK] 테이블 생성 완료")

        # 인덱스 스키마 복사 (나중에 생성)
        source_cursor.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type='index' AND tbl_name='biblio' AND sql IS NOT NULL
        """
        )
        indexes = [row[0] for row in source_cursor.fetchall()]

        print()
        print("3[OK]  KAC 있는 레코드 복사 중...")
        start_time = time.time()

        # 배치 복사 (빠른 처리)
        source_cursor.execute(
            """
            SELECT nlk_id, year, creator, dc_creator, dcterms_creator,
                   title, author_names, kac_codes
            FROM biblio
            WHERE kac_codes IS NOT NULL AND kac_codes != ''
        """
        )

        batch_size = 10000
        batch = []
        copied = 0

        for row in source_cursor:
            batch.append(row)
            if len(batch) >= batch_size:
                new_cursor.executemany(
                    """
                    INSERT INTO biblio
                    (nlk_id, year, creator, dc_creator, dcterms_creator,
                     title, author_names, kac_codes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    batch,
                )
                new_conn.commit()
                copied += len(batch)
                batch.clear()
                elapsed = time.time() - start_time
                rate = copied / elapsed
                eta = (kac_count - copied) / rate if rate > 0 else 0
                print(
                    f"   진행: {copied:,}/{kac_count:,}건 "
                    f"({copied/kac_count*100:.1f}%) - "
                    f"{rate:.0f}건/초 - 예상 남은 시간: {eta/60:.1f}분",
                    end="\r",
                )

        # 남은 배치 처리
        if batch:
            new_cursor.executemany(
                """
                INSERT INTO biblio
                (nlk_id, year, creator, dc_creator, dcterms_creator,
                 title, author_names, kac_codes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                batch,
            )
            new_conn.commit()
            copied += len(batch)

        elapsed = time.time() - start_time
        print()
        print(f"   [OK] 복사 완료: {copied:,}건 ({elapsed:.1f}초)")
        print()

        # 인덱스 생성
        print("4[OK]  인덱스 생성 중...")
        for i, index_sql in enumerate(indexes, 1):
            print(f"   - 인덱스 {i}/{len(indexes)} 생성 중...")
            new_cursor.execute(index_sql)
        new_conn.commit()
        print("   [OK] 인덱스 생성 완료")
        print()

        # FTS5 테이블 생성 및 인덱싱
        print("5[OK]  FTS5 전문 검색 인덱스 생성 중...")
        print("   (시간이 다소 걸릴 수 있습니다...)")

        # FTS5 가상 테이블 생성
        new_cursor.execute(
            """
            CREATE VIRTUAL TABLE biblio_title_fts USING fts5(
                nlk_id UNINDEXED,
                title,
                author_names,
                kac_codes,
                content=biblio,
                content_rowid=rowid,
                tokenize='unicode61 remove_diacritics 2'
            )
        """
        )

        # 트리거 생성
        new_cursor.execute(
            """
            CREATE TRIGGER biblio_ai AFTER INSERT ON biblio BEGIN
                INSERT INTO biblio_title_fts(rowid, nlk_id, title, author_names, kac_codes)
                VALUES (new.rowid, new.nlk_id, new.title, new.author_names, new.kac_codes);
            END
        """
        )

        new_cursor.execute(
            """
            CREATE TRIGGER biblio_ad AFTER DELETE ON biblio BEGIN
                DELETE FROM biblio_title_fts WHERE rowid = old.rowid;
            END
        """
        )

        new_cursor.execute(
            """
            CREATE TRIGGER biblio_au AFTER UPDATE ON biblio BEGIN
                UPDATE biblio_title_fts
                SET title = new.title,
                    author_names = new.author_names,
                    kac_codes = new.kac_codes
                WHERE rowid = new.rowid;
            END
        """
        )

        # FTS5 인덱스 빌드
        new_cursor.execute("INSERT INTO biblio_title_fts(biblio_title_fts) VALUES('rebuild')")
        new_conn.commit()
        print("   [OK] FTS5 인덱스 생성 완료")
        print()

        # VACUUM으로 최적화
        print("6[OK]  DB 최적화 (VACUUM) 중...")
        new_conn.execute("VACUUM")
        print("   [OK] 최적화 완료")
        print()

        # 최종 확인
        new_cursor.execute("SELECT COUNT(*) FROM biblio")
        final_count = new_cursor.fetchone()[0]

        print("=" * 70)
        print("[OK] 새 DB 생성 완료!")
        print("=" * 70)
        print(f"최종 레코드 수: {final_count:,}건")
        print(f"파일 크기: {new_db_path.stat().st_size / 1024 / 1024:.1f} MB")
        print()

        # DB 닫기
        source_conn.close()
        new_conn.close()

        # 교체 안내
        print("=" * 70)
        print("다음 단계:")
        print("=" * 70)
        print()
        print("1. 새 DB 테스트:")
        print(f"   python -c \"import sqlite3; conn = sqlite3.connect('{new_db_path}'); ")
        print(f"   cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM biblio'); ")
        print(f"   print(f'레코드 수: {{cursor.fetchone()[0]:,}}'); conn.close()\"")
        print()
        print("2. 기존 DB 백업:")
        print(f"   move {db_path} {backup_path}")
        print()
        print("3. 새 DB로 교체:")
        print(f"   move {new_db_path} {db_path}")
        print()

    except Exception as e:
        print(f"\n[OK] 오류 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
