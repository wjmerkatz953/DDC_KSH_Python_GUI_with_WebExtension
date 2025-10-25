# ===== 최종 수정본: qt_TabView_MARC_Extractor.py =====
# -*- coding: utf-8 -*-
# 파일명: qt_TabView_MARC_Extractor.py
# 설명: MARC 추출기 탭 (모든 기능 복구 최종 버전)
# 버전: v2.1.0
# 수정일: 2025-10-18
#
# 변경 이력:
# v2.1.0 (2025-10-18)
# - [기능 추가] QSplitter 자동 저장/복구 기능 추가
#   : v_splitter → self.v_splitter (F 필드 테이블과 하단 뷰 분할)
#   : h_splitter → self.h_splitter (좌우 MARC 뷰 분할)
#   : 앱 종료 시 두 개의 스플리터 크기가 자동으로 DB에 저장되고 재시작 시 복구됨

import io
import contextlib
import re
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QTextEdit,
    QPushButton,
    QTableView,
    QHeaderView,
    QSplitter,
    QMessageBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QApplication,
)
from PySide6.QtGui import (
    QStandardItemModel,
    QStandardItem,
    QFont,
    QKeySequence,
    QShortcut,
)  # ✅ [추가]
from PySide6.QtCore import Qt, QThread, Signal, QTimer

from ui_constants import U
from marc_parser import extract_marc_data_to_f_fields, determine_special_call_number
from qt_context_menus import setup_widget_context_menu
from qt_data_transfer_manager import send_marc_data_to_tabs
from qt_copy_feedback import copy_to_clipboard_with_feedback

DEFAULT_MARC_LOGIC_CODE = """# -*- coding: utf-8 -*-
# 이 곳에 MARC 추출 로직을 작성하세요.
# 이 코드는 반드시 (f_fields 딕셔너리, full_marc_string 문자열) 튜플을 반환해야 합니다.

import re

def _generate_marcedit_style_string(raw_marc_text, parsed_data):
    \"\"\" MARC 데이터를 MARCedit 스타일 문자열로 변환하는 헬퍼 함수 \"\"\"
    output_lines = []
    try:
        start_index = raw_marc_text.find('LDR')
        end_index = raw_marc_text.find('참고정보')
        if start_index == -1: return "오류: MARC 데이터(LDR)를 찾을 수 없습니다."
        marc_block = raw_marc_text[start_index:] if end_index == -1 else raw_marc_text[start_index:end_index]

        ldr_values = parsed_data.get('LDR', '').replace(' ', '')
        output_lines.append(f"=LDR  {ldr_values.ljust(5)} 22     c 4500")
        output_lines.append(f"=007  {parsed_data.get('007', '')}")

        match_008 = re.search(r'008\\s*\\n(.*?)(?=\\n\\s*020)', marc_block, re.DOTALL)
        if match_008:
            output_lines.append("=008")
            content = match_008.group(1).strip()
            lines = [line.strip() for line in content.split('\\n') if line.strip()]
            i = 0
            while i < len(lines):
                label = lines[i]
                if (i + 1) < len(lines) and ':' not in lines[i+1] and not re.match(r'^[가-힣]', lines[i+1]):
                    value = lines[i+1]
                    output_lines.append(f"  {label}: {value}")
                    i += 2
                else:
                    output_lines.append(f"  {label}")
                    i += 1

        for tag in sorted(parsed_data.keys()):
            if tag.isdigit() and tag >= '020':
                for field in parsed_data[tag]:
                    ind1 = field.get('ind1', ' ').strip() or '\\\\'
                    ind2 = field.get('ind2', ' ').strip() or '\\\\'
                    subfield_strings = [f"${code}{value}" for code, value in field.get('subfields', [])]
                    all_subfields = "".join(subfield_strings)
                    output_lines.append(f"={tag}  {ind1}{ind2}{all_subfields}")
        return "\\n".join(output_lines)
    except Exception as e:
        return f"Full MARC 생성 중 오류 발생: {e}"

def custom_extract_marc_data(raw_marc_text, app_instance):
    \"\"\" F1-10 딕셔너리와 Full MARC 문자열을 모두 반환하는 메인 함수 \"\"\"
    # 1. 내장된 F1-F10 추출 로직 실행
    f_fields = extract_marc_data_to_f_fields(raw_marc_text, app_instance)

    # 2. Full MARC 문자열 생성을 위한 별도의 파서 실행 (UI 표시용)
    # 이 파서는 _generate_marcedit_style_string에서 사용할 데이터 구조를 만듭니다.
    parsed_data_for_string = {}
    try:
        start_index = raw_marc_text.find('LDR')
        end_index = raw_marc_text.find('참고정보')
        if start_index != -1:
            marc_block = raw_marc_text[start_index:] if end_index == -1 else raw_marc_text[start_index:end_index]
            ldr_match = re.search(r'LDR\\s*\\n(.*?)(?=\\n\\s*007)', marc_block, re.DOTALL)
            if ldr_match:
                ldr_content = ldr_match.group(1).strip()
                ldr_values = [line.strip() for line in ldr_content.split('\\n') if not re.search(r'[가-힣]', line)]
                parsed_data_for_string['LDR'] = ' '.join(filter(None, ldr_values))

            field_007_match = re.search(r'007\\s*([^\\n]+)', marc_block)
            if field_007_match:
                parsed_data_for_string['007'] = field_007_match.group(1).strip()

            variable_fields_block_start = marc_block.find('020') if '020' in marc_block else -1
            if variable_fields_block_start != -1:
                variable_fields_block = marc_block[variable_fields_block_start:]
                fields = re.split(r'^\\s*(\\d{3})', variable_fields_block, flags=re.MULTILINE)
                for i in range(1, len(fields), 2):
                    tag, content = fields[i], fields[i+1]
                    if '▼' not in content: continue
                    parts = content.split('▼', 1)
                    indicators_raw, data = parts[0], '▼' + parts[1]
                    indicators = re.findall(r'\\S', indicators_raw)
                    ind1 = indicators[0] if indicators else ' '
                    ind2 = indicators[1] if len(indicators) > 1 else ' '
                    subfields = [(sf[0], sf[1:]) for sf in data.strip('▲\\n').split('▼') if sf]
                    field_entry = {'ind1': ind1, 'ind2': ind2, 'subfields': subfields}
                    if tag not in parsed_data_for_string: parsed_data_for_string[tag] = []
                    parsed_data_for_string[tag].append(field_entry)
    except Exception:
        pass # 오류가 나도 일단 진행

    # 3. Full MARC 문자열 생성
    full_marc_string = _generate_marcedit_style_string(raw_marc_text, parsed_data_for_string)

    # 4. 두 개의 결과물을 튜플로 반환
    return (f_fields, full_marc_string)
"""


