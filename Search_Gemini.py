# Search_Gemini.py (계층적 검증 시스템)
# -*- coding: utf-8 -*-
import os
import json

# ✅ [추가] PyInstaller 환경에서 SSL 인증서 경로 설정
from ssl_cert_utils import configure_ssl_certificates
configure_ssl_certificates()

import requests
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from database_manager import DatabaseManager
from search_query_manager import SearchQueryManager  # ✅ 최신 DDC 캐시/조회 경유 계층


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    m = JSON_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    # 백틱 없는 경우: 처음 '{'로 시작하는 JSON 블록만 추출
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidate = text[first : last + 1].strip()
        return candidate
    return text.strip()


def _safe_json_loads(text: str) -> Optional[dict]:
    if not text:
        return None
    s = _strip_code_fences(text)
    try:
        return json.loads(s)
    except Exception:
        # 흔한 패턴: 트레일링 콤마, 잘못된 따옴표 → 보정 시도
        s2 = re.sub(r",\s*}", "}", s)
        s2 = re.sub(r",\s*]", "]", s2)
        try:
            return json.loads(s2)
        except Exception:
            return None


def _fallback_hierarchy_from_text(review_text: str) -> dict:
    """
    모델 JSON 파싱이 실패했을 때 최소 동작 보장을 위한 폴백.
    - 마침표/쉼표/개행 기준으로 토큰화 후, 길이 1~8의 한글/영문 단어 추출
    - 상위: 빈도 상위 2~3개, 중간: 다음 3~4개, 하위: 명사/기술어로 추정되는 2~3개
    """
    txt = (review_text or "").strip()
    tokens = re.findall(r"[A-Za-z가-힣0-9\-]{2,}", txt)
    # 간단 빈도 집계
    freq = {}
    for t in tokens:
        t = t.lower()
        freq[t] = freq.get(t, 0) + 1
    ranked = [w for w, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))]
    broad = ranked[:3]
    specific = ranked[3:7]
    technical = [
        w
        for w in ranked
        if re.search(
            r"(학|론|법|모형|모델|알고리즘|분석|실험|데이터|미디어|심리|사회|공학|neural|model|algorithm|analysis)$",
            w,
        )
    ][:3]
    if not technical:
        technical = ranked[7:10]
    return {
        "broad": broad or ["일반"],
        "specific": specific or broad,
        "technical": technical or specific or broad,
    }


