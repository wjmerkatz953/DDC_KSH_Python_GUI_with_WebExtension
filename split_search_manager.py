"""
search_query_manager.py를 3개 파일로 분할하는 스크립트
"""
import sys
import re

# UTF-8 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

# 메서드 분류
DEWEY_METHODS = [
    '_cache_ddc_description', '_search_by_ddc_ranking_logic', '_search_by_ddc_with_fallback',
    '_search_ddc_by_sql_fts', '_search_ddc_from_cache', '_search_ddc_with_fallback_hierarchy',
    'get_all_ddc_labels_bulk', 'get_ddc_description_cached', 'get_ddc_labels',
    'get_dewey_by_notation', 'get_dewey_cache_entry', 'get_dewey_from_cache',
    'get_multiple_ddcs_descriptions', 'save_dewey_to_cache', 'search_ddc_by_keyword',
    'search_ddc_by_multiple_keywords'
]

KSH_METHODS = [
    '_format_korean_search_results', '_format_ksh_column_optimized', '_format_ksh_display',
    '_format_ksh_labeled_to_markup', '_get_broader_for_concept', '_get_narrower_for_concept',
    '_get_related_for_concept', '_get_synonyms_for_concept', '_search_by_korean_subject',
    '_search_by_ksh_code', 'get_concept_relations', 'get_ksh_entries',
    'get_ksh_entries_batch', 'get_ksh_entries_batch_exact', 'get_ksh_entries_exact_match',
    'search_integrated_ksh', 'search_integrated_ksh_with_relations', 'search_ksh_by_language'
]

COMMON_METHODS = [
    '__init__', '_extract_and_save_keywords', '_get_best_matched_term', '_get_broader_batch',
    '_get_clean_subject_for_sorting', '_get_narrower_batch', '_get_pref_label',
    '_get_related_batch', '_get_synonyms_batch', '_process_parentheses_for_equal_terms',
    '_save_keywords_separately', '_singularize_search_term', '_sort_by_year_and_identifier',
    '_strip_namespace', 'dedup_lang_variants', 'get_bibliographic_by_subject_name',
    'get_bibliographic_by_title', 'preprocess_search_term', 'search_bibliographic_by_subject_optimized'
]

def extract_methods(content):
    """파일에서 메서드들을 추출"""
    lines = content.split('\n')
    methods = {}
    current_method = None
    method_start = 0
    method_lines = []

    for i, line in enumerate(lines):
        # 메서드 정의 시작
        method_match = re.match(r'    def ([a-zA-Z_][a-zA-Z0-9_]*)\(', line)

        if method_match:
            # 이전 메서드 저장
            if current_method:
                methods[current_method] = {
                    'start': method_start,
                    'lines': method_lines.copy()
                }

            # 새 메서드 시작
            current_method = method_match.group(1)
            method_start = i
            method_lines = [line]
        elif current_method:
            # 클래스 종료 또는 다음 메서드 전까지
            if line and not line.startswith(' '):
                # 들여쓰기 없는 줄 = 클래스 끝
                methods[current_method] = {
                    'start': method_start,
                    'lines': method_lines.copy()
                }
                current_method = None
                method_lines = []
            else:
                method_lines.append(line)

    # 마지막 메서드 저장
    if current_method:
        methods[current_method] = {
            'start': method_start,
            'lines': method_lines.copy()
        }

    return methods

# 원본 파일 읽기
with open(r'c:\Python\search_query_manager.py', 'r', encoding='utf-8') as f:
    original_content = f.read()

lines = original_content.split('\n')

# 헤더 추출 (클래스 정의 전까지)
class_start_idx = None
for i, line in enumerate(lines):
    if line.startswith('class SearchQueryManager'):
        class_start_idx = i
        break

if class_start_idx is None:
    print("❌ 클래스 정의를 찾을 수 없습니다!")
    exit(1)

header = '\n'.join(lines[:class_start_idx])

# 메서드들 추출
methods = extract_methods(original_content)

print(f"✅ 총 {len(methods)}개 메서드 추출 완료")
print(f"   - Dewey: {len([m for m in methods if m in DEWEY_METHODS])}개")
print(f"   - KSH: {len([m for m in methods if m in KSH_METHODS])}개")
print(f"   - Common: {len([m for m in methods if m in COMMON_METHODS])}개")

# 1. search_common_manager.py 생성
common_content = header + '''

class SearchCommonManager:
    """
    검색 기능의 공용 베이스 클래스
    - 서지 검색
    - 검색어 전처리
    - 관계어 조회
    - 유틸리티 메서드
    """
'''

for method_name in COMMON_METHODS:
    if method_name in methods:
        common_content += '\n' + '\n'.join(methods[method_name]['lines']) + '\n'

with open(r'c:\Python\search_common_manager.py', 'w', encoding='utf-8') as f:
    f.write(common_content)

print(f"✅ search_common_manager.py 생성 완료 ({len(common_content.split(chr(10)))}줄)")

# 2. search_dewey_manager.py 생성
dewey_content = '''# 파일명: search_dewey_manager.py
# 설명: 듀이십진분류(DDC) 검색 전용 모듈

import pandas as pd
import re
import json
import logging
from typing import List
from database_manager import DatabaseManager
from search_common_manager import SearchCommonManager

logger = logging.getLogger("qt_main_app.database_manager")


class SearchDeweyManager(SearchCommonManager):
    """
    듀이탭 전용 검색 클래스
    - DDC 검색 및 랭킹
    - DDC 캐시 관리
    - DDC 키워드 검색
    """
'''

for method_name in DEWEY_METHODS:
    if method_name in methods:
        dewey_content += '\n' + '\n'.join(methods[method_name]['lines']) + '\n'

with open(r'c:\Python\search_dewey_manager.py', 'w', encoding='utf-8') as f:
    f.write(dewey_content)

print(f"✅ search_dewey_manager.py 생성 완료 ({len(dewey_content.split(chr(10)))}줄)")

# 3. search_ksh_manager.py 생성
ksh_content = '''# 파일명: search_ksh_manager.py
# 설명: KSH(한국주제명표목) 검색 전용 모듈

import pandas as pd
import re
import time
import logging
from typing import List
from database_manager import DatabaseManager
from search_common_manager import SearchCommonManager

logger = logging.getLogger("qt_main_app.database_manager")


class SearchKshManager(SearchCommonManager):
    """
    KSH탭 전용 검색 클래스
    - KSH 개념 검색
    - 한글 주제명 검색
    - 통합 검색
    - 개념 관계어 조회
    """
'''

for method_name in KSH_METHODS:
    if method_name in methods:
        ksh_content += '\n' + '\n'.join(methods[method_name]['lines']) + '\n'

with open(r'c:\Python\search_ksh_manager.py', 'w', encoding='utf-8') as f:
    f.write(ksh_content)

print(f"✅ search_ksh_manager.py 생성 완료 ({len(ksh_content.split(chr(10)))}줄)")

print("\n🎉 파일 분할 완료!")
print("   - search_common_manager.py (베이스 클래스)")
print("   - search_dewey_manager.py (듀이탭)")
print("   - search_ksh_manager.py (KSH탭)")
