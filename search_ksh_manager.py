# 파일명: search_ksh_manager.py
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

    def _format_korean_search_results(self, df, search_term=None):
        if df.empty:
            return df
        try:
            # ksh_labeled → 마크업으로 변환
            df["ksh_labeled"] = df.apply(
                lambda row: self._format_ksh_labeled_to_markup(
                    row.get("ksh_labeled", ""), row.get("ksh", "")
                ),
                axis=1,
            )
            # 표시용
            df["matched"] = df["ksh_korean"]

            # ✅ [신규 추가] DDC 레이블 및 출현 카운트 매핑
            if "ddc" in df.columns:
                # DDC 레이블 매핑
                unique_ddcs = df["ddc"].dropna().unique().tolist()
                if unique_ddcs:
                    ddc_label_map = self.get_all_ddc_labels_bulk(unique_ddcs)
                    df["ddc_label"] = df["ddc"].map(ddc_label_map).fillna("")
                else:
                    df["ddc_label"] = ""

                # DDC 출현 카운트 계산
                ddc_counts = df["ddc"].value_counts()
                df["ddc_count"] = df["ddc"].map(ddc_counts).fillna(0).astype(int)

            # ✅ [신규 추가] 검색어 기반 정렬 로직
            print(
                f"🔍 [DEBUG] _format_korean_search_results called with search_term: '{search_term}'"
            )
            if search_term:
                print(
                    f"🔍 [DEBUG] 정렬 로직 시작 - 검색어: '{search_term}', 결과: {len(df)}개"
                )
                # DDC 빈도 계산 (각 DDC가 mapping_data에서 몇 번 나타나는지)
                ddc_counts = df["ddc"].value_counts().to_dict()
                df["ddc_frequency"] = df["ddc"].map(ddc_counts).fillna(0)
                # print(f"🔍 [DEBUG] DDC 빈도: {ddc_counts}")

                # ✅ [디버그] 샘플 ksh_korean 확인
                print(f"🔍 [DEBUG] 샘플 ksh_korean (첫 3개):")
                for idx, ksh in enumerate(df["ksh_korean"].head(3), 1):
                    print(f"  {idx}. {ksh}")

                # 매칭 우선순위 계산 함수
                def _calculate_match_priority(row):
                    ksh_korean = str(row.get("ksh_korean", "")).lower()
                    search_lower = search_term.strip().replace(" ", "").lower()
                    ddc_freq = row.get("ddc_frequency", 0)

                    # ksh_korean에서 각 주제명 추출 (세미콜론으로 분리)
                    subjects = [s.strip() for s in ksh_korean.split(";") if s.strip()]

                    for subject in subjects:
                        # 괄호 제거한 순수 주제명
                        pure_subject = re.sub(r"[\(\[].*?[\)\]]", "", subject).strip()

                        # 1순위: 순수 주제명에서 완전 매칭
                        if pure_subject == search_lower:
                            return (1, -ddc_freq, row.get("publication_year", 0))

                    for subject in subjects:
                        pure_subject = re.sub(r"[\(\[].*?[\)\]]", "", subject).strip()

                        # 2순위: 순수 주제명에서 부분 매칭
                        if search_lower in pure_subject:
                            return (2, -ddc_freq, row.get("publication_year", 0))

                    # 3순위: 괄호 안 매칭
                    for subject in subjects:
                        # 괄호 안 내용 추출
                        paren_content = re.findall(r"\(([^\)]+)\)", subject)
                        bracket_content = re.findall(r"\[([^\]]+)\]", subject)

                        all_content = " ".join(paren_content + bracket_content).lower()
                        if search_lower in all_content:
                            return (3, -ddc_freq, row.get("publication_year", 0))

                    # 4순위: 기타
                    return (4, -ddc_freq, row.get("publication_year", 0))

                # 우선순위 계산
                df["_sort_priority"] = df.apply(_calculate_match_priority, axis=1)

                # ✅ [디버그] 우선순위 분포 확인
                priority_dist = (
                    df["_sort_priority"]
                    .apply(lambda x: x[0])
                    .value_counts()
                    .sort_index()
                )
                print(f"🔍 [DEBUG] 우선순위 분포: {dict(priority_dist)}")

                # 정렬: 우선순위 → DDC 빈도 → 발행연도
                df = df.sort_values("_sort_priority").drop(
                    ["_sort_priority", "ddc_frequency"], axis=1
                )
                # ✅ 정렬 후 상위 200개만 반환
                df = df.head(200)
                print(f"🔍 [DEBUG] 정렬 완료 - 상위 {len(df)}개 반환")
            else:
                # 검색어가 없으면 기존대로 발행연도 역순
                df["pub_year_numeric"] = pd.to_numeric(
                    df["publication_year"], errors="coerce"
                ).fillna(0)
                df = df.sort_values("pub_year_numeric", ascending=False).drop(
                    "pub_year_numeric", axis=1
                )
                # ✅ 상위 200개만 반환
                df = df.head(200)

            # ❌ (삭제 금지) if "ksh" in df.columns: df.drop(...)

            return df.fillna("")
        except Exception as e:
            print(f"경고: 한국어 검색 결과 포맷팅 중 오류: {e}")
            return df

    # 💎 마스터 검색 함수

    def _format_ksh_column_optimized(
        self, ksh_codes_str: str, ksh_korean: str = "", ksh_labeled: str = ""
    ) -> str:
        """
        🔧 포맷팅 함수도 정규화된 데이터에 맞춰 수정
        """
        if not ksh_codes_str or pd.isna(ksh_codes_str):
            return ""

        import re

        # ksh_labeled에서 라벨 추출
        label_map = {}
        if ksh_labeled and str(ksh_labeled).lower() != "nan":
            for segment in str(ksh_labeled).split(";"):
                seg = segment.strip().replace("\u00a0", " ")
                # 이미 포맷된 경우 파싱
                m_fmt = re.match(r"^▼a(.+?)▼0(?i:(ksh)\d+)▲$", seg)
                if m_fmt:
                    label_map[m_fmt.group(2).upper()] = m_fmt.group(1).strip()
                    continue
                # 일반적인 "라벨 - KSH123" 패턴
                m = re.match(r"^(?P<label>.+?)\s*[-–—]\s*(?P<code>(?i:ksh)\d+)$", seg)
                if m:
                    label_map[m.group("code").upper()] = m.group("label").strip()

        # KSH 코드 토큰화
        codes = [t for t in re.split(r"[,\s]+", str(ksh_codes_str)) if t.strip()]
        out = []

        for raw in codes:
            code = raw.strip().upper()
            if not code.startswith("KSH"):
                out.append(raw)
                continue

            # 라벨 매핑 우선순위
            if code in label_map:
                label = label_map[code]
                out.append(f"▼a{label}▼0{code}▲")
                continue

            # ksh_korean 사용 (정규화된 상태)
            if ksh_korean and str(ksh_korean).lower() != "nan":
                # 주의: ksh_korean은 이제 공백이 제거된 상태
                first_ko = str(ksh_korean).split(";")[0].strip()
                if first_ko:
                    out.append(f"▼a{first_ko}▼0{code}▲")
                    continue

            # 최종 폴백: 코드만
            out.append(code)

        return ", ".join(out)

    def _format_ksh_display(self, concept_id: str, label: str) -> str:
        """KSH 표시 형식: ▼a{label}▼0{KSH_code}▲"""
        ksh_code = self._strip_namespace(concept_id)
        return f"▼a{label}▼0{ksh_code}▲"

    def _format_ksh_labeled_to_markup(
        self, ksh_labeled: str, ksh_fallback: str = ""
    ) -> str:
        if not ksh_labeled or str(ksh_labeled).lower() == "nan":
            return ksh_fallback or ""

        # 이미 마크업이면 그대로
        if (
            "▼a" in str(ksh_labeled)
            and "▼0" in str(ksh_labeled)
            and "▲" in str(ksh_labeled)
        ):
            return str(ksh_labeled)

        segments = str(ksh_labeled).split(";")
        formatted = []
        for seg in segments:
            s = seg.strip()
            if not s:
                continue
            m = re.match(r"^(?P<label>.+?)\s*[-–—]\s*(?P<code>(?i:ksh)\d+)$", s)
            if m:
                label = m.group("label").strip()
                code = m.group("code").upper()
                formatted.append(f"▼a{label}▼0{code}▲")
            else:
                formatted.append(s)
        return "; ".join(formatted) if formatted else (ksh_fallback or "")

    def _get_broader_for_concept(self, conn, concept_id: str) -> list:
        """개념의 상위어들을 KSH 형식으로 가져옵니다."""
        cursor = conn.cursor()

        # broader 관계 조회
        cursor.execute(
            "SELECT target FROM uri_props WHERE concept_id=? AND prop='broader'",
            (concept_id,),
        )
        broader_ids = [row[0] for row in cursor.fetchall() if row and row[0]]

        # narrower의 역관계도 확인
        cursor.execute(
            "SELECT concept_id FROM uri_props WHERE target=? AND prop='narrower'",
            (concept_id,),
        )
        inverse_broader = [row[0] for row in cursor.fetchall() if row and row[0]]

        # 중복 제거
        all_broader = list(set(broader_ids + inverse_broader))

        broader_terms = []
        for broader_id in all_broader:
            broader_label = self._get_pref_label(conn, broader_id)
            if broader_label:
                broader_terms.append(
                    self._format_ksh_display(broader_id, broader_label)
                )

        return broader_terms

    def _get_narrower_for_concept(self, conn, concept_id: str) -> list:
        """개념의 하위어들을 KSH 형식으로 가져옵니다."""
        cursor = conn.cursor()

        # narrower 관계 조회
        cursor.execute(
            "SELECT target FROM uri_props WHERE concept_id=? AND prop='narrower'",
            (concept_id,),
        )
        narrower_ids = [row[0] for row in cursor.fetchall() if row and row[0]]

        # broader의 역관계도 확인
        cursor.execute(
            "SELECT concept_id FROM uri_props WHERE target=? AND prop='broader'",
            (concept_id,),
        )
        inverse_narrower = [row[0] for row in cursor.fetchall() if row and row[0]]

        # 중복 제거
        all_narrower = list(set(narrower_ids + inverse_narrower))

        narrower_terms = []
        for narrower_id in all_narrower:
            narrower_label = self._get_pref_label(conn, narrower_id)
            if narrower_label:
                narrower_terms.append(
                    self._format_ksh_display(narrower_id, narrower_label)
                )

        return narrower_terms

    def _get_related_for_concept(self, conn, concept_id: str) -> list:
        """개념의 관련어들을 KSH 형식으로 가져옵니다."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT target FROM uri_props WHERE concept_id=? AND prop='related'",
            (concept_id,),
        )
        related_ids = [row[0] for row in cursor.fetchall() if row and row[0]]

        related_terms = []
        for related_id in related_ids:
            related_label = self._get_pref_label(conn, related_id)
            if related_label:
                related_terms.append(
                    self._format_ksh_display(related_id, related_label)
                )

        # -------------------
        # 항목 수 제한 제거 - 모든 관련어를 표시
        return related_terms  # 🎯 [:20] 제거하여 전체 표시
        # -------------------

    def _get_synonyms_for_concept(
        self, conn, concept_id: str, exclude_term: str = None
    ) -> list:
        """동의어 조회 + 언어태그 중복 제거 적용"""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM literal_props WHERE concept_id=? AND prop='altLabel'",
            (concept_id,),
        )
        synonyms = [row[0] for row in cursor.fetchall() if row and row[0]]

        if exclude_term:
            synonyms = [s for s in synonyms if s != exclude_term]

        # 🎯 언어태그 기준 중복 제거
        return self.dedup_lang_variants(synonyms)

    def _search_by_korean_subject(self, korean_terms):
        """
        kdc_to_dd DB에서 한국어 주제명으로 직접 검색
        ✅ [성능 개선] 2단계 검색(CTE)을 통해 FTS5와 SQL 정렬의 장점을 모두 활용합니다.
        """
        conn = None
        try:
            conn = self.db_manager._get_mapping_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='mapping_data_fts'"
            )
            use_fts = cursor.fetchone() is not None

            if not use_fts:
                logger.warning(
                    "⚠️ FTS5 테이블이 없어 검색을 건너뜁니다. (LIKE 검색 비활성화)"
                )
                return pd.DataFrame()

            # 🚀 FTS5 + SQL 최적화 쿼리
            search_term = korean_terms[0] if korean_terms else ""
            if not search_term:
                return pd.DataFrame()

            term_clean = search_term.strip().replace(" ", "")

            # FTS5용 쿼리 (단일 검색어 기준)
            fts_query = f'ksh_korean:("{term_clean}" OR {term_clean}*)'

            # -------------------
            # ✅ [핵심 성능 개선] WITH 절(CTE)을 사용하여 검색 단계를 명확히 분리
            # 1단계: FTS5에서 rank 기준으로 상위 10,000개의 후보 rowid를 빠르게 추출
            # 2단계: 추출된 10,000개의 rowid만 가지고 실제 테이블과 JOIN하여 정밀 정렬
            query = """
            WITH TopFtsResults AS (
                SELECT rowid
                FROM mapping_data_fts
                WHERE mapping_data_fts MATCH ?
                ORDER BY rank -- FTS5의 내장 관련도 점수(rank)로 1차 정렬
                LIMIT 10000
            )
            SELECT
                m.identifier, m.kdc, m.ddc, m.ksh, m.kdc_edition, m.ddc_edition,
                m.publication_year, m.title, m.data_type, m.source_file,
                m.ksh_labeled, m.ksh_korean,
                (LENGTH(m.ksh) - LENGTH(REPLACE(m.ksh, 'KSH', ''))) / 3 as ksh_count,
                CASE
                    WHEN m.ksh_korean = ? THEN 0 -- 1순위: 완전 일치
                    WHEN m.ksh_korean LIKE ? THEN 1 -- 2순위: 맨 앞에 일치
                    ELSE 2 -- 3순위: 그 외 FTS 매칭
                END as match_priority
            FROM TopFtsResults tfr -- 전체 테이블이 아닌 10,000건의 후보 테이블
            JOIN mapping_data m ON tfr.rowid = m.rowid
            ORDER BY
                match_priority ASC,      -- 1. 정확도 순
                publication_year DESC,   -- 2. 발행년도 최신순
                ksh_count DESC           -- 3. KSH 개수 많은 순
            """

            # SQL 파라미터: FTS쿼리, CASE용 파라미터 2개
            params = (fts_query, term_clean, f"{term_clean};%")
            df_result = pd.read_sql_query(query, conn, params=params)
            # -------------------

            if not df_result.empty:
                logger.info(
                    f"🎯 [SQL 최적화] 서지 DB 검색 완료: {len(df_result)}개 결과만 가져와 후처리 시작"
                )
                formatted_result = self._format_korean_search_results(
                    df_result, search_term
                )
                return formatted_result
            else:
                return pd.DataFrame()

        except Exception as e:
            print(f"오류: 한국어 주제명 검색 중 오류 발생: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    def _search_by_ksh_code(self, ksh_codes):
        conn = self.db_manager._get_mapping_connection()
        try:
            query_parts = ["ksh LIKE ?"] * len(ksh_codes)
            # ✅ [성능 개선] 필요한 컬럼만 조회
            query = f"""
                SELECT
                    identifier,
                    kdc,
                    ddc,
                    ksh,
                    ksh_korean,
                    ksh_labeled,
                    kdc_edition,
                    ddc_edition,
                    publication_year,
                    title,
                    source_file
                FROM mapping_data
                WHERE {' OR '.join(query_parts)}
            """
            params = [f"%{code}%" for code in ksh_codes]
            df = pd.read_sql_query(query, conn, params=params)

            # 🚀 성능 개선: 행 단위로 최적화된 포맷팅 적용
            if not df.empty and "ksh" in df.columns:
                df["ksh"] = df.apply(
                    lambda row: self._format_ksh_column_optimized(
                        row.get("ksh", ""),
                        row.get("ksh_korean", ""),
                        row.get("ksh_labeled", ""),
                    ),
                    axis=1,
                )

            return df.fillna("")
        finally:
            if conn:
                conn.close()

    def get_concept_relations(self, keyword):
        """
        특정 키워드의 상/하위어, 관련어 정보 반환
        실제 Concept DB 구조에 맞춰 구현
        """
        conn = None
        try:
            conn = self.db_manager._get_concepts_connection()
            cursor = conn.cursor()

            # 정규화된 키워드로 검색
            normalized_keyword = keyword.strip().lower().replace(" ", "")

            # 1. 키워드로 concept_id들 찾기
            search_query = """
            SELECT DISTINCT concept_id, value, prop
            FROM literal_props
            WHERE concept_id LIKE 'nlk:KSH%'
            AND concept_id NOT LIKE 'nls:%'
            AND (value_normalized LIKE ? OR value LIKE ?)
            AND prop IN ('prefLabel', 'label', 'altLabel')
            LIMIT 10
            """

            cursor.execute(search_query, (f"%{normalized_keyword}%", f"%{keyword}%"))
            concept_results = cursor.fetchall()

            relations = {
                "broader": [],  # 상위어
                "narrower": [],  # 하위어
                "related": [],  # 관련어
                "synonyms": [],  # 동의어/이형어
            }

            # 2. 각 concept_id에 대해 관계 정보 조회
            for concept_row in concept_results:
                concept_id = concept_row[0]

                # object_props 테이블에서 관계 조회
                relations_query = """
                SELECT op.prop, op.object_id
                FROM object_props op
                WHERE op.subject_id = ?
                AND op.prop IN ('broader', 'narrower', 'related')
                """

                cursor.execute(relations_query, (concept_id,))
                relation_results = cursor.fetchall()

                # 관련 개념들의 라벨 조회
                for rel_row in relation_results:
                    relation_type = rel_row[0]  # broader, narrower, related
                    related_concept_id = rel_row[1]

                    # 관련 개념의 preferredLabel 조회
                    label_query = """
                    SELECT value FROM literal_props
                    WHERE concept_id = ? AND prop = 'prefLabel'
                    LIMIT 1
                    """

                    cursor.execute(label_query, (related_concept_id,))
                    label_result = cursor.fetchone()

                    if label_result and relation_type in relations:
                        related_term = label_result[0]
                        if (
                            related_term
                            and related_term not in relations[relation_type]
                        ):
                            relations[relation_type].append(related_term)

            # 각 관계 타입별로 최대 3개로 제한
            for relation_type in relations:
                relations[relation_type] = relations[relation_type][:3]

            return relations

        except Exception as e:
            print(f"오류: Concept DB 관계 정보 조회 실패: {e}")
            return {"broader": [], "narrower": [], "related": [], "synonyms": []}
        finally:
            if conn:
                conn.close()

    def _build_fts5_query(self, processed_term: str) -> str:
        """
        FTS5 검색 쿼리 문자열 생성

        Args:
            processed_term: 전처리된 검색어

        Returns:
            FTS5 MATCH 쿼리 문자열
        """
        normalized_term = processed_term.replace(" ", "")

        if "," in processed_term:
            # 다중 검색어: "한국" OR "경제" OR ...
            terms = [
                term.strip().replace(" ", "")
                for term in processed_term.split(",")
                if term.strip()
            ]

            fts_terms = []
            for t in terms:
                sanitized_t = re.sub(r"[^\w]", "", t)
                if sanitized_t:
                    fts_terms.append(f'"{sanitized_t}" OR {sanitized_t}*')

            return " OR ".join(fts_terms)
        else:
            # 단일 검색어: "한국" OR 한국*
            sanitized_term = re.sub(r"[^\w]", "", normalized_term)
            if sanitized_term:
                return f'"{sanitized_term}" OR {sanitized_term}*'
            else:
                return ""

    def _execute_fts5_search(
        self, cursor, fts_query: str, main_category: str = None, limit: int = None
    ) -> list:
        """
        FTS5 전문 검색 실행

        Args:
            cursor: 데이터베이스 커서
            fts_query: FTS5 MATCH 쿼리 문자열 (None이면 카테고리 전용 검색)
            main_category: 주제 카테고리 필터
            limit: 결과 개수 제한

        Returns:
            검색 결과 리스트 [(concept_id, matched_value), ...]
        """
        # ✅ 카테고리 전용 검색 (fts_query가 None인 경우)
        if fts_query is None:
            base_query = """
            SELECT DISTINCT
                lp.concept_id,
                lp.value as matched_value,
                lp.prop,
                CASE lp.prop WHEN 'prefLabel' THEN 1 WHEN 'label' THEN 2 WHEN 'altLabel' THEN 3 ELSE 4 END as prop_priority
            FROM literal_props lp
            LEFT JOIN category_mapping cm ON lp.concept_id = cm.concept_id
            WHERE lp.concept_id LIKE 'nlk:KSH%'
            AND lp.concept_id NOT LIKE 'nls:%'
            AND lp.prop IN ('prefLabel', 'label', 'altLabel')
            """
            params = []

            # 카테고리 필터 (필수)
            if main_category and main_category != "전체":
                base_query += " AND cm.main_category = ?"
                params.append(main_category)
        else:
            # 일반 FTS5 검색
            base_query = """
            SELECT DISTINCT
                lp.concept_id,
                lp.value as matched_value,
                lp.prop,
                CASE lp.prop WHEN 'prefLabel' THEN 1 WHEN 'label' THEN 2 WHEN 'altLabel' THEN 3 ELSE 4 END as prop_priority
            FROM literal_props_fts fts
            JOIN literal_props lp ON fts.rowid = lp.rowid
            LEFT JOIN category_mapping cm ON lp.concept_id = cm.concept_id
            WHERE lp.concept_id LIKE 'nlk:KSH%'
            AND lp.concept_id NOT LIKE 'nls:%'
            AND lp.prop IN ('prefLabel', 'label', 'altLabel')
            AND fts.value_normalized MATCH ?
            """
            params = [fts_query]

            # 주제 카테고리 필터링
            if main_category and main_category != "전체":
                base_query += " AND cm.main_category = ?"
                params.append(main_category)

        # ORDER BY (카테고리 전용은 fts.rank 없음)
        if fts_query is None:
            base_query += """
            ORDER BY
                prop_priority ASC,
                LENGTH(lp.value) ASC,
                lp.value ASC
            """
        else:
            base_query += """
            ORDER BY
                fts.rank ASC,
                prop_priority ASC,
                LENGTH(lp.value) ASC,
                lp.value ASC
            """

        # WITH + WINDOW FUNCTION으로 중복 제거
        optimized_query = f"""
        WITH RankedResults AS (
            {base_query}
        )
        SELECT DISTINCT
            concept_id,
            FIRST_VALUE(matched_value) OVER (
                PARTITION BY concept_id
                ORDER BY prop_priority ASC, LENGTH(matched_value) ASC
            ) as matched_value
        FROM RankedResults
        """

        cursor.execute(optimized_query, params)
        all_results = cursor.fetchall()

        # Python에서 LIMIT 적용
        return all_results[:limit] if limit else all_results

    def _fetch_concept_details(self, cursor, concept_ids: list) -> list:
        """
        개념들의 상세 정보 조회 (배치)

        Args:
            cursor: 데이터베이스 커서
            concept_ids: 조회할 concept_id 리스트

        Returns:
            상세 정보 결과 리스트
        """
        placeholders = ",".join("?" for _ in concept_ids)
        detail_query = f"""
        SELECT
            c.concept_id,
            (
                SELECT value FROM literal_props
                WHERE concept_id = c.concept_id AND prop IN ('prefLabel', 'label')
                ORDER BY CASE prop WHEN 'prefLabel' THEN 1 ELSE 2 END
                LIMIT 1
            ) as pref_label,
            cm.main_category,
            dm.ddc_classification,
            km.kdc_like_classification
        FROM concepts c
        LEFT JOIN category_mapping cm ON c.concept_id = cm.concept_id
        LEFT JOIN ddc_mapping dm ON c.concept_id = dm.concept_id
        LEFT JOIN kdc_mapping km ON c.concept_id = km.concept_id
        WHERE c.concept_id IN ({placeholders})
        """
        cursor.execute(detail_query, concept_ids)
        return cursor.fetchall()

    def _fetch_concept_relations(self, conn, concept_ids: list) -> dict:
        """
        개념들의 관계어 조회 (broader, narrower, related, synonyms)

        Args:
            conn: 데이터베이스 연결
            concept_ids: 조회할 concept_id 리스트

        Returns:
            {concept_id: {'broader': [...], 'narrower': [...], 'related': [...], 'synonyms': [...]}}
        """
        relations = {}

        for cid in concept_ids:
            relations[cid] = {
                "broader": self._get_broader_for_concept(conn, cid),
                "narrower": self._get_narrower_for_concept(conn, cid),
                "related": self._get_related_for_concept(conn, cid),
                "synonyms": self._get_synonyms_for_concept(conn, cid),
            }

        return relations

    def _calculate_match_priority(self, matched_value: str, search_term: str) -> tuple:
        """
        매칭 우선순위를 계산합니다.

        메르카츠님 요구사항:
        1순위: 완벽 매칭(전방매칭 + 글자 수까지 완벽 매칭)
        2순위: 전방 매칭인데 글자수가 짧은 것
        3순위: 전방 매칭이 아니면서 글자수가 짧은 것
        4순위: 원괄호 안 매칭

        Returns:
            tuple: (priority, length, alphabetical_sort_key)
        """
        if not matched_value or not search_term:
            return (5, 9999, matched_value or "")

        # 한글 여부 검사
        has_korean = bool(re.search(r"[\uac00-\ud7a3]", search_term))

        # 순수 주제명 추출 (괄호/각괄호 제거)
        pure_subject = self._get_clean_subject_for_sorting(matched_value)

        # 괄호 안 내용 추출
        parentheses_content = ""
        brackets_content = ""

        paren_match = re.search(r"\(([^)]*)\)", matched_value)
        if paren_match:
            parentheses_content = paren_match.group(1)

        bracket_match = re.search(r"\[([^\]]*)\]", matched_value)
        if bracket_match:
            brackets_content = bracket_match.group(1)

        # 한글과 영어에 따른 다른 정규화 방식 적용
        if has_korean:
            # 한글 검색: 단수화 없이 공백 제거 + 소문자만
            norm_search = re.sub(r"\s+", "", search_term.lower())
            norm_pure = re.sub(r"\s+", "", pure_subject.lower())
            norm_paren = re.sub(r"\s+", "", parentheses_content.lower())
            norm_bracket = re.sub(r"\s+", "", brackets_content.lower())
        else:
            # 영어 검색: 기존 _norm_for_compare 로직 사용 (단수화 포함)
            def _norm_for_compare_en(s: str) -> str:
                if not s:
                    return ""
                base = self._get_clean_subject_for_sorting(str(s))
                base = re.sub(r"\s+", "", base).lower()
                try:
                    base = inflection.singularize(base)
                except Exception:
                    pass
                return base

            norm_search = _norm_for_compare_en(search_term)
            norm_pure = _norm_for_compare_en(pure_subject)
            norm_paren = _norm_for_compare_en(parentheses_content)
            norm_bracket = _norm_for_compare_en(brackets_content)

        # 1순위: 완벽 매칭 (순수 주제명에서 전방매칭 + 길이 일치)
        if norm_pure.startswith(norm_search) and len(norm_pure) == len(norm_search):
            return (1, len(pure_subject), pure_subject.lower())

        # 2순위: 전방 매칭이면서 순수 주제명이 짧은 것
        if norm_pure.startswith(norm_search):
            return (2, len(pure_subject), pure_subject.lower())

        # 3순위: 순수 주제명에 포함되지만 전방매칭이 아닌 것 (짧은 순)
        if norm_search in norm_pure:
            return (3, len(pure_subject), pure_subject.lower())

        # 4순위: 원괄호 안에서 매칭
        if norm_search in norm_paren or norm_paren.startswith(norm_search):
            return (4, len(matched_value), matched_value.lower())

        # 5순위: 각괄호 안에서 매칭
        if norm_search in norm_bracket or norm_bracket.startswith(norm_search):
            return (4, len(matched_value), matched_value.lower())

        # 6순위: 기타 (매칭되지 않음)
        return (5, len(matched_value), matched_value.lower())

    def _build_concepts_dataframe(
        self,
        detail_results: list,
        relations: dict,
        concept_match_map: dict,
        processed_term: str,
    ) -> pd.DataFrame:
        """
        개념 검색 결과를 DataFrame으로 구성

        Args:
            detail_results: 상세 정보 결과
            relations: 관계어 딕셔너리
            concept_match_map: {concept_id: matched_value}
            processed_term: 전처리된 검색어

        Returns:
            정렬 및 포맷팅된 DataFrame
        """
        # 다중 검색어 처리
        first_search_term = (
            processed_term.split(",")[0].strip()
            if "," in processed_term
            else processed_term
        )

        # 결과 구성
        rows = []
        for row in detail_results:
            concept_id = row["concept_id"]
            matched_value = concept_match_map.get(concept_id, "")

            # 우선순위 계산
            priority = self._calculate_match_priority(matched_value, first_search_term)

            # KSH 마크업 형식으로 주제명 생성: ▼a{label}▼0{KSH_code}▲
            pref_label = row["pref_label"] or matched_value
            subject_with_code = self._format_ksh_display(concept_id, pref_label)

            rows.append(
                {
                    "concept_id": concept_id,
                    "subject": subject_with_code,
                    "main_category": row["main_category"] or "",
                    "classification_ddc": row["ddc_classification"] or "",
                    "classification_kdc_like": row["kdc_like_classification"] or "",
                    "matched": matched_value,
                    "related": "; ".join(
                        relations.get(concept_id, {}).get("related", [])
                    ),
                    "broader": "; ".join(
                        relations.get(concept_id, {}).get("broader", [])
                    ),
                    "narrower": "; ".join(
                        relations.get(concept_id, {}).get("narrower", [])
                    ),
                    "synonyms": "; ".join(
                        relations.get(concept_id, {}).get("synonyms", [])
                    ),
                    "ksh_link_url": f"https://lod.nl.go.kr/page/concept/{self._strip_namespace(concept_id)}",
                    "_sort_priority": priority,
                }
            )

        # DataFrame 생성 및 정렬
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("_sort_priority").drop(columns=["_sort_priority"])

        return df

    def get_ksh_entries(
        self, search_term=None, main_category=None, limit=None, exact_match=False
    ):
        """
        🚀 [리팩토링] KSH 검색 - 작은 메서드들로 분해하여 가독성 향상

        Args:
            search_term: 검색어
            main_category: 주제 카테고리 필터
            limit: 결과 개수 제한
            exact_match: 완전 일치 검색 여부 (현재 미사용)

        Returns:
            검색 결과 DataFrame
        """
        conn = None
        try:
            conn = self.db_manager._get_concepts_connection()
            cursor = conn.cursor()

            logger.info(
                f"🔍 get_ksh_entries: search_term='{search_term}', main_category='{main_category}', limit={limit}"
            )

            # FTS5 테이블 존재 여부 확인
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='literal_props_fts'"
            )
            use_fts5 = cursor.fetchone() is not None

            if not use_fts5:
                logger.warning("⚠️ literal_props_fts 테이블이 없습니다.")
                return pd.DataFrame()

            # 검색어 전처리
            # ✅ 카테고리 검색: search_term이 없어도 main_category가 있으면 진행
            if not search_term:
                if not main_category or main_category == "전체":
                    return pd.DataFrame()
                # 카테고리 전용 검색 (검색어 없이 카테고리만)
                search_term = ""
                processed_term = ""
                fts_query = None
            else:
                processed_term = self.preprocess_search_term(search_term)
                # 1. FTS5 쿼리 생성
                fts_query = self._build_fts5_query(processed_term)
                if not fts_query and not main_category:
                    return pd.DataFrame()

            # 2. FTS5 검색 실행
            search_results = self._execute_fts5_search(
                cursor, fts_query, main_category, limit
            )
            logger.info(
                f"📊 [FTS5 최적화] 검색 완료: {len(search_results)}개 concept 발견"
            )

            if not search_results:
                return pd.DataFrame()

            # 3. concept_id 목록 및 매칭 맵 생성
            concept_match_map = {
                row["concept_id"]: row["matched_value"] for row in search_results
            }
            concept_ids = list(concept_match_map.keys())

            # 4. 상세 정보 조회
            detail_results = self._fetch_concept_details(cursor, concept_ids)

            # 5. 관계어 조회
            relations = self._fetch_concept_relations(conn, concept_ids)

            # 6. DataFrame 구성 및 정렬
            df = self._build_concepts_dataframe(
                detail_results, relations, concept_match_map, processed_term
            )

            return df.fillna("")

        except Exception as e:
            logger.error(f"❌ KSH 검색 중 오류: {e}")
            import traceback

            traceback.print_exc()
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    # 🆕 관계어 조회를 위한 헬퍼 메서드들 추가

    # 🆕 관계어 조회를 위한 헬퍼 메서드들 추가

    def get_ksh_entries_batch(self, search_terms: list):
        """
        주어진 여러 주제어에 대한 KSH 데이터를 한 번의 쿼리로 조회합니다.
        Args:
            search_terms (list): 조회할 pure_subject_name 리스트.
        Returns:
            pandas.DataFrame: 조회된 결과.
        """
        conn = None
        if not search_terms:
            return pd.DataFrame()
        try:
            conn = self.db_manager._get_ksh_connection()
            # SQL Injection을 방지하기 위해 플레이스홀더 사용
            placeholders = ",".join("?" for _ in search_terms)
            query = (
                f"SELECT * FROM ksh_entries WHERE pure_subject_name IN ({placeholders})"
            )

            df = pd.read_sql_query(query, conn, params=search_terms)
            return df
        except Exception as e:
            print(f"오류: KSH 데이터 일괄 조회 중 오류 발생: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    def get_ksh_entries_batch_exact(self, terms_with_qualifiers):
        """
        [수정됨] 여러 용어(수식어 포함)에 대한 정확한 KSH 항목을 일괄 조회합니다.
        literal_props 테이블에서 value를 직접 비교하여 정확성을 높입니다.

        Args:
            terms_with_qualifiers: [(pure_subject, parentheses, brackets), ...] 형태의 리스트

        Returns:
            pandas.DataFrame: 조회된 KSH 항목들 (기존 형식 호환)
        """
        conn = None
        if not terms_with_qualifiers:
            return pd.DataFrame()

        try:
            conn = self.db_manager._get_concepts_connection()
            cursor = conn.cursor()

            # 1. 입력된 모든 주제명(수식어 포함) 문자열 생성
            full_subject_names = []
            input_map = {}  # (pure, paren, bracket) -> full_subject 매핑
            for pure, paren, bracket in terms_with_qualifiers:
                name = pure
                if paren:
                    name += f"({paren})"
                if bracket:
                    name += f"[{bracket}]"
                full_subject_names.append(name)
                input_map[(pure, paren or "", bracket or "")] = name

            if not full_subject_names:
                return pd.DataFrame()

            # 2. literal_props 테이블에서 정확히 일치하는 value 검색 (IN 절 사용)
            placeholders = ",".join(["?" for _ in full_subject_names])
            query = f"""
            SELECT
                lp.concept_id,
                lp.value AS matched_value,
                lp.prop
            FROM literal_props lp
            WHERE lp.value IN ({placeholders})
              AND lp.concept_id LIKE 'nlk:KSH%' -- nls: 제외
              AND lp.prop IN ('prefLabel', 'label', 'altLabel') -- 주요 라벨만 고려
            """
            cursor.execute(query, full_subject_names)
            prop_results = cursor.fetchall()

            # 3. concept_id별로 가장 우선순위 높은 항목 선택 (prefLabel > label > altLabel)
            best_match_per_value = {}  # {full_subject: concept_id}
            temp_matches = {}  # {full_subject: (concept_id, priority)}
            prop_priority = {"prefLabel": 1, "label": 2, "altLabel": 3}

            for row in prop_results:
                concept_id = row["concept_id"]
                value = row["matched_value"]
                prop = row["prop"]
                priority = prop_priority.get(prop, 4)

                if value not in temp_matches or priority < temp_matches[value][1]:
                    temp_matches[value] = (concept_id, priority)

            best_match_per_value = {
                val: cid for val, (cid, pri) in temp_matches.items()
            }

            # 4. 선택된 concept_id들의 상세 정보 (카테고리, DDC, KDC) 조회
            found_concept_ids = list(best_match_per_value.values())
            if not found_concept_ids:
                return pd.DataFrame()

            details_map = {}
            id_placeholders = ",".join(["?" for _ in found_concept_ids])
            detail_query = f"""
            SELECT
                c.concept_id,
                cm.main_category,
                dm.ddc_classification,
                km.kdc_like_classification,
                (
                    SELECT value FROM literal_props
                    WHERE concept_id = c.concept_id AND prop IN ('prefLabel', 'label')
                    ORDER BY CASE prop WHEN 'prefLabel' THEN 1 ELSE 2 END
                    LIMIT 1
                ) as pref_label -- 💡 [핵심 수정] KSH 코드에 매칭되는 실제 prefLabel을 조회합니다.
            FROM concepts c
            LEFT JOIN category_mapping cm ON c.concept_id = cm.concept_id
            LEFT JOIN ddc_mapping dm ON c.concept_id = dm.concept_id
            LEFT JOIN kdc_mapping km ON c.concept_id = km.concept_id
            WHERE c.concept_id IN ({id_placeholders})
            """
            cursor.execute(detail_query, found_concept_ids)
            detail_results = cursor.fetchall()
            for row in detail_results:
                details_map[row["concept_id"]] = row

            # 5. 최종 DataFrame 구성
            data = []
            processed_inputs = set()  # 입력 중복 처리 방지

            for pure, paren, bracket in terms_with_qualifiers:
                input_key = (pure, paren or "", bracket or "")
                if input_key in processed_inputs:
                    continue

                full_subject = input_map.get(input_key)
                if not full_subject:
                    continue

                concept_id = best_match_per_value.get(full_subject)
                if not concept_id:  # DB에서 정확히 일치하는 항목 못 찾음
                    continue

                details = details_map.get(concept_id)
                if not details:  # 상세 정보 못 찾음 (이론상 발생 안 함)
                    continue

                ksh_code = self._strip_namespace(concept_id)
                entry = {
                    # 입력값 기준 필드
                    "pure_subject_name": pure,
                    "qualifier_parentheses": paren or "",
                    "qualifier_square_brackets": bracket or "",
                    # DB 조회 결과 필드
                    "ksh_code": ksh_code,
                    "pref_label": details["pref_label"]
                    or full_subject,  # 💡 [핵심 수정] 조회된 pref_label을 반환값에 추가합니다.
                    "main_category": details["main_category"] or "",
                    "classification_ddc": details["ddc_classification"] or "",
                    "classification_kdc_like": details["kdc_like_classification"] or "",
                    "ksh_link_url": f"https://lod.nl.go.kr/page/concept/{ksh_code}",  # LOD URL로 변경
                }
                data.append(entry)
                processed_inputs.add(input_key)

            return pd.DataFrame(data)

        except Exception as e:
            print(f"오류: [수정됨] 일괄 KSH 정확 매칭 조회 중 오류: {e}")
            import traceback

            traceback.print_exc()  # 상세 에러 출력
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    # 7. 다국어 검색 메서드 추가 (보너스)

    def get_ksh_entries_exact_match(
        self, pure_subject, parentheses=None, brackets=None, limit=1
    ):
        """
        수식어까지 포함한 정확한 KSH 항목 조회
        동음이의어 구분을 위해 parentheses와 brackets까지 매칭

        Args:
            pure_subject (str): 순수 주제명 (예: "눈")
            parentheses (str, optional): 원괄호 수식어 (예: "eye", "snow")
            brackets (str, optional): 각괄호 수식어 (예: "英語", "臺本")
            limit (int): 최대 반환 개수

        Returns:
            pandas.DataFrame: 매칭된 KSH 항목들
        """
        conn = None
        try:
            conn = self.db_manager._get_ksh_connection()

            # 기본 조건: pure_subject_name 매칭
            conditions = ["pure_subject_name = ?"]
            params = [pure_subject]

            # 괄호 조건 추가
            if parentheses and parentheses.strip():
                conditions.append("qualifier_parentheses = ?")
                params.append(parentheses.strip())
            else:
                conditions.append(
                    "(qualifier_parentheses IS NULL OR qualifier_parentheses = '')"
                )

            # 각괄호 조건 추가
            if brackets and brackets.strip():
                conditions.append("qualifier_square_brackets = ?")
                params.append(brackets.strip())
            else:
                conditions.append(
                    "(qualifier_square_brackets IS NULL OR qualifier_square_brackets = '')"
                )

            query = f"""
            SELECT * FROM ksh_entries
            WHERE {' AND '.join(conditions)}
            ORDER BY id ASC
            LIMIT ?
            """
            params.append(limit)

            df_result = pd.read_sql_query(query, conn, params=params)
            return df_result

        except Exception as e:
            print(f"오류: 정확한 매칭 조회 중 오류: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    # 5. get_ksh_entries_batch_exact 메서드 교체

    def search_integrated_ksh(self, search_term):
        """
        🔧 수정된 통합 KSH 검색 로직 - DDC 숫자만 있는 경우도 정확 인식
        """
        start_time = time.time()
        logger.info(f"🟢 [TIMING] search_integrated_ksh 시작: '{search_term}'")

        term = search_term.strip()

        # 1. 검색어 유형 분석 - DDC 숫자만 있는 경우도 인식
        # 기존: r"\b\d{1,3}(?:\.\d+)?\b"
        # 수정: 순수 숫자 3자리도 DDC로 인식하도록 개선
        ddc_codes = []

        # DDC 패턴: 3자리 숫자, 소수점 포함 숫자 (001, 004, 650, 650.1 등)
        ddc_pattern_matches = re.findall(r"\b\d{1,3}(?:\.\d+)?\b", term)

        # 검색어가 순수 숫자로만 구성되어 있고 1~4자리인 경우 DDC로 간주
        if term.isdigit() and 1 <= len(term) <= 4:
            ddc_codes = [term]
            logger.info(f"🔵 [DDC_DETECT] 순수 숫자 '{term}' → DDC 코드로 인식")
        elif ddc_pattern_matches:
            # 기존 패턴 매칭 결과 사용
            for match in ddc_pattern_matches:
                # 3자리 이하 정수이거나 소수점이 있는 경우만 DDC로 인식
                if "." in match or (match.isdigit() and len(match) <= 3):
                    ddc_codes.append(match)

        ksh_codes = [t.strip() for t in re.findall(r"\bKSH\d+\b", term, re.IGNORECASE)]

        # DDC, KSH 코드를 제외한 나머지를 주제명/키워드로 간주
        keywords_str = term
        for code in ddc_codes + ksh_codes:
            keywords_str = keywords_str.replace(code, "")
        keywords = [kw.strip() for kw in keywords_str.split(",") if kw.strip()]

        logger.info(f"🔍 [TIMING] 검색어 분석 완료 ({time.time() - start_time:.3f}초)")
        logger.info(f"   - DDC 코드: {ddc_codes}")
        logger.info(f"   - KSH 코드: {ksh_codes}")
        logger.info(f"   - 키워드: {keywords}")

        # 결과 DataFrame들
        df_concept_search = pd.DataFrame()  # 상단 트리뷰용
        df_bibliographic = pd.DataFrame()  # 하단 트리뷰용

        # 검색 타입을 반환값에 포함하기 위해 저장
        search_type = None

        # 2. 검색어 우선순위에 따라 검색 실행
        # DDC 코드가 있을 경우 서지 DB만 검색 (컨셉 DB 비활성화)
        if ddc_codes:
            search_type = "ddc"
            logger.info(f"🔵 [TIMING] DDC 검색 시작 (서지 DB만)...")
            df_bibliographic = self._search_by_ddc_with_fallback(ddc_codes)
            logger.info(
                f"🔵 [TIMING] DDC 검색 완료 ({time.time() - start_time:.3f}초, {len(df_bibliographic)}개 결과)"
            )

        # KSH 코드가 있을 경우 서지 DB만 검색 (컨셉 DB 비활성화)
        elif ksh_codes:
            search_type = "ksh"
            logger.info(f"🟡 [TIMING] KSH 코드 검색 시작 (서지 DB만)...")
            df_bibliographic = self._search_by_ksh_code(ksh_codes)
            logger.info(
                f"🟡 [TIMING] KSH 코드 검색 완료 ({time.time() - start_time:.3f}초, {len(df_bibliographic)}개 결과)"
            )

        # DDC/KSH 코드가 없고 키워드만 있는 경우 (수정된 로직)
        elif keywords:
            search_type = "keyword"
            # -------------------
            # ✅ [핵심 최적화] 여러 키워드를 루프로 개별 검색하는 대신,
            # 콤마로 연결된 전체 검색어를 한 번에 처리하여 DB 조회를 최소화합니다.
            concept_start = time.time()
            logger.info(
                f"🟠 [TIMING] NLK Concept DB 및 서지 DB 동시 검색 시작 (통합 키워드)..."
            )

            # 1. 컨셉 DB 검색 (전체 검색어 한 번에 전달)
            try:
                from Search_KSH_Local import KshLocalSearcher

                searcher = KshLocalSearcher(self.db_manager)
                # search_concepts -> get_ksh_entries는 콤마로 구분된 문자열을 OR 조건으로 처리하는 기능이 이미 구현되어 있습니다.
                df_concept_search = searcher.search_concepts(keyword=search_term)
            except Exception as e:
                logger.error(f"오류: '{search_term}' 컨셉 DB 검색 중 오류: {e}")
                df_concept_search = (
                    pd.DataFrame()
                )  # 오류 발생 시 빈 DataFrame으로 초기화

            # 2. 서지 DB 검색 (순차 처리 - SQLite Write Lock으로 인해 병렬 처리 무의미)
            # ⚡ [성능 개선] 불필요한 ThreadPoolExecutor 제거
            bibliographic_dfs = []
            try:
                for kw in keywords:
                    try:
                        df_b = self.get_bibliographic_by_subject_name(kw)
                        if not df_b.empty:
                            bibliographic_dfs.append(df_b)
                    except Exception as e:
                        logger.error(f"오류: '{kw}' 서지 DB 검색 중 오류: {e}")
            except Exception as e:
                logger.error(f"오류: 서지 DB 검색 중 오류: {e}")

            # 3. 결과 통합 및 중복 제거
            # df_concept_search는 이미 단일 DataFrame이므로 별도 통합이 필요 없습니다.
            if not df_concept_search.empty:
                logger.info(
                    f"🟠 [TIMING] NLK Concept DB 검색 완료 ({time.time() - concept_start:.3f}초, {len(df_concept_search)}개 결과)"
                )

            if bibliographic_dfs:
                df_bibliographic = pd.concat(
                    bibliographic_dfs, ignore_index=True
                ).drop_duplicates(subset=["identifier"])
                logger.info(
                    f"🟣 [TIMING] 서지 DB 검색 완료 ({time.time() - concept_start:.3f}초, {len(df_bibliographic)}개 결과)"
                )
            else:
                # bibliographic_dfs가 비어있을 경우를 대비해 df_bibliographic을 초기화합니다.
                df_bibliographic = pd.DataFrame()
            # -------------------

        total_time = time.time() - start_time
        logger.info(
            f"🏁 [TIMING] search_integrated_ksh 완료: {total_time:.3f}초, Concept DB: {len(df_concept_search)}개, Biblio DB: {len(df_bibliographic)}개 결과"
        )

        # 🎯 검색 타입도 함께 반환
        return df_concept_search.fillna(""), df_bibliographic.fillna(""), search_type

    def search_integrated_ksh_with_relations(self, hierarchy_keywords):
        """
        계층적 키워드 + 관계 정보 확장 검색
        실제 프로젝트 구조에 맞춰 구현
        """
        all_keywords = set()

        # 계층별 키워드 수집
        if isinstance(hierarchy_keywords, dict):
            for level, keywords in hierarchy_keywords.items():
                if isinstance(keywords, list):
                    all_keywords.update([k.strip() for k in keywords if k.strip()])
        elif isinstance(hierarchy_keywords, list):
            all_keywords.update([k.strip() for k in hierarchy_keywords if k.strip()])
        elif isinstance(hierarchy_keywords, str):
            all_keywords.add(hierarchy_keywords.strip())

        # Concept DB 관계 정보로 키워드 확장
        expanded_keywords = set(all_keywords)

        for keyword in list(all_keywords)[:5]:  # 성능을 위해 최대 5개 키워드만 확장
            try:
                relations = self.get_concept_relations(keyword)

                # 상위어, 하위어, 관련어를 확장 키워드에 추가 (각 타입당 최대 2개)
                for relation_type, terms in relations.items():
                    if relation_type in ["broader", "narrower", "related"] and terms:
                        expanded_keywords.update(terms[:2])

            except Exception as e:
                print(f"경고: '{keyword}' 관계 확장 중 오류: {e}")
                continue

        # 너무 많으면 제한 (성능 고려)
        final_keywords = list(expanded_keywords)[:12]
        expanded_keyword_string = ", ".join(final_keywords)

        print(
            f"🔗 키워드 확장 완료: 원본 {len(all_keywords)}개 → 확장 {len(final_keywords)}개"
        )
        print(f"   확장된 키워드: {expanded_keyword_string}")

        # 확장된 키워드들로 통합 검색
        return self.search_integrated_ksh(expanded_keyword_string)

    def search_ksh_by_language(self, keyword, language="ko", limit=1000):
        """
        🚀 최적화된 다국어 검색: value_normalized 컬럼 활용
        """
        conn = None
        try:
            conn = self.db_manager._get_concepts_connection()
            cursor = conn.cursor()

            # 검색어 정규화
            normalized_keyword = keyword.replace(" ", "")

            if language == "en":
                # 영어: ASCII 문자만 포함된 altLabel, value_normalized 사용
                search_query = """
                SELECT DISTINCT c.concept_id, lp_match.value as matched_term, lp_pref.value as pref_label
                FROM concepts c
                LEFT JOIN literal_props lp_pref ON c.concept_id = lp_pref.concept_id AND lp_pref.prop = 'prefLabel'
                LEFT JOIN literal_props lp_match ON c.concept_id = lp_match.concept_id AND lp_match.prop = 'altLabel'
                WHERE lp_match.value_normalized LIKE ?
                AND lp_match.value NOT GLOB '*[ㄱ-ㅣ가-힣]*'
                LIMIT ?
                """
            else:
                # 한국어: 모든 라벨에서 검색, value_normalized 사용
                search_query = """
                SELECT DISTINCT c.concept_id, lp_match.value as matched_term, lp_pref.value as pref_label
                FROM concepts c
                LEFT JOIN literal_props lp_pref ON c.concept_id = lp_pref.concept_id AND lp_pref.prop = 'prefLabel'
                LEFT JOIN literal_props lp_match ON c.concept_id = lp_match.concept_id
                    AND lp_match.prop IN ('prefLabel', 'label', 'altLabel')
                WHERE lp_match.value_normalized LIKE ?
                LIMIT ?
                """

            cursor.execute(search_query, (f"%{normalized_keyword}%", limit))
            results = cursor.fetchall()

            # DataFrame 구성
            data = []
            for row in results:
                concept_id = row["concept_id"]
                ksh_code = self._strip_namespace(concept_id)
                pref_label = row["pref_label"] or ""

                entry = {
                    "id": len(data) + 1,
                    "original_subject": self._format_ksh_display(
                        concept_id, pref_label
                    ),
                    "pure_subject_name": pref_label,
                    "matched_term": row["matched_term"],
                    "ksh_code": ksh_code,
                    "language": language,
                    "ksh_link_url": f"https://librarian.nl.go.kr/LI/contents/L20201000000.do?controlNo={ksh_code}",
                }
                data.append(entry)

            return pd.DataFrame(data)

        except Exception as e:
            print(f"오류: 다국어 검색 중 오류: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    # 3. 새 DB 처리용 헬퍼 메서드들 추가
