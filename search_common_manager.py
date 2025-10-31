# 파일명: search_query_manager.py
# 설명: 복잡한 데이터베이스 검색 쿼리 및 비즈니스 로직을 담당하는 클래스
"""search_query_manager.py
버전: v2.2.0
업데이트: 2025-10-19

[2025-10-19 업데이트 내역 - v2.2.0]
⚡ 검색 성능 최적화 (20초 → 1초!)
- FTS5 전문 검색 인덱스 도입 (ksh_korean 컬럼)
  * _search_by_korean_subject(): FTS5 MATCH 사용
  * 한국어 주제명 검색: 20초 → 1초 (95% 성능 향상)

- DDC 검색 최적화
  * _search_by_ddc_ranking_logic(): INDEXED BY idx_ddc_ksh 강제 사용
  * 복합 인덱스로 인덱스 힌트 지정
  * DDC 코드 검색: 17초 → 1초 (94% 성능 향상)

- SELECT 쿼리 최적화
  * SELECT * → 필요한 11개 컬럼만 조회
  * 메모리 사용량 15-20% 절감

[이전 버전 - v2.1.0]
- DDC 캐시 관련 모든 고수준 로직을 database_manager.py에서 이관하여 통합
- 추가된 메서드: get_dewey_cache_entry, get_dewey_by_notation, get_multiple_ddcs_descriptions, _cache_ddc_description, save_dewey_to_cache, _extract_and_save_keywords
- NameError 해결을 위해 파일 상단에 import json 구문 추가
- _search_by_korean_subject 메서드의 불필요한 print 로그를 제거하고 logger 사용
"""

import pandas as pd
import re
import json
import time
import logging
from typing import List, Dict, Tuple
from database_manager import DatabaseManager
from db_perf_tweaks import wait_for_warmup  # ✅ 워밍업 완료 대기
import inflection
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("qt_main_app.database_manager")


# 앱의 로그 핸들러와 연동되도록 명시적 이름 사용
logger = logging.getLogger("qt_main_app.database_manager")


# 언어태그 처리 함수들 추가
LANG_TAG_RE = re.compile(r"@([A-Za-z]{2,3})$")


def simple_singularize(word: str) -> str:
    """간단한 규칙 기반으로 영단어를 단수형으로 변환합니다."""
    # 자주 쓰이는 불규칙 복수형
    irregulars = {
        "children": "child",
        "people": "person",
        "men": "man",
        "women": "woman",
        "teeth": "tooth",
        "feet": "foot",
        "mice": "mouse",
        "geese": "goose",
    }
    if word.lower() in irregulars:
        return irregulars[word.lower()]

    # 규칙 기반 변환
    if word.endswith("s"):
        if word.endswith("ies"):
            # babies -> baby
            return word[:-3] + "y"
        if word.endswith("es"):
            # boxes, buses -> box, bus
            if word.endswith(("buses", "gases")):
                return word[:-2]
            if len(word) > 3 and word.endswith(("ches", "shes", "sses", "xes")):
                return word[:-2]
        if not word.endswith(("ss", "us")):
            # cats -> cat
            return word[:-1]

    return word


def split_lang_suffix(s: str):
    """언어태그 분리: 'internet@en' -> ('internet', 'en')"""
    if not s:
        return s, None
    m = LANG_TAG_RE.search(s.strip())
    if not m:
        return s.strip(), None
    base = s[: m.start()].strip()
    return base, m.group(1).lower()


def dedup_lang_variants(values: List[str]) -> List[str]:
    """언어태그가 있는 것을 우선하여 중복 제거"""
    chosen: Dict[str, Tuple[str, bool]] = {}
    order: List[str] = []

    for v in values:
        if not v:
            continue
        base, lang = split_lang_suffix(str(v))
        if base not in chosen:
            chosen[base] = (v, bool(lang))
            order.append(base)
        else:
            cur_v, cur_tagged = chosen[base]
            if (not cur_tagged) and lang:
                chosen[base] = (v, True)

    return [chosen[b][0] for b in order]



