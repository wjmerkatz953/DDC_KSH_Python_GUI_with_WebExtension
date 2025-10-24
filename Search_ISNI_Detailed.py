# -*- coding: utf-8 -*-
# Version: v1.0.9
# 수정일시: 2025-08-04 13:10 KST (SyntaxError 발생 로직 원상복구 및 컬럼 순서 재조정)

import requests  # requests는 여전히 필요하지만, 직접적인 get 호출은 fetch_content로 대체
import json
import re
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import time  # 요청 간 딜레이를 위해 추가
from bs4 import BeautifulSoup  # ❗ BeautifulSoup 임포트 추가

# ❗ 추가: api_clients 모듈에서 필요한 함수 임포트
from qt_api_clients import fetch_content

# API 기본 URL
BASE_API_URL = "https://www.nl.go.kr/isni/search/detail/selectDetail"

# 고정된 파라미터들 (GAS 코드에서 가져옴)
COMMON_PARAMS = {
    "org_code": "NLK",
    "sort_key": "",
    "sort": "",
    "total_cnt": "1",
    "publish_year": "",
    "field": "",
    "kdc_class_no_name": "",
    "creation_role": "",
    "creation_role_name": "",
    "f_language": "",
    "language_code_name": "",
    "certinlk": "Y",
    "ac_type": "0",
    "offer_dbcode": "A",
    "search_val": "",
    "subject_val": "",
}

# 모든 요청에 공통으로 적용될 기본 헤더 (GAS 코드에서 가져옴)
# ❗ 제거: fetch_content가 자체 헤더를 사용하므로 이 변수는 더 이상 직접 사용되지 않음
# DEFAULT_HEADERS = {
#     'Accept': 'text/html, */*; q=0.01',
#     'Accept-Language': 'ko,en-US;q=0.9,en;q=0.8',
#     'Connection': 'keep-alive',
#     'Sec-Fetch-Dest': 'empty',
#     'Sec-Fetch-Mode': 'cors',
#     'Sec-Fetch-Site': 'same-origin',
#     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
#     'X-Requested-With': 'XMLHttpRequest',
#     'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
#     'sec-ch-ua-mobile': '?0',
#     'sec-ch-ua-platform': '"Windows"'
# }

# 캐시를 위한 딕셔너리 (간단한 인메모리 캐시)
# 실제 앱에서는 SQLite 또는 파일 기반 캐시를 고려할 수 있습니다.
_cache = {}


def _build_url(base_url, params):
    """
    URL 파라미터를 포함하여 완전한 URL을 구성합니다.
    Args:
        base_url (str): 기본 URL.
        params (dict): 파라미터 딕셔너리.
    Returns:
        str: 완성된 URL.
    """
    param_pairs = []
    for key, value in params.items():
        if value is not None:
            param_pairs.append(
                f"{urllib.parse.quote_plus(key)}={urllib.parse.quote_plus(str(value))}"
            )
    return f"{base_url}?{ '&'.join(param_pairs) }"


def _extract_json_from_rawid(person_html_soup):
    """
    BeautifulSoup 객체에서 rawid input 태그의 value 속성에서 JSON 데이터를 추출합니다.
    """
    rawid_input = person_html_soup.find("input", {"name": "rawid"})
    if not rawid_input or not rawid_input.get("value"):
        return None
    try:
        decoded_value = urllib.parse.unquote(rawid_input["value"])
        json_string = decoded_value.split("META||")[-1]
        return json.loads(json_string)
    except (json.JSONDecodeError, IndexError):
        return None


