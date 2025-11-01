# -*- coding: utf-8 -*-
# 파일명: qt_context_menus.py
# 설명: PySide6용 컨텍스트 메뉴 시스템 (QTableWidget 완전 대응)
# 버전: 2.1.0 - QTableWidget -> QTableView
# 생성일: 2025-09-25


from __future__ import annotations
import re
import threading
from PySide6.QtWidgets import (
    QMenu,
    QLineEdit,
    QTextEdit,
    QDialog,
    QTextBrowser,
    QPushButton,
    QTableView,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QApplication,
    QMessageBox,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QAction, QGuiApplication
from PySide6.QtCore import QThread, Signal
from qt_api_clients import translate_text
from functools import partial


# 프로젝트 모듈 import
from qt_copy_feedback import copy_to_clipboard_with_feedback, show_copy_feedback
from text_utils import open_google_translate, open_dictionary, open_naver_dictionary
from qt_utils import (
    apply_dark_title_bar,
    enable_modal_close_on_outside_click,
    linkify_text,
)


from typing import Protocol, runtime_checkable, Any, Callable


@runtime_checkable
class _DeweyOwner(Protocol):
    """
    Dewey 관련 스레드(DeweySearchThread, DeweyRangeSearchThread, DeweyHundredsSearchThread 등)가
    상호작용하는 UI 탭(QtDeweySearchTab)의 속성과 메서드를 명시적으로 정의한 Protocol 클래스입니다.

    이 Protocol을 통해 Pylance는 parent()/ui_owner의 정적 타입을 인식하게 되어,
    'QObject에는 app_instance가 없습니다' 같은 경고를 방지합니다.

    실제 QtDeweySearchTab 클래스는 QWidget 기반이지만,
    구조적 타이핑(Structural Typing)에 의해 이 Protocol을 자동으로 만족하게 됩니다.
    """

    # ---- 핵심 참조 속성 ----
    app_instance: Any  # MainApplication 인스턴스 (로그, DB, 번역기 등 접근용)
    dewey_client: Any  # WebDewey API 클라이언트
    dewey_context_tree: Any  # QTreeView (DDC 계층 트리)
    ksh_table: Any  # QTableView (KSH 결과 테이블)
    dewey_detail_text: Any  # QTextEdit (세부 내용)
    dewey_preview_text: Any  # QTextEdit (프리뷰)
    dewey_ddc_entry: Any  # QLineEdit (DDC 입력창)
    dewey_ksh_search_entry: Any  # QLineEdit (KSH 검색창)
    dewey_progress_bar: Any  # QProgressBar
    dewey_progress_label: Any  # QLabel
    log_text_edit: Any  # QTextEdit (로그 창)
    # ---- 기타 상태 플래그 ----
    is_searching: bool
    _is_cancelled: bool


def is_url_text(text):
    """텍스트가 URL인지 확인"""
    if not text or len(text) < 4:
        return False

    url_patterns = [
        r"^https?://",
        r"^www\.",
        r"\.com\b",
        r"\.org\b",
        r"\.net\b",
        r"\.edu\b",
        r"\.gov\b",
        r"\.co\.kr\b",
        r"\.kr\b",
    ]

    text_lower = text.lower().strip()
    return any(re.search(pattern, text_lower) for pattern in url_patterns)


def show_text_info(text, app_instance):
    """텍스트 정보 표시 (문자수, 바이트수 등)"""
    try:
        char_count = len(text)
        byte_count = len(text.encode("utf-8"))
        word_count = len(text.split())
        line_count = text.count("\n") + 1

        info_text = f"""텍스트 정보:
- 문자 수: {char_count:,}
- 바이트 수: {byte_count:,}
- 단어 수: {word_count:,}
- 줄 수: {line_count:,}

미리보기:
{text[:200]}{'...' if len(text) > 200 else ''}"""

        show_info_dialog("텍스트 정보", info_text, app_instance)

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 텍스트 정보 표시 실패: {e}", "ERROR")


def show_info_dialog(title, content, app_instance):
    """정보 대화상자 표시"""
    try:
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextBrowser
        from PySide6.QtCore import QSize, QRect  # QRect 추가
        from ui_constants import UI_CONSTANTS

        dialog = QDialog()
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(400, 300)

        # ✅ [추가] 외부 클릭 시 닫기 기능 적용
        enable_modal_close_on_outside_click(dialog)
        apply_dark_title_bar(dialog)

        layout = QVBoxLayout(dialog)

        # -------------------
        # QDialog를 먼저 생성해야 sizeHint가 정상 작동하므로 순서 유지

        text_browser = QTextBrowser()
        text_browser.setReadOnly(True)

        # 링크 활성화 및 스타일 적용
        # UI_CONSTANTS가 정의되어 있지 않은 환경을 고려하여 기본값 설정
        try:
            link_color = UI_CONSTANTS.ACCENT_BLUE
        except NameError:
            link_color = "#0078D4"  # Windows Accent Blue

        text_browser.setStyleSheet(
            f"a {{ color: {link_color}; text-decoration: none; }}"
        )
        text_browser.setOpenExternalLinks(True)

        # 내용을 HTML로 변환하여 설정
        linked_content = linkify_text(content).replace("\n", "<br>")
        text_browser.setHtml(linked_content)
        layout.addWidget(text_browser)

        close_button = QPushButton("닫기")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        # ----------------------------------------
        # ✅ [수정] 다이얼로그를 부모 앱 중앙에 위치시키기
        # 'isWidgetType' 오류 해결을 위해, 'geometry' 속성을 가지고 있는지 확인하는 방식으로 변경합니다.
        # 또한, exec() 전에 move를 호출하기 위해 setMinimumSize() 이후에 위치 계산을 시도합니다.

        parent_widget = None
        # app_instance 자체가 Qt 위젯일 경우
        if hasattr(app_instance, "geometry") and callable(app_instance.geometry):
            parent_widget = app_instance
        # app_instance가 메인 윈도우 속성을 가지고 있을 경우 (예: IntegratedSearchApp.main_window)
        elif (
            hasattr(app_instance, "main_window")
            and hasattr(app_instance.main_window, "geometry")
            and callable(app_instance.main_window.geometry)
        ):
            parent_widget = app_instance.main_window

        if parent_widget:
            # layout.addWidget(close_button)까지 완료 후 다이얼로그의 최종 크기를 확정합니다.
            dialog.adjustSize()

            parent_rect = parent_widget.geometry()
            dialog_size = dialog.size()  # adjustSize() 호출 후 실제 크기 사용

            # 다이얼로그의 좌측 상단 x, y 좌표 계산
            x = parent_rect.x() + (parent_rect.width() - dialog_size.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - dialog_size.height()) // 2

            # 계산된 위치로 이동
            dialog.move(x, y)
        # ----------------------------------------

        dialog.exec()

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 대화상자 표시 실패: {e}", "ERROR")


# === 외부 서비스 연동 ===


def open_url_safely(url, app_instance):
    """URL을 안전하게 브라우저에서 열기"""
    try:
        # URL 정규화
        if url and not url.startswith(("http://", "https://")):
            if url.startswith("www."):
                url = "https://" + url
            else:
                url = "https://" + url

        # 별도 스레드에서 브라우저 열기 (GUI 블로킹 방지)
        def _open_browser():
            try:
                QDesktopServices.openUrl(QUrl(url))
            except Exception as browser_error:
                if hasattr(app_instance, "log_message"):
                    app_instance.log_message(
                        f"❌ 브라우저 열기 실패: {browser_error}", "ERROR"
                    )

        browser_thread = threading.Thread(target=_open_browser, daemon=True)
        browser_thread.start()

        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"🌐 링크 열림: {url}", "INFO")
    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 링크 열기 실패: {e}", "ERROR")


