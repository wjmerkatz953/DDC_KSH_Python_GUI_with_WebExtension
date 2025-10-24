# -*- coding: utf-8 -*-
import sqlite3
import time
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('kdc_ddc_mapping.db')
cursor = conn.cursor()

# 테스트 키워드들
test_keywords = ['한국', '경제', '미술', '물리학']

for keyword in test_keywords:
    print(f"\n{'='*60}")
    print(f"Testing keyword: '{keyword}'")
    print(f"{'='*60}")

    # 1. FTS5 MATCH 방식 (권장)
    start = time.time()
    fts_query = f'"{keyword}" OR {keyword}*'
    cursor.execute("""
        SELECT COUNT(*)
        FROM mapping_data_fts f
        JOIN mapping_data m ON f.rowid = m.rowid
        WHERE mapping_data_fts MATCH ?
    """, (fts_query,))
    count_fts = cursor.fetchone()[0]
    time_fts = time.time() - start
    print(f"[FTS5 MATCH] {count_fts:,} results in {time_fts:.3f}s")

    # 2. LIKE 방식 (기존 - 느림)
    start = time.time()
    cursor.execute("""
        SELECT COUNT(*)
        FROM mapping_data
        WHERE ksh_korean LIKE ?
    """, (f'%{keyword}%',))
    count_like = cursor.fetchone()[0]
    time_like = time.time() - start
    print(f"[LIKE] {count_like:,} results in {time_like:.3f}s")

    speedup = time_like / time_fts if time_fts > 0 else 0
    print(f"Speedup: {speedup:.1f}x faster")

conn.close()