def _get_nlk_resource_count(ac_control_no, app_instance=None):
    """
    Librarian 페이지를 먼저 스크레이핑하여 nlk_resource_count (정확한 저작물 총 개수)를 가져옵니다.
    """
    try:
        # rawid 안정성을 위해 긴 URL 구조를 사용합니다.
        count_url = f"https://librarian.nl.go.kr/LI/contents/L20101000000.do?searchType=detail&page=1&pageSize=1000&acType=0&val=&detailAcControlName=KAC&detailAcControlNo={ac_control_no}&isni=&detailBirth=&detailDeath=&detailActivity=&detailJob=&detailOrgType=&detailRegion=&detailRegionView=&detailResourceName=&detailIdentiType=&detailIdentiNo=&detailKeyword="
        if app_instance:
            app_instance.log_message(
                f"정보: KAC 저작물 개수 파악 URL: {count_url}", level="INFO"
            )

        html_content = fetch_content(count_url, "KAC 저작물 개수 파악", app_instance)
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, "html.parser")
        person_section = soup.find("div", class_="table_bd")
        if not person_section:
            if app_instance:
                app_instance.log_message(
                    "경고: 저작물 개수 파악을 위한 HTML('.table_bd') 섹션을 찾지 못했습니다.",
                    level="WARNING",
                )
            return None

        # 1순위: rawid의 JSON에서 정확한 값 파싱 시도
        raw_id_json = _extract_json_from_rawid(person_section)
        if raw_id_json and "nlk_resource_count" in raw_id_json:
            count = int(raw_id_json["nlk_resource_count"])
            if app_instance:
                app_instance.log_message(
                    f"성공: KAC({ac_control_no})의 저작물 총 {count}개 파악 완료 (From JSON).",
                    level="INFO",
                )
            return count

        # 2순위: rawid가 없을 경우, HTML에서 직접 '창작물' 텍스트를 파싱 (대체 방안)
        remark_span = person_section.find("span", class_="remark", string="창작물")
        if remark_span and remark_span.find_next_sibling("span", class_="cont"):
            # strip_html_tags_and_trim 헬퍼가 필요하므로 임시로 간략히 구현
            count_text_html = remark_span.find_next_sibling(
                "span", class_="cont"
            ).get_text()
            count_text = re.sub(r"\s+", " ", count_text_html).strip()
            if count_text.isdigit():
                count = int(count_text)
                if app_instance:
                    app_instance.log_message(
                        f"성공: KAC({ac_control_no})의 저작물 총 {count}개 파악 완료 (From HTML).",
                        level="INFO",
                    )
                return count

        if app_instance:
            app_instance.log_message(
                f"경고: {ac_control_no}의 저작물 개수를 JSON과 HTML 모두에서 파악하지 못했습니다.",
                level="WARNING",
            )
        return None

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 저작물 개수 파악 중 예외 발생: {e}", level="ERROR"
            )
        return None


def _infer_pagination_from_pagehtml(page_html: str):
    """
    PageHTML 내 anchor의 searchResourceList(...) 패턴에서
    (최대 페이지 번호, 총건수 추정치)를 보조적으로 추론한다.
    """
    if not page_html:
        return (None, None)
    m_all = re.findall(
        r'searchResourceList\(\s*(\d+)\s*,\s*"NLK"\s*,\s*(\d+)\s*,', page_html
    )
    if not m_all:
        return (None, None)
    return (max(int(p) for p, c in m_all), int(m_all[-1][1]))


def _to_int(x):
    try:
        return int(str(x).strip())
    except Exception:
        return None


def _extract_json_from_response_text(text):
    """
    응답 텍스트에서 JSON 문자열을 추출합니다.
    GAS 코드의 JSON 파싱 로직을 모방합니다.
    Args:
        text (str): API 응답 텍스트.
    Returns:
        dict: 파싱된 JSON 객체, 또는 None.
    """
    json_start_marker = '{"PageHTML"'
    json_end_marker = "}]}"

    json_start = text.find(json_start_marker)
    json_end = text.rfind(json_end_marker)

    if json_start != -1 and json_end != -1 and json_end >= json_start:
        json_string = text[json_start : json_end + len(json_end_marker)]
        try:
            return json.loads(json_string)
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 오류: {e}")
            print(f"파싱 시도한 문자열 시작 부분: {json_string[:200]}")
            return None
    else:
        # print(f"JSON 시작/끝 패턴을 찾을 수 없습니다. (앞 500자): {text[:500]}")
        # print(f"JSON 시작/끝 패턴을 찾을 수 없습니다. (뒤 500자): {text[-500:]}")
        return None