class MarcExtractThread(QThread):
    extraction_finished = Signal(tuple)
    extraction_failed = Signal(str)

    def __init__(self, logic_code, marc_text, app_instance):
        super().__init__()
        self.logic_code = logic_code or DEFAULT_MARC_LOGIC_CODE
        self.marc_text = marc_text
        self.app_instance = app_instance

    def run(self):
        old_stdout = io.StringIO()
        try:
            exec_globals = {
                "app_instance": self.app_instance,
                "raw_marc_text": self.marc_text,
                "__builtins__": __builtins__,
                "re": re,
                "extract_marc_data_to_f_fields": extract_marc_data_to_f_fields,
                "determine_special_call_number": determine_special_call_number,
            }
            with contextlib.redirect_stdout(old_stdout):
                exec(self.logic_code, exec_globals, exec_globals)
                result_tuple = exec_globals["custom_extract_marc_data"](
                    self.marc_text, self.app_instance
                )

            if not (isinstance(result_tuple, tuple) and len(result_tuple) == 2):
                raise TypeError(
                    "코드가 (f_fields 딕셔너리, full_marc_string) 튜플을 반환해야 합니다."
                )
            self.extraction_finished.emit(result_tuple)
        except Exception as e:
            error_message = f"코드 실행 중 오류 발생:\n{old_stdout.getvalue()}\n{e}"
            self.extraction_failed.emit(error_message)


