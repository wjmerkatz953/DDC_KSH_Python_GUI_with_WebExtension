# -*- coding: utf-8 -*-
# Version: v1.0.0
# 작성일시: 2025-09-17 (GAS 버전 1.0.22를 Python으로 포팅)

"""
Search_CiNii.py - CiNii Books API 검색 모듈
GAS 버전의 CiNii Books 검색 로직을 Python으로 포팅하여 NDL 탭과 통합
"""

# ✅ [추가] PyInstaller 환경에서 SSL 인증서 경로 설정
from ssl_cert_utils import configure_ssl_certificates
configure_ssl_certificates()

import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
import re


def search_cinii_books(
    title_query, author_query, isbn_query, year_query="", app_instance=None
):
    """
    CiNii Books API를 사용하여 단행본 정보를 검색합니다.
    NDL 탭과 호환되는 형식으로 결과를 반환합니다.

    Args:
        title_query (str): 검색할 제목
        author_query (str): 검색할 저자
        isbn_query (str): 검색할 ISBN
        year_query (str): 검색할 발행연도
        app_instance: GUI 애플리케이션 인스턴스 (로그용)

    Returns:
        list: 검색 결과 딕셔너리 목록 (NDL 형식과 호환)
    """
    if app_instance:
        app_instance.log_message("정보: CiNii Books 검색 시작")
        app_instance.update_progress(0)  # ✅ 수정된 코드

    # 검색어 구성 (GAS 로직과 동일)
    api_query_values = []
    search_criteria = {}

    if title_query:
        api_query_values.append(quote_plus(title_query))
        search_criteria["title"] = title_query.strip()

    if author_query:
        api_query_values.append(quote_plus(author_query))
        search_criteria["author"] = author_query.strip()

    if isbn_query:
        api_query_values.append(quote_plus(isbn_query))

    # 발행 연도는 API 쿼리에서 제외하고 스크립트 내부에서 필터링 (GAS 로직과 동일)
    if year_query:
        year_value = year_query.strip()
        if re.match(r"^\d{4}$", year_value):
            search_criteria["year"] = year_value

    if not api_query_values:
        if app_instance:
            app_instance.log_message(
                "경고: CiNii 검색을 위한 검색어가 없습니다.", level="WARNING"
            )
        return []

    # API 요청 구성
    query_string = "+".join(api_query_values)
    api_endpoint = "https://ci.nii.ac.jp/books/opensearch/search"
    url = f"{api_endpoint}?q={query_string}&count=100"

    if app_instance:
        app_instance.log_message(f"정보: CiNii API URL: {url}")

    try:
        # API 호출
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        # XML 파싱
        xml_content = response.text
        document = ET.fromstring(xml_content)

        # 네임스페이스 정의 (GAS와 동일)
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "dc": "http://purl.org/dc/elements/1.1/",
            "dcterms": "http://purl.org/dc/terms/",
            "prism": "http://prismstandard.org/namespaces/basic/2.0/",
            "cinii": "http://ci.nii.ac.jp/ns/1.0/",
        }

        # entry 요소들 찾기
        entries = document.findall(".//atom:entry", namespaces)

        if app_instance:
            app_instance.log_message(f"정보: CiNii에서 {len(entries)}개 항목 발견")

        if not entries:
            if app_instance:
                app_instance.log_message("정보: CiNii 검색 결과가 없습니다.")
            return []

        # 결과 파싱
        results = []
        filtered_count = 0

        for entry in entries:
            try:
                # 데이터 추출 (GAS 로직과 동일)
                title = _get_element_text(entry, ".//atom:title", namespaces) or ""
                link = (
                    _get_element_attribute(entry, ".//atom:link", "href", namespaces)
                    or ""
                )

                # 저자 정보
                author_element = entry.find(".//atom:author", namespaces)
                author = ""
                if author_element is not None:
                    author_name = author_element.find(".//atom:name", namespaces)
                    if author_name is not None:
                        author = author_name.text or ""

                # 출판사
                publisher = (
                    _get_element_text(entry, ".//dc:publisher", namespaces) or ""
                )

                # 발행년도
                pub_year_text = (
                    _get_element_text(entry, ".//prism:publicationDate", namespaces)
                    or ""
                )

                # ISBN 추출
                isbn = ""
                has_part_elements = entry.findall(".//dcterms:hasPart", namespaces)
                for has_part in has_part_elements:
                    if has_part.text and has_part.text.startswith("urn:isbn:"):
                        isbn = has_part.text.replace("urn:isbn:", "")
                        break

                # 연도 필터링 (GAS 로직과 동일)
                matched_year = re.match(r"^(\d{4})", pub_year_text)
                matched_year = matched_year.group(1) if matched_year else ""

                year_match = not search_criteria.get(
                    "year"
                ) or matched_year == search_criteria.get("year")

                if year_match:
                    # NDL 형식에 맞춰 결과 구성
                    result_entry = {
                        "제목": title,
                        "저자": author,
                        "연도": matched_year,
                        "출판사": publisher,
                        "650 필드": "",  # CiNii에는 주제어 정보가 제한적
                        "상세 링크": link,
                        "ISBN": isbn,
                        "출처": "CiNii",
                    }
                    results.append(result_entry)
                else:
                    filtered_count += 1

            except Exception as e:
                if app_instance:
                    app_instance.log_message(
                        f"경고: CiNii 항목 파싱 중 오류: {e}", level="WARNING"
                    )
                continue

        # 발행 연도 최신순 정렬 (GAS 로직과 동일)
        results.sort(
            key=lambda x: int(x["연도"]) if x["연도"].isdigit() else 0,
            reverse=True,
        )

        if app_instance:
            app_instance.log_message(
                f"정보: CiNii 검색 완료. {len(results)}개 결과 반환 ({filtered_count}개 필터링됨)"
            )

        return results

    except requests.exceptions.RequestException as e:
        if app_instance:
            app_instance.log_message(f"오류: CiNii API 요청 실패: {e}", level="ERROR")
        return []
    except ET.ParseError as e:
        if app_instance:
            app_instance.log_message(f"오류: CiNii XML 파싱 실패: {e}", level="ERROR")
        return []
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"오류: CiNii 검색 중 예상치 못한 오류: {e}", level="ERROR"
            )
        return []