def _extract_resource_data(resource):
    """
    단일 RESOURCE 객체에서 필요한 모든 데이터를 추출하여 리스트로 반환합니다.
    Args:
        resource (dict): 단일 RESOURCE 객체 (JSON).
    Returns:
        list: 시트의 한 행에 해당하는 데이터 리스트.
    """
    # 헤더 정의와 순서를 맞춰 모든 필드를 추출합니다.
    # GAS 코드의 headers 배열 순서와 동일하게 맞춰야 합니다.
    # "TITLE", "ITITLE", "LANGUAGE", "PUBLISHER", "PUBLISH_YEAR", "INFO_CODE",
    # "IS_MA", "SHAPE_NAME", "SUBJECT_INFO", "JOIN_TYPE", "REC_KEY",
    # "AC_CONTROL_NO (Main)", "KDC_CLASS_NO", "AUTHOR (Main)", "KDC", "CONTROL_NO",
    # # "MANAGE_CODE", "OFFER_DBCODE_1S", "RNUM", "IMAGE_URL", "TYPE_CODE", "ID", "EBOOK_YN",
    # "NOT_IMAGE", "OFF_AUTHOR_LIST (공저자명 (KAC코드))"
    row = [
        resource.get("TITLE", ""),
        resource.get("ITITLE", ""),
        resource.get("AUTHOR", ""),
        ", ".join(
            [
                f"{off_author.get('AUTHOR', '')}{' (' + off_author.get('AC_CONTROL_NO', '') + ')' if off_author.get('AC_CONTROL_NO') else ''}"
                for off_author in resource.get("OFF_AUTHOR_LIST", [])
            ]
        ),
        resource.get("PUBLISHER", ""),
        resource.get("PUBLISH_YEAR", ""),
        resource.get("SUBJECT_INFO", ""),
        resource.get("KDC", ""),
        resource.get("KDC_CLASS_NO", ""),
        resource.get("LANGUAGE", ""),
        resource.get("IMAGE", ""),
        resource.get("CONTROL_NO", ""),
        resource.get("EBOOK_YN", ""),
        resource.get("JOIN_TYPE", ""),
        resource.get("REC_KEY", ""),
        resource.get("AC_CONTROL_NO", ""),
        resource.get("MANAGE_CODE", ""),
        resource.get("OFFER_DBCODE_1S", ""),
        resource.get("RNUM", ""),
        resource.get("TYPE_CODE", ""),
        resource.get("ID", ""),
        resource.get("NOT_IMAGE", ""),
        resource.get("INFO_CODE", ""),
        resource.get("IS_MA", ""),
        resource.get("SHAPE_NAME", ""),
    ]
    return row


def _fetch_page_data(
    session, url, app_instance=None, page_num=1, total_pages=1, delay_sec=0.0
):
    """
    단일 페이지의 데이터를 가져오고 파싱합니다.
    Args:
        session (requests.Session): HTTP 세션 객체.
        url (str): 요청할 URL.
        app_instance (object, optional): GUI 애플리케이션 인스턴스 (로그 및 진행도 업데이트용).
        page_num (int): 현재 페이지 번호.
        total_pages (int): 전체 페이지 수 (진행률 계산용).
    Returns:
        list: 추출된 리소스 데이터 리스트, 또는 빈 리스트.
    """
    extracted_resources = []
    try:
        if app_instance and app_instance.stop_search_flag.is_set():
            app_instance.log_message(
                f"정보: 페이지 {page_num} 요청 전 중단되었습니다.", level="INFO"
            )
            return []

        # ❗ 수정: requests.get 대신 fetch_content 사용
        response_text = fetch_content(
            url, f"ISNI 상세 페이지 {page_num}", app_instance, accept_header="text/html"
        )

        if response_text is None:  # fetch_content에서 오류 처리되었거나 중단된 경우
            if app_instance:
                app_instance.log_message(
                    f"오류: 페이지 {page_num} HTML 콘텐츠를 가져오지 못했습니다.",
                    level="ERROR",
                )
            return []

        json_data = _extract_json_from_response_text(response_text)

        if (
            json_data
            and json_data.get("RESOURCE_LIST")
            and isinstance(json_data["RESOURCE_LIST"], list)
        ):
            for resource in json_data["RESOURCE_LIST"]:
                extracted_resources.append(_extract_resource_data(resource))
            if app_instance:
                app_instance.log_message(
                    f"페이지 {page_num}에서 {len(json_data['RESOURCE_LIST'])}개 자료 추출 완료.",
                    level="INFO",
                )
        else:
            if app_instance:
                app_instance.log_message(
                    f"페이지 {page_num}에서 'RESOURCE_LIST'를 찾을 수 없거나 비어 있습니다.",
                    level="INFO",
                )

        if app_instance:
            # 진행률 업데이트 (첫 페이지에서 total_pages를 확정하므로, 여기서는 page_num만으로 계산)
            progress = int((page_num / total_pages) * 100)
            app_instance.update_progress(progress)

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 페이지 {page_num} 요청 실패: {e}", level="ERROR"
            )
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 페이지 {page_num} 처리 중 예기치 않은 오류: {e}", level="ERROR"
            )

    # Adaptive pacing: delay_sec > 0일 때만 동적으로 sleep
    if delay_sec and delay_sec > 0:
        time.sleep(delay_sec)
    return extracted_resources


