# -*- coding: utf-8 -*-
# 파일명: qt_shortcuts.py
# 설명: PySide6 애플리케이션용 키보드 단축키 시스템 (QTableWidget 완전 대응)
# 버전: 2.1.0 - 모든 기능 복구 및 개선
# 생성일: 2025-09-24

import re
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QTextEdit,
    QTableView,
    QMessageBox,
    QTableWidget,
    QTreeView,
)
from PySide6.QtGui import QShortcut, QKeySequence, QAction
from PySide6.QtCore import Qt
from qt_api_clients import translate_text
from qt_utils import apply_dark_title_bar


class ShortcutManager:
    """
    PySide6용 단축키 관리 클래스 (모든 기능 복구)
    """

    def __init__(self, parent, app_instance):
        self.parent = parent
        self.app_instance = app_instance
        self.shortcuts = []

        # 단축키 설정
        self.setup_search_shortcuts()
        self.setup_navigation_shortcuts()
        self.setup_copy_shortcuts()
        self.setup_view_shortcuts()

    def setup_search_shortcuts(self):
        """검색 관련 단축키"""
        search_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.parent)
        search_shortcut.activated.connect(self._start_search)
        self.shortcuts.append(search_shortcut)

        cancel_shortcut = QShortcut(QKeySequence("Escape"), self.parent)
        cancel_shortcut.activated.connect(self._stop_search)
        self.shortcuts.append(cancel_shortcut)

        find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self.parent)
        find_shortcut.activated.connect(self._focus_find_entry)
        self.shortcuts.append(find_shortcut)

        find_next_shortcut = QShortcut(QKeySequence("F3"), self.parent)
        find_next_shortcut.activated.connect(self._find_next)
        self.shortcuts.append(find_next_shortcut)

        find_prev_shortcut = QShortcut(QKeySequence("Shift+F3"), self.parent)
        find_prev_shortcut.activated.connect(self._find_previous)
        self.shortcuts.append(find_prev_shortcut)

    def setup_navigation_shortcuts(self):
        """네비게이션 관련 단축키"""
        # ✅ [복구 및 개선] 특정 입력창 포커스
        # BaseSearchTab의 input_widgets 딕셔너리를 사용하여 더 유연하게 만듭니다.
        # 자식 탭에서 'query', 'author', 'isbn' 키로 위젯을 추가하면 단축키가 동작합니다.
        # -------------------
        input_map = {"Ctrl+1": "title", "Ctrl+2": "author", "Ctrl+3": "isbn"}
        # -------------------
        for key, widget_name in input_map.items():
            if (
                hasattr(self.parent, "input_widgets")
                and widget_name in self.parent.input_widgets
            ):
                shortcut = QShortcut(QKeySequence(key), self.parent)
                shortcut.activated.connect(
                    lambda w_name=widget_name: self.parent.input_widgets[
                        w_name
                    ].setFocus()
                )
                self.shortcuts.append(shortcut)

        # ✅ [복구 및 개선] 결과 위젯 포커스 (tree_widget -> table_widget)
        if hasattr(self.parent, "table_widget"):
            table_focus_shortcut = QShortcut(QKeySequence("Ctrl+R"), self.parent)
            table_focus_shortcut.activated.connect(
                lambda: self.parent.table_widget.setFocus()
            )
            self.shortcuts.append(table_focus_shortcut)

        # 기본 네비게이션 단축키
        select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self.parent)
        select_all_shortcut.activated.connect(self._select_all)
        self.shortcuts.append(select_all_shortcut)

        go_first_shortcut = QShortcut(QKeySequence("Ctrl+Home"), self.parent)
        go_first_shortcut.activated.connect(self._go_to_first_item)
        self.shortcuts.append(go_first_shortcut)

        go_last_shortcut = QShortcut(QKeySequence("Ctrl+End"), self.parent)
        go_last_shortcut.activated.connect(self._go_to_last_item)
        self.shortcuts.append(go_last_shortcut)

    def setup_copy_shortcuts(self):
        """복사 및 편집 관련 단축키"""
        copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self.parent)
        copy_shortcut.activated.connect(self._copy_with_feedback)
        self.shortcuts.append(copy_shortcut)

        clear_all_shortcut = QShortcut(QKeySequence("Ctrl+L"), self.parent)
        clear_all_shortcut.activated.connect(self._clear_all_inputs)
        self.shortcuts.append(clear_all_shortcut)

        # ✅ [복구] 컬럼 설정 저장/불러오기
        copy_column_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self.parent)
        copy_column_shortcut.activated.connect(self._save_column_settings)
        self.shortcuts.append(copy_column_shortcut)

        paste_column_shortcut = QShortcut(QKeySequence("Ctrl+Shift+V"), self.parent)
        paste_column_shortcut.activated.connect(self._load_column_settings)
        self.shortcuts.append(paste_column_shortcut)

        copy_markdown_shortcut = QShortcut(QKeySequence("Ctrl+Shift+M"), self.parent)
        copy_markdown_shortcut.activated.connect(self._copy_as_markdown)
        self.shortcuts.append(copy_markdown_shortcut)

    def setup_view_shortcuts(self):
        """보기 관련 단축키"""
        html_viewer_shortcut = QShortcut(QKeySequence("Ctrl+H"), self.parent)
        html_viewer_shortcut.activated.connect(self._open_html_viewer)
        self.shortcuts.append(html_viewer_shortcut)

        pandas_viewer_shortcut = QShortcut(QKeySequence("Ctrl+D"), self.parent)
        pandas_viewer_shortcut.activated.connect(self._open_pandas_viewer)
        self.shortcuts.append(pandas_viewer_shortcut)

        show_all_columns_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self.parent)
        show_all_columns_shortcut.activated.connect(self._show_all_columns)
        self.shortcuts.append(show_all_columns_shortcut)

        hide_all_columns_shortcut = QShortcut(QKeySequence("Ctrl+Shift+H"), self.parent)
        hide_all_columns_shortcut.activated.connect(self._hide_all_columns)
        self.shortcuts.append(hide_all_columns_shortcut)

        # ✅ [복구] 모든 필터 지우기
        clear_filters_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self.parent)
        clear_filters_shortcut.activated.connect(self._clear_all_filters)
        self.shortcuts.append(clear_filters_shortcut)

    # === 단축키 액션 메서드들 ===

    def _copy_with_feedback(self):
        """✅ [수정] Ctrl+C 복사 + copy_feedback 사용"""
        try:
            focused_widget = QApplication.focusWidget()
            if not focused_widget:
                self._log_warning("복사: 포커스된 위젯이 없습니다")
                return

            selected_text = ""

            if isinstance(focused_widget, QLineEdit):
                selected_text = focused_widget.selectedText() or focused_widget.text()
            elif isinstance(focused_widget, QTextEdit):
                selected_text = (
                    focused_widget.textCursor().selectedText()
                    or focused_widget.toPlainText()
                )
            elif isinstance(focused_widget, QTreeView):
                selection_model = focused_widget.selectionModel()
                if selection_model and selection_model.hasSelection():
                    indexes = selection_model.selectedIndexes()
                    if indexes:
                        # -------------------
                        # ✅ [핵심 수정] DDC 코드만 추출하도록 로직 변경
                        data_by_row = {}
                        # DDC 코드(범위 포함)를 추출하는 정규식
                        ddc_pattern = re.compile(
                            r"^\s*[\-\+]?└?\s*(\d+(?:\.\d+)?(?:[~\-–—]+\d+(?:\.\d+)?)?)"
                        )
                        for index in indexes:
                            if index.column() == 0:  # 첫 번째 열의 데이터만 처리
                                full_text = str(index.data(Qt.DisplayRole) or "")
                                match = ddc_pattern.match(full_text.strip())
                                if match:
                                    # DDC 코드가 발견되면, 해당 코드만 저장
                                    data_by_row[index.row()] = match.group(1)
                                # DDC 코드가 없는 행(예: '+ 관련 개념')은 복사 대상에서 제외

                        # 행 순서대로 정렬하여 텍스트 조합
                        sorted_rows = sorted(data_by_row.keys())
                        selected_text = "\n".join(
                            data_by_row[row] for row in sorted_rows
                        )
                        # -------------------

            elif isinstance(focused_widget, (QTableWidget, QTableView)):
                # QTableView/QTableWidget 처리
                if isinstance(focused_widget, QTableWidget):
                    selected_ranges = focused_widget.selectedRanges()
                    if selected_ranges:
                        all_data = []
                        for r in selected_ranges:
                            for row in range(r.topRow(), r.bottomRow() + 1):
                                row_data = []
                                for col in range(r.leftColumn(), r.rightColumn() + 1):
                                    item = focused_widget.item(row, col)
                                    row_data.append(item.text() if item else "")
                                all_data.append("\t".join(row_data))
                        selected_text = "\n".join(all_data)
                    else:
                        # 현재 셀
                        item = focused_widget.currentItem()
                        if item:
                            selected_text = item.text()
                else:  # QTableView
                    selection_model = focused_widget.selectionModel()
                    if selection_model and selection_model.hasSelection():
                        indexes = selection_model.selectedIndexes()
                        if indexes:
                            # 선택된 셀들을 행/컬럼으로 정렬
                            data_by_row = {}
                            for index in indexes:
                                row = index.row()
                                col = index.column()
                                cell_data = focused_widget.model().data(
                                    index, Qt.DisplayRole
                                )
                                cell_text = str(cell_data) if cell_data else ""

                                if row not in data_by_row:
                                    data_by_row[row] = {}
                                data_by_row[row][col] = cell_text

                            # TSV 형식으로 변환
                            tsv_lines = []
                            for row in sorted(data_by_row.keys()):
                                row_data = data_by_row[row]
                                row_values = [
                                    row_data.get(col, "")
                                    for col in sorted(row_data.keys())
                                ]
                                tsv_lines.append("\t".join(row_values))
                            selected_text = "\n".join(tsv_lines)
                    else:
                        # 현재 셀
                        current_index = focused_widget.currentIndex()
                        if current_index.isValid():
                            cell_data = focused_widget.model().data(
                                current_index, Qt.DisplayRole
                            )
                            selected_text = str(cell_data) if cell_data else ""

            if selected_text:
                # ✅ [핵심 수정] copy_feedback 사용
                from qt_copy_feedback import copy_to_clipboard_with_feedback

                copy_to_clipboard_with_feedback(selected_text, self.app_instance)
            else:
                if hasattr(self.app_instance, "log_message"):
                    self.app_instance.log_message(
                        "⚠️ 복사: 복사할 텍스트가 없습니다", "WARNING"
                    )

        except Exception as e:
            self._log_error(f"복사 실패: {e}")

    def _copy_as_markdown(self):
        """선택된 데이터를 마크다운 테이블로 복사"""
        if hasattr(self.parent, "copy_selected_as_markdown"):
            self.parent.copy_selected_as_markdown()

    def _start_search(self):
        if hasattr(self.parent, "start_search"):
            self.parent.start_search()

    def _stop_search(self):
        if hasattr(self.parent, "stop_search"):
            self.parent.stop_search()

    def _find_next(self):
        if hasattr(self.app_instance.main_window, "find_next"):
            self.app_instance.main_window.find_next()

    def _find_previous(self):
        if hasattr(self.app_instance.main_window, "find_prev"):
            self.app_instance.main_window.find_prev()

    def _focus_find_entry(self):
        if hasattr(self.parent, "find_entry"):
            self.parent.find_entry.setFocus()

    def _select_all(self):
        focused = QApplication.focusWidget()
        if hasattr(focused, "selectAll"):
            focused.selectAll()

    def _go_to_first_item(self):
        focused = QApplication.focusWidget()
        if isinstance(focused, QTableWidget) and focused.rowCount() > 0:
            focused.setCurrentCell(0, 0)

    def _go_to_last_item(self):
        focused = QApplication.focusWidget()
        if isinstance(focused, QTableWidget) and focused.rowCount() > 0:
            focused.setCurrentCell(focused.rowCount() - 1, 0)

    def _clear_all_inputs(self):
        if hasattr(self.parent, "input_widgets"):
            for widget in self.parent.input_widgets.values():
                if isinstance(widget, (QLineEdit, QTextEdit)):
                    widget.clear()
            self._log_info("모든 입력 필드를 지웠습니다.")

    def _save_column_settings(self):
        """✅ [복원] 컬럼 설정 저장"""
        if hasattr(self.parent, "save_column_settings_action"):
            self.parent.save_column_settings_action()  # 이미 올바르게 되어 있으므로 확인만 합니다.

    def _load_column_settings(self):
        """✅ [복원] 컬럼 설정 불러오기"""
        if hasattr(self.parent, "load_column_settings_action"):
            self.parent.load_column_settings_action()  # 이미 올바르게 되어 있으므로 확인만 합니다.

    def _open_html_viewer(self):
        """✅ [복구] HTML 뷰어"""
        if hasattr(self.parent, "show_html_viewer"):
            self.parent.show_html_viewer()
        else:
            self._log_warning("HTML 뷰어 기능이 현재 탭에 없습니다.")

    def _open_pandas_viewer(self):
        """✅ [복구] Pandas 뷰어"""
        if hasattr(self.parent, "show_pandas_viewer"):
            self.parent.show_pandas_viewer()
        else:
            self._log_warning("Pandas 뷰어 기능이 현재 탭에 없습니다.")

    def _show_all_columns(self):
        focused = QApplication.focusWidget()
        # ✅ QTableView도 지원하도록 수정
        if isinstance(focused, (QTableWidget, QTableView)):
            if hasattr(focused, "columnCount"):  # QTableWidget
                for i in range(focused.columnCount()):
                    focused.setColumnHidden(i, False)
            elif hasattr(focused, "model"):  # QTableView
                model = focused.model()
                if model:
                    for i in range(model.columnCount()):
                        focused.setColumnHidden(i, False)
            self._log_info("모든 컬럼을 표시합니다.")

    def _hide_all_columns(self):
        focused = QApplication.focusWidget()
        # ✅ QTableView도 지원하도록 수정
        if isinstance(focused, (QTableWidget, QTableView)):
            if hasattr(focused, "columnCount"):  # QTableWidget
                for i in range(1, focused.columnCount()):
                    focused.setColumnHidden(i, True)
            elif hasattr(focused, "model"):  # QTableView
                model = focused.model()
                if model:
                    for i in range(1, model.columnCount()):
                        focused.setColumnHidden(i, True)
            self._log_info("첫 번째 컬럼을 제외하고 모두 숨깁니다.")

    def _clear_all_filters(self):
        """✅ [복구] 모든 필터 지우기"""
        if hasattr(self.parent, "table_widget"):
            header = self.parent.table_widget.horizontalHeader()
            if hasattr(header, "clear_all_filters"):
                header.clear_all_filters()
                self._log_info("모든 필터를 제거했습니다.")
            else:
                self._log_warning("필터 지우기 기능이 현재 헤더에 없습니다.")

    def _log_info(self, message):
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(f"⌨️ {message}", "INFO")

    def _log_warning(self, message):
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(f"⚠️ {message}", "WARNING")

    def _log_error(self, message):
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(f"❌ {message}", "ERROR")

    def cleanup(self):
        for shortcut in self.shortcuts:
            shortcut.deleteLater()
        self.shortcuts.clear()