# === 컨텍스트 메뉴 구현 ===
def show_qtableview_context_menu(table_view, row, column, pos, app_instance):
    """✅ [새로 추가] QTableView용 컨텍스트 메뉴 - 모델/뷰 아키텍처 호환!"""

    # 모델에서 데이터 가져오기
    model = table_view.model()
    if not model:
        return

    # 셀 데이터 및 메타정보
    index = model.index(row, column)
    item = model.itemFromIndex(index) if hasattr(model, "itemFromIndex") else None
    cell_value = (
        item.text() if item else model.data(index, Qt.ItemDataRole.DisplayRole) or ""
    )

    # 컬럼 헤더 정보
    column_name = (
        model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        or f"컬럼 {column}"
    )

    # 선택 정보
    selection_model = table_view.selectionModel()
    selected_indexes = selection_model.selectedIndexes() if selection_model else []
    has_selection = len(selected_indexes) > 0

    # 메뉴 생성
    menu = QMenu(table_view)
    menu.setTitle(f"행 {row+1}, {column_name}")

    # === 기본 복사 기능 ===

    copy_cell_action = QAction(f"📋 셀 값 복사: '{cell_value[:20]}...'", menu)
    copy_cell_action.triggered.connect(
        lambda: copy_to_clipboard_with_feedback(cell_value, app_instance)
    )
    menu.addAction(copy_cell_action)

    copy_row_action = QAction(f"📄 행 {row+1} 전체 복사", menu)
    copy_row_action.triggered.connect(
        lambda: copy_tableview_row_data(table_view, row, app_instance)
    )
    menu.addAction(copy_row_action)

    if has_selection:
        copy_selection_action = QAction(
            f"📑 선택 영역 복사 ({len(selected_indexes)}개 셀)", menu
        )
        copy_selection_action.triggered.connect(
            lambda: copy_tableview_selection(table_view, app_instance)
        )
        menu.addAction(copy_selection_action)

    # === 고급 복사 기능 ===

    menu.addSeparator()

    copy_markdown_action = QAction("📝 선택 영역 → 마크다운 테이블", menu)
    copy_markdown_action.triggered.connect(
        lambda: copy_tableview_as_markdown(table_view, app_instance)
    )
    copy_markdown_action.setEnabled(has_selection)
    menu.addAction(copy_markdown_action)

    copy_csv_action = QAction("📊 선택 영역 → CSV 형식", menu)
    copy_csv_action.triggered.connect(
        lambda: copy_tableview_as_csv(table_view, app_instance)
    )
    copy_csv_action.setEnabled(has_selection)
    menu.addAction(copy_csv_action)

    # === 링크 처리 ===

    if is_url_text(cell_value):
        menu.addSeparator()
        open_link_action = QAction(f"🌐 링크 열기: {cell_value[:30]}...", menu)
        open_link_action.triggered.connect(
            lambda: open_url_safely(cell_value, app_instance)
        )
        menu.addAction(open_link_action)

    # === 테이블 조작 ===

    menu.addSeparator()

    # 컬럼별 정렬
    sort_asc_action = QAction(f"↑ '{column_name}' 오름차순 정렬", menu)
    sort_asc_action.triggered.connect(
        lambda: table_view.sortByColumn(column, Qt.AscendingOrder)
    )
    menu.addAction(sort_asc_action)

    sort_desc_action = QAction(f"↓ '{column_name}' 내림차순 정렬", menu)
    sort_desc_action.triggered.connect(
        lambda: table_view.sortByColumn(column, Qt.DescendingOrder)
    )
    menu.addAction(sort_desc_action)

    # 컬럼 숨기기/표시
    hide_column_action = QAction(f"👁️‍🗨️ '{column_name}' 컬럼 숨기기", menu)
    hide_column_action.triggered.connect(
        lambda: table_view.setColumnHidden(column, True)
    )
    menu.addAction(hide_column_action)

    # 모든 컬럼 표시
    show_all_action = QAction("👁️ 모든 컬럼 표시", menu)
    show_all_action.triggered.connect(lambda: show_all_tableview_columns(table_view))
    menu.addAction(show_all_action)

    # === 필터 기능 ===

    menu.addSeparator()

    filter_action = QAction(f"🔍 '{column_name}' 값으로 필터", menu)
    filter_action.triggered.connect(
        lambda: filter_tableview_by_value(table_view, column, cell_value, app_instance)
    )
    menu.addAction(filter_action)

    clear_filter_action = QAction("🔄 모든 필터 지우기", menu)
    clear_filter_action.triggered.connect(
        lambda: clear_tableview_filter(table_view, app_instance)
    )
    menu.addAction(clear_filter_action)

    menu.addSeparator()
    # -------------------
    # ✅ [핵심 추가] '셀 상세 정보 보기' 메뉴 항목을 추가합니다.
    # 이전에 포팅한 show_cell_detail_dialog 함수를 호출합니다.
    show_cell_detail_action = QAction(f"📋 '{column_name}' 셀 상세 정보", menu)
    show_cell_detail_action.triggered.connect(
        lambda: show_cell_detail_dialog(cell_value, column_name, app_instance)
    )
    menu.addAction(show_cell_detail_action)
    # -------------------

    # 기존 '행 전체 정보' 메뉴
    show_row_details_action = QAction(f"📊 행 {row+1} 전체 정보 보기", menu)
    show_row_details_action.triggered.connect(
        lambda: show_tableview_row_details(table_view, row, app_instance)
    )
    menu.addAction(show_row_details_action)

    menu.addSeparator()
    info_action = QAction("📏 셀 문자수/바이트", menu)  # 이름 명확화
    info_action.triggered.connect(lambda: show_text_info(cell_value, app_instance))
    menu.addAction(info_action)

    # === 선택 영역 고급 기능 ===

    if has_selection and len(selected_indexes) > 1:
        menu.addSeparator()

        selection_info_action = QAction(
            f"📊 선택 영역 통계 ({len(selected_indexes)}개 셀)", menu
        )
        selection_info_action.triggered.connect(
            lambda: show_tableview_selection_stats(table_view, app_instance)
        )
        menu.addAction(selection_info_action)

    # 텍스트 관련 기능 (셀 값이 있을 때)
    if cell_value.strip():
        menu.addSeparator()

        # -------------------
        # [추가] 인앱 번역 기능
        in_app_translate_action = QAction("📲 인앱 번역 (자동→한)", menu)
        in_app_translate_action.triggered.connect(
            lambda: perform_in_app_translation(cell_value, "ko", app_instance)
        )
        menu.addAction(in_app_translate_action)
        # -------------------
        # 번역 기능
        # [핵심] 삭제된 함수 대신 text_utils의 open_google_translate 함수를 호출하도록 수정
        google_en_ko_action = QAction("🌐 구글 번역 (자동→한)", menu)
        google_en_ko_action.triggered.connect(
            lambda: open_google_translate(
                cell_value, app_instance, source_lang="auto", target_lang="ko"
            )
        )
        menu.addAction(google_en_ko_action)

        google_ko_en_action = QAction("🌐 구글 번역 (자동→영)", menu)
        google_ko_en_action.triggered.connect(
            lambda: open_google_translate(
                cell_value, app_instance, source_lang="auto", target_lang="en"
            )
        )
        menu.addAction(google_ko_en_action)

        dictionary_action = QAction("📖 롱맨 영영사전", menu)
        dictionary_action.triggered.connect(
            lambda: open_dictionary(cell_value, app_instance)
        )
        menu.addAction(dictionary_action)

        naver_dict_action = QAction("📚 네이버 사전", menu)
        naver_dict_action.triggered.connect(
            lambda: open_naver_dictionary(cell_value, app_instance)
        )
        menu.addAction(naver_dict_action)

    # -------------------
    # ✅ [핵심 추가] F9 청구기호 특별 처리 로직 (CTk 버전 이식)
    try:
        model = table_view.model()
        if model:
            # 1. 첫 번째 컬럼('필드')과 세 번째 컬럼('추출결과') 데이터 가져오기
            field_id_index = model.index(row, 0)
            result_index = model.index(row, 2)

            field_id = model.data(field_id_index)
            call_number = model.data(result_index)

            # 2. CTk 버전과 동일한 조건으로 F9 행인지, 유효한 청구기호인지 확인
            if (
                field_id == "F9"
                and call_number
                and call_number.strip()
                and call_number != "(청구기호 추출 실패)"
            ):

                menu.addSeparator()
                base_url = (
                    "https://las.pusan.ac.kr/#/cat/biblio/management?q=ALL%3DK%7CA%7C"
                )

                # 3. 각기 다른 길이의 청구기호에 대한 검색 액션을 생성하고 메뉴에 추가
                action_full = QAction(f"🔗 청구기호 검색 (전체): {call_number}", menu)
                action_full.triggered.connect(
                    partial(open_url_safely, base_url + call_number, app_instance)
                )
                menu.addAction(action_full)

                if len(call_number) > 1:
                    shortened_cn = call_number[:-1]
                    action_short1 = QAction(
                        f"🔗 청구기호 검색 (-1자리): {shortened_cn}", menu
                    )
                    action_short1.triggered.connect(
                        partial(open_url_safely, base_url + shortened_cn, app_instance)
                    )
                    menu.addAction(action_short1)

                if len(call_number) > 2:
                    shortest_cn = call_number[:-2]
                    action_short2 = QAction(
                        f"🔗 청구기호 검색 (-2자리): {shortest_cn}", menu
                    )
                    action_short2.triggered.connect(
                        partial(open_url_safely, base_url + shortest_cn, app_instance)
                    )
                    menu.addAction(action_short2)
    except Exception as e:
        if app_instance:
            app_instance.log_message(
                f"WARN: F9 컨텍스트 메뉴 생성 중 오류: {e}", "WARNING"
            )
    # -------------------
    # 메뉴 표시
    menu.exec(table_view.mapToGlobal(pos))


