# 파일: Search_Dewey.py )
"""버전: v1.1.0
수정 내역:
    DeweyClient가 DB 조회 시 DatabaseManager 대신 SearchQueryManager를 사용하도록 의존성 구조를 올바르게 수정했습니다.
    Negative Cache 로직을 구현했습니다.
        API 조회 시 WebDewey에 없는 번호일 경우, {"exists": false} 형태로 캐시에 기록합니다.
        캐시 조회 시 '없음' 기록이 3개월 이내일 경우 API 호출을 건너뛰도록 하여 성능을 향상시켰습니다.( 'Time To Live' 또는 줄여서 'TTL)
아래는 DLD API가 보내온 JSON 샘플
{"id":"https://id.oclc.org/worldcat/ddc/E37yQ6jKcj8VqkypgYVCyj3b63","altLabel":{"sv":["Internetresurser","Webbplatser--bibliografier","Webbplatser--informationssystem","Webbdatabaser--informationssystem"],"de":["Websites--Informationssysteme","Webdatenbanken--Informationssysteme","Websites--Bibliografien","Internetquellen"],"no":["Internettressurser","Nettsteder--bibliografier","Webdatabaser--informasjonssystemer","Nettsteder--informasjonssystemer"],"en":["Web sites--bibliographies","Web sites--information systems","Web databases--information systems","Internet resources"],"it":["Siti web--sistemi informativi","Risorse di Internet","Siti web--bibliografie","Database web--sistemi informativi"],"fr":["Sites Web--systèmes d'information","Ressources Internet","Sites Web--bibliographies","Bases de données Web--systèmes d'information","Portails Web--bibliographies"]},"related":["https://id.oclc.org/worldcat/ddc/E3pdK7wtKYVRbJKdFTyrg9rTd8","https://id.oclc.org/worldcat/ddc/E3h74Y87yHXrmHRPwqhrghtKvH"],"scopeNote":{"en":["Class here directories of web sites, portals"],"no":["Her: Registre over nettsteder; nettportaler"],"sv":["Klassificera här register över webbplatser, nätportaler"],"de":["Hier auch: Webverzeichnisse, Portale"],"fr":["Classer ici les répertoires de sites Web ; les portails"],"it":["Classificare qui le cartelle dei siti web, i portali"]},"prefLabel":{"fr":"Sites Web","it":"Siti web","sv":"Webbplatser","no":"Nettsteder","de":"Websites","en":"Web sites"},"notation":"025.0422","historyNote":{"de":["Erweitert aus 025.04, 2008-08, Edition 22"],"sv":["Webbplatser under 025.04, 2008-08, Edition 22"],"no":["Nettsteder utvidet fra 025.04, 2008-08, Edition 22"],"en":["Web sites continued from 025.04, 2008-08, Edition 22"],"it":["I siti web specificati da 025.04, 2008-08, Edition 22"],"fr":["Sites Web prolongé à partir de 025.04, 2008-08, Edition 22"]},"type":"Concept","modified":"2021-01-19T07:51:53Z","inScheme":"https://id.oclc.org/worldcat/ddc/","created":"2008-08-28","broader":"https://id.oclc.org/worldcat/ddc/E3BfQcQb8xjtVxb8Br6p8xyRPP","narrower":"https://id.oclc.org/worldcat/ddc/E3M6jGBd49y8kFHCxpwTXMP9Jr","@context":"https://id.oclc.org/worldcat/ddc/context.json"}
"""
import base64
import time
import json
import logging
import re
from typing import Dict, List, Tuple, Optional
import requests
import threading
from collections import OrderedDict
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from search_query_manager import SearchQueryManager
from text_utils import clean_ksh_search_input

