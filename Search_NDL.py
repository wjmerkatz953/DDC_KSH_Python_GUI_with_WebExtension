# -*- coding: utf-8 -*-
# Version: v1.0.56
# 수정일시: 2025-08-04 16:00 KST (GAS 버전 로직을 기반으로 NDL 상세 링크 추출 로직 재구성)

"""
Search_NDL.py - 일본 국립국회도서관(NDL) SRU API 검색 로직을 포함합니다.
이 모듈은 NDL SRU API를 사용하여 서지 정보를 검색하고, 필요한 경우 텍스트를 번역합니다.
"""

# ✅ [추가] PyInstaller 환경에서 SSL 인증서 경로 설정
from ssl_cert_utils import configure_ssl_certificates
configure_ssl_certificates()

import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
import re
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

# ❗ 추가: DatabaseManager 모듈 임포트
from database_manager import DatabaseManager

# ❗ 수정: api_clients 모듈에서 extract_year와 translate_text 함수 임포트
from qt_api_clients import extract_year, translate_text

# NDL SRU API 기본 URL (GAS와 동일하게 변경)
NDL_SRU_BASE_URL = "https://ndlsearch.ndl.go.jp/api/sru"


# Search_NDL.py 파일 상단의 임포트 부분 다음에 추가
def _should_auto_translate(app_instance):
    """자동 번역 여부를 확인합니다."""
    if hasattr(app_instance, "foreign_auto_translation_var"):
        return app_instance.foreign_auto_translation_var.get()
    return _get_foreign_auto_translation_setting(app_instance)


def _get_foreign_auto_translation_setting(app_instance):
    """해외 도서관 자동 번역 설정을 가져옵니다."""
    if hasattr(app_instance, "db_manager") and app_instance.db_manager:
        value = app_instance.db_manager.get_setting("foreign_auto_translation")
        return value == "true" if value else True  # 기본값: 활성화
    return True