def show_qlineedit_context_menu(widget, pos, app_instance):
    """QLineEdit용 컨텍스트 메뉴"""
    menu = QMenu(widget)

    # 현재 텍스트와 선택 상태 확인
    current_text = widget.text()
    has_selection = widget.hasSelectedText()
    selected_text = widget.selectedText() if has_selection else ""

    # 기본 편집 기능
    copy_action = QAction("📋 복사", menu)
    copy_action.setEnabled(has_selection)
    copy_action.triggered.connect(
        lambda: copy_to_clipboard_with_feedback(
            selected_text, app_instance, widget
        )  # 👈 parent_widget 인자 추가
    )
    menu.addAction(copy_action)

    paste_action = QAction("📌 붙여넣기", menu)
    paste_action.triggered.connect(lambda: widget.paste())
    menu.addAction(paste_action)

    cut_action = QAction("✂️ 잘라내기", menu)
    cut_action.setEnabled(has_selection)
    cut_action.triggered.connect(lambda: widget.cut())
    menu.addAction(cut_action)

    menu.addSeparator()

    select_all_action = QAction("📄 모두 선택", menu)
    select_all_action.setEnabled(bool(current_text))
    select_all_action.triggered.connect(lambda: widget.selectAll())
    menu.addAction(select_all_action)

    clear_action = QAction("🧹 모두 지우기", menu)
    clear_action.setEnabled(bool(current_text))
    clear_action.triggered.connect(lambda: widget.clear())
    menu.addAction(clear_action)

    # 유틸리티 기능
    if current_text.strip():
        menu.addSeparator()

        info_action = QAction("📊 문자수/바이트 정보", menu)
        info_action.triggered.connect(
            lambda: show_text_info(current_text, app_instance)
        )
        menu.addAction(info_action)

        # 번역/사전 기능 추가
        detail_action = QAction("🔍 값 상세 보기", menu)
        detail_action.triggered.connect(
            lambda: show_cell_detail_dialog(current_text, "입력 텍스트", app_instance)
        )
        menu.addAction(detail_action)

        # 번역 기능 (텍스트가 있을 때만)
        if len(current_text.strip()) > 0:
            menu.addSeparator()

            # [핵심] 삭제된 함수 대신 text_utils의 open_google_translate 함수를 호출하도록 수정
            google_en_ko_action = QAction("🌐 구글 번역 (자동→한)", menu)
            google_en_ko_action.triggered.connect(
                lambda: open_google_translate(
                    selected_text, app_instance, source_lang="auto", target_lang="ko"
                )
            )
            menu.addAction(google_en_ko_action)

            google_ko_en_action = QAction("🌐 구글 번역 (자동→영)", menu)
            google_ko_en_action.triggered.connect(
                lambda: open_google_translate(
                    selected_text, app_instance, source_lang="auto", target_lang="en"
                )
            )
            menu.addAction(google_ko_en_action)

            dictionary_action = QAction("📖 롱맨 영영사전", menu)
            dictionary_action.triggered.connect(
                lambda: open_dictionary(current_text, app_instance)
            )
            menu.addAction(dictionary_action)

            naver_dict_action = QAction("📚 네이버 사전", menu)
            naver_dict_action.triggered.connect(
                lambda: open_naver_dictionary(current_text, app_instance)
            )
            menu.addAction(naver_dict_action)

            if is_url_text(current_text):
                open_link_action = QAction("🌐 링크 열기", menu)
                open_link_action.triggered.connect(
                    lambda: open_url_safely(current_text, app_instance)
                )
                menu.addAction(open_link_action)

    # 메뉴 표시
    menu.exec(widget.mapToGlobal(pos))


def show_qtextedit_context_menu(widget, pos, app_instance):
    """QTextEdit용 컨텍스트 메뉴"""
    menu = QMenu(widget)

    # 현재 텍스트와 선택 상태 확인
    cursor = widget.textCursor()
    has_selection = cursor.hasSelection()
    selected_text = cursor.selectedText() if has_selection else ""
    full_text = widget.toPlainText()

    # 기본 편집 기능
    copy_action = QAction("📋 복사", menu)
    copy_action.setEnabled(has_selection)
    copy_action.triggered.connect(
        lambda: copy_to_clipboard_with_feedback(
            selected_text, app_instance, widget
        )  # 👈 parent_widget 인자 추가
    )
    menu.addAction(copy_action)

    paste_action = QAction("📌 붙여넣기", menu)
    paste_action.triggered.connect(lambda: widget.paste())
    menu.addAction(paste_action)

    cut_action = QAction("✂️ 잘라내기", menu)
    cut_action.setEnabled(has_selection)
    cut_action.triggered.connect(lambda: widget.cut())
    menu.addAction(cut_action)

    menu.addSeparator()

    select_all_action = QAction("📄 모두 선택", menu)
    select_all_action.setEnabled(bool(full_text))
    select_all_action.triggered.connect(lambda: widget.selectAll())
    menu.addAction(select_all_action)

    clear_action = QAction("🧹 모두 지우기", menu)
    clear_action.setEnabled(bool(full_text))
    clear_action.triggered.connect(lambda: widget.clear())
    menu.addAction(clear_action)

    # 고급 기능
    if full_text.strip():
        menu.addSeparator()

        info_action = QAction("📊 문서 통계", menu)
        info_action.triggered.connect(lambda: show_text_info(full_text, app_instance))
        menu.addAction(info_action)

        # 선택된 텍스트가 있으면 선택된 텍스트에 대한 기능 제공
        if has_selection and selected_text.strip():
            menu.addSeparator()

            selected_info_action = QAction("🔍 선택 영역 상세보기", menu)
            selected_info_action.triggered.connect(
                lambda: show_cell_detail_dialog(
                    selected_text, "선택된 텍스트", app_instance
                )
            )
            menu.addAction(selected_info_action)

            # 번역 기능
            # -------------------
            # [추가] 인앱 번역 기능
            in_app_translate_action = QAction("📲 인앱 번역 (자동→한)", menu)
            in_app_translate_action.triggered.connect(
                lambda: perform_in_app_translation(selected_text, "ko", app_instance)
            )
            menu.addAction(in_app_translate_action)
            # -------------------

            google_en_ko_action = QAction("🌐 구글 번역 (영→한)", menu)
            google_en_ko_action.triggered.connect(
                lambda: open_google_translate(selected_text, app_instance)
            )
            menu.addAction(google_en_ko_action)

            google_ko_en_action = QAction("🌐 구글 번역 (한→영)", menu)
            google_ko_en_action.triggered.connect(
                lambda: open_google_translate(selected_text, app_instance)
            )
            menu.addAction(google_ko_en_action)

            dictionary_action = QAction("📖 롱맨 영영사전", menu)
            dictionary_action.triggered.connect(
                lambda: open_dictionary(selected_text, app_instance)
            )
            menu.addAction(dictionary_action)

            naver_dict_action = QAction("📚 네이버 사전", menu)
            naver_dict_action.triggered.connect(
                lambda: open_naver_dictionary(selected_text, app_instance)
            )
            menu.addAction(naver_dict_action)

            if is_url_text(selected_text):
                open_selected_link = QAction("🌐 선택 링크 열기", menu)
                open_selected_link.triggered.connect(
                    lambda: open_url_safely(selected_text, app_instance)
                )
                menu.addAction(open_selected_link)

    # 메뉴 표시
    menu.exec(widget.mapToGlobal(pos))