TOKEN_URL = "https://oauth.oclc.org/token"
URL_MAP_API = "https://id.oclc.org/worldcat/ddc/api/url?ddc={ddc}"
DEFAULT_TIMEOUT = 15
RETRY_SECONDS = 0.6

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class DeweyClient:
    def __init__(self, db_manager):
        self.db = db_manager
        self.query_manager = SearchQueryManager(db_manager)
        self._token_cache: Tuple[Optional[str], float] = (None, 0.0)
        # -------------------
        # ✅ 세션 LRU (notation → payload) + 스레드 락
        self._lru_capacity = 256
        self._lru_cache: "OrderedDict[str, dict]" = OrderedDict()
        self._lru_lock = threading.Lock()
        # 부모 코드 계산 메모이제이션(가벼움)
        self._parent_cache: dict[str, list[str]] = {}
        # ✅ 토큰 발급 동시성 제어용 락
        self._token_lock = threading.Lock()
        # -------------------

    # --- OAuth ---
    def _fetch_token(self) -> str:
        cid, secret = self.db.get_dewey_api_credentials()
        if not cid or not secret:
            raise ConnectionRefusedError("Dewey API 자격증명이 설정되지 않았습니다.")

        basic = base64.b64encode(f"{cid}:{secret}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials", "scope": "deweyLinkedData"}

        resp = requests.post(
            TOKEN_URL, headers=headers, data=data, timeout=DEFAULT_TIMEOUT
        )
        resp.raise_for_status()
        payload = resp.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Dewey 토큰 응답에 access_token이 없습니다.")
        return token

    def _get_token(self) -> str:
        # ✅ [동시성 개선] Double-checked locking 패턴
        # 먼저 락 없이 확인 (빠른 경로)
        token, ts = self._token_cache
        if token and (time.time() - ts) < 2580:  # 43분
            return token

        # 토큰이 만료되었거나 없으면 락을 획득하고 재확인
        with self._token_lock:
            # 다른 쓰레드가 이미 토큰을 발급받았을 수 있으므로 재확인
            token, ts = self._token_cache
            if token and (time.time() - ts) < 2580:
                return token

            # 실제 토큰 발급 (락 안에서만 한 번 실행)
            try:
                token = self._fetch_token()
                self._token_cache = (token, time.time())
                log.info("새로운 DDC API 토큰 발급 완료")
                return token
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    log.error("DDC API 자격증명 오류 - Client ID/Secret 확인 필요")
                else:
                    log.error(f"DDC API 토큰 발급 HTTP 오류: {e.response.status_code}")
                self._token_cache = (None, 0.0)
                raise
            except Exception as e:
                log.error(f"DDC API 토큰 발급 실패: {e}")
                self._token_cache = (None, 0.0)
                raise

    def _get_json(self, url: str) -> dict:
        # -------------------
        # 1) notation 파싱 (쿼리 ?ddc=, 경로 /ddc/api/url?ddc=, 추후 payload 폴백)
        notation = None
        try:
            m = re.search(r"[?&]ddc=([\d.]+)", url) or re.search(
                r"/ddc/[^?]*\?ddc=([\d.]+)", url
            )
            if m:
                notation = m.group(1)
        except Exception:
            notation = None

        # 2) LRU 조회
        if notation:
            with self._lru_lock:
                if notation in self._lru_cache:
                    payload = self._lru_cache.pop(notation)
                    self._lru_cache[notation] = payload
                    return payload

        # 3) DB 캐시(DDC 코드) 우선 조회
        if notation:
            # ✅ [수정] self.query_manager를 통해 캐시 조회
            raw = self.query_manager.get_dewey_by_notation(notation)
            if raw:
                try:
                    payload = json.loads(raw)
                    with self._lru_lock:
                        self._lru_cache[notation] = payload
                        if len(self._lru_cache) > self._lru_capacity:
                            self._lru_cache.popitem(last=False)
                    return payload
                except Exception as e:
                    log.warning(f"DDC 캐시 JSON 파싱 실패({notation}): {e}")

        # 4) 기존 IRI/URL 키 기반 캐시 (하위 호환)
        # ✅ [수정] self.query_manager를 통해 캐시 조회
        cached_json = self.query_manager.get_dewey_from_cache(url)
        if cached_json:
            try:
                payload = json.loads(cached_json)
                n2 = payload.get("notation")
                if n2:
                    with self._lru_lock:
                        self._lru_cache[n2] = payload
                        if len(self._lru_cache) > self._lru_capacity:
                            self._lru_cache.popitem(last=False)
                return payload
            except Exception as e:
                log.warning(f"IRI 캐시 JSON 파싱 실패({url}): {e}")

        # 5) API 호출 - 🎯 401 오류 자동 복구 추가
        # 🔥 토큰은 API 호출 직전에만 요청 (캐시 히트 시 불필요한 토큰 요청 방지)
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        for attempt in range(3):
            try:
                r = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
                r.raise_for_status()
                payload = r.json()
                try:
                    ddc_code = payload.get("notation", "") or notation
                    iri = payload.get("@id", url)
                    if ddc_code and iri:
                        # ✅ [수정] self.query_manager를 통해 캐시 저장
                        self.query_manager.save_dewey_to_cache(iri, ddc_code, r.text)
                    if ddc_code:
                        with self._lru_lock:
                            self._lru_cache[ddc_code] = payload
                            if len(self._lru_cache) > self._lru_capacity:
                                self._lru_cache.popitem(last=False)
                except Exception as e:
                    log.warning(f"Dewey 캐시 저장 실패: {e}")
                return payload
            except requests.exceptions.HTTPError as e:
                # 🎯 401 오류 시 토큰 갱신 후 재시도
                if e.response.status_code == 401:
                    log.warning(
                        f"401 Unauthorized 오류 감지 - 토큰 갱신 후 재시도 (시도 {attempt + 1}/3)"
                    )
                    # 토큰 캐시 강제 초기화
                    self._token_cache = (None, 0.0)
                    # 새로운 토큰으로 헤더 갱신
                    try:
                        headers = {"Authorization": f"Bearer {self._get_token()}"}
                        log.info("토큰 갱신 완료 - 재시도")
                    except Exception as token_error:
                        log.error(f"토큰 갱신 실패: {token_error}")
                        if attempt == 2:  # 마지막 시도
                            raise
                    if attempt == 2:  # 마지막 시도에서도 401이면 예외 발생
                        log.error("3회 시도 후에도 401 오류 지속 - 자격증명 확인 필요")
                        raise
                elif e.response.status_code == 429:
                    # Rate limit 오류 - UI 프리징 방지를 위해 재시도 없이 즉시 실패
                    log.warning(
                        f"429 Rate Limit 오류 - API 제한 도달 (DDC: {notation or url})"
                    )
                    raise  # 즉시 예외 발생
                else:
                    # 다른 HTTP 오류
                    if attempt == 2:
                        raise
                time.sleep(RETRY_SECONDS * (attempt + 1))
            except requests.exceptions.RequestException as e:
                # 네트워크 오류 등 기타 요청 오류
                if attempt == 2:
                    raise
                time.sleep(RETRY_SECONDS * (attempt + 1))
        return {}

    def _get_parent_codes(self, ddc: str) -> List[str]:
        parts = []
        current = ddc
        while True:
            parent = ""
            if "." in current:
                parent = current.rsplit(".", 1)[0]
            elif len(current) == 3:
                if current.endswith("00"):
                    parent = ""
                elif current.endswith("0"):
                    parent = current[0] + "00"
                else:
                    parent = current[:2] + "0"
            if parent and parent not in parts:
                parts.append(parent)
                current = parent
            else:
                break
        return parts

    def _fetch_url_job(self, url, result_list):
        try:
            if isinstance(url, str) and url.startswith("http"):
                result_list.append(self._get_json(url))
            elif isinstance(url, dict):
                result_list.append(url)
        except Exception as e:
            log.error(f"Concurrent fetch failed for {url}: {e}")

    def _fetch_many_concurrent(self, links: list) -> List[dict]:
        if not links:
            return []

        results = []
        threads = []
        lock = threading.Lock()

        def job_wrapper(url, res_list, thread_lock):
            try:
                data = self._get_json(url)
                with thread_lock:
                    if data:
                        res_list.append(data)
            except Exception as e:
                # 429 Rate Limit 등의 오류는 조용히 무시 (이미 로깅됨)
                pass

        for link in links:
            if isinstance(link, str) and link.startswith("http"):
                thread = threading.Thread(
                    target=job_wrapper, args=(link, results, lock)
                )
                threads.append(thread)
                thread.start()
            elif isinstance(link, dict):
                results.append(link)

        for thread in threads:
            thread.join(timeout=20)

        return results

    def get_dewey_context_by_iri(self, iri: str) -> dict:
        return {"main": self._get_json(iri)}

    def _fetch_chain_upwards(self, concept: dict) -> List[dict]:
        """
        [최종 안정화 버전] broader 속성을 추적하여 상위 계층을 수집합니다.
        """
        chain = []
        seen_ids = set()
        current_concept = concept
        for _ in range(10):  # 무한 루프 방지
            if not current_concept or not isinstance(current_concept, dict):
                break
            concept_id = current_concept.get("@id")
            if not concept_id or concept_id in seen_ids:
                break

            seen_ids.add(concept_id)
            chain.append(current_concept)
            broader = current_concept.get("broader")

            if isinstance(broader, str) and broader.startswith("http"):
                try:
                    current_concept = self._get_json(broader)
                except Exception:
                    break
            elif isinstance(broader, dict):
                current_concept = broader
            else:
                break
        return list(reversed(chain))

    def get_dewey_context(self, ddc: str) -> dict:
        """
        [최종 안정화 버전] broader 추적 방식으로 DDC 컨텍스트를 반환합니다.
        (Negative Cache 3개월 유효기간 적용)
        """
        from datetime import datetime, timedelta
        import json

        # 1️⃣ DB 캐시에서 전체 데이터 먼저 조회 (Positive & Negative Cache)
        iri = None
        main = None

        # ✅ [핵심 로직 1] Negative Cache 확인
        cached_entry = self.query_manager.get_dewey_cache_entry(ddc)
        if cached_entry:
            cached_json, last_updated = cached_entry
            try:
                payload = json.loads(cached_json)
                if payload.get("exists") is False:
                    # Negative Cache 항목 발견. 저장 시각 확인
                    three_months_ago = datetime.now() - timedelta(days=90)
                    updated_time = datetime.fromisoformat(last_updated.split(".")[0])

                    if updated_time > three_months_ago:
                        # 3개월 이내의 유효한 '없음' 캐시. API 호출 생략
                        log.info(
                            f"✅ DDC {ddc}: Negative Cache HIT (3개월 이내). API 호출을 건너뜁니다."
                        )
                        raise ValueError(
                            f"'{ddc}' 에 대한 DLD URL을 찾지 못했습니다. (Negative Cache)"
                        )
                    else:
                        # 3개월 지난 '없음' 캐시. 재검증 필요
                        log.warning(
                            f"⚠️ DDC {ddc}: Negative Cache 만료 (3개월 초과). API로 재검증합니다."
                        )
                else:
                    # Positive Cache 항목. 정상 처리
                    main = payload
                    iri = main.get("@id")
                    log.info(
                        f"✅ DDC {ddc} 전체 데이터를 DB 캐시에서 조회 (API 호출 없음)"
                    )
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                # JSON 파싱 오류 또는 Negative Cache 히트 시의 ValueError는 정상 흐름
                if "Negative Cache" in str(e):
                    raise e  # Negative cache 히트는 다시 예외 발생시켜 UI로 전달
                log.warning(f"⚠️ DDC {ddc} DB 캐시 처리 실패: {e}")
                pass  # 캐시가 손상되었거나 문제가 있으면 API로 재조회

        # 2️⃣ DB에 없거나 만료되었으면 API로 조회
        if not main:
            if not iri:
                try:
                    map_url = URL_MAP_API.format(ddc=ddc)
                    iri_map = self._get_json(map_url)
                    iri = iri_map.get(ddc)
                    if not iri:
                        # ✅ [핵심 로직 2] Negative Cache 기록
                        log.warning(
                            f"DDC {ddc}는 WebDewey에 없음. Negative Cache에 기록합니다."
                        )
                        not_found_payload = json.dumps({"exists": False})
                        self.query_manager.save_dewey_to_cache(
                            map_url, ddc, not_found_payload
                        )
                        raise ValueError(f"'{ddc}' 에 대한 DLD URL을 찾지 못했습니다.")
                except Exception as e:
                    raise e  # 여기서 발생한 예외는 상위로 전달

            main = self._get_json(iri)
            if not main:
                return {}

        # broader 추적 방식으로 hierarchy를 생성합니다.
        hierarchy = self._fetch_chain_upwards(main)

        # -------------------
        # ✅ [핵심 수정] 값이 문자열일 경우 리스트로 감싸주는 헬퍼 함수
        def _to_list(value):
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return [value]

        narrower = self._fetch_many_concurrent(_to_list(main.get("narrower")))
        related = self._fetch_many_concurrent(_to_list(main.get("related")))
        # -------------------

        return {
            "iri": iri,
            "main": main,
            "hierarchy": hierarchy,
            "narrower": narrower,
            "related": related,
        }

    def _get_parent_codes_memo(self, ddc: str) -> list[str]:
        if not ddc:
            return []
        if ddc in self._parent_cache:
            return self._parent_cache[ddc]
        parts = []
        current = ddc
        while True:
            parent = ""
            if "." in current:
                parent = current.rsplit(".", 1)[0]
            elif len(current) == 3:
                if current.endswith("00"):
                    parent = ""
                elif current.endswith("0"):
                    parent = current[0] + "00"
                else:
                    parent = current[:2] + "0"
            if parent and parent not in parts:
                parts.append(parent)
                current = parent
            else:
                break
        self._parent_cache[ddc] = parts
        return parts

    def get_ddc_with_parents(self, ddc: str) -> dict:
        """
        입력 DDC와 상위코드를 LRU/DB에서 우선 조회하고,
        캐시 미스만 API로 가져온 뒤 LRU를 채운다. 반환값은 '입력 DDC'의 payload.
        """
        if not ddc:
            return {}
        # 1) 현재 + 상위 목록
        codes = [ddc] + self._get_parent_codes_memo(ddc)

        # 2) LRU hit / DB hit 먼저
        results: dict[str, dict] = {}
        to_fetch_urls: list[str] = []
        for code in codes:
            # LRU
            with self._lru_lock:
                if code in self._lru_cache:
                    results[code] = self._lru_cache[code]
                    continue
            # DB
            # ✅ [수정] self.query_manager를 통해 캐시 조회
            raw = self.query_manager.get_dewey_by_notation(code)
            if raw:
                try:
                    payload = json.loads(raw)
                    results[code] = payload
                    with self._lru_lock:
                        self._lru_cache[code] = payload
                        if len(self._lru_cache) > self._lru_capacity:
                            self._lru_cache.popitem(last=False)
                    continue
                except Exception as e:
                    log.warning(f"DDC 캐시 JSON 파싱 실패({code}): {e}")

            # 미스 → API 대상
            to_fetch_urls.append(URL_MAP_API.format(ddc=code))

        # 3) API 호출(미스만)
        for url in to_fetch_urls:
            payload = self._get_json(url)  # 내부에서 저장 및 LRU 적재됨
            n = payload.get("notation")
            if n:
                results[n] = payload

        # 4) 최종 반환: 입력 DDC
        return results.get(ddc, {})