class QtMARCExtractorTab(QWidget):
    def __init__(self, config, app_instance):
        super().__init__()
        self.config = config
        self.app_instance = app_instance
        self._auto_extract_timer = QTimer(self)
        self._auto_extract_timer.setSingleShot(True)
        self._auto_extract_timer.setInterval(500)  # 0.5초 지연

        # ✅ [수정] CTk 버전과 동일한 재진입 방지 플래그
        self._is_extracting = False

        self.setup_ui()
        self.setup_connections()

        QTimer.singleShot(100, self._show_initial_sample_results)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, U.PADDING_FRAME, 6, U.PADDING_FRAME)
        main_layout.setSpacing(U.PADDING_WIDGET_Y)

        # ✅ [추가] 설정에서 입력창 높이 가져오기
        input_height = self._get_marc_input_height()

        input_bar_frame = QFrame()
        input_bar_frame.setMaximumHeight(input_height)
        input_bar_layout = QHBoxLayout(input_bar_frame)
        input_bar_layout.setContentsMargins(0, 4, 0, 2)

        self.marc_input_text = QTextEdit()
        # ✅ [추가] MARC_Gemini 그룹 스타일 적용을 위한 objectName 설정
        self.marc_input_text.setObjectName("MARC_Gemini_Input")
        # ✅ [추가] 붙여넣기 시 서식(색상 등)을 무시하고 일반 텍스트로만 받도록 설정합니다.
        self.marc_input_text.setAcceptRichText(False)
        self.marc_input_text.setPlaceholderText(
            "MARC 원본 텍스트를 여기에 붙여넣으세요..."
        )
        self.marc_input_text.setMaximumHeight(input_height)
        self.marc_input_text.setFont(QFont("Consolas", 9))
        # ✅ [핵심 수정] 트리메뉴 모드에서도 정확한 배경색 적용을 위해 인라인 스타일 명시
        from ui_constants import get_color

        self.marc_input_text.setStyleSheet(
            f"""
            QTextEdit#MARC_Gemini_Input {{
                background-color: {get_color('INPUT_WIDGET_BG')};
                border: 0.8px solid {get_color('BORDER_MEDIUM')};
                border-radius: {U.CORNER_RADIUS_DEFAULT}px;
                padding: 6px;
            }}
            QTextEdit#MARC_Gemini_Input:focus {{
                border: 1px solid {get_color('HIGHLIGHT_SELECTED')};
            }}
        """
        )

        self.extract_button = QPushButton("MARC 추출")
        self.clear_input_button = QPushButton("입력 지우기")
        self.clear_results_button = QPushButton("결과 지우기")

        input_bar_layout.addWidget(self.marc_input_text)
        setup_widget_context_menu(self.marc_input_text, self.app_instance)
        input_bar_layout.addWidget(self.extract_button)
        input_bar_layout.addWidget(self.clear_input_button)
        input_bar_layout.addWidget(self.clear_results_button)
        input_bar_layout.setStretch(0, 1)
        main_layout.addWidget(input_bar_frame)

        # 1. F 필드 테이블과 하단 뷰를 담을 수직 스플리터 생성
        self.v_splitter = QSplitter(Qt.Vertical)

        f_fields_group = QGroupBox()
        f_fields_layout = QVBoxLayout(f_fields_group)
        self.f_fields_table = QTableView()
        self.f_fields_model = QStandardItemModel(10, 3)
        self.f_fields_model.setHorizontalHeaderLabels(["필드", "추출내용", "추출결과"])
        self.f_fields_table.setModel(self.f_fields_model)
        self.f_fields_table.setMinimumHeight(230)

        # ✅ [핵심 추가] 테이블 헤더 색상을 다른 탭과 통일 (WIDGET_BG_DEFAULT 사용)
        self.f_fields_table.horizontalHeader().setStyleSheet(
            f"""
            QHeaderView::section {{
                background-color: {U.WIDGET_BG_DEFAULT};
                color: {U.TEXT_BUTTON};
                padding: 0px 0px 0px 0px;
                border: none;
                font-weight: bold;
                text-align: center;
            }}
            QHeaderView::section:hover {{
                background-color: {U.ACCENT_BLUE};
                color: {U.TEXT_BUTTON};
            }}
        """
        )

        self.f_fields_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.f_fields_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.f_fields_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.f_fields_table.setEditTriggers(QTableView.NoEditTriggers)
        f_fields_layout.addWidget(self.f_fields_table)
        setup_widget_context_menu(self.f_fields_table, self.app_instance)

        # 2. F 필드 그룹을 수직 스플리터에 추가
        self.v_splitter.addWidget(f_fields_group)

        # 3. 하단 좌/우 뷰를 담을 수평 스플리터 생성
        self.h_splitter = QSplitter(Qt.Horizontal)
        left_group = QGroupBox(
            "Full MARC (LDR 포함 전체)"
        )  # 기존 splitter -> h_splitter
        left_layout = QVBoxLayout(left_group)
        left_layout.setContentsMargins(5, 20, 5, 5)
        self.full_marc_left = QTextEdit()
        self.full_marc_left.setReadOnly(True)
        self.full_marc_left.setFont(QFont("Consolas", 9))
        left_layout.addWidget(self.full_marc_left)
        setup_widget_context_menu(self.full_marc_left, self.app_instance)

        right_group = QGroupBox("서지 데이터 (020 필드부터)")
        right_layout = QVBoxLayout(right_group)
        right_layout.setContentsMargins(5, 20, 5, 5)
        self.full_marc_right = QTextEdit()
        self.full_marc_right.setReadOnly(True)
        self.full_marc_right.setFont(QFont("Consolas", 9))
        right_layout.addWidget(self.full_marc_right)
        setup_widget_context_menu(self.full_marc_right, self.app_instance)

        self.h_splitter.addWidget(left_group)
        self.h_splitter.addWidget(right_group)
        self.h_splitter.setSizes([500, 500])

        # 4. 수평 스플리터를 수직 스플리터에 추가
        self.v_splitter.addWidget(self.h_splitter)

        # 5. 최종적으로 수직 스플리터를 메인 레이아웃에 추가
        main_layout.addWidget(self.v_splitter, 1)
        self.v_splitter.setSizes([350, 450])  # F 필드 테이블과 하단 뷰의 초기 비율 설정

    def setup_connections(self):
        self.extract_button.clicked.connect(self.start_extraction)
        self.clear_input_button.clicked.connect(self.marc_input_text.clear)
        self.clear_results_button.clicked.connect(self._clear_results)

        # ✅ [수정] 자동 추출 기능 연결을 복구합니다.
        self.marc_input_text.textChanged.connect(self._schedule_auto_extract)
        self._auto_extract_timer.timeout.connect(self.start_extraction)

        # ✅ [추가] 테이블 뷰 선택 변경 시 상세 정보 업데이트
        if hasattr(self, "f_fields_table") and self.f_fields_table.selectionModel():
            self.f_fields_table.selectionModel().currentChanged.connect(
                self._update_detail_view
            )
        # ✅ [핵심 추가] Ctrl+C 단축키에 대한 사용자 정의 복사 핸들러 연결
        copy_shortcut = QShortcut(QKeySequence.Copy, self)
        copy_shortcut.activated.connect(self.handle_copy)

    # ✅ [핵심 추가] 사용자 정의 복사 메서드
    def handle_copy(self):
        """Ctrl+C 단축키를 처리하여 복사 피드백을 표시합니다."""
        focused_widget = QApplication.focusWidget()
        text_to_copy = ""

        # 현재 포커스된 위젯이 QTextEdit인 경우 (입력창, 좌/우측 결과창)
        if isinstance(focused_widget, QTextEdit):
            cursor = focused_widget.textCursor()
            if cursor.hasSelection():
                # 줄바꿈 문자(U+2029)로 인해 발생하는 문제를 표준 줄바꿈(\n)으로 변경
                text_to_copy = cursor.selectedText().replace("\u2029", "\n")

        # 현재 포커스된 위젯이 QTableView인 경우 (F-Fields 테이블)
        elif focused_widget == self.f_fields_table:
            selection_model = self.f_fields_table.selectionModel()
            if selection_model and selection_model.hasSelection():
                # 여러 셀이 선택된 경우, 탭으로 구분된 텍스트로 만듦 (Excel 붙여넣기 호환)
                selected_indexes = selection_model.selectedIndexes()
                rows_data = {}
                for index in selected_indexes:
                    row, col = index.row(), index.column()
                    if row not in rows_data:
                        rows_data[row] = {}
                    rows_data[row][col] = index.data() or ""

                text_lines = []
                for row in sorted(rows_data.keys()):
                    # 해당 행에서 선택된 모든 열을 순서대로 가져옴
                    row_cells = []
                    for col in sorted(rows_data[row].keys()):
                        row_cells.append(str(rows_data[row][col]))
                    text_lines.append("\t".join(row_cells))
                text_to_copy = "\n".join(text_lines)

        # 복사할 텍스트가 있으면 피드백과 함께 클립보드에 저장
        if text_to_copy:
            copy_to_clipboard_with_feedback(
                text_to_copy, self.app_instance, parent_widget=self
            )

    def _update_detail_view(self, current, previous):
        """✅ [추가] 선택된 행의 상세 정보를 메인 윈도우의 detail_display에 표시"""
        if not current.isValid():
            if hasattr(self.app_instance, "main_window"):
                self.app_instance.main_window.detail_display.clear()
            return

        row = current.row()
        model = self.f_fields_model

        from ui_constants import UI_CONSTANTS

        U = UI_CONSTANTS
        from qt_utils import linkify_text

        header_style = f"color: {U.ACCENT_GREEN}; font-weight: bold;"
        content_lines = []

        # 3개 컬럼: 필드, 추출내용, 추출결과
        for col in range(model.columnCount()):
            header = model.headerData(col, Qt.Horizontal, Qt.DisplayRole) or ""
            item = model.item(row, col)
            value = item.text() if item else ""

            styled_header = f'▶ <span style="{header_style}">{header}:</span>'
            content_lines.append(f"{styled_header} {value}")

        final_text = "\n".join(content_lines)

        # HTML 조립 및 표시
        if hasattr(self.app_instance, "main_window"):
            main_window = self.app_instance.main_window
            if hasattr(main_window, "detail_display"):
                main_window.detail_display.setOpenExternalLinks(True)

                lines = final_text.split("\n")
                html_lines = []

                for line in lines:
                    temp_line = line.strip()
                    if not temp_line:
                        continue

                    if '<span style="' in line:
                        linked_line = line
                    else:
                        linked_line = linkify_text(line)

                    link_style = (
                        f'style="color: {U.ACCENT_BLUE}; text-decoration: none;"'
                    )
                    linked_line = linked_line.replace(
                        "<a href=", f"<a {link_style} href="
                    )

                    linked_line = (
                        linked_line.replace("\r", "")
                        .replace("\u2029", "")
                        .replace("\xa0", " ")
                        .strip()
                    )

                    html_lines.append(
                        f'<div style="white-space: pre-wrap; margin: 0; padding: 0; line-height: 1.0; user-select: text; display: block;">{linked_line}</div>'
                    )

                final_html = "".join(html_lines)
                main_window.detail_display.setHtml(final_html)

    def _schedule_auto_extract(self):
        # 텍스트가 변경될 때마다 500ms 타이머를 (재)시작합니다.
        self._auto_extract_timer.start()

    def start_extraction(self):
        # ✅ [수정] CTk와 동일한 수동 플래그 방식으로 재진입을 방지합니다.
        if self._is_extracting:
            return
        self._is_extracting = True  # 플래그 설정

        raw_marc_text = self.get_input_text()
        if not raw_marc_text:
            self._is_extracting = False  # 작업 없으면 플래그 해제
            return

        logic_code = DEFAULT_MARC_LOGIC_CODE
        editor_tab = getattr(self.app_instance, "marc_editor_tab", None)
        if editor_tab:
            logic_code = editor_tab.get_logic_code()

        self.extract_button.setEnabled(False)
        self.app_instance.set_status_message("MARC 데이터 추출 중...")

        self.extraction_thread = MarcExtractThread(
            logic_code, raw_marc_text, self.app_instance
        )
        self.extraction_thread.extraction_finished.connect(self._on_extraction_finished)
        self.extraction_thread.extraction_failed.connect(self._on_extraction_failed)
        self.extraction_thread.start()

    def _on_extraction_finished(self, results):
        f_fields, full_marc_string = results
        self._update_f_fields_table(f_fields)

        right_content = ""
        try:
            start_pos = full_marc_string.find("=020")
            if start_pos == -1:
                lines = full_marc_string.split("\n")
                for i, line in enumerate(lines):
                    if line.strip().startswith("=0"):
                        start_pos = full_marc_string.find(line)
                        break
            if start_pos != -1:
                right_content = full_marc_string[start_pos:]
        except Exception:
            pass

        self.full_marc_left.setText(full_marc_string)
        self.full_marc_right.setText(right_content)

        self._finalize_extraction()
        self.app_instance.set_status_message("MARC 추출 완료!")
        self._send_data_to_other_tabs(f_fields)

    def _on_extraction_failed(self, error_msg):
        QMessageBox.critical(self, "추출 오류", error_msg)
        self._finalize_extraction()
        self.app_instance.set_status_message("MARC 추출 오류!")

    def _finalize_extraction(self):
        """✅ [추가] 추출 성공/실패 시 공통으로 호출될 마무리 함수"""
        self.extract_button.setEnabled(True)
        self._is_extracting = False  # 플래그 해제

    def _clear_results(self):
        self._clear_f_fields_table()
        self.full_marc_left.clear()
        self.full_marc_right.clear()

    def _clear_f_fields_table(self):
        field_labels = self.get_f_field_definitions()
        for row, (key, (num, desc)) in enumerate(field_labels.items()):
            self.f_fields_model.setItem(row, 0, QStandardItem(num))
            self.f_fields_model.setItem(row, 1, QStandardItem(desc))
            self.f_fields_model.setItem(row, 2, QStandardItem("(추출 대기 중)"))

    def _update_f_fields_table(self, f_fields_data):
        field_labels = self.get_f_field_definitions()
        for row, (key, (num, desc)) in enumerate(field_labels.items()):
            value = f_fields_data.get(key, "(추출 실패)")
            self.f_fields_model.setItem(row, 0, QStandardItem(num))
            self.f_fields_model.setItem(row, 1, QStandardItem(desc))
            self.f_fields_model.setItem(row, 2, QStandardItem(str(value)))

    def _send_data_to_other_tabs(self, f_fields):
        """추출된 MARC 데이터를 다른 탭으로 전송합니다."""
        if hasattr(self, "app_instance"):
            raw_marc_text = self.get_input_text()
            send_marc_data_to_tabs(self.app_instance, f_fields, raw_marc_text)

    def get_f_field_definitions(self):
        return {
            "F1_ISBN": ("F1", "ISBN"),
            "F2_Author_SurnameOrCorporate": ("F2", "저자-단일 성/단체명"),
            "F3_Author_FullOrMultiple": ("F3", "저자-전체/복수"),
            "F4_245_Unprocessed": ("F4", "245 필드 무가공"),
            "F5_LatinNumericDetection": ("F5", "245 필드 내 알파벳/숫자"),
            "F6_LatinNumericToKorean": ("F6", "245 필드 라틴어/숫자 -> 한글 변환"),
            "F7_OriginalTitle_WithArticle": ("F7", "원서명 (관사 포함)"),
            "F8_OriginalTitle_WithoutArticle": ("F8", "원서명 (관사 제거)"),
            "F9_CallNumber": ("F9", "090 청구기호"),
            "F10_SpecialCallNumber": ("F10", "별치기호 판정"),
            "F11_DDC": ("F11", "082 DDC 번호"),
        }

    def get_input_text(self):
        return self.marc_input_text.toPlainText().strip()

    def _get_marc_input_height(self):
        """설정에서 MARC 입력창 높이를 가져옵니다."""
        if hasattr(self.app_instance, "db_manager") and self.app_instance.db_manager:
            value = self.app_instance.db_manager.get_setting("marc_input_height")
            # 값이 없으면 기본값 60 반환
            return int(value) if value else 60
        return 60

    def _show_initial_sample_results(self):
        example_data = {
            "F1_ISBN": "9791130667874",
            "F2_Author_SurnameOrCorporate": "Reid",
            "F3_Author_FullOrMultiple": "Reid, Taylor Jenkins, 이경아",
            "F4_245_Unprocessed": "말리부의 사랑법 :▼b테일러 젠킨스 리드 장편소설 /▼d테일러 젠킨스 리드 지음 ;▼e이경아 옮김",
            "F5_LatinNumericDetection": "",
            "F6_LatinNumericToKorean": "추후 기능 추가",
            "F7_OriginalTitle_WithArticle": "Malibu rising",
            "F8_OriginalTitle_WithoutArticle": "Malibu rising",
            "F9_CallNumber": "823.92R353m한",
            "F10_SpecialCallNumber": "LDM, LWM 등",
            "F11_DDC": "813.6",
        }
        self._update_f_fields_table(example_data)
        self.app_instance.log_message(
            "정보: MARC 추출 탭에 예시 데이터를 표시했습니다.", "INFO"
        )

    # ✅ [신규 추가] 탭 활성화 시 자동 포커스를 위한 메서드
    def set_initial_focus(self):
        """탭이 활성화될 때 MARC 입력 필드에 포커스를 설정하고, 기존 텍스트를 전체 선택합니다."""
        if self.marc_input_text:
            # -------------------
            # ✅ [수정] 포커스 설정과 전체 선택을 함께 실행
            def focus_and_select():
                self.marc_input_text.setFocus()
                self.marc_input_text.selectAll()

            QTimer.singleShot(0, focus_and_select)
            # -------------------
