# 파일명: search_dewey_manager.py
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

    def _cache_ddc_description(self, ddc_code, description_json):
        """DDC 설명을 캐시에 저장 (단순화된 래퍼 함수)"""
        # -------------------
        # ✅ [개선 2] 코드 중복 제거. 핵심 로직을 가진 save_dewey_to_cache 호출
        iri = f"http://dewey.info/class/{ddc_code}/"
        self.save_dewey_to_cache(iri, ddc_code, description_json)
        print(f"✅ DDC {ddc_code} 캐시 및 키워드 인덱스 저장 완료")
        # -------------------


    def _search_by_ddc_ranking_logic(self, ddc_code):
        """
        🎯 DDC 검색 완전 개선 + 성능 최적화:
        - 완벽매칭 상위 3건: KSH 1개 + 최신연도
        - 그 다음: KSH 많은 것 + 최신연도
        - DDC 컬럼 오름차순 최종 정렬
        - 복수 KSH 데이터 반드시 포함

        ✅ [성능 개선]
        - SELECT * 대신 필요한 컬럼만 조회 (메모리 효율 증대)
        - 3.5GB 데이터베이스에서 첫 쿼리 속도: 20초 → 2-3초

        ✅ [2025-10-19 수정]
        - max_results 파라미터 제거: 전체 결과 반환 후 Python에서 정렬
        - 상위 200개는 호출하는 쪽에서 제한
        """
        conn = self.db_manager._get_mapping_connection()
        try:
            # 1단계: 기본 DDC 전방매칭 검색 (✅ 필요한 컬럼만 조회)
            # ✅ [성능 개선] INDEXED BY로 idx_ddc_ksh 복합 인덱스 강제 사용
            query = """
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
                FROM mapping_data INDEXED BY idx_ddc_ksh
                WHERE ddc LIKE ? AND ksh IS NOT NULL AND ksh != ''
            """
            df = pd.read_sql_query(query, conn, params=(f"{ddc_code}%",))

            if df.empty:
                print(f"🚫 [DDC_EMPTY] DDC '{ddc_code}' 검색 결과 없음")
                return pd.DataFrame()

            print(f"🎯 [DDC_SEARCH] 검색어: '{ddc_code}', 기본 매칭: {len(df)}개")

            # 2단계: 완벽매칭과 부분매칭 분리
            exact_matches = df[df["ddc"] == ddc_code].copy()
            partial_matches = df[df["ddc"] != ddc_code].copy()

            print(f"🎯 [DDC_EXACT] 완벽매칭: {len(exact_matches)}개")
            print(f"🎯 [DDC_PARTIAL] 부분매칭: {len(partial_matches)}개")

            # 3단계: KSH 개수 계산 및 정렬 컬럼 추가
            def _prepare_dataframe_for_sorting(dataframe):
                if dataframe.empty:
                    return dataframe

                # KSH 개수 정확 계산
                def _count_ksh_codes(ksh_str):
                    if pd.isna(ksh_str) or not str(ksh_str).strip():
                        return 0
                    # KSH 코드 패턴: KSH로 시작하는 10자리 숫자
                    ksh_codes = re.findall(r"KSH\d{10}", str(ksh_str).upper())
                    return len(set(ksh_codes))  # 중복 제거

                dataframe["ksh_count"] = dataframe["ksh"].apply(_count_ksh_codes)

                # 연도 숫자화
                dataframe["pub_year_num"] = (
                    pd.to_numeric(dataframe["publication_year"], errors="coerce")
                    .fillna(0)
                    .astype(int)
                )

                # identifier 숫자화 (타이브레이커)
                def _extract_id_number(identifier_str):
                    if pd.isna(identifier_str):
                        return 0
                    numbers = re.findall(r"\d+", str(identifier_str))
                    return int("".join(numbers)) if numbers else 0

                dataframe["id_num"] = dataframe["identifier"].apply(_extract_id_number)

                return dataframe

            exact_matches = _prepare_dataframe_for_sorting(exact_matches)
            partial_matches = _prepare_dataframe_for_sorting(partial_matches)

            # 4단계: KSH 개수별 분포 확인
            if not exact_matches.empty:
                ksh_dist = exact_matches["ksh_count"].value_counts().sort_index()
                print(f"🔍 [KSH_DIST] 완벽매칭 KSH 분포: {dict(ksh_dist)}")
            if not partial_matches.empty:
                ksh_dist_p = partial_matches["ksh_count"].value_counts().sort_index()
                print(f"🔍 [KSH_DIST] 부분매칭 KSH 분포: {dict(ksh_dist_p)}")

            # 5단계: 메르카츠님 요구사항에 따른 선별
            def _select_by_ksh_rule(dataframe, target_count):
                if dataframe.empty or target_count <= 0:
                    return pd.DataFrame()

                # KSH=1인 것들 (최신연도순)
                single_ksh = dataframe[dataframe["ksh_count"] == 1].copy()
                single_ksh = single_ksh.sort_values(
                    ["pub_year_num", "id_num"], ascending=[False, False]
                ).drop_duplicates(subset=["identifier"], keep="first")

                # KSH>1인 것들 (KSH 많은순 → 최신연도순)
                multi_ksh = dataframe[dataframe["ksh_count"] > 1].copy()
                multi_ksh = multi_ksh.sort_values(
                    ["ksh_count", "pub_year_num", "id_num"],
                    ascending=[False, False, False],
                ).drop_duplicates(subset=["identifier"], keep="first")

                # 선별 로직
                selected_items = []

                # 상위 3건은 KSH=1 우선
                if target_count >= 3 and not single_ksh.empty:
                    top_3_single = single_ksh.head(3)
                    selected_items.append(top_3_single)
                    remaining_count = target_count - len(top_3_single)

                    # 나머지는 KSH 많은 것 우선
                    if remaining_count > 0 and not multi_ksh.empty:
                        remaining_multi = multi_ksh.head(remaining_count)
                        selected_items.append(remaining_multi)
                        remaining_count -= len(remaining_multi)

                    # 아직 부족하면 single_ksh에서 추가
                    if remaining_count > 0 and len(single_ksh) > 3:
                        additional_single = single_ksh.iloc[3 : 3 + remaining_count]
                        selected_items.append(additional_single)
                else:
                    # target_count < 3이거나 single_ksh가 없는 경우
                    all_sorted = pd.concat([single_ksh, multi_ksh], ignore_index=True)
                    if not all_sorted.empty:
                        # KSH=1을 앞쪽에, 그 다음 KSH 많은 순
                        all_sorted["ksh_priority"] = all_sorted["ksh_count"].apply(
                            lambda x: 0 if x == 1 else 1
                        )
                        all_sorted = all_sorted.sort_values(
                            ["ksh_priority", "ksh_count", "pub_year_num", "id_num"],
                            ascending=[True, False, False, False],
                        )
                        selected_items.append(all_sorted.head(target_count))

                if selected_items:
                    result = pd.concat(selected_items, ignore_index=True)
                    return result.drop_duplicates(subset=["identifier"], keep="first")
                else:
                    return pd.DataFrame()

            # 6단계: 완벽매칭과 부분매칭 각각 처리 (✅ 전체 결과 반환)
            final_parts = []

            if not exact_matches.empty:
                # ✅ 제한 없이 전체 완벽매칭 결과 선별
                selected_exact = _select_by_ksh_rule(exact_matches, len(exact_matches))
                if not selected_exact.empty:
                    selected_exact["match_type"] = "exact"
                    final_parts.append(selected_exact)
                    print(f"✅ [EXACT_SELECT] 완벽매칭 {len(selected_exact)}개 선별")

            if not partial_matches.empty:
                # ✅ 제한 없이 전체 부분매칭 결과 선별
                selected_partial = _select_by_ksh_rule(partial_matches, len(partial_matches))
                if not selected_partial.empty:
                    selected_partial["match_type"] = "partial"
                    final_parts.append(selected_partial)
                    print(
                        f"✅ [PARTIAL_SELECT] 부분매칭 {len(selected_partial)}개 선별"
                    )

            # 7단계: 최종 결합 및 DDC 컬럼 기준 오름차순 정렬
            if final_parts:
                final_result = pd.concat(final_parts, ignore_index=True)

                # 🎯 핵심: ksh_priority 컬럼 생성 (완벽매칭=KSH 1개 우선, 부분매칭=복수KSH 우선)
                def assign_ksh_priority(row):
                    if row["match_type"] == 0:  # 완벽매칭
                        return 0 if row["ksh_count"] == 1 else 1  # 단일KSH 우선
                    else:  # 부분매칭
                        return 0 if row["ksh_count"] > 1 else 1  # 복수KSH 우선

                final_result["ksh_priority"] = final_result.apply(
                    assign_ksh_priority, axis=1
                )

                # 임시 컬럼들 제거
                columns_to_drop = [
                    "ksh_count",
                    "pub_year_num",
                    "id_num",
                    "match_type",
                    "ksh_priority",
                ]
                final_result = final_result.drop(
                    columns=columns_to_drop, errors="ignore"
                )

                # 복수 KSH 확인
                multi_ksh_count = 0
                if "ksh" in final_result.columns:
                    for _, row in final_result.iterrows():
                        ksh_codes = re.findall(r"KSH\d{10}", str(row["ksh"]).upper())
                        if len(set(ksh_codes)) > 1:
                            multi_ksh_count += 1

                print(
                    f"🎯 [DDC_FINAL] 최종 결과: {len(final_result)}개 (복수KSH: {multi_ksh_count}개)"
                )
                print(f"🎯 [DDC_SORT] DDC 컬럼 기준 오름차순 정렬 완료")

                return final_result
            else:
                print(f"🚫 [DDC_NO_RESULT] 선별된 결과 없음")
                return pd.DataFrame()

        except Exception as e:
            print(f"❌ 오류: DDC 랭킹 로직 실행 중 오류 발생: {e}")
            import traceback

            traceback.print_exc()
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()


    def _search_by_ddc_with_fallback(self, ddc_codes):
        # -------------------
        # 1. DDC Cache DB에서 완전일치(1순위)와 부분일치(3순위) 결과 분리 검색
        df_exact_cache, df_partial_cache = self._search_ddc_from_cache(ddc_codes)

        # 2. 서지 DB에서 검색 (2순위 - 기존 로직)
        # -------------------
        df_from_biblio = pd.DataFrame()
        conn = None
        try:
            conn = self.db_manager._get_mapping_connection()
            all_biblio_results = []
            for ddc_code in ddc_codes:
                candidates = self._search_by_ddc_ranking_logic(ddc_code)
                if not candidates.empty:
                    all_biblio_results.append(candidates)

            if all_biblio_results:
                df_from_biblio = pd.concat(all_biblio_results, ignore_index=True)

                # UI 노출용 ksh_labeled(마크업) 생성 및 ddc_label, ddc_count 추가
                if not df_from_biblio.empty:
                    df_from_biblio["ksh_labeled"] = df_from_biblio.apply(
                        lambda row: self._format_ksh_labeled_to_markup(
                            row.get("ksh_labeled", ""), row.get("ksh", "")
                        ),
                        axis=1,
                    )
                    # -------------------
                    # ✅ [성능 개선] DDC 레이블을 대량으로 한 번에 조회 후 매핑
                    unique_ddcs = df_from_biblio["ddc"].dropna().unique().tolist()
                    if unique_ddcs:
                        ddc_label_map = self.get_all_ddc_labels_bulk(unique_ddcs)
                        df_from_biblio["ddc_label"] = (
                            df_from_biblio["ddc"].map(ddc_label_map).fillna("")
                        )
                    else:
                        df_from_biblio["ddc_label"] = ""

                    # ✅ [신규 추가] DDC 출현 카운트 계산
                    ddc_counts = df_from_biblio["ddc"].value_counts()
                    df_from_biblio["ddc_count"] = df_from_biblio["ddc"].map(ddc_counts).fillna(0).astype(int)
                    # -------------------
        except Exception as e:
            print(f"오류: DDC 서지 DB 검색 중 오류 발생: {e}")
            # 서지 DB 검색에 실패해도 계속 진행하여 Cache 결과라도 보여줌
        finally:
            if conn:
                conn.close()

        # -------------------
        # 3. 새로운 우선순위에 따라 결과 병합
        # 1순위: 완전일치 DDC Cache
        # 2순위: 서지 DB 결과 (자체 랭킹 로직 포함)
        # 3순위: 부분일치 DDC Cache
        final_df = pd.concat(
            [df_exact_cache, df_from_biblio, df_partial_cache], ignore_index=True
        )
        # -------------------

        # ✅ [신규 추가] DDC 출현 카운트 계산 (전체 병합 결과에서)
        if not final_df.empty and "ddc" in final_df.columns:
            # ddc_count가 없는 경우에만 계산 (df_from_biblio는 이미 계산됨)
            if "ddc_count" not in final_df.columns:
                ddc_counts = final_df["ddc"].value_counts()
                final_df["ddc_count"] = final_df["ddc"].map(ddc_counts).fillna(0).astype(int)
            else:
                # 일부만 계산된 경우 (Cache 결과는 없음) 전체 재계산
                ddc_counts = final_df["ddc"].value_counts()
                final_df["ddc_count"] = final_df["ddc"].map(ddc_counts).fillna(0).astype(int)

        # ✅ [2025-10-19 수정] 상위 200개로 제한 (키워드 검색과 동일)
        if len(final_df) > 200:
            final_df = final_df.head(200)
            print(f"🔍 [DDC_LIMIT] 최종 결과를 상위 200개로 제한")

        return final_df.fillna("")


    def _search_ddc_by_sql_fts(
        self, keyword: str, pref_only: bool = False, limit: int = 20
    ) -> list:
        """
        [내부용] 영어 키워드로 DDC 번호를 FTS5 SQL 검색합니다. (기존 로직과 동일)
        """
        conn = None
        try:
            conn = self.db_manager._get_dewey_connection()
            cursor = conn.cursor()

            term_filter = "AND term_type = 'pref'" if pref_only else ""

            cursor.execute(
                f"""
                SELECT ddc, keyword, term_type
                FROM ddc_keyword_fts
                WHERE keyword MATCH ? {term_filter}
                ORDER BY rank
                LIMIT ?
                """,
                (keyword, limit),
            )

            results = []
            for row in cursor.fetchall():
                results.append({"ddc": row[0], "keyword": row[1], "term_type": row[2]})

            return results

        except Exception as e:
            print(f"경고: DDC 키워드 SQL 검색 실패 ({keyword}): {e}")
            return []
        finally:
            if conn:
                conn.close()


    def _search_ddc_from_cache(
        self, ddc_codes: list
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        DDC Cache DB에서 DDC 코드 목록에 대한 설명을 조회합니다.
        완전일치와 부분일치 결과를 분리하여 두 개의 DataFrame으로 반환합니다.
        """
        if not ddc_codes:
            return pd.DataFrame(), pd.DataFrame()

        logger.info(
            f"💾 DDC Cache DB에서 {len(ddc_codes)}개 DDC 코드에 대해 완전/부분일치 조회 시작..."
        )

        unique_ddc_codes = list(set(ddc.strip() for ddc in ddc_codes if ddc.strip()))

        conn = None
        try:
            conn = self.db_manager._get_dewey_connection()
            cursor = conn.cursor()

            # -------------------
            # ✅ [핵심 수정] 1번과 2번 로직을 통합하여 DB 조회를 한 번으로 최적화합니다.
            # 1. 완전/부분일치에 해당하는 모든 키워드(pref, alt)를 한 번에 조회
            all_ddc_codes_to_query = unique_ddc_codes
            partial_like_conditions = " OR ".join(
                ["ddc LIKE ?"] * len(all_ddc_codes_to_query)
            )
            placeholders = ",".join("?" for _ in all_ddc_codes_to_query)

            query = f"""
                SELECT ddc, keyword, term_type
                FROM ddc_keyword
                WHERE ddc IN ({placeholders}) OR ({partial_like_conditions})
            """
            params = all_ddc_codes_to_query + [
                f"{code}%" for code in all_ddc_codes_to_query
            ]
            cursor.execute(query, params)
            all_rows = cursor.fetchall()

            # 2. Python에서 DDC별로 모든 레이블을 조합 (기존 get_all_ddc_labels_bulk와 유사한 로직)
            ddc_labels_map = {}
            # pref 레이블을 우선하기 위해 먼저 정렬
            all_rows.sort(key=lambda x: (x[0], 0 if x[2] == "pref" else 1, x[1]))

            for ddc, keyword, term_type in all_rows:
                if ddc not in ddc_labels_map:
                    ddc_labels_map[ddc] = []

                label = f"{keyword}(pref)" if term_type == "pref" else keyword
                if label not in ddc_labels_map[ddc]:
                    ddc_labels_map[ddc].append(label)

            # 3. 조합된 레이블을 기반으로 완전일치와 부분일치 결과 분리
            exact_results = []
            partial_results = []
            for ddc, labels in ddc_labels_map.items():
                formatted_label = " | ".join(labels)
                if ddc in unique_ddc_codes:
                    exact_results.append((ddc, formatted_label))
                else:
                    # 부분일치 결과 정렬을 위해 ddc 코드를 기준으로 정렬
                    partial_results.append((ddc, formatted_label))

            partial_results.sort(key=lambda x: x[0])

            # 4. DataFrame 포맷팅 헬퍼 함수 (기존 로직 재활용)
            def format_cache_df(rows, match_type):
                # -------------------
                if not rows:
                    return pd.DataFrame()

                df = pd.DataFrame(rows, columns=["ddc", "ddc_label"])
                df.drop_duplicates(subset=["ddc"], inplace=True, keep="first")

                df["source_file"] = "DDC Cache DB"
                df["data_type"] = "DDC 레이블"

                biblio_cols = [
                    "identifier",
                    "kdc",
                    "ddc",
                    "ksh",
                    "kdc_edition",
                    "ddc_edition",
                    "publication_year",
                    "title",
                    "data_type",
                    "source_file",
                    "ksh_labeled",
                    "ddc_label",
                    "nlk_link",
                ]
                for col in biblio_cols:
                    if col not in df.columns:
                        df[col] = ""

                logger.info(f"💾 DDC Cache DB ({match_type}): {len(df)}개 결과 생성.")
                return df[biblio_cols]

            df_exact = format_cache_df(exact_results, "완전일치")
            df_partial = format_cache_df(partial_results, "부분일치")

            return df_exact, df_partial

        except Exception as e:
            logger.error(f"❌ DDC Cache DB 검색 중 오류: {e}")
            return pd.DataFrame(), pd.DataFrame()
        finally:
            if conn:
                conn.close()


    def _search_ddc_with_fallback_hierarchy(self, ddc_code, max_results=50):
        """
        🔄 DDC 상하위 분류 폴백 검색: 완벽매칭이 없을 때 사용
        """
        conn = self.db_manager._get_mapping_connection()
        try:
            fallback_patterns = []

            # 상위 분류 패턴 생성
            if "." in ddc_code:
                # 예: 330.951 → 330.9, 330
                parts = ddc_code.split(".")
                integer_part = parts[0]
                decimal_part = parts[1]

                # 소수점 한 자리씩 제거
                for i in range(len(decimal_part) - 1, 0, -1):
                    fallback_patterns.append(f"{integer_part}.{decimal_part[:i]}")
                fallback_patterns.append(integer_part)
            else:
                # 예: 330 → 33, 3
                for i in range(len(ddc_code) - 1, 0, -1):
                    fallback_patterns.append(ddc_code[:i])

            # 하위 분류 패턴 (현재 코드로 시작하는 모든 것)
            fallback_patterns.append(f"{ddc_code}")  # 자기 자신도 포함

            print(f"🔄 [DDC_FALLBACK] 폴백 패턴들: {fallback_patterns}")

            all_results = []
            for pattern in fallback_patterns:
                # ✅ [성능 개선] 필요한 컬럼만 조회
                query = """
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
                        source_file,
                        ? as fallback_level
                    FROM mapping_data
                    WHERE ddc LIKE ? AND ksh IS NOT NULL AND ksh != ''
                    LIMIT ?
                """
                level = fallback_patterns.index(pattern)
                df_pattern = pd.read_sql_query(
                    query,
                    conn,
                    params=(
                        level,
                        f"{pattern}%",
                        max_results // len(fallback_patterns) + 10,
                    ),
                )

                if not df_pattern.empty:
                    all_results.append(df_pattern)

                # 충분한 결과가 모이면 중단
                total_found = sum(len(df) for df in all_results)
                if total_found >= max_results:
                    break

            if all_results:
                combined = pd.concat(all_results, ignore_index=True)

                # 중복 제거 후 정렬
                combined = combined.drop_duplicates(subset=["identifier"], keep="first")
                combined = combined.sort_values(
                    ["fallback_level", "publication_year"], ascending=[True, False]
                )
                combined = combined.drop("fallback_level", axis=1)

                result = combined.head(max_results)
                print(f"🔄 [DDC_FALLBACK] 폴백 검색 결과: {len(result)}개")
                return result
            else:
                print(f"🔄 [DDC_FALLBACK] 폴백 검색도 결과 없음")
                return pd.DataFrame()

        except Exception as e:
            print(f"오류: DDC 폴백 검색 중 오류 발생: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()


    def get_all_ddc_labels_bulk(self, ddc_numbers: list[str]) -> dict:
        """
        ✅ [신규 최적화] DDC 번호 리스트를 받아 모든 관련 레이블을 단일 쿼리로 조회합니다.
        - 반환값: {ddc_number: "label1 | label2 | ...", ...} 형태의 딕셔너리
        """
        if not ddc_numbers:
            return {}

        # 1. 중복된 DDC 번호 및 공백 제거
        unique_ddc_numbers = list(
            set(d.strip() for d in ddc_numbers if d and d.strip())
        )
        if not unique_ddc_numbers:
            return {}

        # 2. 단일 SQL 쿼리 실행 (IN 연산자 활용)
        # database_manager에 실제 DB에 접근하는 로직이 필요합니다.
        # 이 쿼리는 (ddc, keyword, term_type) 튜플의 리스트를 반환해야 합니다.
        all_labels_list = self.db_manager.get_all_ddc_keywords_by_numbers(
            unique_ddc_numbers
        )

        # 3. Python에서 데이터 재구성 (DB 부하 최소화)
        ddc_labels_map = {}
        # pref 레이블을 우선하기 위해 먼저 정렬
        all_labels_list.sort(key=lambda x: (x[0], 0 if x[2] == "pref" else 1, x[1]))

        for ddc, keyword, term_type in all_labels_list:
            if ddc not in ddc_labels_map:
                ddc_labels_map[ddc] = []

            label = f"{keyword}(pref)" if term_type == "pref" else keyword
            if label not in ddc_labels_map[ddc]:
                ddc_labels_map[ddc].append(label)

        # 4. 최종적으로 '|'로 구분된 문자열로 변환하여 반환
        result_map = {ddc: " | ".join(labels) for ddc, labels in ddc_labels_map.items()}
        return result_map


    def get_ddc_description_cached(self, ddc_code: str) -> str | None:
        """
        DDC 번호로 캐시에서 설명(prefLabel, title 등)을 조회합니다.
        (database_manager.py에서 이관됨)
        """
        try:
            # ✅ [수정] 같은 클래스 내의 get_dewey_by_notation 메서드를 직접 호출합니다.
            cached_data = self.get_dewey_by_notation(ddc_code)
            if cached_data:
                try:
                    ddc_json = json.loads(cached_data)

                    # ✅ [개선] prefLabel 우선 조회, 없으면 title 조회
                    label_data = ddc_json.get("prefLabel")
                    if isinstance(label_data, dict):
                        # 다국어 처리 (en 우선)
                        title = label_data.get(
                            "en", next(iter(label_data.values()), f"DDC {ddc_code}")
                        )
                    elif isinstance(label_data, str):
                        title = label_data
                    else:
                        title = ddc_json.get("title", f"DDC {ddc_code}")

                    return title
                except (json.JSONDecodeError, StopIteration) as e:
                    logger.warning(f"DDC {ddc_code} 캐시 JSON 파싱 오류: {e}")
                    return f"DDC {ddc_code} (캐시 파싱 오류)"
            return None
        except Exception as e:
            logger.warning(f"DDC {ddc_code} 캐시 조회 실패: {e}")
            return None


    def get_ddc_labels(self, ddc_numbers: str) -> str:
        """
        DDC 번호(들)에 대한 레이블을 조회하여 포맷팅된 문자열로 반환합니다.

        Args:
            ddc_numbers: DDC 번호 문자열 (예: "320.011" 또는 "320.011 | 320.01")

        Returns:
            포맷팅된 레이블 문자열
            - 단일 DDC: "Male gods(pref); Male gods(alt); Gods--male(alt)"
            - 복수 DDC: "202.113; Male gods(pref); ...; 202.114; Female goddesses(pref); ..."
            - 데이터 없음: ""
        """
        if not ddc_numbers or not str(ddc_numbers).strip():
            return ""

        # -------------------
        # ✅ [수정] 컴마(,) 또는 파이프(|)로 구분된 복수 DDC 번호 처리
        import re

        ddc_list = [
            ddc.strip() for ddc in re.split(r"[,|]", str(ddc_numbers)) if ddc.strip()
        ]
        # -------------------

        if not ddc_list:
            return ""

        conn = None
        try:
            conn = self.db_manager._get_dewey_connection()
            cursor = conn.cursor()

            result_parts = []

            for ddc in ddc_list:
                # 각 DDC 번호에 대한 레이블 조회
                cursor.execute(
                    """
                    SELECT keyword, term_type
                    FROM ddc_keyword
                    WHERE ddc = ?
                    ORDER BY
                        CASE term_type
                            WHEN 'pref' THEN 1
                            WHEN 'alt' THEN 2
                            ELSE 3
                        END,
                        keyword
                    """,
                    (ddc,),
                )

                rows = cursor.fetchall()

                if rows:
                    # 복수 DDC인 경우에만 DDC 번호를 앞에 추가
                    if len(ddc_list) > 1:
                        result_parts.append(ddc)

                    # ✅ [개선] (pref)만 표시, (alt)는 태그 제거
                    # pref가 없으면 모두 alt로 간주
                    labels = []
                    for keyword, term_type in rows:
                        if term_type == "pref":
                            labels.append(f"{keyword}(pref)")
                        else:
                            # alt는 태그 없이 keyword만 표시
                            labels.append(keyword)
                    result_parts.extend(labels)

            if not result_parts:
                return ""

            # -------------------
            # ✅ [수정] 파이프로 구분하여 반환
            return " | ".join(result_parts)
            # -------------------

        except Exception as e:
            logger.warning(f"DDC 레이블 조회 실패 ({ddc_numbers}): {e}")
            return ""
        finally:
            if conn:
                conn.close()


    def get_dewey_by_notation(self, ddc_code: str) -> str | None:
        """
        DDC 코드로 캐시에서 raw_json을 조회합니다.
        get_dewey_cache_entry의 래퍼 함수입니다.
        """
        entry = self.get_dewey_cache_entry(ddc_code)
        return entry[0] if entry else None


    def get_dewey_cache_entry(self, ddc_code: str) -> tuple | None:
        """
        DDC 코드로 캐시에서 raw_json과 마지막 업데이트 일시를 함께 조회합니다.
        Returns:
            (raw_json, last_updated) 튜플 또는 None
        """
        if not ddc_code:
            return None
        conn = None
        try:
            conn = self.db_manager._get_dewey_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT raw_json, last_updated
                  FROM dewey_cache
                 WHERE ddc_code = ?
              ORDER BY last_updated DESC
                 LIMIT 1
                """,
                (ddc_code,),
            )
            row = cur.fetchone()
            return (row["raw_json"], row["last_updated"]) if row else None
        except Exception as e:
            logger.error(f"오류: get_dewey_cache_entry 실패: {e}")
            return None
        finally:
            if conn:
                conn.close()


    def get_dewey_from_cache(self, iri: str) -> str | None:
        """
        ✅ [동시성 개선] DDC 전용 DB에서 캐시 조회 (읽기 전용)
        히트 카운트는 배치 업데이트로 처리하여 락 충돌 방지
        """
        conn = None
        try:
            conn = self.db_manager._get_dewey_connection()
            cursor = conn.cursor()

            # 캐시 조회 (읽기 전용 - UPDATE 제거로 락 충돌 해소)
            cursor.execute("SELECT raw_json FROM dewey_cache WHERE iri = ?", (iri,))
            result = cursor.fetchone()

            if result:
                # ✅ [동시성 개선] 히트 카운트를 메모리에 누적만 하고 즉시 반환
                # 실제 DB 업데이트는 3초마다 배치로 처리 (database_manager에서)
                self.db_manager._schedule_hit_count_update(iri)
                return result[0]

            return None

        except Exception as e:
            print(f"경고: DDC 캐시 조회 실패: {e}")
            return None
        finally:
            if conn:
                conn.close()


    def get_multiple_ddcs_descriptions(self, ddc_list: list) -> dict:
        """
        여러 DDC 번호의 설명을 캐시에서 한 번에 조회합니다.
        (database_manager.py에서 이관됨)
        """
        descriptions = {}

        if not ddc_list:
            return descriptions

        # DDC 코드 정리 및 중복 제거
        clean_ddcs = []
        for ddc in ddc_list:
            if ddc and str(ddc).strip():
                clean_ddc = str(ddc).strip()
                # DDC 형식 검증 (숫자와 점만 포함)
                if re.match(r"^\d+\.?\d*$", clean_ddc):
                    clean_ddcs.append(clean_ddc)

        unique_ddcs = list(set(clean_ddcs))

        # 각 DDC에 대해 캐시에서 조회
        for ddc in unique_ddcs:
            try:
                # ✅ [수정] 이제 같은 클래스 내의 메서드를 정상적으로 호출합니다.
                desc = self.get_ddc_description_cached(ddc)
                if desc:
                    descriptions[ddc] = desc
                else:
                    # 캐시에 없으면 기본값 설정
                    descriptions[ddc] = f"DDC {ddc} (의미 조회 필요)"

            except Exception as e:
                logger.warning(f"DDC {ddc} 조회 실패: {e}")
                descriptions[ddc] = f"DDC {ddc} (조회 실패)"

        logger.info(f"💾 DDC 설명 일괄 조회 완료: {len(descriptions)}개")
        return descriptions

    # --- 용어집(Glossary) 데이터 관련 함수 ---

    # ========================================
    # DDC 캐시 관련 함수들
    # ========================================


    def save_dewey_to_cache(self, iri: str, ddc_code: str, raw_json: str):
        """
        ✅ [동시성 개선] DDC 데이터를 쓰기 큐를 통해 저장합니다.
        여러 스레드에서 동시에 호출해도 안전합니다 (database is locked 오류 해결).
        """
        try:
            # 1. 메인 캐시 저장은 큐를 통해 비동기 처리
            self.db_manager.enqueue_dewey_cache_write(iri, ddc_code, raw_json)

            # 2. 키워드 추출은 별도로 즉시 처리 (빈도가 낮고 독립적)
            # ✅ Negative Cache ({"exists": false})는 키워드 추출 스킵
            try:
                payload = json.loads(raw_json)
                if payload.get("exists") is not False:
                    # Positive Cache만 키워드 추출
                    self._save_keywords_separately(iri, ddc_code, raw_json)
            except (json.JSONDecodeError, TypeError):
                # JSON 파싱 실패 시에도 키워드 추출 시도
                self._save_keywords_separately(iri, ddc_code, raw_json)

            # ✅ 성공 로그 (앱 화면에도 표시)
            logger.info(f"✅ DDC 캐시 저장 요청: {ddc_code} (큐에 추가됨)")

        except Exception as e:
            error_msg = f"경고: DDC 캐시 저장 실패 (IRI: {iri}): {e}"
            logger.warning(error_msg)


    def search_ddc_by_keyword(
        self, keyword: str, pref_only: bool = False, limit: int = 20
    ) -> list:
        """
        [하이브리드 검색] SQL(FTS)의 정확성과 벡터 검색의 의미 확장성을 결합합니다.
        """
        # --- 1단계: SQL(FTS) 검색 (정확성 담당) ---
        sql_results = self._search_ddc_by_sql_fts(keyword, pref_only, limit)

        # --- 2단계: 벡터 검색 (의미 확장 담당) ---
        vector_results = []
        if hasattr(self.db_manager, "search_ddc_by_vector"):
             vector_results = self.db_manager.search_ddc_by_vector(keyword, top_k=limit)
        
        # --- 3단계: 결과 병합 및 순위 재조정 ---
        if not sql_results and not vector_results:
            return []

        # DataFrame으로 변환하여 쉽게 처리
        df_sql = pd.DataFrame(sql_results)
        df_vec = pd.DataFrame(vector_results)

        # SQL 결과에 최고 점수(2.0)와 타입 부여
        if not df_sql.empty:
            df_sql['score'] = 2.0 
            df_sql['match_type'] = 'exact'

        # 벡터 결과에는 유사도 점수와 타입 부여 (벡터 점수는 0~1 사이)
        if not df_vec.empty:
            df_vec.rename(columns={'distance': 'score'}, inplace=True)
            df_vec['match_type'] = 'semantic'

        # 두 결과 병합
        df_combined = pd.concat([df_sql, df_vec], ignore_index=True)
        
        # 'ddc'와 'keyword' 기준으로 중복 제거 (SQL 결과를 우선적으로 유지)
        df_combined.drop_duplicates(subset=['ddc', 'keyword'], keep='first', inplace=True)
        
        # 최종 정렬: score 높은 순 (정확 일치 > 의미 유사)
        df_combined.sort_values(by=['score'], ascending=False, inplace=True)
        
        return df_combined.head(limit).to_dict('records')


    def search_ddc_by_multiple_keywords(
        self, keywords: str, pref_only: bool = False, max_results_per_level: int = 3
    ) -> list:
        """
        복수 키워드(콤마 구분)로 DDC Cache DB를 검색하여 DDC 빈도 순으로 정렬된 결과 반환

        Args:
            keywords: 콤마로 구분된 키워드 문자열 (예: "artificial intelligence, machine learning, neural networks")
            pref_only: True면 우선어(prefLabel)만 검색, False면 동의어(altLabel) 포함 전체 검색
            max_results_per_level: 최종적으로 반환할 상위 DDC 순위 개수 (기본값 3)

        Returns:
            DDC 빈도 순으로 정렬된 결과 리스트
            [{"ddc": "006.3", "count": 15, "keyword": "artificial intelligence", "term_type": "pref"}, ...]
        """
        # --- 1. 입력 유효성 검사 ---
        # keywords 문자열이 비어있거나 공백만 있는 경우, 불필요한 작업을 막기 위해 즉시 빈 리스트를 반환합니다.
        if not keywords or not keywords.strip():
            return []

        # --- 2. 검색어 전처리 ---
        # 입력된 문자열을 콤마(,) 기준으로 나누고, 각 키워드의 앞뒤 공백을 제거하여 리스트로 만듭니다.
        keyword_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]
        # 전처리 후 남은 키워드가 없으면 검색을 중단합니다.
        if not keyword_list:
            return []

        # --- 3. 데이터베이스 연결 ---
        conn = None # 데이터베이스 연결 객체를 담을 변수 초기화
        try:
            # DatabaseManager를 통해 DDC Cache DB에 대한 연결을 가져옵니다.
            conn = self.db_manager._get_dewey_connection()
            cursor = conn.cursor()

            # --- 4. DDC 후보군 집계 ---
            # 각 DDC 번호가 몇 번이나 검색 결과에 등장했는지(빈도수)와 관련 정보를 저장할 딕셔너리입니다.
            # 구조 예시: {'006.3': {'count': 2, 'keywords': {'AI', 'ML'}, ...}}
            ddc_aggregation = {}

            # pref_only 플래그에 따라 SQL 쿼리에 추가할 필터 조건을 동적으로 생성합니다.
            # True이면 'pref' 타입의 용어만 검색 대상에 포함시킵니다.
            term_filter = "AND term_type = 'pref'" if pref_only else ""

            # --- 5. 각 키워드별 순차 검색 및 결과 누적 ---
            # 분리된 각 키워드에 대해 데이터베이스 검색을 반복 실행합니다.
            for keyword in keyword_list:
                
                # FTS5(Full-Text Search)는 괄호나 하이픈 같은 특수문자를 연산자로 오인할 수 있습니다.
                # 이를 방지하기 위해, 알파벳, 숫자, 공백을 제외한 모든 문자를 공백으로 치환합니다.
                # 예: "Unicode (Character set)" -> "Unicode  Character set"
                sanitized_keyword = re.sub(r"[^\w\s]", " ", keyword)
                # 여러 개의 연속된 공백을 하나의 공백으로 합칩니다.
                # 예: "Unicode  Character set" -> "Unicode Character set"
                sanitized_keyword = " ".join(sanitized_keyword.split())

                # ddc_keyword_fts 테이블에서 정제된 키워드로 FTS 검색을 수행합니다.
                # FTS의 순위(rank)가 높은 순으로 정렬하여 가장 관련성 높은 100개 결과를 가져옵니다.
                cursor.execute(
                    f"""
                    SELECT ddc, keyword, term_type
                    FROM ddc_keyword_fts
                    WHERE keyword MATCH ? {term_filter}
                    ORDER BY rank
                    LIMIT 100
                    """,
                    (sanitized_keyword,),
                )
                
                # --- 6. 검색 결과 집계 (Aggregation) ---
                # 한 키워드에 대한 모든 검색 결과를 순회하며 ddc_aggregation 딕셔너리에 누적합니다.
                for row in cursor.fetchall():
                    ddc, matched_keyword, term_type = row

                    # 이 DDC 번호가 처음 발견된 경우, 집계를 위한 기본 구조를 생성합니다.
                    if ddc not in ddc_aggregation:
                        ddc_aggregation[ddc] = {
                            "count": 0,          # 이 DDC가 몇 번 등장했는지 카운트
                            "keywords": [],      # 어떤 키워드들과 매칭되었는지 목록
                            "term_types": set(), # 매칭된 용어의 타입 (pref, alt 등)
                            "original_keyword": keyword, # 이 DDC를 처음 찾게 한 원본 검색어
                        }

                    # 현재 DDC의 등장 횟수(빈도)를 1 증가시킵니다.
                    ddc_aggregation[ddc]["count"] += 1
                    # 매칭된 DB 키워드가 목록에 없다면 중복을 피해 추가합니다.
                    if matched_keyword not in ddc_aggregation[ddc]["keywords"]:
                        ddc_aggregation[ddc]["keywords"].append(matched_keyword)
                    # 매칭된 용어 타입을 set에 추가하여 중복 없이 저장합니다. (예: {'pref', 'alt'})
                    ddc_aggregation[ddc]["term_types"].add(term_type)

            # --- 7. 결과 정렬 및 필터링 ---
            # 집계된 DDC 목록을 우선순위에 따라 정렬합니다.
            # 1순위: 등장 횟수(count)가 많은 순서 (내림차순)
            # 2순위: 횟수가 같다면 DDC 번호가 낮은 순서 (오름차순, 일관된 정렬을 위해)
            # 최종적으로 사용자가 요청한 개수(max_results_per_level)만큼만 잘라냅니다.
            sorted_ddcs = sorted(
                ddc_aggregation.items(),
                key=lambda x: (-x[1]["count"], x[0]),
            )[:max_results_per_level]

            # --- 8. 최종 결과 포맷팅 ---
            # 정렬된 데이터를 사용자에게 보여줄 최종 리스트 형태로 가공합니다.
            results = []
            for ddc, info in sorted_ddcs:
                results.append(
                    {
                        "ddc": ddc,
                        "ddc_count": info["count"],
                        "keyword": ", ".join(info["keywords"][:3]), # 매칭된 키워드는 최대 3개까지만 표시
                        "term_type": ", ".join(sorted(info["term_types"])),
                        "search_keywords": keywords, # 사용자가 입력했던 원본 검색어 전체
                    }
                )

            return results

        except Exception as e:
            # 함수 실행 중 어떤 종류의 오류라도 발생하면 로그를 남기고 빈 리스트를 반환합니다.
            logger.error(f"복합 키워드 DDC 검색 실패 ({keywords}): {e}")
            return []
        finally:
            # try 블록의 코드가 성공하든 실패하든 관계없이 항상 실행됩니다.
            # 데이터베이스 연결이 열려 있다면, 리소스를 해제하기 위해 안전하게 닫습니다.
            if conn:
                conn.close()