# ========================================
# Helper Functions (from qt_TabView_Dewey.py)
# ========================================


def extract_all_ksh_concept_ids(subject_text):
    """KSH 마크업에서 모든 KSH Concept ID (nlk:KSH...)를 추출합니다."""
    try:
        matches = re.findall(r"▼0(KSH\d+)▲", subject_text)
        return [f"nlk:{ksh_code}" for ksh_code in matches]
    except:
        return []


def format_ksh_content_for_preview(content_list, max_items=None):
    """미리보기용으로 KSH 관련어 목록의 형식을 지정합니다."""
    if not content_list:
        return ""

    if max_items is None:
        return "\n".join(content_list)
    else:
        limited_list = content_list[:max_items]
        result = "\n".join(limited_list)
        if len(content_list) > max_items:
            result += f"\n... 외 {len(content_list) - max_items}개"
        return result


def normalize_ddc_code(ddc_code: str) -> str:
    """DDC 코드 정규화"""
    if not ddc_code:
        return ""

    code = re.sub(r"[^0-9.\- ]", "", str(ddc_code)).strip()

    if "-" in code:
        parts = code.split("-")
        normalized_parts = []
        for part in parts:
            part = part.strip()
            if "." in part:
                base, decimal = part.split(".", 1)
                decimal = decimal.rstrip("0")
                normalized_parts.append(base if not decimal else f"{base}.{decimal}")
            else:
                normalized_parts.append(part)
        return "-".join(normalized_parts)

    if "." in code:
        base, decimal = code.split(".", 1)
        decimal = decimal.rstrip("0")
        return base if not decimal else f"{base}.{decimal}"
    return code


