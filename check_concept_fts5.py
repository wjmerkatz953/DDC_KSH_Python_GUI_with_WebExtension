# -*- coding: utf-8 -*-
import sqlite3
import sys
import io
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('nlk_concepts.sqlite')
cursor = conn.cursor()

# FTS5 테이블 구조 확인
cursor.execute("SELECT sql FROM sqlite_master WHERE name='literal_props_fts'")
result = cursor.fetchone()
if result:
    print("=== FTS5 Table Schema ===")
    print(result[0])
    print()

# FTS5 인덱스 데이터 개수 확인
cursor.execute("SELECT COUNT(*) FROM literal_props_fts")
fts_count = cursor.fetchone()[0]
print(f"FTS5 entries: {fts_count:,}")

cursor.execute("SELECT COUNT(*) FROM literal_props WHERE concept_id LIKE 'nlk:KSH%'")
total_count = cursor.fetchone()[0]
print(f"Total literal_props (KSH): {total_count:,}")
print()

# 성능 비교: "한국" 검색
keyword = "한국"
normalized = keyword.replace(" ", "")

print(f"=== Performance Test: '{keyword}' ===")

# 1. 기존 LIKE 방식
start = time.time()
cursor.execute("""
    SELECT COUNT(DISTINCT concept_id)
    FROM literal_props
    WHERE concept_id LIKE 'nlk:KSH%'
    AND prop IN ('prefLabel', 'label', 'altLabel')
    AND (value_normalized LIKE ? OR value_normalized LIKE ?)
""", (f'{normalized}%', f'%{normalized}%'))
count_like = cursor.fetchone()[0]
time_like = time.time() - start
print(f"[LIKE] {count_like:,} concepts in {time_like:.3f}s")

# 2. FTS5 MATCH 방식
start = time.time()
cursor.execute("""
    SELECT COUNT(DISTINCT fts.concept_id)
    FROM literal_props_fts fts
    JOIN literal_props lp ON fts.rowid = lp.rowid
    WHERE lp.concept_id LIKE 'nlk:KSH%'
    AND lp.prop IN ('prefLabel', 'label', 'altLabel')
    AND literal_props_fts MATCH ?
""", (f'"{normalized}" OR {normalized}*',))
count_fts = cursor.fetchone()[0]
time_fts = time.time() - start
print(f"[FTS5] {count_fts:,} concepts in {time_fts:.3f}s")

speedup = time_like / time_fts if time_fts > 0 else 0
print(f"Speedup: {speedup:.1f}x faster")

conn.close()
