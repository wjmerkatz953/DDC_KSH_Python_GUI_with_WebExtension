# -*- coding: utf-8 -*-
import sqlite3
import time
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('nlk_concepts.sqlite')
cursor = conn.cursor()

# 테스트 키워드들
test_keywords = ['한국', '경제', '미술', '물리학']

for keyword in test_keywords:
    print(f"\n{'='*60}")
    print(f"Testing keyword: '{keyword}'")
    print(f"{'='*60}")

    normalized = keyword.replace(" ", "")

    # 1. 기존 방식: LIKE '%keyword%' (느림)
    start = time.time()
    cursor.execute("""
        SELECT COUNT(DISTINCT concept_id)
        FROM literal_props
        WHERE concept_id LIKE 'nlk:KSH%'
        AND prop IN ('prefLabel', 'label', 'altLabel')
        AND value_normalized LIKE ?
    """, (f'%{normalized}%',))
    count_old = cursor.fetchone()[0]
    time_old = time.time() - start
    print(f"[OLD - LIKE '%...%'] {count_old:,} concepts in {time_old:.3f}s")

    # 2. 새 방식: LIKE 'keyword%' OR LIKE '%keyword%' (빠름)
    start = time.time()
    cursor.execute("""
        SELECT COUNT(DISTINCT concept_id)
        FROM literal_props
        WHERE concept_id LIKE 'nlk:KSH%'
        AND prop IN ('prefLabel', 'label', 'altLabel')
        AND (value_normalized LIKE ? OR value_normalized LIKE ?)
    """, (f'{normalized}%', f'%{normalized}%'))
    count_new = cursor.fetchone()[0]
    time_new = time.time() - start
    print(f"[NEW - Optimized] {count_new:,} concepts in {time_new:.3f}s")

    speedup = time_old / time_new if time_new > 0 else 0
    print(f"Speedup: {speedup:.1f}x faster")

conn.close()