def get_parent_code(code: str) -> str:
    """상위 DDC 코드 계산"""
    if not code or code == "000":
        return ""

    if "-" in str(code):
        code = str(code).split("-", 1)[0].strip()

    normalized_code = normalize_ddc_code(code)

    if "." in normalized_code:
        base, decimal = normalized_code.split(".", 1)
        trimmed = decimal[:-1] if len(decimal) > 1 else ""
        if not trimmed or set(trimmed) == {"0"}:
            return base
        return f"{base}.{trimmed}"

    if len(normalized_code) == 3:
        if normalized_code.endswith("00"):
            return ""
        if normalized_code.endswith("0"):
            return normalized_code[0] + "00"
        return normalized_code[:2] + "0"

    return ""


def is_table_notation(raw: str) -> bool:
    """보조표 표기 확인"""
    s = str(raw).strip()
    return bool(re.fullmatch(r"\d{4,}", s)) and s[0] in "123456"


def format_table_notation(raw: str) -> str:
    """보조표 포맷팅"""
    s = str(raw).strip()
    t = s[0]
    rest = s[1:].zfill(4)
    return f"T{t}--{rest}"


def format_ddc_for_display(code: str) -> str:
    """표시용 DDC 코드 포맷"""
    if not code:
        return ""

    if "." in code:
        return code

    if re.fullmatch(r"\d{1,3}", code):
        return code

    if is_table_notation(code):
        return format_table_notation(code)

    m = re.match(r"^(\d)--(\d+)$", code)
    if m:
        table_no, rest = m.groups()
        return f"T{table_no}--{rest.zfill(4)}"

    return code