def show_textbrowser_context_menu(tb: "QTextBrowser", viewport_pos, app_instance=None):
    from ui_constants import UI_CONSTANTS as U

    print("[DEBUG] 📋 show_textbrowser_context_menu() 호출됨")
    print(f"[DEBUG] viewport_pos: {viewport_pos}")

    menu = QMenu(tb.viewport())  # ✅ viewport 기준으로 메뉴 생성

    # ✅ 스타일 강제 지정 (테마에 맞게 메뉴 항목이 보이도록)
    menu.setStyleSheet(
        f"""
        QMenu::item {{
            color: {U.TEXT_DEFAULT};
            padding: 6px 12px;
        }}
        QMenu::item:disabled {{
            color: {U.TEXT_SUBDUED};
        }}
    """
    )

    has_sel = bool(tb.textCursor().hasSelection())
    selected_text = tb.textCursor().selectedText()
    anchor = tb.anchorAt(viewport_pos)
    global_pos = tb.viewport().mapToGlobal(viewport_pos)

    print(f"[DEBUG] 선택 텍스트 있음: {has_sel} → '{selected_text}'")
    print(f"[DEBUG] anchor: {anchor}")
    print(f"[DEBUG] global_pos: {global_pos}")

    act_copy = menu.addAction("📋 Copy")
    act_copy.setEnabled(has_sel)

    if anchor:
        menu.addSeparator()
        act_open = menu.addAction("🔗 Open Link")
        act_copy_link = menu.addAction("🔗 Copy Link Location")

    menu.addSeparator()
    act_nlk_search = menu.addAction("🔍 NLK 탭에서 제목 검색")  # ✅ 항상 추가
    act_author_check_search = menu.addAction(
        "🔍 저자 확인 탭에서 저작물 일괄 검색"
    )  # ✅ 저자 확인 탭 검색 추가

    menu.addSeparator()
    act_select_all = menu.addAction("🧲 Select All")

    print(f"[DEBUG] 메뉴 항목 수: {len(menu.actions())}")

    chosen = menu.exec(global_pos)
    print(f"[DEBUG] 선택된 메뉴: {chosen}")
    if not chosen:
        print("[DEBUG] 메뉴 선택 없음 (사용자 취소)")
        return

    if chosen is act_copy:
        print("[DEBUG] 📋 Copy 선택됨")
        tb.copy()
        try:
            from qt_copy_feedback import show_copy_feedback

            show_copy_feedback(app_instance, "복사됨")
        except Exception as e:
            print(f"[DEBUG] show_copy_feedback 실패: {e}")

    elif anchor and chosen.text().startswith("🔗 Open Link"):
        print(f"[DEBUG] 🔗 Open Link 선택됨 → {anchor}")
        QDesktopServices.openUrl(QUrl(anchor))

    elif anchor and chosen.text().startswith("🔗 Copy Link"):
        print(f"[DEBUG] 🔗 Copy Link 선택됨 → {anchor}")
        QGuiApplication.clipboard().setText(anchor)
        try:
            from qt_copy_feedback import show_copy_feedback

            show_copy_feedback(app_instance, "링크 복사됨")
        except Exception as e:
            print(f"[DEBUG] show_copy_feedback 실패: {e}")

    elif chosen is act_nlk_search:
        print("[DEBUG] 🔍 NLK 탭에서 제목 검색 선택됨")
        selected_text = tb.textCursor().selectedText()

        if not selected_text:
            print("[DEBUG] 선택 텍스트 없음 → 경고창 표시")
            QMessageBox.warning(tb, "선택 오류", "검색할 텍스트를 먼저 선택하세요.")
            return

        # ✅ tab_widget이 있는 대상 찾기
        target = getattr(app_instance, "main_window", None)
        if target and hasattr(target, "tab_widget"):
            print(f"[DEBUG] NLK 검색 실행: '{selected_text}' → main_window 전달")
            _search_in_nlk_tab(target, selected_text)
        else:
            print("[ERROR] ❌ tab_widget을 가진 객체를 찾을 수 없습니다.")
            if hasattr(app_instance, "log_message"):
                app_instance.log_message(
                    "❌ tab_widget을 가진 객체를 찾을 수 없습니다.", "ERROR"
                )

    elif chosen is act_author_check_search:
        print("[DEBUG] 🔍 저자 확인 탭에서 저작물 일괄 검색 선택됨")
        selected_text = tb.textCursor().selectedText()

        if not selected_text:
            print("[DEBUG] 선택 텍스트 없음 → 경고창 표시")
            QMessageBox.warning(tb, "선택 오류", "검색할 텍스트를 먼저 선택하세요.")
            return

        # ✅ tab_widget이 있는 대상 찾기
        target = getattr(app_instance, "main_window", None)
        if target and hasattr(target, "tab_widget"):
            print(f"[DEBUG] 저자 확인 검색 실행: '{selected_text}' → main_window 전달")
            _search_in_author_check_tab(target, selected_text)
        else:
            print("[ERROR] ❌ tab_widget을 가진 객체를 찾을 수 없습니다.")
            if hasattr(app_instance, "log_message"):
                app_instance.log_message(
                    "❌ tab_widget을 가진 객체를 찾을 수 없습니다.", "ERROR"
                )

    elif chosen is act_select_all:
        print("[DEBUG] 🧲 Select All 선택됨")
        tb.selectAll()


def _search_in_nlk_tab(app_instance, title_text):
    """
    ✅ [수정] 탭 모드와 트리뷰 모드를 모두 지원하도록 수정
    NLK 탭으로 전환하고 제목 검색을 실행합니다.

    Args:
        app_instance: 메인 앱 인스턴스 또는 탭 인스턴스
        title_text: 검색할 제목 텍스트
    """
    print(f"[DEBUG] _search_in_nlk_tab() 호출됨 → '{title_text}'")
    print(f"[DEBUG] app_instance 타입: {type(app_instance).__name__}")

    # ✅ [핵심 수정] app_instance가 실제 IntegratedSearchApp인지, 아니면 탭 인스턴스인지 확인
    if hasattr(app_instance, "main_window"):
        # IntegratedSearchApp 인스턴스
        main_window = app_instance.main_window
        print(f"[DEBUG] app_instance.main_window 사용")
    elif hasattr(app_instance, "app_instance") and hasattr(
        app_instance.app_instance, "main_window"
    ):
        # 탭 인스턴스 (app_instance.app_instance.main_window)
        main_window = app_instance.app_instance.main_window
        print(f"[DEBUG] app_instance.app_instance.main_window 사용")
    else:
        print("[ERROR] ❌ main_window를 찾을 수 없습니다.")
        return

    try:
        # ✅ [핵심 수정] main_window의 switch_to_tab_by_name 메서드 사용
        main_window.switch_to_tab_by_name("NLK 검색")

        # ✅ [핵심 수정] main_window의 get_tab_by_name 메서드 사용
        nlk_tab = main_window.get_tab_by_name("NLK 검색")

        if nlk_tab is None:
            print("[ERROR] ❌ NLK 탭을 찾을 수 없습니다.")
            return

        # 3. 모든 검색 입력 필드 초기화 (input_widgets 딕셔너리 사용)
        nlk_tab.input_widgets["title"].clear()
        nlk_tab.input_widgets["author"].clear()
        nlk_tab.input_widgets["isbn"].clear()
        nlk_tab.input_widgets["year"].clear()

        # DDC 입력창이 있으면 초기화
        if hasattr(nlk_tab, "ddc_input"):
            nlk_tab.ddc_input.clear()

        # 4. 제목 입력 필드에 텍스트 설정
        nlk_tab.input_widgets["title"].setText(title_text)
        print(f"[DEBUG] 제목 입력 완료: '{title_text}' → input_widgets['title'] 사용")

        # 5. ✅ [중요] 타이밍 이슈 해결: GUI 이벤트 처리를 위해 약간의 지연 추가
        from PySide6.QtCore import QTimer

        print(f"[DEBUG] 검색 실행 준비 완료 → 200ms 후 검색 시작")
        QTimer.singleShot(200, nlk_tab.start_search)

        # ✅ [수정] log_message도 올바른 app_instance에서 호출
        real_app = None
        if hasattr(app_instance, "log_message"):
            real_app = app_instance
        elif hasattr(app_instance, "app_instance") and hasattr(
            app_instance.app_instance, "log_message"
        ):
            real_app = app_instance.app_instance

        if real_app:
            real_app.log_message(
                f"✅ NLK 탭에서 '{title_text}' 제목 검색을 시작합니다.", "INFO"
            )

    except Exception as e:
        print(f"[ERROR] _search_in_nlk_tab 예외 발생: {e}")
        import traceback

        traceback.print_exc()