def search_ndl_catalog(
    title_query,
    author_query,
    isbn_query,
    year_query="",
    app_instance=None,
    db_manager: DatabaseManager = None,
):
    """
    NDL SRU 카탈로그를 검색하고 결과를 반환합니다.
    Args:
        title_query (str): 검색할 제목 쿼리.
        author_query (str): 검색할 저자 쿼리.
        isbn_query (str): 검색할 ISBN 쿼리.
        year_query (str): 검색할 발행연도 쿼리.
        app_instance (object, optional): GUI 애플리케이션 인스턴스 (로그 및 진행도 업데이트용).
        db_manager (DatabaseManager, optional): DatabaseManager 인스턴스 (용어집 접근용).
    Returns:
        list: 검색 결과 레코드 목록. 각 레코드는 딕셔너리 형태.
    """
    if db_manager is None:
        if app_instance:
            app_instance.log_message(
                "오류: DatabaseManager 인스턴스가 제공되지 않았습니다.", level="ERROR"
            )
        return []

    if app_instance:
        app_instance.log_message(
            f"정보: NDL 검색 시작: 제목='{title_query}', 저자='{author_query}', ISBN='{isbn_query}', 발행연도='{year_query}'"
        )

    # ❗ 변경: db_manager를 통해 맞춤형 용어집을 한 번만 로드
    custom_glossary_map = db_manager.get_all_custom_translations()
    if app_instance:
        app_instance.log_message(
            f"정보: SQLite 용어집 {len(custom_glossary_map)}개 항목 로드됨.",
            level="INFO",
        )

    # 검색어 유효성 검사 및 우선순위 로직 적용
    cql_query_parts = []

    if isbn_query:
        cql_query_parts.append(f'isbn="{isbn_query}"')
        if app_instance:
            app_instance.log_message(
                f"정보: NDL 검색 쿼리: ISBN='{isbn_query}'", level="INFO"
            )
    else:
        if title_query:
            cql_query_parts.append(f'title="{title_query}"')
        if author_query:
            cql_query_parts.append(f'creator="{author_query}*"')
        if year_query:
            cql_query_parts.append(f'from="{year_query}" AND until="{year_query}"')

        if not cql_query_parts:
            if app_instance:
                app_instance.log_message(
                    "경고: NDL 검색을 위해 ISBN, 제목, 저자, 발행연도 중 하나 이상을 입력해야 합니다.",
                    level="WARNING",
                )
            return []
        if app_instance:
            app_instance.log_message(
                f"정보: NDL 검색 쿼리: 제목='{title_query}', 저자='{author_query}'",
                level="INFO",
            )

    cql_query = " AND ".join(cql_query_parts)

    ndl_api_url = (
        f"{NDL_SRU_BASE_URL}?"
        f"version=1.2&"
        f"operation=searchRetrieve&"
        f"maximumRecords=200&"
        f"recordSchema=dcndl&"
        f"query={quote_plus(cql_query)}"
    )

    if app_instance:
        app_instance.log_message(f"정보: NDL SRU API URL: {ndl_api_url}", level="INFO")

    all_results = []
    # 함수 전체를 감싸는 최상위 try-except-finally 블록
    try:
        if app_instance and app_instance.stop_search_flag.is_set():
            app_instance.log_message(
                "정보: NDL 검색 스레드가 시작 전 중단되었습니다.", level="INFO"
            )
            return []

        response = requests.get(ndl_api_url, timeout=15)
        response.raise_for_status()

        response_body = response.text
        # if app_instance:
        #     app_instance.log_message(
        #         f"DEBUG: NDL API Raw Response Body (truncated): {response_body[:1000]}...",
        #         level="DEBUG",
        #     )

        root = ET.fromstring(response_body)

        # 네임스페이스 정의 (GAS와 동일)
        sru_uri = "http://www.loc.gov/zing/srw/"
        dc_uri = "http://purl.org/dc/elements/1.1/"
        dcterms_uri = "http://purl.org/dc/terms/"
        rdf_uri = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        rdfs_uri = "http://www.w3.org/2000/01/rdf-schema#"
        foaf_uri = "http://xmlns.com/foaf/0.1/"
        xsi_uri = "http://www.w3.org/2001/XMLSchema-instance"
        dcndl_uri = "http://ndl.go.jp/dcndl/terms/"

        number_of_records_element = root.find(f"{{{sru_uri}}}numberOfRecords")
        number_of_records = (
            int(number_of_records_element.text)
            if number_of_records_element is not None
            else 0
        )
        if app_instance:
            app_instance.log_message(
                f"정보: NDL Number of Records: {number_of_records}", level="INFO"
            )

        if number_of_records == 0:
            if app_instance:
                app_instance.log_message(
                    "정보: NDL 검색 결과가 없습니다.", level="INFO"
                )

            return []

        records_wrapper_element = root.find(f"{{{sru_uri}}}records")
        if records_wrapper_element is None:
            if app_instance:
                app_instance.log_message(
                    "오류: SRU 응답에 'records' 요소가 없습니다.", level="ERROR"
                )

            return []

        records = records_wrapper_element.findall(f"{{{sru_uri}}}record")
        if app_instance:
            app_instance.log_message(
                f"정보: 처리할 레코드 수: {len(records)}", level="INFO"
            )

        for i, record in enumerate(records):
            if app_instance and app_instance.stop_search_flag.is_set():
                app_instance.log_message(
                    "정보: NDL 검색 중단 요청 수신. 현재까지의 결과 반환.", level="INFO"
                )
                return all_results

            record_data_element = record.find(f"{{{sru_uri}}}recordData")
            dcndl_record = None
            inner_root = None

            if record_data_element is not None and record_data_element.text:
                try:
                    inner_root = ET.fromstring(record_data_element.text)
                    bib_resources = inner_root.findall(f"{{{dcndl_uri}}}BibResource")
                    if bib_resources:
                        dcndl_record = bib_resources[0]
                    else:
                        if app_instance:
                            app_instance.log_message(
                                f"경고: recordData 내에서 dcndl:BibResource를 찾을 수 없습니다. innerRoot tag: {inner_root.tag}",
                                level="WARNING",
                            )
                except ET.ParseError as e:
                    if app_instance:
                        app_instance.log_message(
                            f"오류: recordDataElement 내부 XML 파싱 오류: {e}. 원본 문자열 시작: {record_data_element.text[:200]}...",
                            level="ERROR",
                        )

            result_entry = {
                "제목": "없음",
                "저자": "없음",
                "제목 번역": "없음",
                "연도": "없음",
                "상세 링크": "없음",
                "출판사": "없음",
                "650 필드 (번역)": [],
                "650 필드": [],
                "NDL ID": "없음",
                "ISBN": "없음",
            }

            if dcndl_record:
                # ❗ 수정: 제목 추출 (dcterms:title 또는 dc:title)
                title_element = dcndl_record.find(f"{{{dcterms_uri}}}title")
                if title_element is not None and title_element.text is not None:
                    result_entry["제목"] = title_element.text.strip()
                else:
                    dc_title_element = dcndl_record.find(f"{{{dc_uri}}}title")
                    if dc_title_element is not None:
                        rdf_value_element = dc_title_element.find(
                            f"{{{rdf_uri}}}Description/{{{rdf_uri}}}value"
                        )
                        if (
                            rdf_value_element is not None
                            and rdf_value_element.text is not None
                        ):
                            result_entry["제목"] = rdf_value_element.text.strip()

                # 🆕 추가: 제목 번역 처리 (번역 설정 확인)
                if result_entry["제목"] != "없음":
                    original_title = result_entry["제목"]
                    if _should_auto_translate(app_instance):
                        # 번역 활성화 시 - 일본어 제목인 경우에만 번역 대상으로 설정
                        if original_title and any(
                            ord(char) >= 0x3040 for char in original_title
                        ):
                            # 즉시 번역하지 않고 원본 제목 저장 (일괄 번역에서 처리)
                            result_entry["제목_원문"] = original_title
                            result_entry["제목 번역"] = (
                                "번역 설정 OFF"  # 임시값, 후에 실제 번역으로 교체됨
                            )
                        else:
                            result_entry["제목 번역"] = "번역 불필요"
                    else:
                        # 번역 비활성화 시 - 원문 그대로 사용
                        result_entry["제목 번역"] = original_title
                else:
                    result_entry["제목 번역"] = "없음"

                # ❗ 수정: 저자 추출 (dcterms:creator -> foaf:Agent -> foaf:name)
                creators = dcndl_record.findall(f"{{{dcterms_uri}}}creator")
                author_names = []
                for creator_element in creators:
                    foaf_agent = creator_element.find(f"{{{foaf_uri}}}Agent")
                    if foaf_agent is not None:
                        foaf_name = foaf_agent.find(f"{{{foaf_uri}}}name")
                        if foaf_name is not None and foaf_name.text is not None:
                            # 쉼표로 분할하는 대신 전체 저자 이름을 직접 추가
                            author_names.append(foaf_name.text.strip())
                result_entry["저자"] = (
                    " | ".join(author_names) if author_names else "없음"
                )

                # ❗ 수정: 연도 추출 (dcterms:issued)
                issued_element = dcndl_record.find(f"{{{dcterms_uri}}}issued")
                if issued_element is not None and issued_element.text is not None:
                    result_entry["연도"] = extract_year(issued_element.text.strip())

                # ❗ 수정: NDL 상세 링크 및 NDL ID 추출 (GAS 버전 로직 포팅)
                primary_link_candidate = None  # ndlsearch.ndl.go.jp/books/
                secondary_link_candidate = None  # id.ndl.go.jp/bib/

                if inner_root:
                    bib_admin_resource = inner_root.find(
                        f"{{{dcndl_uri}}}BibAdminResource"
                    )
                    if bib_admin_resource is not None:
                        about_attr = bib_admin_resource.get(f"{{{rdf_uri}}}about")
                        if about_attr:
                            if "https://ndlsearch.ndl.go.jp/books/" in about_attr:
                                primary_link_candidate = about_attr
                            elif "http://id.ndl.go.jp/bib/" in about_attr:
                                secondary_link_candidate = about_attr

                    bib_resources = inner_root.findall(f"{{{dcndl_uri}}}BibResource")
                    for bib_res in bib_resources:
                        about_attr = bib_res.get(f"{{{rdf_uri}}}about")
                        if about_attr:
                            if "https://ndlsearch.ndl.go.jp/books/" in about_attr:
                                if not primary_link_candidate:
                                    primary_link_candidate = about_attr
                            elif "http://id.ndl.go.jp/bib/" in about_attr:
                                if not secondary_link_candidate:
                                    secondary_link_candidate = about_attr

                link = primary_link_candidate or secondary_link_candidate or "없음"
                ndl_id = "없음"

                if link != "없음":
                    if "http://id.ndl.go.jp/bib/" in link:
                        ndl_id = link.split("/")[-1]
                        if not link.endswith("#bib"):
                            link += "#bib"
                    elif "https://ndlsearch.ndl.go.jp/books/" in link:
                        match = re.search(r"I(\d+)$", link)
                        if match:
                            ndl_id = match.group(1)

                result_entry["상세 링크"] = link
                result_entry["NDL ID"] = ndl_id

                # ❗ 수정: ISBN/ISSN 추출 (dcterms:identifier)
                identifiers = dcndl_record.findall(f"{{{dcterms_uri}}}identifier")
                for id_element in identifiers:
                    type_attr = id_element.get(f"{{{xsi_uri}}}type")
                    data_type_attr = id_element.get(f"{{{rdf_uri}}}datatype")
                    id_value = (
                        id_element.text.strip() if id_element.text is not None else ""
                    )

                    if type_attr and ("ISBN" in type_attr or "ISSN" in type_attr):
                        # -------------------
                        # 하이픈 및 공백 제거 (LC 로직과 동일)
                        isbn_cleaned = re.sub(r"[\s\-]", "", id_value)
                        result_entry["ISBN"] = isbn_cleaned
                        # -------------------
                        break
                    elif data_type_attr and (
                        "ISBN" in data_type_attr or "ISSN" in data_type_attr
                    ):
                        # -------------------
                        # 하이픈 및 공백 제거 (LC 로직과 동일)
                        isbn_cleaned = re.sub(r"[\s\-]", "", id_value)
                        result_entry["ISBN"] = isbn_cleaned
                        # -------------------
                        break
                    elif id_value and (
                        re.match(
                            r"^(?:ISBN(?:-13)?:?|(?=97[89]))(?=.{13}$)([0-9]{3}-?){2}[0-9]{3}[0-9X]$",
                            id_value,
                            re.IGNORECASE,
                        )
                        or re.match(
                            r"^(?:ISBN(?:-10)?:?)(?=.{10}$)[0-9]{9}[0-9X]$",
                            id_value,
                            re.IGNORECASE,
                        )
                        or re.match(
                            r"^ISSN\s+\d{4}-\d{3}[\dX]$", id_value, re.IGNORECASE
                        )
                    ):
                        # -------------------
                        # 하이픈 및 공백 제거 (LC 로직과 동일)
                        isbn_cleaned = re.sub(r"[\s\-]", "", id_value)
                        result_entry["ISBN"] = isbn_cleaned
                        # -------------------
                        break

                # ❗ 수정: 출판사 추출 (dcterms:publisher -> foaf:Agent -> foaf:name)
                publisher_element = dcndl_record.find(f"{{{dcterms_uri}}}publisher")
                if publisher_element is not None:
                    foaf_agent = publisher_element.find(f"{{{foaf_uri}}}Agent")
                    if foaf_agent is not None:
                        foaf_name = foaf_agent.find(f"{{{foaf_uri}}}name")
                        if foaf_name is not None and foaf_name.text is not None:
                            result_entry["출판사"] = foaf_name.text.strip()

                # --- 주제어 추출 (번역은 일괄 처리) ---
                subjects = dcndl_record.findall(f"{{{dcterms_uri}}}subject")
                raw_subjects_for_record = []

                for subject_element in subjects:
                    raw_subject_text = ""
                    rdf_description = subject_element.find(f"{{{rdf_uri}}}Description")
                    if rdf_description is not None:
                        rdf_value = rdf_description.find(f"{{{rdf_uri}}}value")
                        if rdf_value is not None and rdf_value.text is not None:
                            raw_subject_text = rdf_value.text.strip()

                    if not raw_subject_text:
                        ndlsh_element = subject_element.find(f"{{{dcndl_uri}}}NDLSH")
                        if ndlsh_element is not None and ndlsh_element.text is not None:
                            raw_subject_text = ndlsh_element.text.strip()

                    if not raw_subject_text:
                        ndlc_element = subject_element.find(f"{{{dcndl_uri}}}NDLC")
                        if ndlc_element is not None and ndlc_element.text is not None:
                            raw_subject_text = ndlc_element.text.strip()

                    if not raw_subject_text:
                        ndc10_element = subject_element.find(f"{{{dcndl_uri}}}NDC10")
                        if ndc10_element is not None and ndc10_element.text is not None:
                            raw_subject_text = ndc10_element.text.strip()

                    if not raw_subject_text and subject_element.text is not None:
                        raw_subject_text = subject_element.text.strip()

                    if raw_subject_text:
                        raw_subject_text = re.sub(
                            r"典拠$", "", raw_subject_text
                        ).strip()
                        raw_subject_text = raw_subject_text.replace("--", " - ")
                        raw_subjects_for_record.append(raw_subject_text)

                result_entry["650 필드"] = raw_subjects_for_record
                result_entry["650 필드 (번역)"] = []
            else:
                if app_instance:
                    app_instance.log_message(
                        "경고: dcndlRecord가 null이어서 데이터 파싱을 건너뜀 (recordData 내부 XML에서 dcndl:BibResource 없음).",
                        level="WARNING",
                    )

            all_results.append(result_entry)
            if app_instance:
                progress = int(((i + 1) / len(records)) * 80)

        # 연도 기준으로 최신순 정렬 (클라이언트 측)
        all_results.sort(
            key=lambda x: int(x["연도"]) if x["연도"].isdigit() else 0,
            reverse=True,
        )
        if app_instance:
            app_instance.log_message("정보: NDL 검색 결과 정렬 완료.", level="INFO")

        # === 🚀🚀 비동기 고유 주제어 개별 번역 시스템! (품질 개선) ===
        # ===== 🆕 변수 선언을 조건문 밖으로 이동 =====
        all_unique_subjects = set()
        total_subjects_count = 0

        # 주제어 수집 (번역 여부와 관계없이 항상 수행)
        for item in all_results:
            raw_subjects = item.get("650 필드", [])
            total_subjects_count += len(raw_subjects)
            for subject in raw_subjects:
                if subject and subject.strip():
                    all_unique_subjects.add(subject.strip())

        # ===== 🆕 설정 확인 후 번역 실행 =====
        translation_map = {}

        if _should_auto_translate(app_instance) and all_unique_subjects:
            if app_instance:
                app_instance.log_message(
                    "🚀🚀 비동기 고유 주제어 개별 번역 시스템 시작! (번역 품질 향상)",
                    level="INFO",
                )
                app_instance.log_message(
                    f"📊 통계: 전체 주제어 {total_subjects_count}개 → 고유 주제어 {len(all_unique_subjects)}개",
                    level="INFO",
                )
                if total_subjects_count > len(all_unique_subjects):
                    app_instance.log_message(
                        f"⚡ 성능 개선: {total_subjects_count - len(all_unique_subjects)}번의 중복 번역 제거!",
                        level="INFO",
                    )

            # 2단계: 🚀🚀 고유 주제어 개별 비동기 번역 실행!
            # 비동기 처리를 위한 새 이벤트 루프 생성 및 설정 (현재 스레드가 아닐 수 있으므로)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # 개별 번역 작업을 위한 코루틴 함수 정의
            async def _perform_individual_translations():
                nonlocal translation_map  # 외부 translation_map을 사용
                # ThreadPoolExecutor를 사용하여 동기 함수를 비동기로 실행
                # max_workers는 동시에 실행될 스레드 수를 나타냅니다. 너무 높으면 API 제한에 걸릴 수 있습니다.
                # 🚀 성능 개선: 동시 작업 스레드 수를 15개로 늘려 번역 속도 향상 (DNB 방식 적용)
                num_workers = 15
                if app_instance:
                    app_instance.log_message(
                        f"🚀 정보: {num_workers}개의 스레드로 병렬 번역을 시작합니다.",
                        level="INFO",
                    )

                with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    tasks = []
                    unique_subjects_list = list(
                        all_unique_subjects
                    )  # 일관된 반복 순서를 위해 리스트로 변환
                    for i, subject_to_translate in enumerate(unique_subjects_list):
                        if app_instance and app_instance.stop_search_flag.is_set():
                            break  # 중단 요청 시 루프 종료

                        # ❗ 수정: translate_text에 db_manager 인스턴스 전달
                        task = loop.run_in_executor(
                            executor,
                            translate_text,
                            subject_to_translate,
                            custom_glossary_map,
                            db_manager,
                        )
                        tasks.append((subject_to_translate, task))

                        # 진행률 업데이트 (예: 5개마다)
                        if app_instance and (i + 1) % 5 == 0:
                            progress = 85 + int(
                                ((i + 1) / len(all_unique_subjects)) * 10
                            )
                            app_instance.root.after(
                                0, app_instance.update_progress, progress
                            )

                    # 제출된 모든 작업이 완료될 때까지 기다림
                    for original_subject, task in tasks:
                        try:
                            translated_in_hangul = (
                                await task
                            )  # translate_text에서 이미 한글 변환까지 완료됨
                            translation_map[original_subject] = translated_in_hangul
                        except Exception as e:
                            translation_map[original_subject] = (
                                f"{original_subject} (번역 오류)"
                            )
                            if app_instance:
                                app_instance.log_message(
                                    f'오류: 주제어 개별 번역 실패 ("{original_subject}"): {e}',
                                    level="ERROR",
                                )

                if app_instance:
                    app_instance.log_message(
                        f"✅ 고유 주제어 개별 번역 완료! {len(translation_map)}개 주제어 완료",
                        level="INFO",
                    )

            # _perform_individual_translations 코루틴 실행
            # 이벤트 루프가 이미 실행 중인 경우 (예: GUI 메인 루프), 스케줄링하여 실행
            if not loop.is_running():
                loop.run_until_complete(_perform_individual_translations())
            else:
                # GUI의 메인 스레드에서 비동기 작업을 실행하기 위해 별도의 스레드를 생성하여 루프를 실행
                # 이는 Tkinter와 같은 GUI 프레임워크의 메인 루프를 블로킹하지 않기 위함입니다.
                threading.Thread(
                    target=lambda: loop.run_until_complete(
                        _perform_individual_translations()
                    )
                ).start()

        elif all_unique_subjects and app_instance:
            # 번역 비활성화 시 원문을 그대로 사용
            app_instance.log_message(
                "정보: 해외 도서관 자동 번역이 비활성화되어 원문 주제어를 사용합니다.",
                level="INFO",
            )

        # 번역 결과 적용 (설정에 따라 완전히 분기 처리)
        if app_instance:
            app_instance.log_message("🔧 검색 결과 처리 중...", level="INFO")

        if _should_auto_translate(app_instance):
            # ===== 번역 활성화 시만 번역 로직 실행 =====
            # 제목 번역 맵 생성
            title_translation_map = {}
            all_unique_titles = set()
            for item in all_results:
                if item.get("제목_원문") and item["제목_원문"] != "없음":
                    all_unique_titles.add(item["제목_원문"])

            if all_unique_titles:
                with ThreadPoolExecutor(max_workers=15) as executor:
                    future_to_title = {
                        executor.submit(
                            translate_text, title, custom_glossary_map, db_manager
                        ): title
                        for title in all_unique_titles
                    }
                    for future in future_to_title:
                        title = future_to_title[future]
                        try:
                            title_translation_map[title] = future.result()
                        except Exception as exc:
                            title_translation_map[title] = f"{title} (번역 오류)"

            # 번역 활성화 시 결과 적용
            for item in all_results:
                if app_instance and app_instance.stop_search_flag.is_set():
                    break

                raw_subjects = item.get("650 필드", [])

                # 제목 번역 적용
                if item.get("제목_원문") and item["제목_원문"] in title_translation_map:
                    item["제목 번역"] = title_translation_map[item["제목_원문"]]
                elif item.get("제목_원문"):
                    item["제목 번역"] = item["제목_원문"]  # 번역 실패 시 원문 유지

                if "제목_원문" in item:
                    del item["제목_원문"]

                # 주제어 번역 적용
                translated_subjects_for_item = []
                seen_translated_subjects = set()

                for raw_subject_text in raw_subjects:
                    cleaned_subject = raw_subject_text.strip()
                    if cleaned_subject in translation_map:
                        translated_value = translation_map[cleaned_subject]
                        if translated_value not in seen_translated_subjects:
                            translated_subjects_for_item.append(translated_value)
                            seen_translated_subjects.add(translated_value)
                    else:
                        if raw_subject_text not in seen_translated_subjects:
                            translated_subjects_for_item.append(raw_subject_text)
                            seen_translated_subjects.add(raw_subject_text)

                item["650 필드 (번역)"] = translated_subjects_for_item

        else:
            # ===== 번역 비활성화 시 원문 그대로 사용 (translate_text 호출 안 함) =====
            for item in all_results:
                if app_instance and app_instance.stop_search_flag.is_set():
                    break

                raw_subjects = item.get("650 필드", [])

                # 주제어 원문 그대로 사용
                item["650 필드 (번역)"] = raw_subjects if raw_subjects else []

                # 제목도 원문 그대로 사용
                if item.get("제목_원문"):
                    item["제목 번역"] = item["제목_원문"]
                    del item["제목_원문"]

        # 🔔 루프 종료 후 1회만 출력
        if app_instance:
            if _should_auto_translate(app_instance):
                app_instance.log_message("🎉 NDL 검색 및 번역 처리 완료!", level="INFO")
            else:
                app_instance.log_message(
                    "🎉 NDL 검색 완료 (번역 비활성화)!", level="INFO"
                )

        return all_results

    # ❗ 최상위 try 블록에 대한 except 블록들 (들여쓰기 수정됨) ❗
    except requests.exceptions.RequestException as e:
        error_message = f"NDL Search API 요청 오류: {e}"
        if app_instance:
            app_instance.log_message(f"오류: {error_message}", level="ERROR")
            app_instance.show_messagebox(
                "NDL 서버 연결 오류",
                f"NDL 서버 접속이 불안정합니다. 잠시 후 다시 시도해주세요.\n\n오류: {e}",
                "error",
            )
        return []
    except ET.ParseError as e:
        error_message = f"NDL Search API 응답 파싱 오류: {e}"
        if app_instance:
            app_instance.log_message(f"오류: XML 파싱 오류: {e}", level="ERROR")
            # response.text가 없을 수 있으므로 조건부 접근
            response_text_preview = (
                response_body[:500]
                if "response_body" in locals() and response_body
                else "N/A"
            )
            app_instance.log_message(
                f"오류 발생 XML (일부): {response_text_preview}...", level="ERROR"
            )
            app_instance.show_messagebox(
                "NDL 서버 응답 형식 오류",
                f"NDL 서버에서 비정상적인 응답을 받았습니다. 잠시 후 다시 시도해주세요.\n\n오류: {e}",
                "error",
            )
        return []
    except Exception as e:
        error_message = f"NDL 검색 중 예기치 않은 오류 발생: {e}"
        if app_instance:
            app_instance.log_message(f"오류: 예기치 않은 오류: {e}", level="ERROR")
            app_instance.show_messagebox(
                "NDL 검색 오류",
                f"NDL 검색 중 예기치 않은 오류가 발생했습니다. 잠시 후 다시 시도해주세요.\n\n오류: {e}",
                "error",
            )
        return []
    finally:
        # 이 finally 블록은 try 또는 except 실행 후 항상 실행됩니다.
        # 최종 정리 작업이나 진행률을 100%로 보장하는 데 유용합니다.
        if app_instance:
            app_instance.log_message("정보: NDL 검색 기능 최종 마무리.", level="INFO")