def should_lazy_expand(code: str) -> bool:
    """지연 로딩 대상 판정"""
    if not code:
        return False

    if is_table_notation(code):
        return False

    if "." in code:
        return True

    if "-" in code:
        return True

    return len(code) == 3 and code.isdigit()


def preprocess_dewey_description_for_ksh(db_manager, text: str) -> str:
    if not text:
        return ""

    sqm = SearchQueryManager(db_manager)

    def replace_parentheses(match):
        main_term, parentheses_term = match.group(1).strip(), match.group(2).strip()
        if re.match(r"^[\\d\s\-–—,]+$", parentheses_term):
            return main_term
        ref_patterns = [
            r"^(see\s+also|cf\.?,|etc\.?,|e\.g\.?,|i\.e\.?)?",
            r"^(참조|참고|예|즉)",
        ]
        if any(re.match(p, parentheses_term.lower()) for p in ref_patterns):
            return main_term
        return f"{main_term}, {parentheses_term}"

    processed_text = text
    for _ in range(3):
        if not re.search(r"([^()]+?)\s*\(([^()]+?)\)", processed_text):
            break
        processed_text = re.sub(
            r"([^()]+?)\s*\(([^()]+?)\)", replace_parentheses, processed_text
        )

    text = processed_text.strip().replace("--", ", ")
    text = re.sub(r"(,\s*)?(\.\s*){2,}$", "", text).strip()
    text = re.sub(r"\s+(and|&)\s+", ", ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{4}[-‐−–—]?\d*[-‐−–—]?\b", "", text)
    text = re.sub(r"[0-9\-‐−–—]+", "", text)
    text = re.sub(r"[;:]+", "", text)
    text = re.sub(r",+", ",", text)
    text = re.sub(r"\s*,\s*$", "", text).strip()
    text = re.sub(r"^\s*,\s*", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return sqm._singularize_search_term(text)


def get_ksh_detailed_info(concept_id, db_manager, log_message_func):
    """KSH 개념 ID로부터 상세 정보를 가져옵니다."""
    result = {
        "definition": "",
        "pref": "",
        "related": [],
        "broader": [],
        "narrower": [],
        "synonyms": [],
        "ksh_link_url": "",
    }
    try:
        conn = db_manager._get_concepts_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT prop, value FROM literal_props WHERE concept_id = ? ORDER BY prop",
            (concept_id,),
        )
        for prop, value in cursor.fetchall():
            if prop == "definition":
                result["definition"] = value
            elif prop == "prefLabel":
                result["pref"] = value
            elif prop == "altLabel":
                result["synonyms"].append(value)

        cursor.execute(
            "SELECT prop, target FROM uri_props WHERE concept_id = ?", (concept_id,)
        )
        for prop, target_id in cursor.fetchall():
            if target_id and target_id.startswith("nlk:KSH"):
                cursor.execute(
                    "SELECT value FROM literal_props WHERE concept_id = ? AND prop = 'prefLabel' LIMIT 1",
                    (target_id,),
                )
                label_result = cursor.fetchone()
                if label_result:
                    label, ksh_code = label_result[0], target_id.replace("nlk:", "")
                    formatted = f"▼a{label}▼0{ksh_code}▲"
                    if prop in result:
                        result[prop].append(formatted)

        if concept_id.startswith("nlk:"):
            ksh_code = concept_id.replace("nlk:", "")
            result["ksh_link_url"] = (
                f"https://librarian.nl.go.kr/LI/contents/L20201000000.do?controlNo={ksh_code}"
            )
        conn.close()
    except Exception as e:
        log_message_func(f"오류: KSH 상세 정보 조회 실패 - {e}", level="ERROR")
    return result


