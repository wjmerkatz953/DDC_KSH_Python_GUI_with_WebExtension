# ===== 신규 파일: qt_TabView_MARC_Editor.py =====
# -*- coding: utf-8 -*-
# 파일명: qt_TabView_MARC_Editor.py
# 설명: MARC 추출 로직 편집기 탭 - PySide6 포팅 완전판
# 버전: v2.1.0
# 수정일: 2025-10-18
#
# 변경 이력:
# v2.1.0 (2025-10-18)
# - [기능 추가] QSplitter 자동 저장/복구 기능 추가
#   : splitter → self.main_splitter (코드 편집기와 결과 콘솔 분할)
#   : 앱 종료 시 스플리터 크기가 자동으로 DB에 저장되고 재시작 시 복구됨

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QTextEdit,
    QPushButton,
    QDialog,
    QMessageBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QComboBox,
    QDialogButtonBox,
    QSplitter,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui_constants import U
from preset_manager import (
    get_preset_names,
    get_preset_content,
    add_or_update_preset,
    save_last_used_preset,
    load_last_used_preset,
    delete_preset,
    rename_preset,
)
from qt_TabView_MARC_Extractor import DEFAULT_MARC_LOGIC_CODE
from qt_context_menus import setup_widget_context_menu


class PresetDialog(QDialog):
    """프리셋 선택을 위한 공용 대화상자"""

    def __init__(self, title, label, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))

        self.combo = QComboBox()
        if items:
            self.combo.addItems(items)
        layout.addWidget(self.combo)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_selected_item(self):
        return self.combo.currentText()