def _search_in_author_check_tab(app_instance, title_text):
    """
    저자 확인 탭으로 전환하고 제목 검색을 실행합니다.

    ✅ QTextBrowser의 selectedText()가 반환하는 U+2029(paragraph separator)를
       일반 줄바꿈(\n)으로 변환하여 복수 제목 일괄 검색을 지원합니다.

    Args:
        app_instance: 메인 앱 인스턴스 또는 탭 인스턴스
        title_text: 검색할 제목 텍스트 (U+2029로 구분될 수 있음)
    """
    print(f"[DEBUG] _search_in_author_check_tab() 호출됨 → '{title_text}'")
    print(f"[DEBUG] app_instance 타입: {type(app_instance).__name__}")

    # ✅ [핵심 추가] 특수 구분자를 줄바꿈으로 변환
    # - U+2029: QTextCursor.selectedText()의 paragraph separator
    # - U+FDD0/U+FDD1: AI Feed의 커스텀 제목 구분자
    normalized_text = title_text.replace("\u2029", "\n")
    normalized_text = normalized_text.replace("\ufdd0", "\n").replace("\ufdd1", "")

    # 빈 줄 제거 및 정리
    lines = [line.strip() for line in normalized_text.split("\n") if line.strip()]
    normalized_text = "\n".join(lines)

    print(f"[DEBUG] 정규화된 텍스트 (특수문자 → \\n): '{normalized_text}'")

    # ✅ app_instance가 실제 IntegratedSearchApp인지, 아니면 탭 인스턴스인지 확인
    if hasattr(app_instance, "main_window"):
        # IntegratedSearchApp 인스턴스
        main_window = app_instance.main_window
        print(f"[DEBUG] app_instance.main_window 사용")
    elif hasattr(app_instance, "app_instance") and hasattr(
        app_instance.app_instance, "main_window"
    ):
        # 탭 인스턴스 (app_instance.app_instance.main_window)
        main_window = app_instance.app_instance.main_window
        print(f"[DEBUG] app_instance.app_instance.main_window 사용")
    else:
        print("[ERROR] ❌ main_window를 찾을 수 없습니다.")
        return

    try:
        # ✅ 저자 확인 탭으로 전환
        main_window.switch_to_tab_by_name("저자 확인")

        # ✅ 저자 확인 탭 가져오기
        author_check_tab = main_window.get_tab_by_name("저자 확인")

        if author_check_tab is None:
            print("[ERROR] ❌ 저자 확인 탭을 찾을 수 없습니다.")
            return

        # 모든 검색 입력 필드 초기화 (input_widgets 딕셔너리 사용)
        author_check_tab.input_widgets["title"].clear()
        author_check_tab.input_widgets["author"].clear()
        author_check_tab.input_widgets["year"].clear()

        # KAC 입력창이 있으면 초기화
        if hasattr(author_check_tab, "kac_input"):
            author_check_tab.kac_input.clear()

        # ✅ [수정] 정규화된 텍스트를 제목 입력 필드에 설정 (복수 제목 지원)
        author_check_tab.input_widgets["title"].setText(normalized_text)

        # 제목 개수 계산 (로그용)
        title_count = len([t for t in normalized_text.split("\n") if t.strip()])
        print(
            f"[DEBUG] 제목 입력 완료: {title_count}개 제목 → input_widgets['title'] 사용"
        )

        # ✅ 타이밍 이슈 해결: GUI 이벤트 처리를 위해 약간의 지연 추가
        from PySide6.QtCore import QTimer

        print(f"[DEBUG] 검색 실행 준비 완료 → 200ms 후 검색 시작")
        QTimer.singleShot(200, author_check_tab.start_search)

        # ✅ log_message도 올바른 app_instance에서 호출
        real_app = None
        if hasattr(app_instance, "log_message"):
            real_app = app_instance
        elif hasattr(app_instance, "app_instance") and hasattr(
            app_instance.app_instance, "log_message"
        ):
            real_app = app_instance.app_instance

        if real_app:
            # 로그 메시지에 제목 개수 표시
            if title_count > 1:
                real_app.log_message(
                    f"✅ 저자 확인 탭에서 {title_count}개 제목 일괄 검색을 시작합니다.",
                    "INFO",
                )
            else:
                real_app.log_message(
                    f"✅ 저자 확인 탭에서 '{normalized_text}' 제목 검색을 시작합니다.",
                    "INFO",
                )

    except Exception as e:
        print(f"[ERROR] _search_in_author_check_tab 예외 발생: {e}")
        import traceback

        traceback.print_exc()


def setup_widget_context_menu(widget, app_instance):
    """✅ [모델/뷰 전용] 위젯에 컨텍스트 메뉴 자동 설정 - QTableWidget 완전 폐기"""

    widget.setContextMenuPolicy(Qt.CustomContextMenu)

    if isinstance(widget, QLineEdit):
        widget.customContextMenuRequested.connect(
            lambda pos: show_qlineedit_context_menu(widget, pos, app_instance)
        )
    elif isinstance(widget, QTextEdit):
        widget.customContextMenuRequested.connect(
            lambda pos: show_qtextedit_context_menu(widget, pos, app_instance)
        )
    elif isinstance(widget, QTableView):
        # ✅ [QTableWidget 교체] QTableView만 지원
        def show_tableview_menu(pos):
            """QTableView 컨텍스트 메뉴 표시"""
            index = widget.indexAt(pos)
            if index.isValid():
                show_qtableview_context_menu(
                    widget, index.row(), index.column(), pos, app_instance
                )

        widget.customContextMenuRequested.connect(show_tableview_menu)

    # 성공적으로 설정되었음을 로그로 남김
    widget_type = type(widget).__name__
    if hasattr(app_instance, "log_message"):
        app_instance.log_message(f"✅ {widget_type} 컨텍스트 메뉴 설정 완료", "DEBUG")


def copy_row_data(table_view, row, app_instance):
    """특정 행의 모든 데이터를 TSV로 복사"""
    try:
        row_data = []
        col_count = table_view.columnCount()

        for col in range(col_count):
            item = table_view.item(row, col)
            cell_text = item.text() if item else ""
            row_data.append(cell_text)

        tsv_text = "\t".join(row_data)
        copy_to_clipboard_with_feedback(tsv_text, app_instance)

        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"📋 행 복사 완료: {col_count}개 컬럼", "INFO")

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 행 복사 실패: {e}", "ERROR")


def copy_selection_data(table_view, app_instance):
    """선택된 범위를 TSV로 복사"""
    try:
        selected_ranges = table_view.selectedRanges()
        if not selected_ranges:
            return

        all_data = []
        total_cells = 0

        for range_obj in selected_ranges:
            for row in range(range_obj.topRow(), range_obj.bottomRow() + 1):
                row_data = []
                for col in range(range_obj.leftColumn(), range_obj.rightColumn() + 1):
                    item = table_view.item(row, col)
                    cell_text = item.text() if item else ""
                    row_data.append(cell_text)
                    total_cells += 1
                all_data.append("\t".join(row_data))

        tsv_text = "\n".join(all_data)
        copy_to_clipboard_with_feedback(tsv_text, app_instance)

        if hasattr(app_instance, "log_message"):
            app_instance.log_message(
                f"📋 선택 영역 복사 완료: {total_cells}개 셀", "INFO"
            )

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 선택 영역 복사 실패: {e}", "ERROR")


def copy_selection_as_markdown(table_view, app_instance):
    """선택된 범위를 마크다운 테이블로 복사"""
    try:
        selected_ranges = table_view.selectedRanges()
        if not selected_ranges:
            return

        first_range = selected_ranges[0]

        # 헤더 수집
        headers = []
        for col in range(first_range.leftColumn(), first_range.rightColumn() + 1):
            header_item = table_view.horizontalHeaderItem(col)
            header_name = header_item.text() if header_item else f"Col_{col}"
            headers.append(header_name)

        # 데이터 수집
        data_rows = []
        for range_obj in selected_ranges:
            for row in range(range_obj.topRow(), range_obj.bottomRow() + 1):
                row_data = []
                for col in range(range_obj.leftColumn(), range_obj.rightColumn() + 1):
                    item = table_view.item(row, col)
                    cell_text = item.text() if item else ""
                    row_data.append(cell_text)
                data_rows.append(row_data)

        # 마크다운 테이블 생성
        markdown_lines = []

        # 헤더 라인
        header_line = "| " + " | ".join(headers) + " |"
        markdown_lines.append(header_line)

        # 구분선
        separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        markdown_lines.append(separator)

        # 데이터 라인들
        for row_data in data_rows:
            data_line = "| " + " | ".join(row_data) + " |"
            markdown_lines.append(data_line)

        markdown_text = "\n".join(markdown_lines)
        copy_to_clipboard_with_feedback(markdown_text, app_instance)

        if hasattr(app_instance, "log_message"):
            app_instance.log_message(
                f"📋 마크다운 테이블 복사 완료: {len(headers)}x{len(data_rows)}", "INFO"
            )

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 마크다운 복사 실패: {e}", "ERROR")


def show_selection_info(table_view, app_instance):
    """선택된 영역의 정보를 표시합니다."""
    try:
        selected_ranges = table_view.selectedRanges()

        if not selected_ranges:
            show_info_dialog("선택 정보", "선택된 영역이 없습니다.", app_instance)
            return

        total_cells = 0
        total_rows = 0
        total_cols = 0
        range_info = []

        for i, range_obj in enumerate(selected_ranges):
            rows = range_obj.bottomRow() - range_obj.topRow() + 1
            cols = range_obj.rightColumn() - range_obj.leftColumn() + 1
            cells = rows * cols

            total_cells += cells
            total_rows += rows
            total_cols += cols

            range_info.append(f"범위 {i+1}: {rows}행 × {cols}열 = {cells}개 셀")

        info_text = f"""선택 영역 정보:

총 선택된 셀: {total_cells:,}개
총 범위 수: {len(selected_ranges)}개

세부 정보:
{chr(10).join(range_info)}

데이터 미리보기:
{get_selection_preview(table_view, selected_ranges)}"""

        show_info_dialog("선택 영역 정보", info_text, app_instance)

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 선택 정보 표시 실패: {e}", "ERROR")