def search_ksh_for_dewey_tab(sqm, search_term, is_cancelled_callback=None):
    """
    Dewey 탭의 KSH 검색 패널에서 실행되는 모든 비즈니스 로직을 총괄하는 함수입니다.
    이 함수는 QThread의 백그라운드 작업으로 실행됩니다.
    """
    # ----------------------------------------------------------------------------------
    # [사전 준비 1단계] - 필수 라이브러리(pandas) 로드 확인
    # ----------------------------------------------------------------------------------
    # 이 프로그램은 데이터를 DataFrame 형태로 다루므로, pandas 라이브러리가 필수적입니다.
    # 만약 pandas가 설치되어 있지 않으면, 오류를 발생시키지 않고 조용히 함수를 종료합니다.
    try:
        import pandas as pd
    except ImportError:
        # pandas가 없는 환경에서는 아무 작업도 할 수 없으므로 None을 반환합니다.
        print("Pandas is not installed. Returning empty DataFrame.")
        return None

    # ----------------------------------------------------------------------------------
    # [사전 준비 2단계] - 사용자 입력값 전처리
    # ----------------------------------------------------------------------------------
    # 사용자가 입력한 검색어(예: "  파이썬   프로그래밍  ")에 포함된 불필요한 공백이나
    # 특수문자를 제거하여 순수한 검색 키워드만 남깁니다. (예: "파이썬프로그래밍")
    cleaned_search_term = clean_ksh_search_input(search_term)

    # ----------------------------------------------------------------------------------
    # [메인 검색 1단계] - KSH 개념 DB 및 서지 DB 통합 검색
    # ----------------------------------------------------------------------------------
    # 사용자가 '검색 취소' 버튼을 눌렀는지 확인하고, 취소했다면 즉시 중단합니다.
    if is_cancelled_callback and is_cancelled_callback():
        return pd.DataFrame()

    # search_integrated_ksh 함수는 입력된 검색어를 분석하여 'DDC', 'KSH 코드', '키워드' 등
    # 유형을 자동으로 판별하고, KSH 개념 DB와 서지 DB에서 관련된 모든 정보를 한 번에 가져옵니다.
    # 이 함수는 (개념 DataFrame, 서지 DataFrame, 검색어 타입) 세 가지를 반환합니다.
    final_concepts, final_bibliographic, search_type = sqm.search_integrated_ksh(
        search_term=cleaned_search_term
    )

    # 검색 결과가 하나도 없는 경우를 대비하여, None 대신 빈 DataFrame으로 변수를 초기화합니다.
    # 이렇게 하면 이후의 코드에서 데이터가 없는 경우에도 오류 없이 안전하게 처리할 수 있습니다.
    final_concepts = final_concepts if final_concepts is not None else pd.DataFrame()
    final_bibliographic = (
        final_bibliographic if final_bibliographic is not None else pd.DataFrame()
    )

    # ----------------------------------------------------------------------------------
    # [결과 취합 준비] - 최종 결과 테이블의 컬럼 순서 및 이름 정의
    # ----------------------------------------------------------------------------------
    # 화면에 표시될 테이블의 컬럼 순서와 헤더 이름을 미리 정의합니다.
    # 이 순서대로 데이터가 조합되어 최종 DataFrame이 만들어집니다.
    biblio_cols = [
        "ksh",
        "title",
        "ddc",
        "ddc_label",
        "kdc",
        "publication_year",
        "identifier",
        "data_type",
        "source_file",
    ]

    # 여러 검색 소스(서지, 컨셉, DDC Cache)의 결과를 담을 빈 리스트를 생성합니다.
    all_data = []

    # ----------------------------------------------------------------------------------
    # [결과 취합 1단계] - 서지 DB 검색 결과(final_bibliographic) 처리
    # ----------------------------------------------------------------------------------
    # 서지 DB에서 가져온 결과가 있는지 확인합니다.
    if not final_bibliographic.empty:
        # 각 행을 순회하면서, 미리 정의한 컬럼(biblio_cols) 형식에 맞게 데이터를 정리합니다.
        for _, row in final_bibliographic.iterrows():
            all_data.append(
                {
                    "ksh": row.get("ksh_labeled", row.get("ksh", "")),
                    "title": row.get("title", ""),
                    "ddc": row.get("ddc", ""),
                    "ddc_label": row.get("ddc_label", ""),
                    "kdc": row.get("kdc", ""),
                    "publication_year": row.get("publication_year", ""),
                    "identifier": row.get("identifier", ""),
                    "data_type": "서지",  # 이 데이터의 출처가 '서지 DB'임을 명시합니다.
                    "source_file": row.get("source_file", ""),
                }
            )

    # ----------------------------------------------------------------------------------
    # [결과 취합 2단계] - KSH 개념 DB 검색 결과(final_concepts) 처리
    # ----------------------------------------------------------------------------------
    # KSH 개념 DB에서 가져온 결과가 있는지 확인합니다.
    if not final_concepts.empty:
        # 성능 향상을 위해, 결과에 포함된 모든 DDC 코드의 레이블을 DB에서 한 번에 조회합니다.
        # 이렇게 하면 각 행마다 DB에 접근하는 비효율을 막을 수 있습니다.
        unique_ddcs = final_concepts["DDC"].dropna().unique().tolist()
        ddc_label_map = {}
        if unique_ddcs:
            ddc_label_map = sqm.get_all_ddc_labels_bulk(unique_ddcs)

        # 각 행을 순회하면서, 미리 정의한 컬럼 형식에 맞게 데이터를 정리합니다.
        for _, row in final_concepts.iterrows():
            ddc_value = row.get("DDC", "")
            # 위에서 미리 만들어 둔 DDC 레이블 맵에서 해당 DDC의 설명을 가져옵니다.
            ddc_label_value = ddc_label_map.get(ddc_value, "") if ddc_value else ""

            all_data.append(
                {
                    "ksh": row.get("주제명", ""),
                    "title": row.get("Matched", ""),
                    "ddc": ddc_value,
                    "ddc_label": ddc_label_value,
                    "kdc": row.get("KDC-Like", ""),
                    "publication_year": "",  # 컨셉 데이터에는 발행년 정보가 없습니다.
                    "identifier": row.get("_concept_id", ""),
                    "data_type": "컨셉",  # 이 데이터의 출처가 '컨셉 DB'임을 명시합니다.
                    "source_file": row.get("주제모음", ""),
                }
            )

    # ----------------------------------------------------------------------------------
    # [메인 검색 2단계] - DDC Cache DB 보조 검색 (핵심 수정 지점)
    # ----------------------------------------------------------------------------------
    # 이전 단계에서 '숫자/DDC 형식'이 아닌 '순수 텍스트 키워드'만 분리합니다.
    # 이 로직은 불필요한 중복/에러 검색을 막는 핵심적인 역할을 합니다.
    keywords_only = []
    original_keywords = [
        kw.strip() for kw in re.split(r"[,;]", search_term) if kw.strip()
    ]
    for kw in original_keywords:
        # 정규식을 사용해 숫자와 점(.)만으로 이루어진 DDC 형식의 키워드를 걸러냅니다.
        if not re.fullmatch(r"[\d\.]+", kw):
            keywords_only.append(kw)

    # 분리된 '순수 텍스트 키워드'가 있을 경우에만 DDC Cache DB 보조 검색을 실행합니다.
    if keywords_only:
        # 검색할 키워드들을 다시 쉼표로 연결된 문자열로 만듭니다. (예: "Python, Java")
        supplemental_search_term = ", ".join(keywords_only)

        # DDC Cache DB에서 텍스트 키워드로 DDC 정보를 검색합니다.
        ddc_keyword_results = sqm.search_ddc_by_multiple_keywords(
            supplemental_search_term, max_results_per_level=5
        )

        # 보조 검색 결과가 있다면, 최종 결과 리스트(all_data)에 추가합니다.
        if ddc_keyword_results:
            # 성능 향상을 위해, 찾은 DDC 코드들의 레이블을 한 번에 조회합니다.
            found_ddcs = [res["ddc"] for res in ddc_keyword_results]
            ddc_label_map = sqm.get_all_ddc_labels_bulk(found_ddcs)

            for result in ddc_keyword_results:
                ddc_val = result.get("ddc", "")
                label_text = ddc_label_map.get(ddc_val, "")
                all_data.append(
                    {
                        "ksh": f"DDC: {ddc_val}",
                        "title": label_text,
                        "ddc": ddc_val,
                        "ddc_label": label_text,
                        "kdc": "",
                        "publication_year": "",
                        "identifier": "",
                        "data_type": "DDC Cache",  # 이 데이터의 출처가 'DDC Cache'임을 명시합니다.
                        "source_file": "DDC Cache DB",
                    }
                )

    # ----------------------------------------------------------------------------------
    # [최종 마무리] - 통합된 결과를 DataFrame으로 변환하여 반환
    # ----------------------------------------------------------------------------------
    # 모든 검색 결과를 취합한 all_data 리스트가 비어있으면, 빈 DataFrame을 반환합니다.
    if not all_data:
        return pd.DataFrame()

    # all_data 리스트와 미리 정의한 컬럼 순서(biblio_cols)를 사용하여 최종 DataFrame을 생성합니다.
    combined_df = pd.DataFrame(all_data, columns=biblio_cols)
    # 생성된 DataFrame을 호출한 쪽(DeweyKshSearchThread)으로 반환합니다.
    return combined_df