# === 외부 인터페이스 ===


def setup_shortcuts(parent, app_instance):
    """단축키 시스템 설정"""
    shortcut_manager = ShortcutManager(parent, app_instance)
    if not hasattr(parent, "_shortcut_managers"):
        parent._shortcut_managers = []
    parent._shortcut_managers.append(shortcut_manager)
    if hasattr(app_instance, "log_message"):
        app_instance.log_message("✅ 단축키 시스템 설정 완료 (모든 기능 복구)", "INFO")
    return shortcut_manager


def cleanup_shortcuts(parent):
    """단축키 정리"""
    if hasattr(parent, "_shortcut_managers"):
        for manager in parent._shortcut_managers:
            manager.cleanup()
        parent._shortcut_managers.clear()


def show_shortcuts_help(parent):
    """단축키 도움말 대화상자"""
    title = "단축키 안내"
    shortcuts = {
        "검색": [
            ("Ctrl + Enter", "검색 시작"),
            ("Escape", "검색 중지"),
        ],
        "결과 탐색": [
            ("Ctrl + F", "결과 내 찾기"),
            ("F3", "다음 찾기"),
            ("Shift + F3", "이전 찾기"),
            ("Ctrl + R", "검색 결과로 이동"),
            ("Ctrl + Home", "첫 항목으로 이동"),
            ("Ctrl + End", "마지막 항목으로 이동"),
        ],
        "데이터 편집/복사": [
            ("Ctrl + A", "전체 선택"),
            ("Ctrl + C", "선택 복사"),
            ("Ctrl + L", "입력 필드 지우기"),
            ("Ctrl + Shift + M", "마크다운으로 복사"),
        ],
        "보기 및 기능": [
            ("Ctrl + 1/2/3", "각 입력창으로 이동"),
            ("Ctrl + H", "HTML 뷰어"),
            ("Ctrl + D", "상세 데이터 보기"),
            ("Ctrl + Shift + A", "모든 컬럼 표시"),
            ("Ctrl + Shift + H", "일부 컬럼 숨기기"),
            ("Ctrl + Shift + F", "모든 필터 지우기"),
            ("Ctrl + Shift + C/V", "컬럼 설정 저장/로드"),
        ],
    }
    message = "<b> 자주 사용하는 단축키 목록입니다. </b><br><br>"
    for category, items in shortcuts.items():
        message += f"<b>- {category} -</b><br>"
        for key, desc in items:
            message += f"&nbsp;&nbsp;<b>{key}</b>: {desc}<br>"
        message += "<br>"

    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setTextFormat(Qt.RichText)
    msg_box.setText(message)
    msg_box.setIcon(QMessageBox.Icon.Information)
    # ✅ [추가] 외부 클릭 시 닫기 기능 적용
    from qt_utils import enable_modal_close_on_outside_click

    enable_modal_close_on_outside_click(msg_box)
    apply_dark_title_bar(msg_box)

    msg_box.exec()