def get_selection_preview(table_view, selected_ranges):
    """선택된 영역의 미리보기 텍스트를 생성합니다."""
    try:
        preview_lines = []
        max_preview_cells = 20  # 최대 미리보기 셀 수
        cell_count = 0

        for range_obj in selected_ranges:
            if cell_count >= max_preview_cells:
                preview_lines.append("... (더 많은 데이터가 있음)")
                break

            for row in range(range_obj.topRow(), range_obj.bottomRow() + 1):
                if cell_count >= max_preview_cells:
                    break

                row_data = []
                for col in range(range_obj.leftColumn(), range_obj.rightColumn() + 1):
                    if cell_count >= max_preview_cells:
                        break

                    item = table_view.item(row, col)
                    cell_value = item.text() if item else ""

                    # 긴 텍스트는 줄임
                    if len(cell_value) > 20:
                        cell_value = cell_value[:20] + "..."

                    row_data.append(cell_value)
                    cell_count += 1

                if row_data:
                    preview_lines.append("\t".join(row_data))

        return "\n".join(preview_lines) if preview_lines else "(빈 선택)"

    except Exception as e:
        return f"(미리보기 생성 실패: {e})"


def show_all_columns(table_view):
    """모든 숨겨진 컬럼을 다시 표시합니다."""
    try:
        col_count = table_view.columnCount()
        shown_count = 0

        for col in range(col_count):
            if table_view.isColumnHidden(col):
                table_view.setColumnHidden(col, False)
                shown_count += 1

        return shown_count

    except Exception as e:
        print(f"컬럼 표시 오류: {e}")
        return 0


# === QTableView 전용 유틸리티 함수들 ===


def copy_tableview_row_data(table_view, row, app_instance):
    """✅ [새로 추가] QTableView의 특정 행 모든 데이터를 TSV로 복사"""
    try:
        model = table_view.model()
        if not model:
            return

        row_data = []
        col_count = model.columnCount()

        for col in range(col_count):
            index = model.index(row, col)
            if hasattr(model, "itemFromIndex"):
                item = model.itemFromIndex(index)
                cell_text = item.text() if item else ""
            else:
                cell_text = model.data(index, Qt.ItemDataRole.DisplayRole) or ""
            row_data.append(str(cell_text))

        # TSV 형식으로 복사
        row_tsv = "\t".join(row_data)
        copy_to_clipboard_with_feedback(
            row_tsv, app_instance, table_view
        )  # 👈 통일 및 parent_widget 전달

        if hasattr(app_instance, "log_message"):
            app_instance.log_message(
                f"📄 행 {row+1} 데이터 복사 완료 ({len(row_data)}개 컬럼)", "INFO"
            )

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 행 데이터 복사 실패: {e}", "ERROR")


def copy_tableview_selection(table_view, app_instance):
    """✅ [새로 추가] QTableView의 선택된 영역을 TSV로 복사"""
    try:
        selection_model = table_view.selectionModel()
        if not selection_model:
            return

        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            return

        # 선택된 영역을 행별로 정리
        rows_data = {}
        for index in selected_indexes:
            row = index.row()
            col = index.column()
            if row not in rows_data:
                rows_data[row] = {}

            model = table_view.model()
            if hasattr(model, "itemFromIndex"):
                item = model.itemFromIndex(index)
                cell_text = item.text() if item else ""
            else:
                cell_text = model.data(index, Qt.ItemDataRole.DisplayRole) or ""

            rows_data[row][col] = str(cell_text)

        # TSV 형식으로 변환
        tsv_lines = []
        for row in sorted(rows_data.keys()):
            row_cells = []
            for col in sorted(rows_data[row].keys()):
                row_cells.append(rows_data[row][col])
            tsv_lines.append("\t".join(row_cells))

        tsv_content = "\n".join(tsv_lines)
        copy_to_clipboard_with_feedback(
            tsv_content, app_instance, table_view
        )  # 👈 통일 및 parent_widget 전달

        if hasattr(app_instance, "log_message"):
            app_instance.log_message(
                f"📑 선택 영역 복사 완료: {len(rows_data)}행 x {len(selected_indexes)}셀",
                "INFO",
            )

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 선택 영역 복사 실패: {e}", "ERROR")


def copy_tableview_as_markdown(table_view, app_instance):
    """✅ [새로 추가] QTableView 선택 영역을 마크다운 테이블로 복사"""
    try:
        selection_model = table_view.selectionModel()
        if not selection_model:
            return

        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            return

        model = table_view.model()
        if not model:
            return

        # 선택된 영역의 행과 열 범위 계산
        rows = sorted(set(index.row() for index in selected_indexes))
        cols = sorted(set(index.column() for index in selected_indexes))

        # 마크다운 테이블 생성
        markdown_lines = []

        # 헤더 행
        headers = []
        for col in cols:
            header_text = (
                model.headerData(
                    col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
                )
                or f"Col_{col}"
            )
            headers.append(str(header_text))

        header_line = "| " + " | ".join(headers) + " |"
        markdown_lines.append(header_line)

        # 구분선
        separator_line = "| " + " | ".join("---" for _ in cols) + " |"
        markdown_lines.append(separator_line)

        # 데이터 행들
        for row in rows:
            row_data = []
            for col in cols:
                index = model.index(row, col)
                if hasattr(model, "itemFromIndex"):
                    item = model.itemFromIndex(index)
                    cell_text = item.text() if item else ""
                else:
                    cell_text = model.data(index, Qt.ItemDataRole.DisplayRole) or ""

                # 마크다운에서 파이프 문자 이스케이프
                cell_text = str(cell_text).replace("|", "\\|")
                row_data.append(cell_text)

            data_line = "| " + " | ".join(row_data) + " |"
            markdown_lines.append(data_line)

        # 클립보드에 복사
        markdown_text = "\n".join(markdown_lines)
        copy_to_clipboard_with_feedback(markdown_text, app_instance)

        if hasattr(app_instance, "log_message"):
            app_instance.log_message(
                f"📝 마크다운 테이블 복사 완료: {len(rows)}행 x {len(cols)}열", "INFO"
            )

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 마크다운 복사 실패: {e}", "ERROR")


def copy_tableview_as_csv(table_view, app_instance):
    """✅ [새로 추가] QTableView 선택 영역을 CSV 형식으로 복사"""
    try:
        selection_model = table_view.selectionModel()
        if not selection_model:
            return

        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            return

        model = table_view.model()
        if not model:
            return

        # 선택된 영역의 행과 열 범위 계산
        rows = sorted(set(index.row() for index in selected_indexes))
        cols = sorted(set(index.column() for index in selected_indexes))

        # CSV 형식으로 변환
        csv_lines = []

        # 헤더 행 (선택사항)
        headers = []
        for col in cols:
            header_text = (
                model.headerData(
                    col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
                )
                or f"Col_{col}"
            )
            header_text = str(header_text)
            # CSV에서 쉼표와 따옴표 이스케이프
            if "," in header_text or '"' in header_text:
                escaped_header = header_text.replace('"', '""')
                header_text = f'"{escaped_header}"'
            headers.append(header_text)

        csv_lines.append(",".join(headers))

        # 데이터 행들
        for row in rows:
            row_data = []
            for col in cols:
                index = model.index(row, col)
                if hasattr(model, "itemFromIndex"):
                    item = model.itemFromIndex(index)
                    cell_text = item.text() if item else ""
                else:
                    cell_text = model.data(index, Qt.ItemDataRole.DisplayRole) or ""

                # CSV에서 쉼표와 따옴표 이스케이프
                cell_text = str(cell_text)
                if "," in cell_text or '"' in cell_text or "\n" in cell_text:
                    escaped_cell = cell_text.replace('"', '""')
                    cell_text = f'"{escaped_cell}"'

                row_data.append(cell_text)

            csv_lines.append(",".join(row_data))

        # 클립보드에 복사
        csv_text = "\n".join(csv_lines)
        copy_to_clipboard_with_feedback(
            csv_text, app_instance, table_view
        )  # 👈 통일 및 parent_widget 전달

        if hasattr(app_instance, "log_message"):
            app_instance.log_message(
                f"📊 CSV 복사 완료: {len(rows)}행 x {len(cols)}열 (헤더 포함)", "INFO"
            )

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ CSV 복사 실패: {e}", "ERROR")


def show_all_tableview_columns(table_view):
    """✅ [새로 추가] QTableView의 모든 컬럼을 표시"""
    try:
        model = table_view.model()
        if not model:
            return

        for i in range(model.columnCount()):
            table_view.setColumnHidden(i, False)

    except Exception as e:
        print(f"모든 컬럼 표시 실패: {e}")


def filter_tableview_by_value(table_view, column, value, app_instance):
    """✅ [새로 추가] QTableView에서 특정 값으로 필터링"""
    try:
        # 현재는 간단한 행 숨김으로 구현
        # 나중에 QSortFilterProxyModel로 업그레이드 예정

        model = table_view.model()
        if not model:
            return

        visible_count = 0
        for row in range(model.rowCount()):
            index = model.index(row, column)
            if hasattr(model, "itemFromIndex"):
                item = model.itemFromIndex(index)
                cell_text = item.text() if item else ""
            else:
                cell_text = model.data(index, Qt.ItemDataRole.DisplayRole) or ""

            is_match = str(value).lower() in str(cell_text).lower()
            table_view.setRowHidden(row, not is_match)

            if is_match:
                visible_count += 1

        if hasattr(app_instance, "log_message"):
            total_rows = model.rowCount()
            app_instance.log_message(
                f"🔍 필터 적용: '{value}' → {visible_count}/{total_rows}행 표시", "INFO"
            )

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 필터링 실패: {e}", "ERROR")