def dewey_get_safe(data, key):
    """딕셔너리 안전 get"""
    return data.get(key, "") if isinstance(data, dict) else ""


def dewey_pick_label(value):
    """다국어 레이블 선택"""
    if isinstance(value, dict):
        return value.get("en") or value.get("ko") or value.get("label") or ""
    return str(value) if value else ""


def search_dewey_hierarchy(dewey_client, ddc_code, is_cancelled_callback=None):
    """
    DDC 계층 검색 비즈니스 로직.
    DeweySearchThread로부터 분리되었습니다.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if is_cancelled_callback and is_cancelled_callback():
        return None

    main_ctx = dewey_client.get_dewey_context(ddc_code)

    if is_cancelled_callback and is_cancelled_callback():
        return None

    hierarchy_data = {}

    raw_main_code = dewey_get_safe(main_ctx.get("main", {}), "notation")
    main_code = normalize_ddc_code(raw_main_code)
    main_label = dewey_pick_label(main_ctx.get("main", {}).get("prefLabel"))
    if main_code:
        hierarchy_data[main_code] = main_label or "Label not found"

    for item in main_ctx.get("hierarchy", []):
        if is_cancelled_callback and is_cancelled_callback():
            return None
        code = normalize_ddc_code(dewey_get_safe(item, "notation"))
        if code:
            label = dewey_pick_label(item.get("prefLabel"))
            hierarchy_data[code] = label or "Label not found"

    path_codes = []
    current_code = main_code
    while current_code:
        if is_cancelled_callback and is_cancelled_callback():
            return None
        path_codes.append(normalize_ddc_code(current_code))
        current_code = get_parent_code(current_code)

    if path_codes:
        top_code = path_codes[-1]
        if len(top_code) == 3 and not top_code.endswith("00"):
            path_codes.append(top_code[0] + "00")
    path_codes = sorted(list(set(path_codes)))

    missing_codes = [code for code in path_codes if code not in hierarchy_data]
    if missing_codes and (not is_cancelled_callback or not is_cancelled_callback()):

        def fetch_label(code):
            if is_cancelled_callback and is_cancelled_callback():
                return code, "Label not found"
            if not code or code == "000":
                return code, "Label not found"
            try:
                missing_ctx = dewey_client.get_dewey_context(code)
                label = dewey_pick_label(missing_ctx.get("main", {}).get("prefLabel"))
                return code, label or "Label not found"
            except Exception:
                return code, "Label not found"

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(fetch_label, code): code for code in missing_codes
            }
            for future in as_completed(futures):
                if is_cancelled_callback and is_cancelled_callback():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return None
                code, label = future.result()
                hierarchy_data[code] = label

    if is_cancelled_callback and is_cancelled_callback():
        return None

    return {
        "main_ctx": main_ctx,
        "hierarchy_data": hierarchy_data,
        "path_codes": path_codes,
    }
