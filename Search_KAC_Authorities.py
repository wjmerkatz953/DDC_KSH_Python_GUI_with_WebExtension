# -*- coding: utf-8 -*-
# Version: v1.0.1
# 수정일시: 2025-08-04 15:20 KST (저작물 목록 링크 URL 형식 수정)

# ✅ [추가] PyInstaller 환경에서 SSL 인증서 경로 설정
from ssl_cert_utils import configure_ssl_certificates
configure_ssl_certificates()

import requests
import json
import re
import pandas as pd
from bs4 import BeautifulSoup  # HTML 파싱을 위해 BeautifulSoup 사용
import urllib.parse
import time
from concurrent.futures import ThreadPoolExecutor

# 국립중앙도서관 인명 상세 검색 URL
SEARCH_KAC_BASE_URL = "https://librarian.nl.go.kr/LI/contents/L20101000000.do"
KAC_BASE_URL = "https://librarian.nl.go.kr"  # 상세 페이지 접속을 위한 기본 URL

# User-Agent 헤더 (GAS 코드와 동일)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# 캐시를 위한 딕셔너리 (간단한 인메모리 캐시)
_cache = {}


def strip_html_tags_and_trim(html_string):
    """
    HTML 내용에서 태그를 제거하고 공백을 정리하는 헬퍼 함수.
    Args:
        html_string (str): HTML 문자열.
    Returns:
        str: 정리된 텍스트.
    """
    if not html_string:
        return ""
    # BeautifulSoup을 사용하여 태그 제거
    soup = BeautifulSoup(html_string, "html.parser")
    text = soup.get_text()
    return re.sub(r"\s+", " ", text).strip()


def build_url(base_url, params):
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


def extract_year(date_string):
    """
    날짜 문자열에서 4자리 연도를 추출합니다.
    Args:
        date_string (str): 날짜를 포함하는 문자열.
    Returns:
        str: 추출된 4자리 연도 (예: "2023"), 또는 찾을 수 없을 때 "연도 불명".
    """
    if not isinstance(date_string, str):
        return "연도 불명"
    # YYYY-MM-DDTHH:MM:SS 형식, YYYYMMDD 형식, [YYYY] 또는 YYYY 패턴 처리
    match = re.search(
        r"(\d{4})-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|(\d{4})\d{2}\d{2}|\b(\d{4})\b",
        date_string,
    )
    if match:
        return match.group(1) or match.group(2) or match.group(3)
    return "연도 불명"


