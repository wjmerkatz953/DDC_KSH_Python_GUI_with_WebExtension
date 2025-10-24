# -*- coding: utf-8 -*-
# 파일명: Search_NLK.py
# Version: v6.0.0 (Refactored)
# 수정일시: 2025-09-20 KST
# 설명: NLK OpenAPI 통합 검색 모듈. Search_UPenn.py 스타일의 계층적 구조로 리팩토링됨.

import requests
import xml.etree.ElementTree as ET
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from api_clients import clean_text

# ==============================================================================
# 🎯 1. 설정 및 예외 클래스 (중앙 집중 관리)
# ==============================================================================

NLK_CONFIG = {
    "BASE_URL": "https://www.nl.go.kr/NL/search/openApi/search.do",
    "MARC_DOWNLOAD_URL": "https://www.nl.go.kr/NL/marcDownload.do?downData={view_key},AH1",
    "MODS_DOWNLOAD_URL": "https://www.nl.go.kr/NL/search/mods_view.do?contentsId={view_key}",
    "DEFAULT_PAGE_SIZE": 30,
    "TIMEOUT": 20,
    "MARC_MODS_MAX_WORKERS": 8,
    "MARC_MODS_TIMEOUT": 10,
    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
}

_nlk_cache = {}


class NLKSearchError(Exception):
    """NLK 검색 관련 커스텀 예외"""

    pass


# ==============================================================================
# 🎯 2. 메인 진입점 함수
# ==============================================================================


def search_nlk_catalog(
    title_query=None,
    author_query=None,
    isbn_query=None,
    ddc_query=None,
    year_query=None,  # 현재 NLK API에서 미사용, 향후 확장성을 위해 유지
    app_instance=None,
    db_manager=None,
):
    """NLK 통합 검색 - 단일 진입점"""
    try:
        # ✨ year_query도 검증에 포함
        if not any([title_query, author_query, isbn_query, ddc_query, year_query]):
            raise NLKSearchError("검색어가 하나 이상 필요합니다.")

        api_key = get_nlk_api_key(db_manager)
        if not api_key:
            raise NLKSearchError("NLK API 키가 설정되지 않았습니다.")

        # API 파라미터 구성
        # ✨ year_query도 파라미터 빌더에 전달
        api_params = _build_api_params(
            title_query, author_query, isbn_query, ddc_query, year_query, api_key
        )

        # API 호출 및 기본 파싱
        raw_results = _route_and_parse_search(api_params, app_instance)

        # MARC/MODS 데이터로 후처리
        processed_results = _post_process_with_marc_mods(raw_results, app_instance)

        if app_instance:
            app_instance.log_message(
                f"정보: NLK 검색 완료. 최종 {len(processed_results)}건 결과 반환.",
                level="INFO",
            )

        return processed_results

    except Exception as e:
        _handle_nlk_error(e, app_instance, context="메인 검색 프로세스")
        return []


# ==============================================================================
# 🎯 3. API 파라미터 빌더 및 라우터
# ==============================================================================


def _build_api_params(
    title_query, author_query, isbn_query, ddc_query, year_query, api_key
):
    """검색 조건에 따라 API 파라미터를 동적으로 구성"""
    params = {
        "key": api_key,
        "detailSearch": "true",
        "pageNum": 1,
        "pageSize": NLK_CONFIG["DEFAULT_PAGE_SIZE"],
    }

    # -------------------
    # ✨ FIX: DDC 검색을 위한 특별 파라미터 우선 처리
    if ddc_query:
        params["gu2"] = "ddc"
        params["guCode2"] = ddc_query
    # -------------------

    # OpenAPI 가이드 v2.6에 따른 복합 검색 필드 구성
    fields = []
    if title_query:
        fields.append(("title", title_query))
    if author_query:
        fields.append(("author", author_query))
    if year_query:
        fields.append(("pub_year", year_query))  # ✨ 연도 필드 추가
    # 🐞 BUG FIX: DDC는 위에서 특별 처리했으므로 여기서 제거

    if isbn_query:
        params["isbnOp"] = "isbn"
        params["isbnCode"] = isbn_query

    # 남은 일반 필드들을 f, v 파라미터로 구성
    if fields:
        # DDC가 이미 처리된 경우를 고려하여 and 로직을 유연하게 조정
        start_index = 2 if ddc_query else 1
        for i, (field_name, value) in enumerate(fields, start_index):
            params[f"f{i}"] = field_name
            params[f"v{i}"] = value
            if i > 1:
                params[f"and{i-1}"] = "AND"

    return params