def clear_tableview_filter(table_view, app_instance):
    """✅ [새로 추가] QTableView의 모든 필터를 지우기"""
    try:
        model = table_view.model()
        if not model:
            return

        # 모든 행을 다시 표시
        for row in range(model.rowCount()):
            table_view.setRowHidden(row, False)

        if hasattr(app_instance, "log_message"):
            app_instance.log_message("🔄 모든 필터가 제거되었습니다.", "INFO")

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 필터 제거 실패: {e}", "ERROR")


def show_tableview_selection_stats(table_view, app_instance):
    """✅ [새로 추가] QTableView 선택 영역의 통계 정보 표시"""
    try:
        selection_model = table_view.selectionModel()
        if not selection_model:
            return

        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            return

        model = table_view.model()
        if not model:
            return

        # 통계 계산
        selected_rows = set(index.row() for index in selected_indexes)
        selected_cols = set(index.column() for index in selected_indexes)

        # 숫자 값들 수집 (통계용)
        numeric_values = []
        text_values = []

        for index in selected_indexes:
            if hasattr(model, "itemFromIndex"):
                item = model.itemFromIndex(index)
                cell_text = item.text() if item else ""
            else:
                cell_text = model.data(index, Qt.ItemDataRole.DisplayRole) or ""

            cell_text = str(cell_text).strip()
            if cell_text:
                try:
                    # 숫자 변환 시도
                    numeric_value = float(cell_text.replace(",", ""))
                    numeric_values.append(numeric_value)
                except ValueError:
                    text_values.append(cell_text)

        # 통계 정보 생성
        stats_lines = [
            f"선택 영역 통계",
            "=" * 30,
            f"선택된 셀 수: {len(selected_indexes):,}",
            f"선택된 행 수: {len(selected_rows):,}",
            f"선택된 열 수: {len(selected_cols):,}",
            "",
            "데이터 분석:",
            f"- 숫자 값: {len(numeric_values):,}개",
            f"- 텍스트 값: {len(text_values):,}개",
        ]

        # 숫자 통계 추가
        if numeric_values:
            stats_lines.extend(
                [
                    "",
                    "숫자 통계:",
                    f"- 합계: {sum(numeric_values):,.2f}",
                    f"- 평균: {sum(numeric_values)/len(numeric_values):,.2f}",
                    f"- 최소값: {min(numeric_values):,.2f}",
                    f"- 최대값: {max(numeric_values):,.2f}",
                ]
            )

        # 텍스트 통계 추가
        if text_values:
            unique_texts = set(text_values)
            stats_lines.extend(
                [
                    "",
                    "텍스트 통계:",
                    f"- 고유 값: {len(unique_texts):,}개",
                    f"- 중복 값: {len(text_values) - len(unique_texts):,}개",
                ]
            )

        stats_text = "\n".join(stats_lines)
        show_info_dialog("선택 영역 통계", stats_text, app_instance)

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 선택 영역 통계 실패: {e}", "ERROR")


# === 인앱 번역 기능 (ctk 버전 로직 이식) ===


class TranslationThread(QThread):
    """API 번역을 위한 비동기 작업 스레드"""

    # 번역 완료 시그널: (원문, 번역문)을 전달
    translation_finished = Signal(str, str)
    # 오류 발생 시그널: (에러 메시지)를 전달
    translation_failed = Signal(str)

    def __init__(self, text, app_instance):
        super().__init__()
        self.text_to_translate = text
        self.app_instance = app_instance

    def run(self):
        """백그라운드에서 번역 API 호출"""
        try:
            # [핵심 3] 실제 API 함수 호출 (db_manager 전달)
            translation = translate_text(
                self.text_to_translate, db_manager=self.app_instance.db_manager
            )
            self.translation_finished.emit(self.text_to_translate, translation)
        except Exception as e:
            self.translation_failed.emit(str(e))


def _show_translation_dialog(original_text, translated_text, parent_widget):
    """번역 원문과 결과를 보여주는 커스텀 대화상자"""
    dialog = QDialog(parent_widget)
    dialog.setWindowTitle("인앱 번역 결과")
    dialog.setMinimumSize(500, 400)

    layout = QVBoxLayout(dialog)

    # 원문 표시
    layout.addWidget(QLabel("<b>원문:</b>"))
    original_edit = QTextEdit()
    original_edit.setPlainText(original_text)
    original_edit.setReadOnly(True)
    original_edit.setMaximumHeight(100)
    layout.addWidget(original_edit)

    # 번역문 표시
    layout.addWidget(QLabel("<b>번역 결과:</b>"))
    translated_edit = QTextEdit()
    translated_edit.setPlainText(translated_text)
    translated_edit.setReadOnly(True)
    layout.addWidget(translated_edit)

    # 닫기 버튼
    close_button = QPushButton("닫기")
    close_button.clicked.connect(dialog.accept)
    layout.addWidget(close_button)

    # ✅ [추가] 외부 클릭 시 닫기 기능 적용
    from qt_utils import enable_modal_close_on_outside_click

    enable_modal_close_on_outside_click(dialog)
    apply_dark_title_bar(dialog)

    dialog.exec()


def perform_in_app_translation(text, target_lang, app_instance):
    """[완전 교체] 인앱 번역 스레드를 시작하고 결과/실패를 처리"""

    # 현재 활성화된 위젯을 부모로 사용 (QTableView, QLineEdit 등)
    parent_widget = QApplication.focusWidget()

    def on_finished(original, translated):
        _show_translation_dialog(original, translated, parent_widget)
        if hasattr(app_instance, "log_message"):
            app_instance.log_message("✅ 인앱 번역 완료", "INFO")

    def on_failed(error_message):
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 인앱 번역 실패: {error_message}", "ERROR")
        QMessageBox.critical(
            parent_widget, "번역 오류", f"번역 중 오류가 발생했습니다:\n{error_message}"
        )

    if hasattr(app_instance, "log_message"):
        app_instance.log_message(f"📲 인앱 번역 시작...", "INFO")

    # [핵심 4] 스레드 생성 및 시그널 연결 후 시작
    thread = TranslationThread(text, app_instance)
    thread.translation_finished.connect(on_finished)
    thread.translation_failed.connect(on_failed)

    # [중요] 스레드 객체가 사라지지 않도록 참조를 유지해야 합니다.
    # 여기서는 간단하게 QApplication 인스턴스에 임시로 저장합니다.
    if not hasattr(QApplication.instance(), "_running_threads"):
        QApplication.instance()._running_threads = []
    QApplication.instance()._running_threads.append(thread)
    thread.finished.connect(
        lambda: QApplication.instance()._running_threads.remove(thread)
    )

    thread.start()


# ✅ [추가] CTk 버전의 줄바꿈 로직을 그대로 이식한 헬퍼 함수
def _format_text_for_detail_view(cell_value):
    """상세보기 창에 표시될 텍스트의 줄바꿈을 실무용으로 개선합니다."""
    content = str(cell_value)

    # -------------------
    # ✅ [핵심 추가] 0. U+2029 (PARAGRAPH SEPARATOR) 문자 제거
    content = content.replace("\u2029", "")
    # -------------------

    # 1. 기본 줄바꿈 문자 정리
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # 2. KAC/KSH 형식 데이터를 실무용으로 깔끔하게 정리
    if "▼a" in content and "▲" in content:
        # ▲; ▼a 패턴과 ▲, ▼a 패턴을 모두 줄바꿈으로 변경
        content = content.replace("▲; ▼a", "▲\n▼a")
        content = content.replace("▲, ▼a", "▲\n▼a")

    # 3. 일반 세미콜론 구분 데이터도 깔끔하게
    elif "; " in content and content.count("; ") >= 1:
        content = content.replace("; ", "\n")

    # 3-1. 일반 세미콜론 구분 데이터도 깔끔하게
    elif ";" in content and content.count(";") >= 1:
        content = content.replace(";", "\n")

    # 4. 파이프(|) 구분 데이터도 줄바꿈으로 교체
    elif " | " in content and content.count(" | ") >= 1:
        content = content.replace(" | ", "\n")

    return content.strip()


