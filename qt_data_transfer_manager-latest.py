# -*- coding: utf-8 -*-
# 파일명: qt_data_transfer_manager.py
# 설명: 탭 간 데이터 전송을 관리하는 중앙 모듈

import re
from PySide6.QtCore import Qt


def send_marc_data_to_tabs(app_instance, f_fields, raw_marc_text):
    """
    MARC 추출 데이터를 분석하여 관련 탭으로 자동 전송합니다.
    qt_TabView_MARC_Extractor.py의 _on_extraction_finished에서 호출됩니다.
    """
    if not app_instance or not f_fields:
        return

    # 1. 저자 성명 및 원서명 자동 전송
    # -------------------
    # ✅ [핵심 수정] F8 -> F7 -> 245$a 순서로 Fallback 로직 추가
    author_surname = f_fields.get("F2_Author_SurnameOrCorporate")
    original_title = f_fields.get("F8_OriginalTitle_WithoutArticle") or f_fields.get(
        "F7_OriginalTitle_WithArticle"
    )

    title_to_send = None
    if original_title:
        # F8 또는 F7이 존재하면 (원서)
        title_to_send = original_title
    else:
        # F8, F7이 모두 없으면 (국내서로 간주), 245 $a 필드 파싱
        f4_field = f_fields.get("F4_245_Unprocessed", "")
        if f4_field:
            # $a 서브필드 내용 추출 (다음 서브필드($) 또는 라인 끝까지)
            match = re.search(r"\\$a(.*?)(?:\\$|$)", f4_field)
            if match:
                title_245a = match.group(1).strip()
                # 괄호 안 내용 제거
                title_to_send = re.sub(r"\(.*?\)", "", title_245a).strip()

    if author_surname and title_to_send:
        target_tabs = ["Global 통합검색", "NDL + CiNii 검색", "Western 검색"]
        _transfer_to_tabs(
            app_instance,
            target_tabs,
            author=author_surname,
            title=title_to_send,
            switch_priority=False,  # 탭 전환 안 함
        )

    # 2. 번역자 성명 자동 전송
    # 조건: 041, 246 필드 존재 + 한글 저자명을 가진 700 필드 존재
    # 이 로직은 f_fields만으로는 부족하며, raw_marc_text 분석이 필요합니다.
    if "=041" in raw_marc_text and "=246" in raw_marc_text and "=700" in raw_marc_text:
        # 700 필드에서 한글 이름(첫번째) 추출
        translator_match = re.search(r"=700.*?\\$a([가-힣]+)", raw_marc_text)
        if translator_match:
            translator_name = translator_match.group(1)
            _transfer_to_tabs(
                app_instance,
                ["저자전거 검색"],
                author=translator_name,
                switch_priority=False,
            )

    # 3. ISBN 자동 전송
    isbn = f_fields.get("F1_ISBN")
    if isbn:
        # -------------------
        # ✅ [핵심 수정] NLK 탭에만 switch_priority=True를 부여하여 탭 전환 우선권을 줌
        _transfer_to_tabs(
            app_instance,
            ["NLK 검색"],
            isbn=isbn,
            switch_priority=True,  # NLK 탭으로 전환 시도
        )
        # 다른 탭들은 백그라운드에서 검색만 수행
        _transfer_to_tabs(
            app_instance,
            ["AI 피드", "납본 ID 검색"],
            isbn=isbn,
            switch_priority=False,  # 탭 전환 안 함
        )
        # -------------------

    # 4. DDC 자동 전송
    # MARC 082 $a 필드에서 추출된 F11_DDC 값을 Dewey 탭으로 전송
    ddc_number = f_fields.get("F11_DDC")
    if ddc_number:
        _transfer_to_tabs(app_instance, ["Dewey 분류 검색"], ddc=ddc_number)


def handle_ai_feed_to_gemini(ai_feed_tab):
    """
    AI 피드 탭의 검색 결과를 분석하여 Gemini 탭으로 전송합니다.
    ISBN 검색 완료 후 qt_TabView_AIFeed.py에서 호출됩니다.
    """
    app_instance = ai_feed_tab.app_instance
    model = ai_feed_tab.table_model

    # 1. 데이터 소스별(Naver, Yes24, Kyobo) '분류 정보 취합' 내용 수집
    source_map = {
        "Naver": "",
        "Yes24": "",
        "Kyobo Book": "",
    }

    col_count = model.columnCount()
    source_col_idx = -1
    compile_col_idx = -1

    # 컬럼 인덱스 찾기
    for i in range(col_count):
        header = model.headerData(i, Qt.Horizontal)
        if header == "검색소스":
            source_col_idx = i
        elif header == "분류 정보 취합":
            compile_col_idx = i

    if source_col_idx == -1 or compile_col_idx == -1:
        app_instance.log_message(
            "오류: '검색소스' 또는 '분류 정보 취합' 컬럼을 찾을 수 없습니다.", "ERROR"
        )
        return

    for row in range(model.rowCount()):
        source_index = model.index(row, source_col_idx)
        compile_index = model.index(row, compile_col_idx)

        source = model.data(source_index, Qt.DisplayRole)
        content = model.data(compile_index, Qt.DisplayRole)

        if source and content:
            if source in source_map:
                source_map[source] = content

    # 2. 데이터 조합 (Yes24, Kyobo 비교 후 Naver 추가)
    # 저자, 목차, 서평 분량이 가장 긴 조합을 선택
    yes24_content = source_map.get("Yes24", "")
    kyobo_content = source_map.get("Kyobo Book", "")
    naver_content = source_map.get("Naver", "")

    # 단순 길이 비교로 분량이 더 많은 쪽을 선택
    chosen_content = (
        yes24_content if len(yes24_content) > len(kyobo_content) else kyobo_content
    )

    # 네이버 책 소개를 맨 위에 추가
    final_text = f"[네이버 책 소개]\n{naver_content}\n\n[종합 정보]\n{chosen_content}"

    # 3. Gemini 탭으로 데이터 전송
    # ✅ [수정] 자동 검색을 위한 start_search_now=True 플래그 추가
    _transfer_to_tabs(
        app_instance,
        ["Gemini DDC 분류"],
        text=final_text,
        switch_priority=True,
        start_search_now=True,
    )


def _transfer_to_tabs(app_instance, tab_names, **data):
    """
    지정된 탭 목록에 데이터를 전송하는 내부 헬퍼 함수.
    """
    if not hasattr(app_instance, "main_window"):
        return

    main_window = app_instance.main_window

    for name in tab_names:
        # main_window에 get_tab_by_name 헬퍼 메서드 추가 필요
        if hasattr(main_window, "get_tab_by_name"):
            tab = main_window.get_tab_by_name(name)
            if tab and hasattr(tab, "receive_data"):
                try:
                    tab.receive_data(**data)
                    app_instance.log_message(
                        f"정보: '{name}' 탭으로 데이터를 전송했습니다: {list(data.keys())}"
                    )
                except Exception as e:
                    app_instance.log_message(
                        f"오류: '{name}' 탭으로 데이터 전송 중 오류 발생: {e}", "ERROR"
                    )
            else:
                app_instance.log_message(
                    f"경고: '{name}' 탭을 찾을 수 없거나 receive_data 메서드가 없습니다.",
                    "WARNING",
                )