def _route_and_parse_search(api_params, app_instance):
    """API를 호출하고 기본 결과를 파싱하는 라우터"""
    if app_instance:
        app_instance.log_message(
            f"정보: NLK API 요청 시작. Params: {api_params}", level="INFO"
        )

    response = _call_nlk_api(api_params, app_instance)
    return _parse_nlk_xml_response(response.text, app_instance)


# ==============================================================================
# 🎯 4. API 호출 및 파싱 계층
# ==============================================================================


def _call_nlk_api(api_params, app_instance):
    """통합 NLK API 호출 함수"""
    try:
        response = requests.get(
            NLK_CONFIG["BASE_URL"],
            params=api_params,
            headers={"User-Agent": NLK_CONFIG["USER_AGENT"]},
            timeout=NLK_CONFIG["TIMEOUT"],
        )
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        raise NLKSearchError(f"API 네트워크 요청 실패: {e}")


def _parse_nlk_xml_response(xml_text, app_instance):
    """NLK API의 XML 응답을 파싱하여 기본 결과 리스트 생성"""
    try:
        root = ET.fromstring(xml_text)
        result_element = root.find("result")
        if result_element is None:
            if app_instance:
                app_instance.log_message(
                    "정보: NLK 검색 결과 없음 (result 엘리먼트 없음)", level="INFO"
                )
            return []

        results = []
        for item_element in result_element.findall("item"):
            results.append(_map_nlk_api_item_to_dict(item_element))

        if app_instance:
            app_instance.log_message(
                f"정보: NLK API 기본 파싱 완료. {len(results)}건", level="INFO"
            )
        return results
    except ET.ParseError as e:
        raise NLKSearchError(f"XML 파싱 실패: {e}")


def _map_nlk_api_item_to_dict(item):
    """XML item 엘리먼트를 표준 딕셔너리로 변환"""
    detail_link = clean_text(item.findtext("detail_link", ""))
    if detail_link.startswith("/"):
        detail_link = "https://www.nl.go.kr" + detail_link

    return {
        "제목": clean_text(item.findtext("title_info", "")),
        "저자": clean_text(item.findtext("author_info", "")),
        "출판사": clean_text(item.findtext("pub_info", "")),
        "연도": clean_text(item.findtext("pub_year_info", "")),
        "ISBN": clean_text(item.findtext("isbn", "")),
        "상세 링크": detail_link,
        "KDC": clean_text(item.findtext("class_no", "")),
        "viewKey": extract_nlk_view_key_from_detail_link(detail_link),
        # 아래 필드들은 후처리 단계에서 채워짐
        "082": "",
        "650 필드": "",
    }


# ==============================================================================
# 🎯 5. 상세 정보 후처리 계층 (MARC/MODS)
# ==============================================================================


def _post_process_with_marc_mods(raw_results, app_instance):
    """MARC/MODS 정보를 병렬로 가져와 결과 리스트를 보강"""
    if not raw_results:
        return []

    view_keys = [res["viewKey"] for res in raw_results if res.get("viewKey")]
    if not view_keys:
        return raw_results

    marc_data_map = _batch_fetch_marc_mods_data(view_keys, app_instance)

    for result in raw_results:
        vk = result.get("viewKey")
        if vk in marc_data_map:
            marc_info = marc_data_map[vk]
            result["082"] = marc_info.get("ddc") or result.get("082", "")
            if marc_info.get("kdc"):
                result["KDC"] = marc_info.get("kdc")
            if marc_info.get("kac"):
                result["저자"] = "; ".join(marc_info["kac"])
            if marc_info.get("ksh"):
                result["650 필드"] = "; ".join(marc_info["ksh"])

    return raw_results


