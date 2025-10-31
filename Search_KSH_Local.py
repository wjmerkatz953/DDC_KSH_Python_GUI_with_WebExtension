# ==============================
# 파일명: Search_KSH_Local.py
# 버전: v1.5.0 - 복수 주제어 동시 검색 최적화 메서드 추가
# 설명: KSH Local 전용 검색 모듈 (DB 접근/전처리/진행률/취소) + 주제모음 편집 저장
# 수정일: 2025-10-13
#
# 변경 이력:
# v1.5.0 (2025-10-13)
# - [성능 개선] search_biblio_by_multiple_subjects 메서드 추가
#   : 여러 개의 주제어를 리스트로 받아 단일 SQL 쿼리로 결과를 반환
#   : Gemini 검색 2단계의 DB 조회 성능을 크게 향상시킴
# v1.4.1 (2025-10-02)
# - [버그 수정] search_concepts() 메서드에서 _concept_id 컬럼 보존 (라인 201)
# ==============================

from __future__ import annotations
from typing import Optional, Callable, Dict, Any
import threading
import pandas as pd
import re  # ✅ [추가] re 모듈 임포트
from concurrent.futures import ThreadPoolExecutor, as_completed

# 프로젝트 공용 모듈
from search_query_manager import SearchQueryManager
from database_manager import DatabaseManager

# ✅ [신규 추가] 누락된 타입 정의
ProgressCB = Optional[Callable[[int], None]]

CancelFlag = Optional[Callable[[], bool]]


