"""
get_ksh_entries 메서드를 작은 메서드들로 분해하는 리팩토링 스크립트
472줄 → 6개의 작은 메서드로 분리
"""

# 분해할 메서드들:
# 1. _build_fts5_query(processed_term) -> str
# 2. _execute_fts5_search(cursor, fts_query, main_category, limit) -> list
# 3. _fetch_concept_details(cursor, concept_ids) -> list
# 4. _fetch_concept_relations(conn, concept_ids) -> dict
# 5. _build_concepts_dataframe(detail_results, relations, concept_match_map, processed_term) -> DataFrame
# 6. get_ksh_entries (메인 조정자 메서드) -> DataFrame

refactored_methods = '''
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
            terms = [term.strip().replace(" ", "") for term in processed_term.split(",") if term.strip()]

            fts_terms = []
            for t in terms:
                sanitized_t = re.sub(r'[^\\w]', '', t)
                if sanitized_t:
                    fts_terms.append(f'"{sanitized_t}" OR {sanitized_t}*')

            return " OR ".join(fts_terms)
        else:
            # 단일 검색어: "한국" OR 한국*
            sanitized_term = re.sub(r'[^\\w]', '', normalized_term)
            if sanitized_term:
                return f'"{sanitized_term}" OR {sanitized_term}*'
            else:
                return ""


    def _execute_fts5_search(self, cursor, fts_query: str, main_category: str = None, limit: int = None) -> list:
        """
        FTS5 전문 검색 실행

        Args:
            cursor: 데이터베이스 커서
            fts_query: FTS5 MATCH 쿼리 문자열
            main_category: 주제 카테고리 필터
            limit: 결과 개수 제한

        Returns:
            검색 결과 리스트 [(concept_id, matched_value), ...]
        """
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
                'broader': self._get_broader_for_concept(conn, cid),
                'narrower': self._get_narrower_for_concept(conn, cid),
                'related': self._get_related_for_concept(conn, cid),
                'synonyms': self._get_synonyms_for_concept(conn, cid)
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
        has_korean = bool(re.search(r"[\\uac00-\\ud7a3]", search_term))

        # 순수 주제명 추출 (괄호/각괄호 제거)
        pure_subject = self._get_clean_subject_for_sorting(matched_value)

        # 괄호 안 내용 추출
        parentheses_content = ""
        brackets_content = ""

        paren_match = re.search(r"\\(([^)]*)\\)", matched_value)
        if paren_match:
            parentheses_content = paren_match.group(1)

        bracket_match = re.search(r"\\[([^\\]]*)\\]", matched_value)
        if bracket_match:
            brackets_content = bracket_match.group(1)

        # 한글과 영어에 따른 다른 정규화 방식 적용
        if has_korean:
            # 한글 검색: 단수화 없이 공백 제거 + 소문자만
            norm_search = re.sub(r"\\s+", "", search_term.lower())
            norm_pure = re.sub(r"\\s+", "", pure_subject.lower())
            norm_paren = re.sub(r"\\s+", "", parentheses_content.lower())
            norm_bracket = re.sub(r"\\s+", "", brackets_content.lower())
        else:
            # 영어 검색: 기존 _norm_for_compare 로직 사용 (단수화 포함)
            def _norm_for_compare_en(s: str) -> str:
                if not s:
                    return ""
                base = self._get_clean_subject_for_sorting(str(s))
                base = re.sub(r"\\s+", "", base).lower()
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


    def _build_concepts_dataframe(self, detail_results: list, relations: dict,
                                   concept_match_map: dict, processed_term: str) -> pd.DataFrame:
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
        first_search_term = processed_term.split(",")[0].strip() if "," in processed_term else processed_term

        # 결과 구성
        rows = []
        for row in detail_results:
            concept_id = row["concept_id"]
            matched_value = concept_match_map.get(concept_id, "")

            # 우선순위 계산
            priority = self._calculate_match_priority(matched_value, first_search_term)

            rows.append({
                "concept_id": concept_id,
                "subject": row["pref_label"] or matched_value,
                "main_category": row["main_category"] or "",
                "classification_ddc": row["ddc_classification"] or "",
                "classification_kdc_like": row["kdc_like_classification"] or "",
                "matched": matched_value,
                "related": "; ".join(relations.get(concept_id, {}).get('related', [])),
                "broader": "; ".join(relations.get(concept_id, {}).get('broader', [])),
                "narrower": "; ".join(relations.get(concept_id, {}).get('narrower', [])),
                "synonyms": "; ".join(relations.get(concept_id, {}).get('synonyms', [])),
                "ksh_link_url": f"https://lod.nl.go.kr/page/concept/{self._strip_namespace(concept_id)}",
                "_sort_priority": priority
            })

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
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='literal_props_fts'")
            use_fts5 = cursor.fetchone() is not None

            if not use_fts5:
                logger.warning("⚠️ literal_props_fts 테이블이 없습니다.")
                return pd.DataFrame()

            # 검색어 전처리
            if not search_term:
                return pd.DataFrame()

            processed_term = self.preprocess_search_term(search_term)

            # 1. FTS5 쿼리 생성
            fts_query = self._build_fts5_query(processed_term)
            if not fts_query:
                return pd.DataFrame()

            # 2. FTS5 검색 실행
            search_results = self._execute_fts5_search(cursor, fts_query, main_category, limit)
            logger.info(f"📊 [FTS5 최적화] 검색 완료: {len(search_results)}개 concept 발견")

            if not search_results:
                return pd.DataFrame()

            # 3. concept_id 목록 및 매칭 맵 생성
            concept_match_map = {row["concept_id"]: row["matched_value"] for row in search_results}
            concept_ids = list(concept_match_map.keys())

            # 4. 상세 정보 조회
            detail_results = self._fetch_concept_details(cursor, concept_ids)

            # 5. 관계어 조회
            relations = self._fetch_concept_relations(conn, concept_ids)

            # 6. DataFrame 구성 및 정렬
            df = self._build_concepts_dataframe(detail_results, relations, concept_match_map, processed_term)

            return df.fillna("")

        except Exception as e:
            logger.error(f"❌ KSH 검색 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()
'''

print("=" * 60)
print("get_ksh_entries 리팩토링 계획")
print("=" * 60)
print("\n기존: get_ksh_entries 1개 메서드 (472줄)")
print("\n분해 후: 7개 메서드")
print("  1. _build_fts5_query (~30줄) - FTS5 쿼리 문자열 생성")
print("  2. _execute_fts5_search (~60줄) - FTS5 검색 실행")
print("  3. _fetch_concept_details (~25줄) - 상세 정보 조회")
print("  4. _fetch_concept_relations (~15줄) - 관계어 조회")
print("  5. _calculate_match_priority (~90줄) - 매칭 우선순위 계산")
print("  6. _build_concepts_dataframe (~50줄) - DataFrame 구성")
print("  7. get_ksh_entries (~60줄) - 메인 조정자")
print("\n총합: ~330줄 (140줄 절감, 중복 제거)")
print("\n리팩토링 메서드를 refactored_get_ksh_entries.txt에 저장...")

with open(r'c:\Python\refactored_get_ksh_entries.txt', 'w', encoding='utf-8') as f:
    f.write(refactored_methods)

print("✅ 완료! refactored_get_ksh_entries.txt 파일 확인 후 수동으로 적용하세요.")