def _batch_fetch_marc_mods_data(view_keys, app_instance):
    """MARC/MODS 데이터를 병렬로 다운로드하고 파싱"""
    if not view_keys:
        return {}
    if app_instance:
        app_instance.log_message(
            f"정보: {len(view_keys)}개 레코드 MARC/MODS 상세 정보 병렬 요청 시작...",
            level="INFO",
        )

    start_time = time.time()
    results = {}

    keys_to_fetch = []
    for vk in view_keys:
        if vk in _nlk_cache:
            results[vk] = _nlk_cache[vk]
        else:
            keys_to_fetch.append(vk)

    if not keys_to_fetch:
        return results

    with ThreadPoolExecutor(
        max_workers=NLK_CONFIG["MARC_MODS_MAX_WORKERS"]
    ) as executor:
        future_to_vk = {
            executor.submit(_fetch_and_parse_single_marc_mod, vk, app_instance): vk
            for vk in keys_to_fetch
        }

        for future in as_completed(future_to_vk):
            vk = future_to_vk[future]
            try:
                data = future.result()
                results[vk] = data
                _nlk_cache[vk] = data  # 캐시에 저장
            except Exception as e:
                _handle_nlk_error(e, app_instance, f"MARC/MODS 처리 ({vk})")
                results[vk] = {"ddc": None, "kdc": None, "kac": [], "ksh": []}

    elapsed = time.time() - start_time
    if app_instance:
        app_instance.log_message(
            f"정보: MARC/MODS 상세 정보 처리 완료. {len(keys_to_fetch)}건 in {elapsed:.2f}초",
            level="INFO",
        )

    return results


def _fetch_and_parse_single_marc_mod(view_key, app_instance):
    """단일 viewKey에 대한 MARC 또는 MODS 데이터를 가져와 파싱"""
    if view_key.startswith("CNTS-"):
        return _fetch_mods_data_single(view_key, app_instance)
    else:
        return _fetch_marc_data_single(view_key, app_instance)


# ==============================================================================
# 🎯 6. 유틸리티 및 레거시 파싱 함수 (수정 없이 그대로 유지)
# ==============================================================================


def get_nlk_api_key(db_manager):
    return db_manager.get_setting("nlk_api_key") if db_manager else None


def extract_nlk_view_key_from_detail_link(detail_link):
    if not detail_link:
        return None
    match = re.search(
        r"viewKey=([A-Za-z]+-[A-Za-z0-9]+|[A-Za-z]+[0-9]+|\d+)", detail_link
    )
    return match.group(1) if match else None


def _handle_nlk_error(error, app_instance, context=""):
    error_msg = f"NLK {context} 오류: {error}"
    if app_instance:
        app_instance.log_message(error_msg, level="ERROR")


# --- 아래 함수들은 메르카츠님께서 완성하신 로직으로, 수정 없이 그대로 유지합니다. ---


def _fetch_marc_data_single(view_key, app_instance):
    marc_url = NLK_CONFIG["MARC_DOWNLOAD_URL"].format(view_key=view_key)
    try:
        with requests.Session() as session:
            response = session.get(
                marc_url,
                headers={"User-Agent": NLK_CONFIG["USER_AGENT"]},
                timeout=NLK_CONFIG["MARC_MODS_TIMEOUT"],
            )
        if response.status_code == 200:
            response.encoding = "utf-8"
            marc_content = response.text
            if "ì" in marc_content or "ë" in marc_content:
                marc_content = response.content.decode("utf-8", errors="ignore")
            ddc, kdc, kac, ksh = _extract_marc_data(marc_content, app_instance)
            return {"ddc": ddc, "kdc": kdc, "kac": kac, "ksh": ksh}
        return {"ddc": None, "kdc": None, "kac": [], "ksh": []}
    except Exception as e:
        raise NLKSearchError(f"MARC 다운로드 실패 ({view_key}): {e}")


def _fetch_mods_data_single(view_key, app_instance):
    mods_url = NLK_CONFIG["MODS_DOWNLOAD_URL"].format(view_key=view_key)
    try:
        with requests.Session() as session:
            response = session.get(
                mods_url,
                headers={"User-Agent": NLK_CONFIG["USER_AGENT"]},
                timeout=NLK_CONFIG["MARC_MODS_TIMEOUT"],
            )
        if response.status_code == 200 and response.content:
            ddc, kdc, kac, ksh = _parse_mods_xml_content(response.content, app_instance)
            return {"ddc": ddc, "kdc": kdc, "kac": kac, "ksh": ksh}
        return {"ddc": None, "kdc": None, "kac": [], "ksh": []}
    except Exception as e:
        raise NLKSearchError(f"MODS 다운로드 실패 ({view_key}): {e}")