class KshLocalSearcher:
    """
    KSH Local 검색 전용 래퍼.
    - 개념(상단) 검색: nlk_concepts.sqlite 기반 (concepts / relations / literal_props 등)
    - 서지(하단) 검색: kdc_ddc_mapping.db 기반 (mapping_data)
    - 진행률 콜백과 취소 플래그를 지원.
    - 🔧 v1.2: 주제모음·DDC·KDC-Like 편집 사항을 DB에 즉시 반영(우선 DatabaseManager setter → 없으면 concepts 테이블 컬럼 upsert).
    """

    def __init__(self, db_manager: DatabaseManager):

        self.db = db_manager

        self._lock = threading.Lock()

    # ---------- 유틸 ----------

    def _emit(self, cb: ProgressCB, v: int):

        if cb:

            try:

                cb(max(0, min(100, v)))

            except Exception:

                pass

    # ---------- 저장(편집) API ----------
    def update_field(self, concept_id: str, field_name: str, new_value: str) -> bool:
        """
        ✅ [통합 메서드] 개념의 특정 필드 값을 업데이트합니다.

        Args:
            concept_id: 개념 ID (예: nlk:KSH2005014167)
            field_name: 필드명 ("주제모음", "DDC", "KDC-Like")
            new_value: 새로운 값

        Returns:
            업데이트 성공 여부
        """
        concept_id = (concept_id or "").strip()
        if not concept_id:
            return False

        new_value = (new_value or "").strip()

        # ✅ [핵심 수정] 필드명을 database_manager의 필드명으로 매핑
        field_mapping = {
            "주제모음": "main_category",
            "DDC": "classification_ddc",  # ✅ 수정: ddc_classification → classification_ddc
            "KDC-Like": "classification_kdc_like",  # ✅ 수정: kdc_like_classification → classification_kdc_like
        }

        db_field_name = field_mapping.get(field_name)
        if not db_field_name:
            print(f"❌ 오류: 알 수 없는 필드명 '{field_name}'")
            return False

        # ✅ [핵심] concept_id에서 KSH 코드 추출
        # concept_id 형식: nlk:KSH2005014167
        if concept_id.startswith("nlk:"):
            ksh_code = concept_id[4:]  # "nlk:" 제거
        else:
            ksh_code = concept_id

        # ✅ [핵심] database_manager의 update_ksh_entry_by_ksh_code 메서드 호출
        try:
            success = self.db.update_ksh_entry_by_ksh_code(
                ksh_code, db_field_name, new_value
            )

            if success:
                print(
                    f"✅ 정보: {field_name} 업데이트 성공 - KSH: {ksh_code}, 값: '{new_value}'"
                )
                return True
            else:
                print(f"⚠️ 경고: {field_name} 업데이트 실패 - KSH: {ksh_code}")
                return False

        except Exception as e:
            print(f"❌ 오류: {field_name} 업데이트 실패 - {e}")
            import traceback

            traceback.print_exc()
            return False

    # ---------- 개념(상단) 검색 ----------
    def search_concepts(
        self,
        keyword: str = None,
        *,
        main_category: Optional[str] = None,
        exact_match: bool = False,
        limit: Optional[int] = None,  # ✅ [수정] 500 → None (제한 없음)
        progress: ProgressCB = None,
        is_cancelled: CancelFlag = None,
        df_raw: pd.DataFrame = None,  # ✅ [추가] 가공할 raw DataFrame을 직접 받을 수 있는 인자
    ) -> pd.DataFrame:
        """
        KSH 개념 검색 또는 이미 조회된 raw DataFrame을 UI에 표시할 DataFrame으로 변환.
        - keyword 인자가 있으면 DB에서 직접 검색합니다. (카테고리 검색 시 사용)
        - df_raw 인자가 있으면, 해당 DataFrame을 UI 형식에 맞게 가공합니다. (통합 검색 시 사용)
        - 반환 컬럼은 Tab에서 기대하는 헤더명으로 표준화합니다.
        """
        if df_raw is not None:
            # 1. 이미 조회된 DataFrame이 인자로 들어온 경우 (통합 검색 경로)
            df = df_raw  # DB 조회 없이 받은 데이터를 그대로 사용
        else:
            # 2. keyword로 DB에서 직접 검색하는 경우 (카테고리 검색 경로)
            kw = (keyword or "").strip()
            self._emit(progress, 3)
            if is_cancelled and is_cancelled():
                return pd.DataFrame()

            # ✅ [핵심 수정] 분리된 SearchQueryManager를 통해 검색 메서드를 호출
            sqm = SearchQueryManager(self.db)
            df = sqm.get_ksh_entries(
                search_term=kw,
                main_category=main_category,
                limit=limit,
                exact_match=exact_match,
            )

        # --- 이하 로직은 DB에서 조회하든, 인자로 받든 공통으로 적용되는 UI 가공 단계 ---

        # ✅ [수정] concept_id가 아직 있으면 _concept_id로 변환 (하위 호환성 유지)
        if "concept_id" in df.columns:
            df.rename(columns={"concept_id": "_concept_id"}, inplace=True)

        self._emit(progress, 60)
        if is_cancelled and is_cancelled():
            return pd.DataFrame()

        # ✅ [핵심 수정 1] UI 헤더명과 일치하도록 컬럼명 매핑을 적용합니다.
        column_mapping_to_ui = {
            # UI 노출용 매핑 (DF 컬럼명: UI 헤더명)
            "subject": "주제명",
            "main_category": "주제모음",
            "classification_ddc": "DDC",
            "classification_kdc_like": "KDC-Like",
            "matched": "Matched",
            "related": "관련어",
            "broader": "상위어",
            "narrower": "하위어",
            "synonyms": "동의어",
            "ksh_link_url": "KSH 링크",
        }

        # DataFrame에 있는 컬럼만 이름 변경
        df.rename(
            columns={
                db_col: ui_col
                for db_col, ui_col in column_mapping_to_ui.items()
                if db_col in df.columns
            },
            inplace=True,
        )

        # ❗ [핵심 보정] database_manager에서 넘어온 "id" 컬럼을 제거합니다.
        if "id" in df.columns:
            df.drop(columns=["id"], inplace=True, errors="ignore")

        # ✅ [핵심 수정 2] UI가 예상하는 최종 컬럼 순서를 정의하고 DF를 재정렬합니다.
        ui_header_order = [
            "주제명",
            "주제모음",
            "DDC",
            "KDC-Like",
            "Matched",
            "관련어",
            "상위어",
            "하위어",
            "동의어",
            "KSH 링크",
        ]

        # ✅ [수정] UI 노출 컬럼만 선택하고, _concept_id는 마지막에 추가 (UI 비노출)
        final_cols = [col for col in ui_header_order if col in df.columns]
        if "_concept_id" in df.columns:
            final_cols.append("_concept_id")
        df = df[final_cols]

        self._emit(progress, 100)
        return df

    # ---------- 서지(하단) 검색 ----------

    def search_biblio_by_subject(
        self,
        subject: str,
        *,
        limit: Optional[int] = 500,  # limit은 이제 검색 로직 내부에서 처리됩니다.
        progress: ProgressCB = None,
        is_cancelled: CancelFlag = None,
    ) -> pd.DataFrame:
        """KSH 라벨(주제명/우선어)에 기반한 매핑 서지 검색 → DataFrame."""
        self._emit(progress, 8)
        if is_cancelled and is_cancelled():
            return pd.DataFrame()

        # ✅ [핵심 수정] 모듈 분리에 따라, SearchQueryManager를 통해 검색 메서드를 호출합니다.
        # self.db (DatabaseManager)에는 더 이상 복잡한 검색 로직이 없습니다.
        try:
            # 1. 분리된 검색 로직 담당 클래스를 생성합니다.
            sqm = SearchQueryManager(self.db)
            # 2. sqm 인스턴스를 통해 올바른 검색 메서드를 호출합니다.
            df = sqm.get_bibliographic_by_subject_name(subject)
        except Exception as e:
            print(f"서지 DB 검색 중 오류 발생: {e}")
            df = pd.DataFrame()

        self._emit(progress, 100)
        return df

    # ✅ [신규 추가] 여러 주제어를 한 번에 검색하는 최적화 메서드
    def search_biblio_by_multiple_subjects(
        self,
        subjects: list[str],
        *,
        limit_per_subject: int = 100,
        progress: ProgressCB = None,
        is_cancelled: CancelFlag = None,
    ) -> pd.DataFrame:
        """
        ✅ [신규 최적화] 복수의 KSH 주제명(리스트)을 사용하여 단일 쿼리로 서지 데이터를 검색합니다.
        """
        if not subjects:
            return pd.DataFrame()

        self._emit(progress, 8)
        if is_cancelled and is_cancelled():
            return pd.DataFrame()

        try:
            # SearchQueryManager에 이와 같은 새로운 메서드를 추가해야 합니다.
            # 여기서는 직접 DB를 호출하여 구현합니다.
            conn = self.db._get_mapping_connection()
            cursor = conn.cursor()

            # 동적 쿼리 생성
            # 1. CASE 문: 어떤 키워드가 매칭되었는지 식별
            case_sql = "CASE "
            for keyword in subjects:
                case_sql += f"WHEN ksh_labeled LIKE ? THEN ? "
            case_sql += "END AS matched_keyword"

            # 2. WHERE 문: 모든 키워드를 OR 조건으로 연결
            where_sql = " OR ".join(["ksh_labeled LIKE ?"] * len(subjects))

            # 3. 파라미터 생성
            # CASE용 파라미터: ['%keyword1%', 'keyword1', '%keyword2%', 'keyword2', ...]
            # WHERE용 파라미터: ['%keyword1%', '%keyword2%', ...]
            params = []
            like_params = []
            for kw in subjects:
                like_kw = f"%{kw}%"
                params.extend([like_kw, kw])
                like_params.append(like_kw)
            params.extend(like_params)

            query = f"""
                SELECT
                    title,
                    ddc,
                    ksh_labeled,
                    {case_sql}
                FROM
                    mapping_data
                WHERE
                    {where_sql}
                LIMIT {len(subjects) * limit_per_subject}
            """

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            cols = [desc[0] for desc in cursor.description]

            conn.close()

            df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame()

        except Exception as e:
            print(f"복수 주제명으로 서지 DB 검색 중 오류 발생: {e}")
            df = pd.DataFrame()

        self._emit(progress, 100)
        return df

    def search_biblio_by_title(
        self,
        title_keyword: str,
        *,
        limit: Optional[int] = 500,
        progress: ProgressCB = None,
        is_cancelled: CancelFlag = None,
    ) -> pd.DataFrame:
        """✅ [신규 추가] 제목으로 서지 DB를 검색합니다."""
        self._emit(progress, 8)
        if is_cancelled and is_cancelled():
            return pd.DataFrame()

        try:
            # SearchQueryManager를 통해 제목 검색 메서드 호출
            sqm = SearchQueryManager(self.db)
            df = sqm.get_bibliographic_by_title(title_keyword)
        except Exception as e:
            print(f"제목으로 서지 DB 검색 중 오류 발생: {e}")
            df = pd.DataFrame()

        self._emit(progress, 100)
        return df


