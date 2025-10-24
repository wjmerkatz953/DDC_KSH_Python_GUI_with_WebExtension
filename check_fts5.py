# -*- coding: utf-8 -*-
import sqlite3
import sys

# UTF-8 출력 설정
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# FTS5 테이블 존재 확인
conn = sqlite3.connect('kdc_ddc_mapping.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mapping_data_fts'")
result = cursor.fetchone()

if result:
    print("[OK] FTS5 table exists: mapping_data_fts")

    # FTS5 테이블 행 수 확인
    cursor.execute("SELECT COUNT(*) FROM mapping_data_fts")
    count = cursor.fetchone()[0]
    print(f"   - FTS5 index entries: {count:,}")

    # 일반 테이블 행 수 확인
    cursor.execute("SELECT COUNT(*) FROM mapping_data")
    total = cursor.fetchone()[0]
    print(f"   - Total biblio data: {total:,}")

    if count < total:
        print(f"[WARNING] FTS5 index incomplete! Missing: {total - count:,}")
    else:
        print("[OK] FTS5 index is complete")
else:
    print("[ERROR] FTS5 table not found - needs creation")

conn.close()