class QtMARCEditorTab(QWidget):
    def __init__(self, config, app_instance):
        super().__init__()
        self.config = config
        self.app_instance = app_instance

        self.setup_ui()
        self.setup_connections()
        self._load_presets_to_ui()

    def setup_ui(self):
        # 메인 레이아웃: 탭 전체의 기본이 되는 수직 레이아웃입니다.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 3, 6, 3)
        main_layout.setSpacing(U.PADDING_WIDGET_Y)

        # -------------------
        # ✅ [핵심 수정 1] 코드 편집기와 결과 콘솔을 담을 수직 QSplitter를 생성합니다.
        self.main_splitter = QSplitter(Qt.Vertical)
        # -------------------

        # ✅ [기존] 코드 편집기 그룹박스 (수정 없음)
        editor_group = QGroupBox()
        editor_layout = QVBoxLayout(editor_group)
        editor_layout.setContentsMargins(6, 6, 6, 6)
        self.marc_logic_editor = QTextEdit()
        self.marc_logic_editor.setFont(QFont("Consolas", 10))
        self.marc_logic_editor.setLineWrapMode(QTextEdit.NoWrap)
        editor_layout.addWidget(self.marc_logic_editor)
        setup_widget_context_menu(self.marc_logic_editor, self.app_instance)

        # -------------------
        # ✅ [핵심 수정 2] 편집기 그룹을 main_layout 대신 splitter의 상단 위젯으로 추가합니다.
        self.main_splitter.addWidget(editor_group)
        # -------------------

        # ✅ [기존] 모든 버튼과 프리셋 레이블을 담을 통합 컨트롤 바 (수정 없음)
        unified_controls_frame = QFrame()
        unified_controls_layout = QHBoxLayout(unified_controls_frame)
        unified_controls_layout.setContentsMargins(0, 6, 0, 0)

        self.run_button = QPushButton("코드 실행")
        self.clear_code_button = QPushButton("코드 지우기")
        self.reset_code_button = QPushButton("코드 초기화")
        self.clear_output_button = QPushButton("결과 지우기")
        self.load_preset_button = QPushButton("불러오기")
        self.rename_preset_button = QPushButton("이름 변경")
        self.save_preset_button = QPushButton("프리셋 저장")
        self.delete_preset_button = QPushButton("삭제")
        self.current_preset_label = QLabel("현재 프리셋: 없음")

        unified_controls_layout.addWidget(self.run_button)
        unified_controls_layout.addWidget(self.clear_code_button)
        unified_controls_layout.addWidget(self.reset_code_button)
        unified_controls_layout.addWidget(self.clear_output_button)
        unified_controls_layout.addSpacing(20)  # 버튼 그룹 간 간격
        unified_controls_layout.addWidget(self.load_preset_button)
        unified_controls_layout.addWidget(self.rename_preset_button)
        unified_controls_layout.addWidget(self.save_preset_button)
        unified_controls_layout.addWidget(self.delete_preset_button)
        unified_controls_layout.addStretch()  # 레이블을 오른쪽 끝으로 밀어냄
        unified_controls_layout.addWidget(self.current_preset_label)

        # ✅ [기존] 결과 콘솔 그룹박스
        console_group = QGroupBox()
        console_layout = QVBoxLayout(console_group)
        console_layout.setContentsMargins(6, 6, 6, 6)
        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setFont(QFont("Consolas", 9))

        # -------------------
        # ❌ [핵심 수정 3] 콘솔의 최대 높이를 제한하던 아래 코드를 '제거'합니다.
        # self.output_console.setMaximumHeight(200)
        # -------------------

        console_layout.addWidget(self.output_console)
        setup_widget_context_menu(self.output_console, self.app_instance)

        # -------------------
        # ✅ [핵심 수정 4] 결과 콘솔 그룹을 main_layout 대신 splitter의 하단 위젯으로 추가합니다.
        self.main_splitter.addWidget(console_group)

        # ✅ [핵심 수정 5] 이제 main_layout에 splitter와 컨트롤 바를 순서대로 추가합니다.
        # stretch factor를 1로 주어 splitter가 최대한 많은 공간을 차지하게 합니다.
        main_layout.addWidget(self.main_splitter, 1)
        main_layout.addWidget(unified_controls_frame)  # 컨트롤 바는 하단에 고정됩니다.

        # ✅ [핵심 수정 6] 스플리터의 초기 비율을 설정하여 보기 좋게 시작합니다. (상단:하단)
        self.main_splitter.setSizes([700, 300])

    def setup_connections(self):
        self.run_button.clicked.connect(self.run_custom_logic)
        self.clear_code_button.clicked.connect(self.marc_logic_editor.clear)
        self.reset_code_button.clicked.connect(self._reset_logic_code)
        self.clear_output_button.clicked.connect(self.output_console.clear)
        self.save_preset_button.clicked.connect(self._open_save_preset_modal)
        self.load_preset_button.clicked.connect(self._open_load_preset_modal)
        self.rename_preset_button.clicked.connect(self._open_rename_preset_modal)
        self.delete_preset_button.clicked.connect(self._open_delete_preset_modal)

    def run_custom_logic(self):
        extractor_tab = getattr(self.app_instance, "marc_extractor_tab", None)
        if not extractor_tab:
            QMessageBox.critical(self, "오류", "MARC 추출 탭을 찾을 수 없습니다.")
            return

        extractor_tab.start_extraction()
        self.output_console.setText(
            "'MARC 추출' 탭에서 코드 실행을 시작했습니다.\n결과는 해당 탭에서 확인하세요."
        )

    def _reset_logic_code(self):
        if (
            QMessageBox.question(
                self, "확인", "현재 코드를 기본 코드로 초기화하시겠습니까?"
            )
            == QMessageBox.Yes
        ):
            self.marc_logic_editor.setText(DEFAULT_MARC_LOGIC_CODE)
            self.current_preset_label.setText("현재 프리셋: 없음")

    def _open_save_preset_modal(self):
        text, ok = QInputDialog.getText(
            self, "프리셋 저장", "저장할 프리셋 이름을 입력하세요:"
        )
        if ok and text:
            code = self.get_logic_code()
            if add_or_update_preset(text, code):
                self._apply_preset_to_editor(text)
                QMessageBox.information(
                    self, "성공", f"프리셋 '{text}'을(를) 저장했습니다."
                )
            else:
                QMessageBox.critical(self, "오류", "프리셋 저장에 실패했습니다.")

    def _open_load_preset_modal(self):
        presets = get_preset_names()
        if not presets:
            QMessageBox.information(self, "알림", "저장된 프리셋이 없습니다.")
            return

        dialog = PresetDialog(
            "프리셋 불러오기", "불러올 프리셋을 선택하세요:", presets, self
        )
        if dialog.exec():
            selected = dialog.get_selected_item()
            self._apply_preset_to_editor(selected)

    def _open_rename_preset_modal(self):
        current_preset = self.current_preset_label.text().replace("현재 프리셋: ", "")
        if current_preset == "없음":
            QMessageBox.information(
                self, "알림", "먼저 프리셋을 불러오거나 저장해주세요."
            )
            return

        new_name, ok = QInputDialog.getText(
            self, "프리셋 이름 변경", f"'{current_preset}'의 새 이름을 입력하세요:"
        )
        if ok and new_name:
            if rename_preset(current_preset, new_name):
                self._apply_preset_to_editor(new_name)
                QMessageBox.information(self, "성공", "이름이 변경되었습니다.")
            else:
                QMessageBox.critical(self, "오류", "이름 변경에 실패했습니다.")

    def _open_delete_preset_modal(self):
        presets = get_preset_names()
        if not presets:
            QMessageBox.information(self, "알림", "저장된 프리셋이 없습니다.")
            return

        dialog = PresetDialog(
            "프리셋 삭제", "삭제할 프리셋을 선택하세요:", presets, self
        )
        if dialog.exec():
            selected = dialog.get_selected_item()
            if (
                QMessageBox.question(
                    self, "확인", f"프리셋 '{selected}'을(를) 정말 삭제하시겠습니까?"
                )
                == QMessageBox.Yes
            ):
                if delete_preset(selected):
                    self._load_presets_to_ui()  # 목록 갱신 및 기본 로드
                    QMessageBox.information(
                        self, "성공", f"'{selected}' 프리셋이 삭제되었습니다."
                    )
                else:
                    QMessageBox.critical(self, "오류", "프리셋 삭제에 실패했습니다.")

    def _load_presets_to_ui(self):
        last_used = load_last_used_preset()
        preset_names = get_preset_names()
        if last_used and last_used in preset_names:
            self._apply_preset_to_editor(last_used)
        else:
            self._reset_logic_code()

    def _apply_preset_to_editor(self, preset_name):
        code = get_preset_content(preset_name)
        if code:
            self.marc_logic_editor.setText(code)
            self.current_preset_label.setText(f"현재 프리셋: {preset_name}")
            save_last_used_preset(preset_name)

    def get_logic_code(self):
        return self.marc_logic_editor.toPlainText().strip()