def search_ksh_local_orchestrated(
    search_term: str, main_category: str, app_instance, db_manager, **kwargs
) -> tuple:
    """
    [수정] BaseSearchTab의 SearchThread와 호환되는 KSH Local 검색 진입점 함수.
    - 검색어 유형(키워드, DDC, KSH코드)을 자동으로 분석하여 통합 검색을 수행합니다.
    - 쉼표(,)로 구분된 다중 키워드는 병렬로 처리하여 검색 속도를 향상시킵니다.
    """
    if not db_manager:
        app_instance.log_message(
            "DB 매니저가 없어 KSH Local 검색을 중단합니다.", "ERROR"
        )
        return pd.DataFrame(), pd.DataFrame(), None

    sqm = SearchQueryManager(db_manager)
    searcher = KshLocalSearcher(db_manager)

    # 쉼표나 세미콜론으로 구분된 다중 키워드인지 확인
    keywords = [kw.strip() for kw in re.split(r"[,;]", search_term) if kw.strip()]

    # -------------------
    # ✅ [핵심 수정] 다중 키워드일 경우 병렬 처리 로직 적용
    if search_term and len(keywords) > 1:
        app_instance.log_message(f"통합 검색 시작 (병렬): {keywords}", "DEBUG")

        def _search_worker(keyword):
            """단일 키워드에 대한 검색 작업을 수행하는 래퍼 함수"""
            # 기존 통합 검색 로직을 단일 키워드에 대해 실행
            df_c_raw, df_b, s_type = sqm.search_integrated_ksh(search_term=keyword)
            return df_c_raw, df_b, s_type

        all_concepts_raw = []
        all_biblio = []
        search_type = "keyword"  # 다중 키워드 검색은 항상 'keyword' 타입

        with ThreadPoolExecutor(max_workers=len(keywords)) as executor:
            future_to_keyword = {
                executor.submit(_search_worker, kw): kw for kw in keywords
            }
            for future in as_completed(future_to_keyword):
                try:
                    df_c_raw, df_b, _ = future.result()
                    if not df_c_raw.empty:
                        all_concepts_raw.append(df_c_raw)
                    if not df_b.empty:
                        all_biblio.append(df_b)
                except Exception as e:
                    kw = future_to_keyword[future]
                    app_instance.log_message(f"'{kw}' 검색 중 오류: {e}", "ERROR")

        # 모든 결과를 하나로 합침
        df_concepts_raw_combined = (
            pd.concat(all_concepts_raw, ignore_index=True)
            if all_concepts_raw
            else pd.DataFrame()
        )
        df_biblio_combined = (
            pd.concat(all_biblio, ignore_index=True) if all_biblio else pd.DataFrame()
        )

        # 최종 UI용 데이터 가공
        df_concepts_ui = searcher.search_concepts(df_raw=df_concepts_raw_combined)
        return df_concepts_ui, df_biblio_combined, search_type
    # -------------------

    # 단일 키워드 또는 카테고리 검색 (기존 로직 유지)
    elif search_term:
        app_instance.log_message(f"통합 검색 시작: '{search_term}'", "DEBUG")
        df_concepts_raw, df_biblio, search_type = sqm.search_integrated_ksh(
            search_term=search_term
        )

        # -------------------
        # ✅ [신규 추가] '키워드' 검색일 경우, DDC Cache DB에서도 키워드 검색을 수행하여 서지 결과에 추가합니다.
        if search_type == "keyword":
            ddc_keyword_results = sqm.search_ddc_by_multiple_keywords(
                search_term, max_results_per_level=5
            )
            if ddc_keyword_results:
                ddc_keyword_data = []
                found_ddcs = [res["ddc"] for res in ddc_keyword_results]
                ddc_label_map = sqm.get_all_ddc_labels_bulk(found_ddcs)

                for result in ddc_keyword_results:
                    ddc_val = result.get("ddc", "")
                    ddc_keyword_data.append(
                        {
                            "ksh_labeled": f"{result.get('keyword', '')}",
                            "title": f"(매칭된 키워드: {result.get('keyword', '')})",
                            "ddc": ddc_val,
                            "ddc_label": ddc_label_map.get(ddc_val, ""),
                            "kdc": "",
                            "publication_year": str(result.get("ddc_count", "N/A")),
                            "identifier": "",
                            "data_type": "DDC 키워드",
                            "source_file": "DDC Cache DB",
                        }
                    )

                if ddc_keyword_data:
                    df_ddc_keywords = pd.DataFrame(ddc_keyword_data)
                    df_biblio = pd.concat(
                        [df_biblio, df_ddc_keywords], ignore_index=True
                    )
        # -------------------
        df_concepts_ui = searcher.search_concepts(df_raw=df_concepts_raw)
        return df_concepts_ui, df_biblio, search_type

    elif main_category and main_category != "전체":
        app_instance.log_message(f"카테고리 검색 시작: '{main_category}'", "DEBUG")
        df_concepts = searcher.search_concepts(
            keyword=None, main_category=main_category
        )
        return df_concepts, pd.DataFrame(), "category"

    else:
        return pd.DataFrame(), pd.DataFrame(), None