def _extract_marc_data(marc_content, app_instance):
    if not marc_content:
        return None, None, [], []
    ddc_code, kdc_code, kac_authors, ksh_subjects = None, None, [], []
    try:
        ddc_matches = re.findall(r"\x1fa(\d+(?:\.\d+)?)\x1f2\d{2}", marc_content)
        if ddc_matches:
            ddc_code = ddc_matches[0]
        cut_match = re.search(r"\x1fc\d{2} cm", marc_content)
        clean_marc = marc_content[cut_match.end() :] if cut_match else marc_content
        ksh_big_matches = re.findall(r"8\x1fa(.*?)\x1f0KSH(\d{10})", clean_marc)
        processed_ksh = set()
        for raw_subject, ksh_digits in ksh_big_matches:
            ksh_code = f"KSH{ksh_digits}"
            clean_subject = re.sub(
                r"[\x00-\x1f\x7f-\x9f]|\s+", " ", raw_subject
            ).strip()
            if (
                len(clean_subject) >= 2
                and not clean_subject.isdigit()
                and ksh_code not in processed_ksh
            ):
                ksh_subjects.append(f"▼a{clean_subject}▼0{ksh_code}▲")
                processed_ksh.add(ksh_code)
        kac_pattern = r"1\s*(?:\x1f6.+?)?\x1fa([^\x1e]+?)\x1f0(KAC[A-Z\d]+)"
        processed_kac = set()
        matches = re.findall(kac_pattern, clean_marc)
        for author_part, kac_code in matches:
            clean_name = author_part.split("\x1f")[0].rstrip(",").strip()
            if (
                clean_name
                and len(clean_name) >= 2
                and kac_code not in processed_kac
                and any(c.isalpha() or "\uac00" <= c <= "\ud7af" for c in clean_name)
            ):
                kac_authors.append(f"{clean_name} {kac_code}")
                processed_kac.add(kac_code)
        if not kac_authors:
            kac_authors = ["KAC 저자명 없음"]
        if not ksh_subjects:
            ksh_subjects = ["KSH 주제명 없음"]
        return ddc_code, kdc_code, kac_authors, ksh_subjects
    except Exception as e:
        if app_instance:
            app_instance.log_message(f"⚠️ MARC 파싱 오류: {e}", level="WARNING")
        return None, None, ["KAC 저자명 없음 (오류)"], ["KSH 주제명 없음 (오류)"]


def _parse_mods_xml_content(xml_content, app_instance):
    if not xml_content:
        return None, None, [], []
    ddc_code, kdc_code, kac_authors, ksh_subjects = None, None, [], []
    try:
        root = ET.fromstring(xml_content)
        namespaces = {"mods": "http://www.loc.gov/mods/v3"}
        classification_elements = root.findall(
            './/mods:classification[@authority="DDC"]', namespaces
        )
        for classification in classification_elements:
            if classification.text and classification.text.strip():
                ddc_code = classification.text.strip()
                break
        kdc_elements = root.findall(
            './/mods:classification[@authority="KDC"]', namespaces
        )
        for classification in kdc_elements:
            if classification.text and classification.text.strip():
                kdc_code = classification.text.strip()
                break
        name_elements = root.findall('.//mods:name[@type="personal"]', namespaces)
        processed_kac = set()
        for name_element in name_elements:
            kac_id = name_element.get("ID", "")
            if kac_id and kac_id.startswith("KAC"):
                name_part = name_element.find("mods:namePart", namespaces)
                if name_part is not None and name_part.text:
                    author_name = name_part.text.strip()
                    if author_name and kac_id not in processed_kac:
                        kac_authors.append(f"{author_name} {kac_id}")
                        processed_kac.add(kac_id)
        subject_elements = root.findall(".//mods:subject", namespaces)
        processed_ksh = set()
        for subject_element in subject_elements:
            ksh_id = subject_element.get("ID", "").strip()
            if ksh_id and ksh_id.startswith("KSH"):
                topic_element = subject_element.find("mods:topic", namespaces)
                if topic_element is not None and topic_element.text:
                    subject_text = topic_element.text.strip()
                    if subject_text and ksh_id not in processed_ksh:
                        ksh_subjects.append(f"▼a{subject_text}▼0{ksh_id}▲")
                        processed_ksh.add(ksh_id)
        return ddc_code, kdc_code, kac_authors, ksh_subjects
    except Exception as e:
        if app_instance:
            app_instance.log_message(f"⚠️ MODS XML 파싱 오류: {e}", level="WARNING")
        return (
            None,
            None,
            ["KAC 저자명 없음 (MODS 오류)"],
            ["KSH 주제명 없음 (MODS 오류)"],
        )