def _get_element_text(parent, xpath, namespaces):
    """XML 요소에서 텍스트 값을 안전하게 추출합니다."""
    element = parent.find(xpath, namespaces)
    return element.text if element is not None else None


def _get_element_attribute(parent, xpath, attr_name, namespaces):
    """XML 요소에서 속성 값을 안전하게 추출합니다."""
    element = parent.find(xpath, namespaces)
    return element.get(attr_name) if element is not None else None


def search_cinii_orchestrated(
    title_query, author_query, isbn_query, year_query, app_instance
):
    """
    CiNii 검색을 오케스트레이션합니다. (search_orchestrator.py와 호환)

    Args:
        title_query (str): 검색할 제목
        author_query (str): 검색할 저자
        isbn_query (str): 검색할 ISBN
        year_query (str): 검색할 발행연도
        app_instance: GUI 애플리케이션 인스턴스

    Returns:
        list: CiNii 검색 결과 목록
    """
    if app_instance:
        app_instance.log_message("정보: CiNii 검색 오케스트레이션 시작")

    results = search_cinii_books(
        title_query, author_query, isbn_query, year_query, app_instance
    )

    if (
        app_instance
        and hasattr(app_instance, "stop_search_flag")
        and app_instance.stop_search_flag.is_set()
    ):
        app_instance.log_message("정보: CiNii 검색이 중단되었습니다.", level="INFO")
        return results

    if app_instance:
        app_instance.log_message("정보: CiNii 검색 오케스트레이션 완료")

    return results