class SearchGemini:
    """
    Gemini API를 사용한 계층적 DDC 분류 + 의미 검증 시스템
    """

    def __init__(self, db_manager: DatabaseManager, app_instance=None):
        """
        SearchGemini 클래스를 초기화합니다.
        """
        self.db_manager = db_manager
        self.app_instance = app_instance
        self.query_manager = SearchQueryManager(
            db_manager
        )  # ✅ 캐시/쿼리 일원화 진입점
        self.api_key = self._get_gemini_api_key()
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    def _log(self, message: str, level: str = "INFO"):
        """앱과 콘솔 모두에 로그 출력"""
        logging_func = getattr(logging, level.lower(), logging.info)
        logging_func(message)
        if self.app_instance and hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(message, level)

    def _get_gemini_api_key(self):
        """DatabaseManager에서 Gemini API 키를 검색합니다."""
        api_key = self.db_manager.get_gemini_api_key()
        if not api_key:
            logging.error("Gemini API 키가 데이터베이스에서 발견되지 않았습니다.")
            raise ConnectionRefusedError(
                "Gemini API 키가 데이터베이스에 설정되지 않았습니다. 'API 키 설정'을 통해 먼저 설정해주세요."
            )
        return api_key

    def _extract_hierarchical_keywords(self, bundle_text: str) -> dict:
        """
        계층적 키워드 추출 (단일 입력창: 저자정보/목차/서평 혼합 텍스트):
        - 사용자는 저자정보/목차/서평을 한 번에 붙여넣는다 (표제가 없어도 내용 단서로 구분 시도)
        - Gemini 응답이 JSON이 아닐 때(빈 문자열/코드펜스/프리앰블/HTML)도 견고하게 처리
        - 파싱 실패 시 규칙 기반 폴백으로 항상 {"broad":[], "specific":[], "technical":[]} 반환
        """

        # ----- 내부 헬퍼: 번들 텍스트 섹션 추정 분리 -----
        def _split_bundle_sections(txt: str) -> dict:
            """
            번들 텍스트에서 (가능하면) 저자정보/목차/서평을 추정 분리.
            - 표제가 없는 경우도 고려: 단서 기반 간이 규칙
            - 반환: {"author": "...", "toc": "...", "review": "..."}
            """
            s = txt or ""
            # 1) 명시적 라벨 시도 (예: 저자정보: ... / 목차: ... / 서평: ...)
            pat = re.compile(
                r"(저자\s*정보|저자정보|저자|목차|서평)\s*[:：]\s*", re.IGNORECASE
            )
            parts = pat.split(s)
            sections = {"author": "", "toc": "", "review": ""}
            if len(parts) >= 3:
                buf = {
                    "저자정보": "author",
                    "저자": "author",
                    "저자 정보": "author",
                    "목차": "toc",
                    "서평": "review",
                }
                it = iter(parts[1:])  # [label1, text1, label2, text2, ...]
                for label, chunk in zip(it, it):
                    key = buf.get(label.strip().lower().replace(" ", ""), None)
                    if key:
                        sections[key] += chunk.strip() + "\n"
                if any(v.strip() for v in sections.values()):
                    return sections

            # 2) 단서 기반 추정
            lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
            author_lines, toc_lines, review_lines = [], [], []
            for ln in lines:
                if re.search(r"(저자|약력|교수|연구원|소속|박사|석사|경력)", ln):
                    author_lines.append(ln)
                    continue
                if re.search(
                    r"(목차|^제\s*\d+\s*장|^chapter\s*\d+|^part\s*\d+|\.\.\.\s*\d+$)",
                    ln,
                    re.IGNORECASE,
                ):
                    toc_lines.append(ln)
                    continue
                review_lines.append(ln)
            sections["author"] = "\n".join(author_lines).strip()
            sections["toc"] = "\n".join(toc_lines).strip()
            sections["review"] = "\n".join(review_lines).strip()
            return sections

        # ----- 폴백: 섹션 가중치 기반 n-gram 빈도 -----
        def _fallback_hierarchy_from_text(txt: str) -> dict:
            sec = _split_bundle_sections(txt)
            # 섹션별 가중치: 목차(1.2), 서평(1.0), 저자정보(0.8)
            weighted_tokens: list[str] = []
            for src, w in (("toc", 1.2), ("review", 1.0), ("author", 0.8)):
                tokens = re.findall(r"[A-Za-z가-힣0-9\-]{2,}", sec.get(src, ""))
                # 가중치만큼 중복 삽입 → 이후 카운팅에서 자연 반영
                for t in tokens:
                    n = max(1, int(w * 5))
                    weighted_tokens.extend([t] * n)

            freq: dict[str, int] = {}
            for t in weighted_tokens:
                key = t.lower()
                freq[key] = freq.get(key, 0) + 1

            ranked = [
                w for w, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
            ]
            broad = ranked[:3]
            specific = ranked[3:7]
            tech_guess = [
                w
                for w in ranked
                if re.search(
                    r"(학|론|법|모형|모델|알고리즘|분석|실험|데이터|미디어|심리|사회|공학|neural|model|algorithm|analysis)$",
                    w,
                )
            ]
            technical = tech_guess[:3] if tech_guess else ranked[7:10]
            # ✅ [수정] 새로운 구조에 맞게 딕셔너리 형태로 반환
            return {
                "broad": {"korean": broad or ["일반"], "english": []},
                "specific": {"korean": specific or broad or ["일반"], "english": []},
                "technical": {"korean": technical or specific or broad or ["일반"], "english": []},
            }

        def _norm_list(v) -> list[str]:
            """문자열/리스트 어떤 형식이 와도 리스트로 정규화"""
            if v is None:
                return []
            if isinstance(v, str):
                return [x.strip() for x in v.split(",") if x.strip()]
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
            return []

        # ----- 프롬프트 구성 (한국어/영어 키워드 분리 추출) -----
        try:
            if hasattr(self, "_build_hierarchy_prompt"):
                prompt = self._build_hierarchy_prompt(bundle_text)
            else:
                prompt = (
                    "다음 '단일 입력'에서 저자정보/목차/서평을 가능한 한 식별/추론하고, "
                    "세 섹션 모두를 반영해 계층적 키워드를 한국어와 영어로 각각 추출하여 JSON으로만 응답하세요.\n\n"
                    "응답 형식:\n"
                    "{\n"
                    '  "broad": {"korean": ["키워드1", "키워드2", ...최대5개], "english": ["keyword1", "keyword2", ...최대5개]},\n'
                    '  "specific": {"korean": ["키워드1", "키워드2", ...최대5개], "english": ["keyword1", "keyword2", ...최대5개]},\n'
                    '  "technical": {"korean": ["키워드1", "키워드2", ...최대5개], "english": ["keyword1", "keyword2", ...최대5개]}\n'
                    "}\n\n"
                    "요구사항:\n"
                    "- 각 분류(broad, specific, technical)당 한국어 키워드 최대 5개, 영어 키워드 최대 5개를 추출하세요.\n"
                    "- 표제가 없어도 내용 단서(약력/소속/경력, 장/절/페이지, 독자평/내용요약)를 활용해 구분하세요.\n"
                    "- 영어 키워드는 DDC(듀이십진분류법) 검색에 적합한 용어를 선택하세요.\n\n"
                    f"단일 입력:\n{bundle_text}\n"
                )
        except Exception as e:
            logging.error(f"[Gemini] 프롬프트 구성 실패: {e}")
            return _fallback_hierarchy_from_text(bundle_text)

        # ----- 모델 호출 -----
        try:
            raw = self._call_gemini_api(prompt)
        except Exception as e:
            logging.error(f"[Gemini] 모델 호출 실패: {e}")
            return _fallback_hierarchy_from_text(bundle_text)

        if not raw or not str(raw).strip():
            logging.error("[Gemini] 키워드 추출 응답이 비어 있습니다.")
            return _fallback_hierarchy_from_text(bundle_text)

        # ----- JSON 파싱 (견고) - 한국어/영어 분리 구조 -----
        parsed = _safe_json_loads(str(raw))
        if not parsed:
            logging.error(
                f"[Gemini] 키워드 추출 응답 파싱 실패. 원문 일부: {str(raw)[:200]!r}"
            )
            return _fallback_hierarchy_from_text(bundle_text)

        # 새로운 구조: {"broad": {"korean": [...], "english": [...]}, ...}
        hierarchy = {}
        for level in ["broad", "specific", "technical"]:
            level_data = parsed.get(level, {})
            if isinstance(level_data, dict):
                hierarchy[level] = {
                    "korean": _norm_list(level_data.get("korean", []))[:5],  # 최대 5개
                    "english": _norm_list(level_data.get("english", []))[
                        :5
                    ],  # 최대 5개
                }
            else:
                # 구조가 예상과 다르면 빈 리스트
                hierarchy[level] = {"korean": [], "english": []}

        # 최소 보장: 비어 있으면 폴백
        all_empty = all(not (v["korean"] or v["english"]) for v in hierarchy.values())
        if all_empty:
            logging.warning("[Gemini] 파싱 결과가 비어 있어 폴백 사용")
            # ✅ [수정] fallback이 이미 올바른 구조를 반환하므로 직접 사용
            hierarchy = _fallback_hierarchy_from_text(bundle_text)

        return hierarchy

    def _search_korean_keyword(
        self, keywords: str, level_name: str, max_results: int = 3
    ) -> list:
        results = []
        error_occurred = False  # 오류 발생 여부 플래그

        try:
            # 콤마로 분리
            keyword_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]
            if not keyword_list:
                self._log(
                    f"⚠️ [한국어 검색] '{keywords}': 유효한 키워드 없음", "WARNING"
                )
                return results

            self._log(
                f"🔍 [한국어 검색] {level_name}: {len(keyword_list)}개 키워드 동시 검색 시작",
                "INFO",
            )
            self._log(f"   검색 키워드: {', '.join(keyword_list)}", "INFO")

            ddc_aggregation = {}

            # ✅ [성능 개선] 여러 키워드를 한 번에 조회하는 최적화 메서드 호출
            from Search_KSH_Local import KshLocalSearcher
            import pandas as pd

            searcher = KshLocalSearcher(self.db_manager)
            df_all = searcher.search_biblio_by_multiple_subjects(keyword_list)

            if df_all is None or getattr(df_all, "empty", True):
                self._log(f"   ⚠️ 모든 키워드에 대한 검색 결과 없음", "WARNING")
            else:
                self._log(f"   🔍 통합 검색으로 {len(df_all)}개 결과 발견", "INFO")
                # ✅ [수정] 엄격한 단일 KSH 필터링 로직을 제거하여 모든 결과를 사용하도록 변경
                df = df_all.copy()

                if getattr(df, "empty", True):
                    self._log("   ⚠️ 단일 KSH 서지 없음", "WARNING")
                else:
                    self._log(
                        f"   🎯 필터링 후 {len(df)}개", "INFO"
                    )  # 로그 메시지 간소화
                    for _, row in df.iterrows():
                        ddc = row.get("ddc") or ""
                        keyword = row.get("matched_keyword")
                        if not ddc or not keyword:
                            continue

                        if ddc not in ddc_aggregation:
                            ddc_aggregation[ddc] = {
                                "count": 0,
                                "titles": [],
                                "ksh_list": [],
                                "keywords": [],
                            }

                        ddc_aggregation[ddc]["count"] += 1
                        if len(ddc_aggregation[ddc]["titles"]) < 1:
                            ddc_aggregation[ddc]["titles"].append(
                                row.get("title") or ""
                            )
                        if len(ddc_aggregation[ddc]["ksh_list"]) < 1:
                            ddc_aggregation[ddc]["ksh_list"].append(
                                row.get("ksh_labeled") or ""
                            )
                        if keyword not in ddc_aggregation[ddc]["keywords"]:
                            ddc_aggregation[ddc]["keywords"].append(keyword)

            if not ddc_aggregation:
                # 결과 없음 로그는 함수 마지막에서 처리하므로 여기서는 return만
                return results

            # ✅ [신규] 1. 최종 결과에 포함될 모든 DDC 번호를 미리 수집
            all_ddc_numbers = list(ddc_aggregation.keys())

            # ✅ [신규] 2. 새로운 대량 조회 함수를 단 한 번만 호출
            all_labels_map = self.query_manager.get_all_ddc_labels_bulk(all_ddc_numbers)

            keyword_results = {kw: [] for kw in keyword_list}
            for ddc, info in ddc_aggregation.items():
                for keyword in info["keywords"]:
                    if keyword in keyword_results:
                        keyword_results[keyword].append((ddc, info))

            for keyword in keyword_list:
                kw_ddcs = keyword_results.get(keyword, [])
                if not kw_ddcs:
                    continue

                kw_ddcs_sorted = sorted(kw_ddcs, key=lambda x: (-x[1]["count"], x[0]))[
                    :max_results
                ]

                for rank, (ddc, info) in enumerate(kw_ddcs_sorted, 1):
                    ddc_clean = re.sub(r"[^\d.]", "", ddc)
                    ddc_label = all_labels_map.get(ddc_clean, "")
                    item = {
                        "level": level_name,
                        "keyword": keyword,
                        "language": "한국어",
                        "rank": rank,
                        "ddc": ddc,
                        "ddc_count": info["count"],
                        "ddc_label": ddc_label,
                        "title": info["titles"][0][:120] if info["titles"] else "",
                        "ksh": info["ksh_list"][0] if info["ksh_list"] else "",
                    }
                    results.append(item)

        # -------------------
        # ✅ [핵심 수정] 누락되었던 except 블록 추가
        except Exception as e:
            error_occurred = True
            self._log(f"❌ [한국어 검색] '{keywords}' 검색 중 오류: {e}", "ERROR")
        # -------------------

        # 최종 결과에 따라 로그 기록
        if results:
            self._log(
                f"✅ [한국어 검색] {level_name}: 키워드 {len(keyword_list)}개 × 최대 {max_results}개 = 총 {len(results)}개 결과",
                "INFO",
            )
        elif not error_occurred:
            self._log(
                f"⚠️ [한국어 검색] {level_name}: 모든 키워드 검색 결과 없음", "WARNING"
            )

        return results

    def _search_english_keyword(
        self, keywords: str, level_name: str, max_results: int = 3
    ) -> list:
        results = []
        conn = None  # 1. DB 연결 변수를 None으로 초기화
        error_occurred = False  # 오류 발생 여부 플래그

        try:
            keyword_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]
            if not keyword_list:
                self._log(f"⚠️ [영어 검색] '{keywords}': 유효한 키워드 없음", "WARNING")
                return results

            self._log(
                f"🔍 [영어 검색] {level_name}: {len(keyword_list)}개 키워드 검색 시작",
                "INFO",
            )
            self._log(f"   검색 키워드: {', '.join(keyword_list)}", "INFO")

            conn = self.db_manager._get_dewey_connection()  # 2. try 블록 안에서 연결
            cursor = conn.cursor()

            # 각 키워드별로 개별 검색 후 최대 3개씩 선택 (이하 로직은 변경 없음)
            for keyword in keyword_list:
                fts_query = (
                    f'"{keyword}"' if "-" in keyword or " " in keyword else keyword
                )

                cursor.execute(
                    """
                    SELECT ddc, keyword, term_type
                    FROM ddc_keyword_fts
                    WHERE keyword MATCH ?
                    ORDER BY rank
                    LIMIT 100
                    """,
                    (fts_query,),
                )
                rows = cursor.fetchall()

                if not rows:
                    self._log(f"   ⚠️ '{keyword}': 검색 결과 없음", "WARNING")
                    continue

                self._log(f"   🔍 '{keyword}': {len(rows)}개 결과 발견", "INFO")

                ddc_aggregation = {}
                for ddc, matched_kw, term_type in rows:
                    if ddc not in ddc_aggregation:
                        ddc_aggregation[ddc] = {
                            "count": 0,
                            "matched_keywords": [],
                            "term_types": set(),
                        }
                    ddc_aggregation[ddc]["count"] += 1
                    if matched_kw not in ddc_aggregation[ddc]["matched_keywords"]:
                        ddc_aggregation[ddc]["matched_keywords"].append(matched_kw)
                    ddc_aggregation[ddc]["term_types"].add(term_type)

                sorted_ddcs = sorted(
                    ddc_aggregation.items(), key=lambda x: (-x[1]["count"], x[0])
                )[:max_results]

                # 결과 포맷팅 (이하 로직은 변경 없음)
                for rank, (ddc, info) in enumerate(sorted_ddcs, 1):
                    ddc_label = self.query_manager.get_ddc_description_cached(ddc) or ""
                    results.append(
                        {
                            "level": level_name,
                            "search_keyword": keyword,
                            "language": "영어",
                            "rank": rank,
                            "ddc": ddc,
                            "ddc_count": info["count"],
                            "ddc_label": ddc_label,
                            "keyword": ", ".join(info["matched_keywords"][:3]),
                            "term_type": ", ".join(sorted(info["term_types"])),
                        }
                    )
        except Exception as e:
            error_occurred = True
            self._log(f"❌ [영어 검색] '{keywords}' 검색 중 오류: {e}", "ERROR")
        finally:
            # 3. try 블록의 성공/실패 여부와 관계없이 항상 DB 연결을 닫음
            if conn:
                conn.close()

        # 4. 모든 로직이 끝난 후, 최종 결과에 따라 로그를 한 번만 기록
        if results:
            self._log(
                f"✅ [영어 검색] {level_name}: 키워드 {len(keyword_list)}개 × 최대 {max_results}개 = 총 {len(results)}개 결과",
                "INFO",
            )
        elif not error_occurred:  # 오류 없이 결과가 없는 경우에만 "결과 없음" 로그 기록
            self._log(
                f"⚠️ [영어 검색] {level_name}: 모든 키워드 검색 결과 없음", "WARNING"
            )

        return results

    def _perform_hierarchical_search(self, hierarchy: dict) -> list:
        """
        2단계: 계층별 한국어/영어 키워드 DB 병렬 검색 (복합 키워드 검색)
        - 각 분류 레벨(대/중/소)당 한국어/영어 검색을 병렬로 실행 (최대 6개 동시 작업)
        - 한국어: 5개 키워드를 콤마로 연결하여 1회 검색 → KSH DB
        - 영어: 5개 키워드를 콤마로 연결하여 1회 검색 → DDC cache DB (FTS5)
        """
        all_search_results: list[dict] = []

        with ThreadPoolExecutor(
            max_workers=6, thread_name_prefix="gemini_search"
        ) as executor:
            futures = []
            for level, keywords_dict in hierarchy.items():
                level_name = {
                    "broad": "대분류",
                    "specific": "중분류",
                    "technical": "소분류",
                }.get(level, level)

                # 한국어 키워드 검색 작업 제출
                korean_keywords = keywords_dict.get("korean", [])
                korean_keywords_filtered = [
                    kw.strip() for kw in korean_keywords if kw and str(kw).strip()
                ]
                if korean_keywords_filtered:
                    korean_keywords_str = ", ".join(korean_keywords_filtered)
                    self._log(f"🇰🇷 한국어 복합 검색 제출: {level_name}", "INFO")
                    futures.append(
                        executor.submit(
                            self._search_korean_keyword,
                            korean_keywords_str,
                            level_name,
                            max_results=3,
                        )
                    )

                # 영어 키워드 검색 작업 제출
                english_keywords = keywords_dict.get("english", [])
                english_keywords_filtered = [
                    kw.strip() for kw in english_keywords if kw and str(kw).strip()
                ]
                if english_keywords_filtered:
                    english_keywords_str = ", ".join(english_keywords_filtered)
                    self._log(f"🇺🇸 영어 복합 검색 제출: {level_name}", "INFO")
                    futures.append(
                        executor.submit(
                            self._search_english_keyword,
                            english_keywords_str,
                            level_name,
                            max_results=3,
                        )
                    )

            # 완료되는 작업 순서대로 결과 수집
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        all_search_results.extend(result)
                except Exception as e:
                    self._log(f"❌ 병렬 검색 작업 중 오류 발생: {e}", "ERROR")

        self._log(
            f"📊 계층별 병렬 검색 완료: 총 {len(all_search_results)}개 결과", "INFO"
        )
        return all_search_results

    def _build_gemini_search_summary(
        self, hierarchy: dict, search_results: list
    ) -> str:
        """
        검색 결과를 대/중/소 분류로 구분하여 Gemini API에 전달할 텍스트 생성
        """
        summary_lines = []

        for level in ["broad", "specific", "technical"]:
            level_name = {
                "broad": "대분류",
                "specific": "중분류",
                "technical": "소분류",
            }.get(level, level)

            level_data = hierarchy.get(level, {})
            korean_keywords = level_data.get("korean", [])
            english_keywords = level_data.get("english", [])

            summary_lines.append(f"\n{'='*60}")
            summary_lines.append(f"【{level_name}】")
            summary_lines.append(f"{'='*60}")

            # 추출된 키워드 표시
            summary_lines.append(f"\n추출 키워드:")
            summary_lines.append(
                f"  - 한국어: {', '.join(korean_keywords) if korean_keywords else '없음'}"
            )
            summary_lines.append(
                f"  - 영어: {', '.join(english_keywords) if english_keywords else '없음'}"
            )

            # 한국어 키워드 검색 결과
            if korean_keywords:
                summary_lines.append(f"\n한국어 키워드 검색 결과:")
                korean_results = [
                    r
                    for r in search_results
                    if r.get("level") == level_name and r.get("language") == "한국어"
                ]
                if korean_results:
                    for result in korean_results:
                        summary_lines.append(f"  키워드: {result.get('keyword', '')}")
                        summary_lines.append(f"    - 순위: {result.get('rank', '')}위")
                        summary_lines.append(f"    - DDC: {result.get('ddc', '')}")
                        summary_lines.append(
                            f"    - DDC 등장 횟수: {result.get('ddc_count', '')}회"
                        )
                        summary_lines.append(
                            f"    - DDC 의미: {result.get('ddc_label', '')}"
                        )
                        summary_lines.append(f"    - 제목: {result.get('title', '')}")
                        summary_lines.append(f"    - KSH: {result.get('ksh', '')}")
                        summary_lines.append("")
                else:
                    summary_lines.append("  (검색 결과 없음)")

            # 영어 키워드 검색 결과
            if english_keywords:
                summary_lines.append(f"\n영어 키워드 검색 결과:")
                english_results = [
                    r
                    for r in search_results
                    if r.get("level") == level_name and r.get("language") == "영어"
                ]
                if english_results:
                    for result in english_results:
                        summary_lines.append(
                            f"  검색어: {result.get('search_keyword', '')}"
                        )
                        summary_lines.append(f"    - 순위: {result.get('rank', '')}위")
                        summary_lines.append(f"    - DDC: {result.get('ddc', '')}")
                        summary_lines.append(
                            f"    - DDC 등장 횟수: {result.get('ddc_count', '')}회"
                        )
                        summary_lines.append(
                            f"    - DDC 레이블: {result.get('ddc_label', '')}"
                        )
                        summary_lines.append(
                            f"    - 매칭 키워드: {result.get('keyword', '')}"
                        )
                        summary_lines.append(
                            f"    - 용어 유형: {result.get('term_type', '')}"
                        )
                        summary_lines.append("")
                else:
                    summary_lines.append("  (검색 결과 없음)")

        return "\n".join(summary_lines)

    def _final_analysis_with_search_results(
        self, bundle_text: str, hierarchy: dict, search_results: list
    ) -> dict:
        """5단계: 검색 결과를 바탕으로 Gemini에게 최종 DDC 추천 요청"""

        # 검색 결과 요약 생성
        search_summary = self._build_gemini_search_summary(hierarchy, search_results)

        final_prompt = f"""입력(저자정보/목차/서평 혼합 텍스트):

{bundle_text}

{search_summary}

🎯 중요 지시사항:
1. 위의 검색 결과를 참고하여, 입력 텍스트에 가장 적합한 DDC 번호를 추천하세요
2. 한국어 검색 결과의 DDC와 DDC 의미, 영어 검색 결과의 DDC를 모두 고려하세요
3. 각 DDC 번호가 입력 텍스트(저자정보/목차/서평)와 얼마나 일치하는지 판단하세요
4. 의미가 일치하는 DDC만 적합도 순으로 추천하세요
5. 각 추천에 대해 "왜 그 DDC가 입력 텍스트와 일치하는지" 근거를 명시하세요

응답은 다음 JSON 형식을 엄격히 준수하세요:

{{
  "overallDescription": "추천된 모든 DDC 분류에 대한 최종 결론을 포함하는 전체적인 설명",
  "classifications": [
    {{
      "ddcNumber": "DDC 분류 번호",
      "reason": "이 분류에 대한 상세한 추천 이유 (실제 의미와의 일치성 포함, 저자·목차·서평 단서 근거 명시)"
    }}
  ]
}}"""

        try:
            response = self._call_gemini_api(final_prompt)
            if isinstance(response, dict) and "error" in response:
                return response

            # JSON 응답 파싱 (견고한 파싱)
            final_result = _safe_json_loads(str(response))
            if not final_result:
                logging.error(f"최종 분석 JSON 파싱 실패: {str(response)[:200]}")
                return {"error": "최종 분석 응답 파싱 오류"}

            # 필수 필드 검증
            if (
                "overallDescription" not in final_result
                or "classifications" not in final_result
            ):
                return {"error": "최종 분석 응답 형식 오류"}

            if not isinstance(final_result["classifications"], list):
                final_result["classifications"] = []

            self._log(
                f"🎉 최종 분석 완료: {len(final_result['classifications'])}개 DDC 추천",
                "INFO",
            )
            return final_result

        except Exception as e:
            self._log(f"❌ 최종 분석 중 오류: {e}", "ERROR")
            return {"error": f"최종 분석 중 오류: {str(e)}"}

    def _call_gemini_api(self, prompt: str) -> str or dict:
        """Gemini API 호출 공통 함수"""
        try:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 2048,
                    "responseMimeType": (
                        "application/json" if "JSON" in prompt else "text/plain"
                    ),
                },
            }

            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            }

            response = requests.post(
                self.api_url, headers=headers, json=payload, timeout=30
            )
            response.raise_for_status()

            response_data = response.json()

            if (
                "candidates" in response_data
                and len(response_data["candidates"]) > 0
                and "content" in response_data["candidates"][0]
                and "parts" in response_data["candidates"][0]["content"]
                and len(response_data["candidates"][0]["content"]["parts"]) > 0
            ):
                return response_data["candidates"][0]["content"]["parts"][0].get(
                    "text", ""
                )
            else:
                return {
                    "error": "Gemini API 응답에서 유효한 텍스트를 찾을 수 없습니다."
                }

        except requests.exceptions.HTTPError as e:
            logging.error(
                f"API HTTP 오류: {e.response.status_code} - {e.response.text}"
            )
            return {"error": f"API 오류 ({e.response.status_code}): {e.response.text}"}
        except requests.exceptions.Timeout:
            logging.error("API 요청 시간 초과")
            return {"error": "API 요청 시간 초과"}
        except Exception as e:
            logging.error(f"API 호출 중 오류: {str(e)}")
            return {"error": f"API 호출 중 오류: {str(e)}"}

    # 기존 classify_ddc 메서드 호환성을 위해 유지
    def classify_ddc(self, bundle_text: str) -> dict:
        """기존 호환성을 위한 메서드 - 새로운 계층적 시스템을 호출 (단일 입력)"""
        return self.classify_ddc_with_hierarchical_validation(bundle_text)

    def classify_ddc_with_hierarchical_validation(
        self, bundle_text: str, intermediate_callback=None
    ) -> dict:
        """
        🚀 한 입력창에 붙여넣은 저자정보/목차/서평(혼합 텍스트)을 반영한
        계층적 검색 + 최종 DDC 추천 시스템

        1단계: Gemini가 한국어/영어 키워드를 대/중/소 분류별로 추출
        2단계: 한국어 키워드로 KSH DB 검색, 영어 키워드로 DDC cache DB 검색
        3단계: 중간 결과창 업데이트
        4단계: 검색 결과를 Gemini에게 전달하여 최종 DDC 추천 받기
        """
        try:
            self._log("=" * 80, "INFO")
            self._log("🎯 1단계: 계층적 키워드 추출 시작 (한국어/영어 분리)", "INFO")
            self._log("=" * 80, "INFO")
            hierarchy = self._extract_hierarchical_keywords(bundle_text)

            self._log(f"📝 추출된 키워드:\n{hierarchy}", "INFO")

            self._log("=" * 80, "INFO")
            self._log("🔍 2단계: 계층별 한국어/영어 키워드 DB 검색", "INFO")
            self._log("=" * 80, "INFO")
            search_results = self._perform_hierarchical_search(hierarchy)

            self._log("=" * 80, "INFO")
            self._log("📊 3단계: 중간 결과창 업데이트", "INFO")
            self._log("=" * 80, "INFO")
            if intermediate_callback:
                intermediate_callback(search_results)

            self._log("=" * 80, "INFO")
            self._log("🎯 4단계: 검색 결과 기반 최종 DDC 추천 요청", "INFO")
            self._log("=" * 80, "INFO")
            return self._final_analysis_with_search_results(
                bundle_text, hierarchy, search_results
            )

        except Exception as e:
            self._log(f"❌ [Gemini] 계층적 분류 중 오류 발생: {e}", "ERROR")
            import traceback

            self._log(traceback.format_exc(), "ERROR")
            return {"error": f"계층적 분류 중 오류 발생: {str(e)}"}