def get_person_sections(html_content):
    """
    전체 HTML에서 각 인명에 해당하는 HTML 섹션을 추출합니다.
    BeautifulSoup을 사용하여 더 안정적으로 파싱합니다.
    Args:
        html_content (str): 웹페이지 전체 HTML 내용.
    Returns:
        list: 각 인명에 대한 BeautifulSoup 태그 객체 리스트.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    # 각 인명 데이터는 <div class="table_bd"> 로 시작합니다.
    # find_all을 사용하여 모든 섹션을 찾습니다.
    person_sections = soup.find_all("div", class_="table_bd")
    return person_sections


def extract_all_json_from_rawid(person_html_soup):
    """
    BeautifulSoup 객체에서 rawid input 태그의 value 속성에서 JSON 데이터를 추출합니다.
    Args:
        person_html_soup (bs4.Tag): 단일 인명 섹션에 해당하는 BeautifulSoup 태그 객체.
    Returns:
        dict|None: 파싱된 JSON 객체 또는 None.
    """
    rawid_input = person_html_soup.find("input", {"name": "rawid"})
    if not rawid_input or not rawid_input.get("value"):
        # print("[extract_all_json_from_rawid] No rawid input tag found or value is empty.") # 디버깅용
        return None

    encoded_value = rawid_input["value"]

    try:
        decoded_value = urllib.parse.unquote(encoded_value)  # Python의 unquote 사용
        json_string = decoded_value
        meta_prefix = "META||"
        if decoded_value.startswith(meta_prefix):
            json_string = decoded_value[len(meta_prefix) :]

        # JSON 문자열이 '{"'로 시작하고 '}'로 끝나는 패턴을 찾음
        json_part_match = re.search(r"(\{[\s\S]*\})$", json_string)

        if not json_part_match or not json_part_match.group(1):
            # print("[extract_all_json_from_rawid] No JSON part found in decoded value.") # 디버깅용
            # print(f"[extract_all_json_from_rawid] Full decoded value for debugging: {decoded_value[:500]}...") # 디버깅용
            return None

        json_string = json_part_match.group(1)

        json_object = json.loads(json_string)
        return json_object
    except Exception as e:
        # print(f"[extract_all_json_from_rawid] rawid 전체 JSON 파싱 오류: {e}. Encoded value: {encoded_value[:200]}...") # 디버깅용
        return None


def parse_person_section(person_html_soup, person_index, app_instance=None):
    """
    단일 인명 HTML 섹션에서 필요한 정보를 파싱합니다.
    Args:
        person_html_soup (bs4.Tag): 단일 인명에 대한 BeautifulSoup 태그 객체.
        person_index (int): 인명 순서 (로그용).
        app_instance (object, optional): GUI 애플리케이션 인스턴스 (로그용).
    Returns:
        list: 파싱된 데이터 배열 (DataFrame 컬럼 순서에 맞춰).
    """
    # if app_instance:
    #     app_instance.log_message(f"[parse_person_section] Processing person {person_index}. HTML snippet: {str(person_html_soup)[:200]}...", level="DEBUG")

    data = {
        "이름": "이름없음",
        "로마자_이름": "",
        "한자_이름": "",
        "직업": "",
        "성별": "",
        "생몰년": "",
        "활동분야": "",
        "지역": "",
        "국가": "",
        "기관명": "",
        "기관_코드": "",
        "관련_기관": "",
        "ISNI": "",
        "제어번호": "",
        "조직_제어번호": "",
        "등록_상태": "",
        "전체_ISNI_리소스_수": "",
        "국립중앙도서관_리소스_수": "",
        "리소스_제목": "",
        "ISNI_발급일": "",
        "상세페이지_링크": "",
        "저작물_목록_링크": "",
        "모든_저작물_목록": "더블 클릭",  # GAS 코드와 동일하게 초기 설정
        "최근_저작물": "",
    }

    # 1. 이름, 제어번호, 상세페이지 링크 추출 (HTML에서 우선적으로)
    name_link_tag = person_html_soup.find(
        "a", class_="link", href=re.compile(r"/LI/contents/L20101000000\.do\?id=KAC\d+")
    )
    if name_link_tag:
        href = name_link_tag["href"]
        id_match = re.search(r"id=(KAC\d+)", href)
        if id_match:
            data["제어번호"] = id_match.group(1)
            data["이름"] = strip_html_tags_and_trim(name_link_tag.get_text())
            data["상세페이지_링크"] = f"{KAC_BASE_URL}{href}"

    # 2. rawid 내 JSON 데이터 추출 및 데이터 병합
    raw_id_json = extract_all_json_from_rawid(person_html_soup)
    if raw_id_json:
        data["로마자_이름"] = raw_id_json.get("roman_name", data["로마자_이름"])
        data["한자_이름"] = raw_id_json.get("cn_name", data["한자_이름"])
        data["직업"] = raw_id_json.get("person_job_name", data["직업"])
        data["성별"] = raw_id_json.get("gender", data["성별"])
        data["생몰년"] = raw_id_json.get("birth_year", data["생몰년"])
        data["활동분야"] = raw_id_json.get("field_of_activity_name", data["활동분야"])
        data["지역"] = raw_id_json.get("ac_region_code_name", data["지역"])
        data["국가"] = raw_id_json.get("country_code_name", data["국가"])
        data["기관명"] = raw_id_json.get("org_name", data["기관명"])
        data["기관_코드"] = raw_id_json.get("org_code", data["기관_코드"])
        data["관련_기관"] = raw_id_json.get(
            "related_org", ""
        )  # GAS 코드와 동일하게 없으면 빈 문자열
        data["ISNI"] = (
            (raw_id_json.get("isni_disp", "") or "").replace(" ", "").replace("+", "")
        )  # 공백과 '+' 제거
        data["제어번호"] = raw_id_json.get("ac_control_no", data["제어번호"])
        data["조직_제어번호"] = raw_id_json.get("org_control_no", data["조직_제어번호"])
        data["등록_상태"] = raw_id_json.get("reg_status_name", data["등록_상태"])
        # ✅ [핵심 수정] NLK/ISNI 리소스 수를 빈 문자열과 비교하여 안전하게 추출
        data["전체_ISNI_리소스_수"] = str(
            raw_id_json.get("all_isni_resource_count", "") or ""
        )
        data["국립중앙도서관_리소스_수"] = str(
            raw_id_json.get("nlk_resource_count", "") or ""
        )
        data["리소스_제목"] = raw_id_json.get("resource_title", data["리소스_제목"])
        data["ISNI_발급일"] = raw_id_json.get("isni_issue_date", data["ISNI_발급일"])
        if raw_id_json.get("name") and data["이름"] == "이름없음":
            data["이름"] = raw_id_json["name"]

    # 3. HTML에서 직접 파싱하는 나머지 필드 (rawid에 없는 경우를 대비)
    # 생몰년
    if not data["생몰년"]:
        remark_span = person_html_soup.find("span", class_="remark", string="생몰년")
        if remark_span and remark_span.find_next_sibling("span", class_="cont"):
            data["생몰년"] = strip_html_tags_and_trim(
                remark_span.find_next_sibling("span", class_="cont").get_text()
            )

    # 직업
    if not data["직업"]:
        remark_span = person_html_soup.find("span", class_="remark", string="직업")
        if remark_span and remark_span.find_next_sibling("span", class_="cont"):
            data["직업"] = strip_html_tags_and_trim(
                remark_span.find_next_sibling("span", class_="cont").get_text()
            )

    # 활동분야
    if not data["활동분야"]:
        remark_span = person_html_soup.find("span", class_="remark", string="활동분야")
        if remark_span and remark_span.find_next_sibling("span", class_="cont"):
            data["활동분야"] = strip_html_tags_and_trim(
                remark_span.find_next_sibling("span", class_="cont").get_text()
            )

    # 국립중앙도서관_리소스_수
    if not data["국립중앙도서관_리소스_수"]:
        remark_span = person_html_soup.find("span", class_="remark", string="창작물")
        if remark_span and remark_span.find_next_sibling("span", class_="cont"):
            count_text = strip_html_tags_and_trim(
                remark_span.find_next_sibling("span", class_="cont").get_text()
            )
            if count_text.isdigit():
                data["국립중앙도서관_리소스_수"] = count_text

    # 최근 창작물
    remark_span = person_html_soup.find("span", class_="remark", string="최근창작물")
    if remark_span and remark_span.find_next_sibling("span", class_="cont"):
        data["최근_저작물"] = strip_html_tags_and_trim(
            remark_span.find_next_sibling("span", class_="cont").get_text()
        )
    else:
        data["최근_저작물"] = ""

    # ❗ 수정: 저작물 목록 링크 URL 형식 변경
    if data["제어번호"]:
        data["저작물_목록_링크"] = f"https://www.nl.go.kr/isni/{data['제어번호']}"
    else:
        data["저작물_목록_링크"] = ""

    # if app_instance:
    #     app_instance.log_message(f"{person_index}번 인명 데이터 추출 완료: {data['이름'] or '이름없음'}", level="DEBUG")

    # GAS 코드의 saveToCurrentSheet 함수에서 정의된 헤더 순서와 일치시켜야 합니다.
    # '번호', '이름', 'ISNI', '제어번호', '직업', '생몰년', '활동분야', '지역', '기관명', '관련 기관',
    # '최근 저작물', '모든 저작물 목록', '국립중앙도서관 리소스 수', '상세페이지 링크', '저작물 목록 링크',
    # '성별', '국가', '기관 코드', '로마자 이름', '한자 이름', '조직 제어번호', '등록 상태',
    # '전체 ISNI 리소스 수', 'ISNI 발급일'
    return [
        data["이름"],
        data["ISNI"],
        data["제어번호"],
        data["직업"],
        data["생몰년"],
        data["활동분야"],
        data["모든_저작물_목록"],
        data["국립중앙도서관_리소스_수"],
        data["관련_기관"],
        data["최근_저작물"],
        data["지역"],
        data["기관명"],
        data["상세페이지_링크"],
        data["저작물_목록_링크"],
        data["성별"],
        data["국가"],
        data["기관_코드"],
        data["로마자_이름"],
        data["한자_이름"],
        data["조직_제어번호"],
        data["등록_상태"],
        data["전체_ISNI_리소스_수"],
        data["ISNI_발급일"],
    ]


def run_full_extraction(search_term, app_instance=None):
    """
    주어진 검색어로 국립중앙도서관 웹사이트에서 인명 데이터를 추출합니다.
    Args:
        search_term (str): 검색할 인명 또는 KAC 코드.
        app_instance (object, optional): GUI 애플리케이션 인스턴스 (로그 및 진행도 업데이트용).
    Returns:
        pd.DataFrame: 추출된 인명 데이터가 담긴 DataFrame.
    """
    if not search_term or not isinstance(search_term, str) or search_term.strip() == "":
        if app_instance:
            app_instance.log_message("오류: 유효한 검색어가 없습니다.", level="ERROR")
        return pd.DataFrame()

    cache_key = f"KAC_PERSON_SEARCH_{search_term}"
    if cache_key in _cache:
        if app_instance:
            app_instance.log_message(
                f"정보: 검색어 '{search_term}'에 대한 데이터가 캐시에서 로드되었습니다.",
                level="INFO",
            )
        return _cache[cache_key]

    if app_instance:
        app_instance.log_message(
            f"정보: 검색어 '{search_term}'로 KAC 인명 데이터 추출 시작...", level="INFO"
        )
        app_instance.update_progress(0)

    all_person_data = []
    page = 1
    page_size = 1000  # GAS 코드와 동일한 페이지당 아이템 수
    session = requests.Session()  # 세션 유지

    # -------------------
    # KAC 코드와 일반 이름 검색 구분 (한 번만 실행)
    if search_term.upper().startswith("KAC") and len(search_term) >= 8:
        # KAC로 시작하는 경우에만 정규식 체크
        is_kac_code = bool(re.match(r"^KAC[A-Z0-9]+$", search_term.upper()))
    else:
        # KAC로 시작하지 않으면 바로 일반 이름으로 처리
        is_kac_code = False

    if is_kac_code:
        # KAC 코드 검색
        val_param = ""
        detail_ac_control_no = search_term.upper()
        if app_instance:
            app_instance.log_message(
                f"정보: KAC 코드 검색 모드 - {detail_ac_control_no}",
                level="INFO",
            )
    else:
        # 일반 이름 검색
        val_param = search_term
        detail_ac_control_no = ""
        if app_instance:
            app_instance.log_message(
                f"정보: 일반 이름 검색 모드 - {val_param}", level="INFO"
            )
    # -------------------

    base_params = {
        "searchType": "detail",
        "pageSize": page_size,
        "acType": 0,
        "val": val_param,
        "detailAcControlName": "KAC",
        "detailAcControlNo": detail_ac_control_no,
        "isni": "",
        "detailBirth": "",
        "detailDeath": "",
        "detailActivity": "",
        "detailJob": "",
        "detailOrgType": "",
        "detailRegion": "",
        "detailRegionView": "",
        "detailResourceName": "",
        "detailIdentiType": "ISBN",
        "detailIdentiNo": "",
        "detailKeyword": "",
    }
    # -------------------

    try:
        while True:
            if app_instance and app_instance.stop_search_flag.is_set():
                app_instance.log_message(
                    "정보: 검색 중단 요청 수신. 현재까지의 결과 반환.", level="INFO"
                )
                break
            # 첫 페이지와 10페이지마다만 로깅
            if app_instance and (page == 1 or page % 10 == 0):
                app_instance.log_message(
                    f"정보: 페이지 {page} 처리 중...", level="INFO"
                )

            # 페이지만 업데이트하고 복사
            params = base_params.copy()
            params["page"] = page
            url = build_url(SEARCH_KAC_BASE_URL, params)

            try:
                response = session.get(url, headers=DEFAULT_HEADERS, timeout=15)
                response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
                html_content = response.text
            except requests.exceptions.RequestException as e:
                if app_instance:
                    app_instance.log_message(
                        f"오류: 페이지 {page} 요청 실패: {e}", level="ERROR"
                    )
                    app_instance.show_messagebox(
                        "네트워크 오류",
                        f"KAC 인명 검색 중 네트워크 오류가 발생했습니다.\n\n오류: {e}",
                        "error",
                    )
                break  # 오류 발생 시 루프 종료

            person_sections = get_person_sections(html_content)

            if not person_sections:
                if app_instance:
                    app_instance.log_message(
                        "정보: 더 이상 인명 데이터를 찾을 수 없습니다.", level="INFO"
                    )
                break  # 더 이상 데이터가 없으면 루프 종료

            for i, person_html_soup in enumerate(person_sections):
                if app_instance and app_instance.stop_search_flag.is_set():
                    app_instance.log_message(
                        "정보: 검색 중단 요청 수신. 현재까지의 결과 반환.", level="INFO"
                    )
                    break
                person_data = parse_person_section(
                    person_html_soup, (page - 1) * page_size + i + 1, app_instance
                )
                all_person_data.append(person_data)

            if app_instance and app_instance.stop_search_flag.is_set():
                break  # 내부 루프에서 중단 요청 시 외부 루프도 종료

            # 다음 페이지가 있는지 확인 (현재 페이지에 pageSize 미만이면 마지막 페이지로 간주)
            if len(person_sections) < page_size:
                break
            else:
                page += 1

            time.sleep(0.5)  # 서버 부하 방지를 위한 딜레이 (500ms)

            if app_instance:
                # 대략적인 진행률 업데이트 (페이지 수 기반)
                # 실제 총 페이지 수를 알 수 없으므로, 페이지가 증가할수록 진행률도 증가하도록 설정
                # 예를 들어 10페이지까지는 빠르게, 그 이상은 천천히
                progress = min(99, int((page / 10) * 100))
                app_instance.update_progress(progress)

        if app_instance:
            app_instance.log_message(
                f"정보: 총 {len(all_person_data)}명의 데이터를 추출했습니다.",
                level="INFO",
            )
            app_instance.update_progress(100)

        # 헤더 정의 (GAS 코드의 saveToCurrentSheet 함수에서 정의된 순서와 일치)
        headers = [
            "이름",
            "ISNI",
            "제어번호",
            "직업",
            "생몰년",
            "활동분야",
            "전체 저작물",
            "국립중앙도서관 리소스 수",  # GUI 키와 일치
            "관련 기관",
            "최근 저작물",
            "지역",
            "기관명",
            "상세페이지 링크",
            "저작물 목록 링크",
            "성별",
            "국가",
            "기관 코드",
            "로마자 이름",
            "한자 이름",
            "조직 제어번호",
            "등록 상태",
            "전체 ISNI 리소스 수",  # GUI 키와 일치
            "ISNI 발급일",
        ]
        df = pd.DataFrame(all_person_data, columns=headers)

        # -------------------
        # ✅ [핵심 수정] GUI column_map의 key와 일치하도록 컬럼명을 명시적으로 변경 (rename)
        # GUI에서 사용하는 key: "NLK 리소스"와 "ISNI 리소스"

        # 'NLK 리소스'는 GUI에서 사용하는 이름이므로, DataFrame 컬럼 이름을 GUI 키와 일치시킵니다.
        df.rename(
            columns={
                "국립중앙도서관 리소스 수": "NLK 리소스",
                "전체 ISNI 리소스 수": "ISNI 리소스",
                "상세페이지 링크": "상세 링크",
                "저작물 목록 링크": "저작물 목록 링크",
            },
            inplace=True,
        )
        # -------------------

        # 캐시에 저장
        _cache[cache_key] = df
        return df

    except Exception as e:
        error_message = f"KAC 인명 검색 중 예기치 않은 오류 발생: {e}"
        if app_instance:
            app_instance.log_message(f"오류: {error_message}", level="ERROR")
            app_instance.show_messagebox(
                "KAC 인명 검색 오류",
                f"KAC 인명 검색 중 예기치 않은 오류가 발생했습니다.\n\n오류: {e}",
                "error",
            )
        return pd.DataFrame()
    finally:
        session.close()  # 세션 종료
        if app_instance:
            app_instance.update_progress(100)


def run_multiple_kac_search(search_terms, app_instance=None):
    """
    복수의 검색어로 KAC 인명 데이터를 병렬 검색하여 통합 결과를 반환합니다.
    Args:
        search_terms (list): 검색할 인명 또는 KAC 코드 리스트.
        app_instance (object, optional): GUI 애플리케이션 인스턴스.
    Returns:
        pd.DataFrame: 통합된 검색 결과 DataFrame.
    """
    if not search_terms:
        if app_instance:
            app_instance.log_message(
                "오류: 검색어 리스트가 비어있습니다.", level="ERROR"
            )
        return pd.DataFrame()

    if app_instance:
        app_instance.log_message(
            f"정보: 복수 KAC 검색 시작 - {len(search_terms)}개 검색어", level="INFO"
        )

    import concurrent.futures
    import threading

    all_results = []

    def search_single_term(term):
        """단일 검색어에 대한 검색 함수"""
        try:
            if app_instance and app_instance.stop_search_flag.is_set():
                return pd.DataFrame()
            return run_full_extraction(term.strip(), app_instance)
        except Exception as e:
            if app_instance:
                app_instance.log_message(
                    f"오류: '{term}' 검색 실패 - {e}", level="ERROR"
                )
            return pd.DataFrame()

    # 병렬 처리로 각 검색어 검색
    max_workers = min(3, len(search_terms))  # 최대 3개 동시 검색

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_term = {
            executor.submit(search_single_term, term): term for term in search_terms
        }

        for future in concurrent.futures.as_completed(future_to_term):
            term = future_to_term[future]
            try:
                if app_instance and app_instance.stop_search_flag.is_set():
                    break

                result_df = future.result()
                if not result_df.empty:
                    all_results.append(result_df)
                    if app_instance:
                        app_instance.log_message(
                            f"정보: '{term}' 검색 완료 - {len(result_df)}건",
                            level="INFO",
                        )
                else:
                    if app_instance:
                        app_instance.log_message(
                            f"정보: '{term}' 검색 결과 없음", level="INFO"
                        )

            except Exception as exc:
                if app_instance:
                    app_instance.log_message(
                        f"오류: '{term}' 검색 중 예외 발생 - {exc}", level="ERROR"
                    )

    # 결과 통합
    if all_results:
        combined_df = pd.concat(all_results, ignore_index=True)
        # 중복 제거 (제어번호 기준)
        if "제어번호" in combined_df.columns:
            combined_df = combined_df.drop_duplicates(subset=["제어번호"], keep="first")

        if app_instance:
            app_instance.log_message(
                f"정보: 복수 검색 완료 - 총 {len(combined_df)}건 (중복 제거 후)",
                level="INFO",
            )

        return combined_df
    else:
        if app_instance:
            app_instance.log_message(
                "정보: 모든 검색어에 대한 결과가 없습니다.", level="INFO"
            )
        return pd.DataFrame()


if __name__ == "__main__":
    print("KAC Person Search Logic Module")
    # 예시: '홍길동'
    # df = run_full_extraction("홍길동")
    # if not df.empty:
    #     print(df.head())
    # else:
    #     print("데이터를 찾을 수 없거나 오류가 발생했습니다.")