# ✅ [수정] CTk 버전의 모든 기능을 포팅한 새로운 상세 보기 대화상자
def show_cell_detail_dialog(cell_value, column_name, app_instance):
    """셀 값 상세보기 대화상자 — 행 상세보기와 동작/구성 100% 일치 버전"""
    try:
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor, QShortcut, QKeySequence
        from qt_custom_widgets import TripleClickLimitedTextBrowser
        from ui_constants import UI_CONSTANTS
        from qt_utils import linkify_text

        # 필요시: from qt_utils import enable_modal_close_on_outside_click

        dialog = QDialog(app_instance.main_window)
        dialog.setWindowTitle(f"상세 정보: {column_name}")
        dialog.setMinimumSize(850, 700)
        dialog.setObjectName("DetailDialog")

        # 창 플래그/모달 성격도 동일하게
        dialog.setModal(True)
        apply_dark_title_bar(dialog)
        # 외부클릭으로 닫기 기능을 쓰려면 아래 주석 해제하되,
        # qt_utils 쪽 필터가 내부 클릭/ESC를 consume하지 않도록 가드가 있어야 함.
        enable_modal_close_on_outside_click(dialog)

        # 행 상세와 동일한 드롭섀도 효과
        shadow = QGraphicsDropShadowEffect(dialog)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 180))
        dialog.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(3, 3, 3, 3)  # 좌, 상, 우, 하 여백 설정

        # 동일한 텍스트 브라우저/스타일
        U = UI_CONSTANTS
        link_color = U.ACCENT_BLUE
        header_style = f"color: {U.ACCENT_GREEN}; font-weight: bold;"

        text_browser = TripleClickLimitedTextBrowser()
        text_browser.setStyleSheet(
            f"""
            QTextBrowser {{
                padding: 10px;
            }}
            a {{
                color: {link_color};
                text-decoration: underline;
            }}
            a:hover {{
                color: {link_color};
                text-decoration: underline;
            }}
            """
        )

        # ✅ 컨텍스트 메뉴는 viewport에 걸어야 함 (QTextBrowser는 스크롤 영역이 따로 있음)
        from qt_context_menus import show_textbrowser_context_menu

        text_browser.viewport().setContextMenuPolicy(Qt.CustomContextMenu)
        text_browser.viewport().customContextMenuRequested.connect(
            # pos는 이미 viewport 좌표 → 빌더로 그대로 전달
            lambda pos: show_textbrowser_context_menu(text_browser, pos, app_instance)
        )

        text_browser.setOpenExternalLinks(True)  # 명시적으로 외부 링크 활성화
        main_layout.addWidget(text_browser)

        # 버튼 영역 — 구성/순서 동일
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        copy_button = QPushButton("📋 내용 복사")
        copy_button.clicked.connect(
            lambda: copy_to_clipboard_with_feedback(
                str(cell_value), app_instance, dialog
            )
        )

        close_button = QPushButton("✖ 닫기")
        close_button.clicked.connect(dialog.accept)

        button_layout.addWidget(copy_button)
        button_layout.addWidget(close_button)
        main_layout.addLayout(button_layout)

        # 내용 구성 로직도 행 상세와 동일하게 (_format_text_for_detail_view 재사용)
        formatted_value = _format_text_for_detail_view(cell_value)
        styled_header = f'▶ <span style="{header_style}">{column_name}:</span>'
        if "\n" in formatted_value:
            final_text = f"{styled_header}\n{formatted_value}"
        else:
            final_text = f"{styled_header} {formatted_value}"

        # 링크화/라인별 테이블화도 동일
        lines = final_text.split("\n")
        html_lines = []
        for line in lines:
            if not line.strip():
                continue
            # ✅ preserve_html=True로 기존 HTML 태그 보존하면서 URL만 링크화
            linked = linkify_text(line, preserve_html=True)
            link_style = f'style="color: {link_color}; text-decoration: underline;"'
            linked = linked.replace("<a href=", f"<a {link_style} href=").strip()
            html_lines.append(linked)

        tables = [
            f'<table cellspacing="0" cellpadding="0" style="border:none;margin:0;padding:0;"><tr><td style="padding:0;border:none;">{ln}</td></tr></table>'
            for ln in html_lines
        ]
        text_browser.setHtml("".join(tables))

        # 행 상세와 ‘입력 처리 우선순위’까지 맞추기: ESC/포커스 세팅
        esc = QShortcut(QKeySequence("Esc"), dialog)
        esc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        esc.activated.connect(dialog.reject)

        close_button.setAutoDefault(True)
        close_button.setDefault(True)
        close_button.setFocus()

        # ✅ [추가] 다이얼로그 위치를 부모 중앙에서 150px 아래로 이동
        parent_widget = app_instance.main_window
        if (
            parent_widget
            and hasattr(parent_widget, "geometry")
            and callable(parent_widget.geometry)
        ):
            dialog.adjustSize()
            parent_rect = parent_widget.geometry()
            dialog_size = dialog.size()

            # 중앙 좌표 계산
            x = parent_rect.x() + (parent_rect.width() - dialog_size.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - dialog_size.height()) // 2

            # y 좌표를 150px 아래로 이동
            y += 150

            dialog.move(x, y)

        dialog.exec()

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 셀 상세보기 실패: {e}", "ERROR")


# ✅ [추가] KSH 관련 필드를 다중 라인으로 포맷하는 헬퍼 함수 (CTk 로직 이식)
# ✅ [수정] CTk 버전의 모든 기능을 포팅한 새로운 행 상세 보기 대화상자
def show_tableview_row_details(table_view, row, app_instance):
    try:
        model = table_view.model()
        if not model:
            return

        dialog = QDialog(app_instance.main_window)
        dialog.setWindowTitle(f"행 {row + 1} 전체 정보")
        dialog.setMinimumSize(800, 750)
        dialog.setObjectName("DetailDialog")

        apply_dark_title_bar(dialog)
        enable_modal_close_on_outside_click(dialog)

        # ✅ [추가] shadow 효과 적용
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor

        shadow = QGraphicsDropShadowEffect(dialog)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 180))
        dialog.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(3, 3, 3, 3)  # 좌, 상, 우, 하 여백 설정

        # -------------------
        # ✅ TripleClickLimitedTextBrowser 사용
        from qt_custom_widgets import TripleClickLimitedTextBrowser
        from ui_constants import UI_CONSTANTS

        U = UI_CONSTANTS
        link_color = U.ACCENT_BLUE
        header_style = (
            f"color: {U.ACCENT_GREEN}; font-weight: bold;"  # 헤더 스타일 정의
        )

        text_browser = TripleClickLimitedTextBrowser()
        text_browser.setStyleSheet(
            f"""
            QTextBrowser {{
                padding: 10px;
            }}
            a {{
                color: {link_color};
                text-decoration: underline;
            }}
            a:hover {{
                color: {link_color};
                text-decoration: underline;
            }}
            """
        )
        text_browser.setOpenExternalLinks(True)  # 명시적으로 외부 링크 활성화
        main_layout.addWidget(text_browser)
        # -------------------

        # 버튼 영역
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        copy_button = QPushButton("📋 TSV로 복사")
        copy_button.clicked.connect(
            lambda: copy_tableview_row_data(table_view, row, app_instance)
        )

        close_button = QPushButton("✖ 닫기")
        close_button.clicked.connect(dialog.accept)

        button_layout.addWidget(copy_button)
        button_layout.addWidget(close_button)
        main_layout.addLayout(button_layout)

        # ✅ [개선] _format_text_for_detail_view 사용하여 세미콜론 자동 줄바꿈
        from qt_utils import linkify_text

        content_lines = []

        for col in range(model.columnCount()):
            column_name = (
                model.headerData(
                    col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
                )
                or ""
            )
            value_content = (
                model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole) or ""
            )

            # ✅ _format_text_for_detail_view로 통일된 포맷팅 적용
            formatted_value = _format_text_for_detail_view(value_content)

            styled_header = f'▶ <span style="{header_style}">{column_name}:</span>'

            # 줄바꿈이 있으면 헤더와 값 사이에 \n 삽입
            if "\n" in formatted_value:
                formatted_line = f"{styled_header}\n{formatted_value}"
            else:
                formatted_line = f"{styled_header} {formatted_value}"

            content_lines.append(formatted_line)

        final_text = "\n".join(content_lines)
        lines = final_text.split("\n")
        html_lines = []

        for line in lines:
            if not line.strip():
                continue

            # ✅ [핵심 수정] span 태그가 있어도 URL을 linkify해야 함
            # preserve_html=True로 기존 HTML 태그 보존하면서 URL만 링크화
            linked_line = linkify_text(line, preserve_html=True)

            # 링크 태그에 인라인 스타일 강제 적용 (색상과 밑줄)
            link_style = f'style="color: {link_color}; text-decoration: underline;"'
            linked_line = linked_line.replace("<a href=", f"<a {link_style} href=")

            # 최종 공백 제거
            linked_line = linked_line.strip()

            html_lines.append(linked_line)

        # 각 줄을 독립된 테이블로
        tables = [
            f'<table cellspacing="0" cellpadding="0" style="border:none;margin:0;padding:0;"><tr><td style="padding:0;border:none;">{line}</td></tr></table>'
            for line in html_lines
        ]
        final_html = "".join(tables)

        text_browser.setHtml(final_html)
        # --- 로직 적용 끝 ---

        dialog.exec()

    except Exception as e:
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 행 세부 정보 표시 실패: {e}", "ERROR")