def scrape_isni_detailed_full_data(ac_control_no, app_instance=None):
    if not ac_control_no:
        if app_instance:
            app_instance.log_message("오류: KAC 코드가 없습니다.", level="ERROR")
        return pd.DataFrame()

    cache_key = f"ISNI_DETAILED_{ac_control_no}"
    if cache_key in _cache:
        if app_instance:
            app_instance.log_message(
                f"정보: 캐시에서 '{ac_control_no}' 데이터 로드.", level="INFO"
            )
        return _cache[cache_key]

    if app_instance:
        app_instance.log_message(
            f"정보: '{ac_control_no}' 상세 데이터 검색 시작...", level="INFO"
        )
        app_instance.update_progress(0)

    try:
        # 1. HTML 페이지를 먼저 파싱하여 정확한 저작물 총 개수(total_cnt)를 가져옵니다.
        total_cnt = _get_nlk_resource_count(ac_control_no, app_instance)

        if total_cnt is None:
            # 개수 파악 실패 시, 10개라도 가져오기 위해 안전한 값으로 설정
            total_cnt = 10
            if app_instance:
                app_instance.log_message(
                    "경고: 저작물 개수 파악 실패. 기본값(10)으로 시도합니다.",
                    level="WARNING",
                )
        elif total_cnt == 0:
            if app_instance:
                app_instance.log_message(
                    "정보: 해당 저자의 저작물이 없습니다.", level="INFO"
                )
            return pd.DataFrame()

        PAGE_SIZE = 10
        total_pages = max(1, (total_cnt + PAGE_SIZE - 1) // PAGE_SIZE)

        if app_instance:
            app_instance.log_message(
                f"정보: 총 {total_pages} 페이지, {total_cnt}개 저작물 확인. 병렬 요청 시작.",
                level="INFO",
            )
            app_instance.update_progress(10)

        # 2. 알아낸 total_cnt를 사용하여 모든 페이지 병렬 요청
        all_rows = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for page in range(1, total_pages + 1):
                if app_instance and app_instance.stop_search_flag.is_set():
                    break

                # total_cnt와 함께 rec_key를 제거하여 안정성 확보
                params = {
                    **COMMON_PARAMS,
                    "page": page,
                    "ac_control_no": ac_control_no,
                    "total_cnt": total_cnt,
                }
                if "rec_key" in params:
                    del params["rec_key"]

                page_url = _build_url(BASE_API_URL, params)
                futures.append(
                    executor.submit(_fetch_page_data, None, page_url, app_instance)
                )

            for i, future in enumerate(futures):
                if app_instance and app_instance.stop_search_flag.is_set():
                    break
                all_rows.extend(future.result())
                if app_instance:
                    app_instance.update_progress(
                        int(((i + 1) / total_pages) * 100)
                    )

        headers = [
            "TITLE",
            "ITITLE",
            "AUTHOR (Main)",
            "OFF_AUTHOR_LIST (공저자명 (KAC코드))",
            "PUBLISHER",
            "PUBLISH_YEAR",
            "SUBJECT_INFO",
            "KDC",
            "KDC_CLASS_NO",
            "LANGUAGE",
            "IMAGE_URL",
            "CONTROL_NO",
            "EBOOK_YN",
            "JOIN_TYPE",
            "REC_KEY",
            "AC_CONTROL_NO (Main)",
            "MANAGE_CODE",
            "OFFER_DBCODE_1S",
            "RNUM",
            "TYPE_CODE",
            "ID",
            "NOT_IMAGE",
            "INFO_CODE",
            "IS_MA",
            "SHAPE_NAME",
        ]

        df = pd.DataFrame(all_rows, columns=headers)
        if app_instance:
            app_instance.log_message(
                f"정보: 총 {len(df)}개 자료 추출 완료.", level="INFO"
            )

        _cache[cache_key] = df
        return df

    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: 상세 정보 스크레이핑 중 예외 발생: {e}", level="ERROR"
            )
        return pd.DataFrame()
    finally:
        if app_instance:
            app_instance.update_progress(100)


if __name__ == "__main__":
    # 이 모듈은 일반적으로 GUI 앱의 다른 부분에서 호출되므로, 직접 실행 시에는 간단한 테스트만 수행합니다.
    # 실제 GUI 앱의 app_instance 객체가 없으므로, Logger나 Toast는 작동하지 않습니다.
    print("ISNI Detailed Search Logic Module")
    # 예시: 'KAC201309056' (홍길동)
    # df = scrape_isni_detailedfull_data("KAC201309056")
    # if not df.empty:
    #     print(df.head())
    # else:
    #     print("데이터를 찾을 수 없거나 오류가 발생했습니다.")