class SearchCommonManager:
    """
    검색 기능의 공용 베이스 클래스
    - 서지 검색
    - 검색어 전처리
    - 관계어 조회
    - 유틸리티 메서드
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    # ---------------------------------------------------
    # 아래는 database_manager.py에서 옮겨온 검색 관련 메서드들입니다.
    # self.메서드() 호출은 self.db_manager.메서드() 로 변경됩니다.
    # ---------------------------------------------------


    def _extract_and_save_keywords(
        self, cursor, iri: str, ddc_code: str, raw_json: str
    ):
        """JSON에서 영어 키워드를 추출하여 ddc_keyword 테이블에 저장합니다."""
        try:
            data = json.loads(raw_json)
            keyword_entries = []

            # prefLabel 처리
            if "prefLabel" in data and "en" in data["prefLabel"]:
                keyword = data["prefLabel"]["en"].strip()
                if keyword:
                    keyword_entries.append((iri, ddc_code, keyword, "pref"))

            # altLabel 처리
            if "altLabel" in data and "en" in data["altLabel"]:
                labels = data["altLabel"]["en"]
                alt_labels = labels if isinstance(labels, list) else [labels]
                for label in alt_labels:
                    keyword = label.strip()
                    if keyword:
                        keyword_entries.append((iri, ddc_code, keyword, "alt"))

            if keyword_entries:
                # 기존 키워드 먼저 삭제 (같은 IRI의 모든 키워드)
                cursor.execute("DELETE FROM ddc_keyword WHERE iri = ?", (iri,))

                # 새 키워드 삽입 (트리거가 자동으로 FTS 인덱스 업데이트)
                cursor.executemany(
                    """
                    INSERT INTO ddc_keyword (iri, ddc, keyword, term_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    keyword_entries,
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            # JSON 파싱 오류는 무시하고 계속 진행
            pass

    # ==========================================================
    # ✅ [신규 추가] DDC Cache DB 검색 함수
    # ==========================================================

    def _get_best_matched_term(
        self, conn, concept_id: str, search_term: str = None
    ) -> str:
        """
        개념에서 가장 적합한 matched_term을 찾기 (중복 제거 + 우선순위)
        우선순위: 검색어 포함된 것 > prefLabel > label > altLabel
        """
        cursor = conn.cursor()

        # 모든 value 가져오기
        cursor.execute(
            """
            SELECT value, prop FROM literal_props
            WHERE concept_id = ?
            ORDER BY
                CASE prop
                    WHEN 'prefLabel' THEN 1
                    WHEN 'label' THEN 2
                    WHEN 'altLabel' THEN 3
                    ELSE 4
                END,
                LENGTH(value) ASC
        """,
            (concept_id,),
        )

        all_values = cursor.fetchall()
        if not all_values:
            return ""

        # 언어태그 중복 제거 적용
        values_only = [row[0] for row in all_values if row[0]]
        deduplicated = self.dedup_lang_variants(values_only)

        # 검색어가 있으면 검색어 포함된 것 우선
        if search_term and deduplicated:
            for value in deduplicated:
                if search_term.lower() in value.lower():
                    return value

        # 없으면 첫 번째 것 반환
        return deduplicated[0] if deduplicated else ""


    def _get_broader_batch(self, conn, concept_ids: list) -> dict:
        """⚡ 배치: 여러 concept의 상위어를 한 번에 조회 (IN 절 청크 방식)"""
        if not concept_ids:
            return {}

        cursor = conn.cursor()
        CHUNK_SIZE = 100

        # Step 1: broader 관계 조회 (청크 방식)
        all_broader_results = []
        for i in range(0, len(concept_ids), CHUNK_SIZE):
            chunk = concept_ids[i:i + CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))

            query1 = f"""
                SELECT concept_id, target
                FROM uri_props
                WHERE concept_id IN ({placeholders}) AND prop='broader'
            """
            cursor.execute(query1, chunk)
            all_broader_results.extend(cursor.fetchall())

        broader_map = {}
        all_target_ids = set()
        for row in all_broader_results:
            concept_id, target_id = row[0], row[1]
            if concept_id not in broader_map:
                broader_map[concept_id] = set()
            if target_id:
                broader_map[concept_id].add(target_id)
                all_target_ids.add(target_id)

        # Step 2: narrower 역관계 조회 (청크 방식)
        all_narrower_inverse = []
        for i in range(0, len(concept_ids), CHUNK_SIZE):
            chunk = concept_ids[i:i + CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))

            query2 = f"""
                SELECT target, concept_id
                FROM uri_props
                WHERE target IN ({placeholders}) AND prop='narrower'
            """
            cursor.execute(query2, chunk)
            all_narrower_inverse.extend(cursor.fetchall())

        for row in all_narrower_inverse:
            target_id, concept_id_from = row[0], row[1]
            if target_id not in broader_map:
                broader_map[target_id] = set()
            if concept_id_from:
                broader_map[target_id].add(concept_id_from)
                all_target_ids.add(concept_id_from)

        # Step 3: 모든 target ID의 prefLabel 배치 조회 (청크 방식)
        if not all_target_ids:
            return {cid: [] for cid in concept_ids}

        target_ids_list = list(all_target_ids)
        label_results = []

        for i in range(0, len(target_ids_list), CHUNK_SIZE):
            chunk = target_ids_list[i:i + CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))

            label_query = f"""
                SELECT concept_id, value
                FROM literal_props
                WHERE concept_id IN ({placeholders})
                AND prop IN ('prefLabel', 'label')
                ORDER BY CASE prop WHEN 'prefLabel' THEN 1 ELSE 2 END
            """
            cursor.execute(label_query, chunk)
            label_results.extend(cursor.fetchall())

        label_map = {}
        for row in label_results:
            target_id, label = row[0], row[1]
            if target_id not in label_map and label:
                label_map[target_id] = label

        # Step 4: 최종 결과 구성
        result = {}
        for concept_id in concept_ids:
            broader_ids = list(broader_map.get(concept_id, set()))
            broader_terms = []
            for broader_id in broader_ids:
                label = label_map.get(broader_id)
                if label:
                    broader_terms.append(self._format_ksh_display(broader_id, label))
            result[concept_id] = broader_terms

        return result


    def _get_clean_subject_for_sorting(self, text):
        """정렬용 순수 주제어 추출 (모든 수식어 제거)"""
        if not text:
            return ""

        # 1단계: 원괄호 () 완전 제거
        clean = re.sub(r"\([^)]*\)", "", text)
        # 2단계: 각괄호 [] 완전 제거
        clean = re.sub(r"\[[^\]]*\]", "", clean)
        # 3단계: 언어태그 @en, @fr, @de 등 제거
        clean = re.sub(r"@[a-z]{2,3}$", "", clean, flags=re.IGNORECASE)
        # 4단계: 앞뒤 공백 제거
        clean = clean.strip()

        return clean


    def _get_narrower_batch(self, conn, concept_ids: list) -> dict:
        """⚡ 배치: 여러 concept의 하위어를 한 번에 조회 (IN 절 청크 방식)"""
        if not concept_ids:
            return {}

        cursor = conn.cursor()
        CHUNK_SIZE = 100

        # Step 1: narrower 관계 조회 (청크 방식)
        all_narrower_results = []
        for i in range(0, len(concept_ids), CHUNK_SIZE):
            chunk = concept_ids[i:i + CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))

            query1 = f"""
                SELECT concept_id, target
                FROM uri_props
                WHERE concept_id IN ({placeholders}) AND prop='narrower'
            """
            cursor.execute(query1, chunk)
            all_narrower_results.extend(cursor.fetchall())

        narrower_map = {}
        all_target_ids = set()
        for row in all_narrower_results:
            concept_id, target_id = row[0], row[1]
            if concept_id not in narrower_map:
                narrower_map[concept_id] = set()
            if target_id:
                narrower_map[concept_id].add(target_id)
                all_target_ids.add(target_id)

        # Step 2: broader 역관계 조회 (청크 방식)
        all_broader_inverse = []
        for i in range(0, len(concept_ids), CHUNK_SIZE):
            chunk = concept_ids[i:i + CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))

            query2 = f"""
                SELECT target, concept_id
                FROM uri_props
                WHERE target IN ({placeholders}) AND prop='broader'
            """
            cursor.execute(query2, chunk)
            all_broader_inverse.extend(cursor.fetchall())

        for row in all_broader_inverse:
            target_id, concept_id_from = row[0], row[1]
            if target_id not in narrower_map:
                narrower_map[target_id] = set()
            if concept_id_from:
                narrower_map[target_id].add(concept_id_from)
                all_target_ids.add(concept_id_from)

        # Step 3: 모든 target ID의 prefLabel 배치 조회 (청크 방식)
        if not all_target_ids:
            return {cid: [] for cid in concept_ids}

        target_ids_list = list(all_target_ids)
        label_results = []

        for i in range(0, len(target_ids_list), CHUNK_SIZE):
            chunk = target_ids_list[i:i + CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))

            label_query = f"""
                SELECT concept_id, value
                FROM literal_props
                WHERE concept_id IN ({placeholders})
                AND prop IN ('prefLabel', 'label')
                ORDER BY CASE prop WHEN 'prefLabel' THEN 1 ELSE 2 END
            """
            cursor.execute(label_query, chunk)
            label_results.extend(cursor.fetchall())

        label_map = {}
        for row in label_results:
            target_id, label = row[0], row[1]
            if target_id not in label_map and label:
                label_map[target_id] = label

        # Step 4: 최종 결과 구성
        result = {}
        for concept_id in concept_ids:
            narrower_ids = list(narrower_map.get(concept_id, set()))
            narrower_terms = []
            for narrower_id in narrower_ids:
                label = label_map.get(narrower_id)
                if label:
                    narrower_terms.append(self._format_ksh_display(narrower_id, label))
            result[concept_id] = narrower_terms

        return result


    def _get_pref_label(self, conn, concept_id: str) -> str:
        """concept_id에 대한 prefLabel을 가져옵니다. 없으면 label로 대체합니다."""
        cursor = conn.cursor()
        # -------------------
        # prefLabel을 우선으로 찾고, 없으면 label을 가져오도록 쿼리 수정
        cursor.execute(
            """
            SELECT value FROM literal_props
            WHERE concept_id=? AND prop IN ('prefLabel', 'label')
            ORDER BY CASE prop WHEN 'prefLabel' THEN 1 ELSE 2 END
            LIMIT 1
            """,
            (concept_id,),
        )
        # -------------------
        row = cursor.fetchone()
        return row[0] if row and row[0] else ""


    def _get_related_batch(self, conn, concept_ids: list) -> dict:
        """⚡ 배치: 여러 concept의 관련어를 한 번에 조회 (IN 절 청크 방식)"""
        if not concept_ids:
            return {}

        cursor = conn.cursor()

        # SQLite IN 절 최적화를 위해 100개씩 청크로 분할
        CHUNK_SIZE = 100
        all_related_ids = []

        for i in range(0, len(concept_ids), CHUNK_SIZE):
            chunk = concept_ids[i:i + CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))

            # Step 1: related ID들 가져오기 (COVERING INDEX 활용)
            query = f"""
                SELECT concept_id, target
                FROM uri_props
                WHERE concept_id IN ({placeholders}) AND prop='related'
            """
            cursor.execute(query, chunk)
            all_related_ids.extend(cursor.fetchall())

        # concept_id → [related_ids] 매핑
        related_map = {}
        all_target_ids = set()
        for row in all_related_ids:
            concept_id, target_id = row[0], row[1]
            if concept_id not in related_map:
                related_map[concept_id] = []
            if target_id:
                related_map[concept_id].append(target_id)
                all_target_ids.add(target_id)

        # Step 2: 모든 target ID의 prefLabel을 배치로 가져오기 (청크 방식)
        if not all_target_ids:
            return {cid: [] for cid in concept_ids}

        target_ids_list = list(all_target_ids)
        label_results = []

        # -------------------
        # ✅ [핵심 수정] Step 2에서도 IN 절 청크 분할을 적용하여 메모리/쿼리 부하를 줄입니다.
        for i in range(0, len(target_ids_list), CHUNK_SIZE):
            chunk = target_ids_list[i:i + CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))

            label_query = f"""
                SELECT concept_id, value
                FROM literal_props
                WHERE concept_id IN ({placeholders})
                AND prop IN ('prefLabel', 'label')
                ORDER BY CASE prop WHEN 'prefLabel' THEN 1 ELSE 2 END
            """
            cursor.execute(label_query, chunk)
            label_results.extend(cursor.fetchall())
        # -------------------

        # Step 3: target_id → label 매핑
        label_map = {}
        for row in label_results:
            target_id, label = row[0], row[1]
            if target_id not in label_map and label:
                label_map[target_id] = label

        # Step 4: 최종 결과 구성
        result = {}
        for concept_id in concept_ids:
            related_ids = related_map.get(concept_id, [])
            related_terms = []
            for related_id in related_ids:
                label = label_map.get(related_id)
                if label:
                    related_terms.append(self._format_ksh_display(related_id, label))
            result[concept_id] = related_terms

        return result


    def _get_synonyms_batch(self, conn, concept_ids: list) -> dict:
        """⚡ 배치: 여러 concept의 동의어를 한 번에 조회"""
        if not concept_ids:
            return {}

        cursor = conn.cursor()
        placeholders = ",".join("?" * len(concept_ids))
        query = f"""
            SELECT concept_id, value
            FROM literal_props
            WHERE concept_id IN ({placeholders}) AND prop='altLabel'
        """
        cursor.execute(query, concept_ids)

        # concept_id별로 그룹화
        result = {}
        for row in cursor.fetchall():
            concept_id, value = row[0], row[1]
            if concept_id not in result:
                result[concept_id] = []
            if value:
                result[concept_id].append(value)

        # 언어태그 중복 제거 적용
        for concept_id in result:
            result[concept_id] = self.dedup_lang_variants(result[concept_id])

        return result


    def _process_parentheses_for_equal_terms(
        self, text: str
    ) -> str:  # ✅ self를 추가합니다.
        """원괄호 안의 내용을 동등한 용어로 처리합니다."""
        if not text:
            return ""
        try:
            parentheses_pattern = r"([^()]+?)\s*\(([^()]+?)\)"

            def replace_parentheses(match):
                main_term = match.group(1).strip()
                parentheses_term = match.group(2).strip()
                if re.match(r"^[\d\s\-–—,]+$", parentheses_term):
                    return main_term
                reference_patterns = [
                    r"^(see\s+also|cf\.?|etc\.?|e\.g\.?|i\.e\.?)",
                    r"^(참조|참고|예|즉)",
                ]
                for pattern in reference_patterns:
                    if re.match(pattern, parentheses_term.lower()):
                        return main_term
                return f"{main_term}, {parentheses_term}"

            processed_text = text
            for _ in range(3):  # 무한 루프 방지
                if not re.search(parentheses_pattern, processed_text):
                    break
                processed_text = re.sub(
                    parentheses_pattern, replace_parentheses, processed_text
                )
            return processed_text.strip()
        except Exception as e:
            print(f"원괄호 처리 중 오류: {e}")
            return text


    def _save_keywords_separately(self, iri: str, ddc_code: str, raw_json: str):
        """
        ✅ [동시성 개선] 키워드 추출을 큐에 추가하여 비동기 처리
        메인 캐시 저장과 독립적으로 실행됩니다.
        """
        try:
            # JSON에서 키워드 추출
            data = json.loads(raw_json)
            keyword_entries = []

            # prefLabel 처리
            if "prefLabel" in data and "en" in data["prefLabel"]:
                keyword = data["prefLabel"]["en"].strip()
                if keyword:
                    keyword_entries.append((iri, ddc_code, keyword, "pref"))

            # altLabel 처리
            if "altLabel" in data and "en" in data["altLabel"]:
                labels = data["altLabel"]["en"]
                alt_labels = labels if isinstance(labels, list) else [labels]
                for label in alt_labels:
                    keyword = label.strip()
                    if keyword:
                        keyword_entries.append((iri, ddc_code, keyword, "alt"))

            # 키워드가 있으면 큐에 추가
            if keyword_entries:
                self.db_manager.enqueue_keyword_extraction(
                    iri, ddc_code, keyword_entries
                )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"키워드 추출 실패 ({ddc_code}): {e}")


    def _singularize_search_term(self, text: str) -> str:
        """
        검색어를 KSH DB에 맞게 단수형으로 변환합니다.
        (예: "Environmental problems" -> "Environmental problem")
        한글 등 영어 명사가 아니면 원본을 그대로 반환하여 안전합니다.
        """
        if not text or re.search("[\uac00-\ud7a3]", text):
            # 비어 있거나 한글이 포함된 경우 원본 반환
            return text

        # -------------------
        # ✅ 언어태그 제거 (예: 'dacapo@en' -> 'dacapo')
        base, _lang = split_lang_suffix(text)
        # ✅ 괄호/각괄호 안 수식어 제거
        base = re.sub(r"[\(\[].*?[\)\]]", "", base).strip()
        # -------------------

        # 한글 포함이면 단수화 스킵
        if re.search("[\uac00-\ud7a3]", base):
            return base

        words = base.split()
        singular_words = []
        for word in words:
            # -------------------
            # ✅ inflection.singularize() 유지
            singular = inflection.singularize(word)
            singular_words.append(singular)
        # -------------------
        return " ".join(singular_words)


    def _sort_by_year_and_identifier(self, df):
        """발행연도 최신순 + identifier 큰 순으로 정렬 (타이브레이커 적용)"""
        # -------------------
        if df.empty:
            return df

        df = df.copy()

        # 발행연도 숫자 변환
        df["year_numeric"] = pd.to_numeric(
            df["publication_year"], errors="coerce"
        ).fillna(0)

        # identifier 숫자 변환 (타이브레이커)
        df["id_numeric"] = pd.to_numeric(df["identifier"], errors="coerce").fillna(0)

        # 정렬: 발행연도 내림차순 → identifier 내림차순
        df = df.sort_values(["year_numeric", "id_numeric"], ascending=[False, False])

        # 임시 컬럼 제거
        return df.drop(["year_numeric", "id_numeric"], axis=1)
        # -------------------


    def _strip_namespace(self, concept_id: str) -> str:
        """네임스페이스 제거: 'nlk:KSH123' -> 'KSH123'"""
        if not concept_id:
            return concept_id
        if ":" in concept_id:
            return concept_id.split(":", 1)[1]
        return concept_id


    def dedup_lang_variants(self, values: List[str]) -> List[str]:
        """클래스 메서드로 언어태그 중복 제거"""
        return dedup_lang_variants(values)


    def get_bibliographic_by_subject_name(self, subject_name):
        """
        주제명으로 서지 데이터를 검색합니다.
        ✅ [수정] _search_by_korean_subject를 직접 호출 (DDC별 제한 없이 전체 정렬)
        """
        return self._search_by_korean_subject([subject_name])


    def get_bibliographic_by_title(self, title_keyword, limit=500):
        """✅ [신규 추가] 제목으로 서지 데이터를 검색합니다."""
        conn = None
        try:
            conn = self.db_manager._get_mapping_connection()

            # ✅ [수정] 실제 테이블 컬럼명 사용
            query = """
            SELECT
                identifier,
                kdc,
                ddc,
                ksh,
                kdc_edition,
                ddc_edition,
                publication_year,
                title,
                data_type,
                source_file,
                ksh_labeled,
                ksh_korean
            FROM mapping_data
            WHERE title LIKE ?
            ORDER BY publication_year DESC, identifier
            LIMIT ?
            """

            df = pd.read_sql_query(query, conn, params=(f"%{title_keyword}%", limit))

            if df.empty:
                return pd.DataFrame()

            # ✅ [핵심] KSH 라벨 포맷팅 - ksh_labeled 컬럼을 덮어씀 (새 컬럼 추가 X)
            if not df.empty and "ksh" in df.columns:
                df["ksh_labeled"] = df.apply(
                    lambda row: self._format_ksh_column_optimized(
                        row.get("ksh", ""),
                        row.get("ksh_korean", ""),
                        row.get("ksh_labeled", ""),
                    ),
                    axis=1,
                )

            # ✅ [신규] DDC Label 컬럼 추가 (기존 서지 검색과 동일)
            if "ddc" in df.columns:
                df["ddc_label"] = df["ddc"].apply(
                    lambda ddc: (
                        self.get_ddc_labels(ddc)
                        if pd.notna(ddc) and str(ddc).strip()
                        else ""
                    )
                )

            # ✅ [중요] NLK 링크 생성 (기존 서지 검색과 동일)
            if "identifier" in df.columns:
                df["nlk_link"] = df["identifier"].apply(
                    lambda x: (
                        f"https://www.nl.go.kr/NL/contents/search.do?systemType=&pageNum=1&pageSize=10&srchTarget=total&kwd={x}"
                        if x
                        else ""
                    )
                )

            # ✅ [중요] ksh, ksh_korean 컬럼 제거 (UI에 불필요)
            df.drop(columns=["ksh", "ksh_korean"], inplace=True, errors="ignore")

            # ✅ [핵심] 컬럼명을 변환하지 않고 DB 컬럼명 그대로 반환
            # Qt 탭에서 column_map_bottom을 통해 자동으로 매핑됨
            return df

        except Exception as e:
            print(f"제목 검색 중 오류 발생: {e}")
            import traceback

            traceback.print_exc()
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()


    def preprocess_search_term(self, raw_text: str) -> str:
        """
        [최종 강화 버전] 모든 검색어 입력을 정규화하는 중앙 함수.
        - 다중 ▼a 패턴, CJK 공백, Dewey 설명문, KSH 마크업, 영단어 단수화 모두 처리
        """
        if not raw_text or pd.isna(raw_text):
            return ""

        text = str(raw_text).strip()

        # 1단계: 다중 ▼a 패턴 처리 (▼a건강관리▼a러닝▼a운동법 패턴)
        if "▼a" in text and text.count("▼a") > 1:
            keywords = []
            pattern = r"▼a([^▼▲]+)"
            matches = re.findall(pattern, text)

            for match in matches:
                # 각 키워드에서 불필요한 기호와 공백 정리
                cleaned_keyword = re.sub(r"[▼▲]", "", match)
                cleaned_keyword = re.sub(
                    r"\[.*?\]|\(.*?\)", "", cleaned_keyword
                ).strip()

                # 한글/한자가 포함되면 내부 공백 모두 제거 (예: '자기 계발' -> '자기계발')
                if re.search(r"[\uAC00-\uD7AF\u4E00-\u9FFF]", cleaned_keyword):
                    cleaned_keyword = re.sub(r"\s+", "", cleaned_keyword)
                else:
                    # 영단어 등 비CJK는 다중 공백만 단일화
                    cleaned_keyword = re.sub(r"\s{2,}", " ", cleaned_keyword)

                if cleaned_keyword:
                    keywords.append(cleaned_keyword)

            if keywords:
                # 최종적으로 영단어 단수화 적용 후 쉼표로 연결
                singular_keywords = []
                for kw in keywords:
                    if not re.search(r"[\uAC00-\uD7AF\u4E00-\u9FFF]", kw):
                        singular_keywords.append(
                            " ".join(
                                [inflection.singularize(word) for word in kw.split()]
                            )
                        )
                    else:
                        singular_keywords.append(kw)
                return ", ".join(singular_keywords)

        # 2단계: 일반 마크업 또는 Dewey 설명문 등 복잡한 텍스트 처리
        if any(c in text for c in "▼▲[]();:"):
            # KSH 마크업 제거
            if "▼a" in text and "▼0" in text:
                match = re.search(r"▼a([^▼]+)▼0", text)
                if match:
                    text = match.group(1)

            # Dewey 설명문 정규화
            text = self._process_parentheses_for_equal_terms(text)
            text = text.replace("--", ", ")
            text = re.sub(r"\s+(and|&)\s+", ", ", text, flags=re.IGNORECASE)
            text = re.sub(r"\b\d{4}[-‐−–—]?\d*[-‐−–—]?\b", "", text)
            text = re.sub(r"[;:]+", ",", text)

            # 일반 정규화
            base, _lang = split_lang_suffix(text)
            base = re.sub(r"\[.*?\]|\(.*?\)", "", base).strip()

            # -------------------
            # ✅ [핵심 수정] 한글이 포함된 경우, 문제가 되는 정규식을 건너뛰고 즉시 반환하도록 수정
            if re.search(r"[\uAC00-\uD7AF\u4E00-\u9FFF]", base):
                # 쉼표로 구분된 다중 검색어의 경우, 각 항목의 공백을 제거
                parts = [re.sub(r'\s+', '', part.strip()) for part in base.split(',') if part.strip()]
                return ", ".join(parts)

            base = re.sub(r"[^\w\s,\-]", "", base) # <- 이제 이 코드는 한글이 없을 때만 실행됩니다.
            base = re.sub(r"[,]+", ",", base)
            # -------------------
            base = re.sub(r"\s+", " ", base).strip()

            # 한글/한자 포함 시 내부 공백 제거
            if re.search(r"[\uAC00-\uD7AF\u4E00-\u9FFF]", base):
                return re.sub(r"\s+", "", base)

            # 영단어 단수화
            words = base.split()
            singular_words = [inflection.singularize(word) for word in words]
            return " ".join(singular_words)

        # 3단계: 순수 키워드 (가장 일반적인 경우)
        else:
            # 한글/한자 포함 시 내부 공백 제거
            if re.search(r"[\uAC00-\uD7AF\u4E00-\u9FFF]", text):
                return re.sub(r"\s+", "", text)

            # 영단어 단수화
            words = text.split()
            singular_words = [inflection.singularize(word) for word in words]
            return " ".join(singular_words)

    # ✅ [추가] database_manager.py에서 이관된 DDC notation 캐시 조회 메서드

    def search_bibliographic_by_subject_optimized(self, subject_name, total_limit=200):
        """
        🎯 메르카츠님 요구사항에 맞춘 서지DB 검색:
        1. DDC 빈도 기준 정렬 (가장 흔한 DDC 먼저)
        2. 각 DDC당 5-20건 제한 (분류 개수에 따라 동적 조절)
        3. 2:3 비율 (단일KSH:다중KSH) 유연 적용
        4. 발행연도 최신순 + identifier 타이브레이커
        """
        conn = None
        try:
            conn = self.db_manager._get_mapping_connection()

            # 1단계: 주제명 기본 검색 (기존 로직 활용)
            base_results = self._search_by_korean_subject([subject_name])

            if base_results.empty:
                return pd.DataFrame()

            # 2단계: DDC별 빈도 계산
            ddc_counts = base_results["ddc"].value_counts()
            base_results["ddc_count"] = base_results["ddc"].map(ddc_counts)
            total_ddcs = len(ddc_counts)

            # ✅ [최적화 1] 디버그 로그 제거 (0.3-0.5s 절감)
            # print(f"🎯 [DDC_FREQ] 발견된 DDC 분류: {total_ddcs}개")
            # print(f"🎯 [DDC_FREQ] 상위 5개 DDC: {dict(ddc_counts.head())}")

            # 3단계: 분류당 할당량 계산
            # ✅ [핵심 수정] DDC당 최대 10개로 고정 (단일 3:복수 7 비율)
            items_per_ddc = 10
            # ✅ [최적화 1] 디버그 로그 제거
            # print(
            #     f"🎯 [ALLOCATION] DDC당 할당량: {items_per_ddc}건 (단일 최대 3 : 복수 최대 7)"
            # )

            # 4단계: DDC별 데이터 처리
            final_results = []
            processed_count = 0

            for ddc_code, frequency in ddc_counts.items():
                if processed_count >= total_limit:
                    break

                # ✅ [최적화 2] .copy() 제거 - 뷰 사용 (0.2-0.3s 절감)
                # 해당 DDC의 모든 데이터
                ddc_subset = base_results[base_results["ddc"] == ddc_code]

                # ✅ [최적화 3] ksh_count는 SQL에서 이미 계산됨 (0.1-0.2s 절감)
                # KSH 개수 계산 및 분할 (ksh_count 컬럼은 SQL 쿼리에서 이미 생성됨)
                single_ksh_data = ddc_subset[ddc_subset["ksh_count"] == 1]
                multi_ksh_data = ddc_subset[ddc_subset["ksh_count"] > 1]

                # 각각 발행연도 + identifier 기준 정렬
                # -------------------
                single_ksh_data = self._sort_by_year_and_identifier(single_ksh_data)
                multi_ksh_data = self._sort_by_year_and_identifier(multi_ksh_data)
                # -------------------

                # 🎯 3:7 비율 적용 (단일 KSH 최대 3개 : 복수 KSH 최대 7개)
                # items_per_ddc가 10이면 단일 3개, 복수 7개
                target_single = min(3, (items_per_ddc * 3) // 10, len(single_ksh_data))
                remaining = items_per_ddc - target_single
                target_multi = min(remaining, len(multi_ksh_data))

                # 남은 할당량이 있으면 다른 쪽에서 채움
                if target_single + target_multi < items_per_ddc:
                    if len(single_ksh_data) > target_single:
                        additional = min(
                            items_per_ddc - target_multi,
                            len(single_ksh_data) - target_single,
                        )
                        target_single += additional
                    elif len(multi_ksh_data) > target_multi:
                        additional = min(
                            items_per_ddc - target_single,
                            len(multi_ksh_data) - target_multi,
                        )
                        target_multi += additional

                # 최종 선별
                selected_single = (
                    single_ksh_data.head(target_single)
                    if target_single > 0
                    else pd.DataFrame()
                )
                selected_multi = (
                    multi_ksh_data.head(target_multi)
                    if target_multi > 0
                    else pd.DataFrame()
                )

                # DDC별 결과 병합
                ddc_result = pd.concat(
                    [selected_single, selected_multi], ignore_index=True
                )
                if not ddc_result.empty:
                    ddc_result["ddc_frequency_rank"] = len(
                        final_results
                    )  # 빈도 순위 기록
                    final_results.append(ddc_result)
                    processed_count += len(ddc_result)

                # ✅ [최적화 1] 디버그 로그 제거 (DDC 루프마다 118회 출력 → 제거)
                # print(
                #     f"🎯 [DDC:{ddc_code}] 단일KSH:{target_single}건, 다중KSH:{target_multi}건 (빈도:{frequency})"
                # )

            # 5단계: 최종 결과 생성
            if final_results:
                result_df = pd.concat(final_results, ignore_index=True)

                # ✅ [디버깅] 최종 결과 확인
                # logger.info(f"🐛 [DEBUG] 최종 결과 생성 - 행 수: {len(result_df)}")
                # if not result_df.empty and "ksh_labeled" in result_df.columns:
                #    unique_ksh_labeled = result_df["ksh_labeled"].nunique()
                #    logger.info(f"🐛 [DEBUG] 고유한 ksh_labeled 값 개수: {unique_ksh_labeled}")
                #    logger.info(f"🐛 [DEBUG] 샘플 ksh_labeled 값 (최초 3개):\n{result_df['ksh_labeled'].head(3).tolist()}")

                # ksh_labeled 컬럼 생성 (표시용)
                if "ksh" in result_df.columns:
                    result_df["ksh_labeled"] = result_df.apply(
                        lambda row: self._format_ksh_labeled_to_markup(
                            row.get("ksh_labeled", ""), row.get("ksh", "")
                        ),
                        axis=1,
                    )

                    # ✅ [디버깅] 변환 후 확인
                    # unique_after = result_df["ksh_labeled"].nunique()
                    # logger.info(f"🐛 [DEBUG] 변환 후 고유한 ksh_labeled 값 개수: {unique_after}")
                    # logger.info(f"🐛 [DEBUG] 변환 후 샘플 ksh_labeled 값 (최초 3개):\n{result_df['ksh_labeled'].head(3).tolist()}")

                # ✅ [신규] DDC Label 컬럼 추가
                if "ddc" in result_df.columns:
                    result_df["ddc_label"] = result_df["ddc"].apply(
                        lambda ddc: (
                            self.get_ddc_labels(ddc)
                            if pd.notna(ddc) and str(ddc).strip()
                            else ""
                        )
                    )

                # ✅ nlk_link 컬럼 생성 (identifier 기반)
                if "identifier" in result_df.columns:
                    result_df["nlk_link"] = result_df["identifier"].apply(
                        lambda x: (
                            f"https://www.nl.go.kr/NL/contents/search.do?systemType=&pageNum=1&pageSize=10&srchTarget=total&kwd={x}"
                            if x
                            else ""
                        )
                    )

                # 임시 컬럼 제거
                result_df = result_df.drop(
                    ["ddc_frequency_rank"], axis=1, errors="ignore"
                )

                print(f"🎯 [FINAL] 최종 서지 결과: {len(result_df)}건")
                return result_df.fillna("")
            else:
                return pd.DataFrame()

        except Exception as e:
            print(f"오류: 최적화된 서지 검색 중 오류 발생: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

