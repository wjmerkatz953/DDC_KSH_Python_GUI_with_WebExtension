# -*- coding: utf-8 -*-
# 파일명: qt_TabView_Settings.py
# 버전: v1.0.1
# 설명: 앱 설정탭 - UI 스타일, 네비게이션 모드 등 설정
# 생성일: 2025-10-02
#
# 변경 이력:
# v1.0.1 (2025-10-02)
# - [수정] UI 상수를 사용하도록 배경색 변경
# - [수정] 메인 위젯, 스크롤 영역: BACKGROUND_PRIMARY
# - [수정] 섹션 프레임: BACKGROUND_SECONDARY
#
# v1.0.0 (2025-10-02)
# - Qt 설정 탭 초기 구현
# - 네비게이션 스타일 선택 (탭/트리메뉴)
# - UI 스타일, 일반 설정 섹션

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QFrame,
    QScrollArea,
    QMessageBox,
    QButtonGroup,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from ui_constants import UI_CONSTANTS as U


class QtSettingsTab(QWidget):
    """Qt 설정 탭"""

    def __init__(self, config, app_instance):
        super().__init__()
        self.config = config
        self.app_instance = app_instance
        # ✅ [추가] 새로 추가된 체크박스 위젯들을 관리하기 위한 딕셔너리
        self.automation_checkboxes = {}
        self.setup_ui()

    def setup_ui(self):
        """설정탭 UI를 구성합니다."""

        # 메인 레이아웃
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 6, 5, 6)
        main_layout.setSpacing(0)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {U.BACKGROUND_PRIMARY};
                border: none;
            }}
        """
        )

        # 스크롤 가능한 컨텐츠 위젯
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(5, 6, 5, 6)
        scroll_layout.setSpacing(15)

        # 제목
        title_label = QLabel("⚙️ 앱 설정")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        scroll_layout.addWidget(title_label)

        # ✅ [핵심 수정] 2열 레이아웃 생성
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(15)

        # 좌측 열
        left_column = QVBoxLayout()
        left_column.setSpacing(15)
        self._create_navigation_section(left_column)
        self._create_ui_style_section(left_column)
        self._create_marc_height_section(left_column)
        left_column.addStretch()

        # 우측 열
        right_column = QVBoxLayout()
        right_column.setSpacing(15)
        self._create_general_section(right_column)
        right_column.addStretch()

        # 좌우 열을 수평 레이아웃에 추가
        columns_layout.addLayout(left_column, 1)
        columns_layout.addLayout(right_column, 1)

        scroll_layout.addLayout(columns_layout)

        # 스트레치 추가 (하단 여백)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        # ✅ [핵심 수정] 저장/복원 버튼은 스크롤 영역 밖에 배치 (항상 보이도록)
        self._create_save_restore_section(main_layout)

    def _create_section_frame(self, parent_layout, title):
        """설정 섹션 프레임을 생성합니다."""
        # 섹션 프레임
        section_frame = QFrame()
        section_frame.setFrameShape(QFrame.StyledPanel)
        section_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {U.BACKGROUND_PRIMARY};
                border-radius: 0px;
                border: 0.6px solid {U.WIDGET_BG_DEFAULT};
            }}
        """
        )

        section_layout = QVBoxLayout(section_frame)
        section_layout.setContentsMargins(5, 5, 5, 5)
        section_layout.setSpacing(10)

        # 섹션 제목
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        section_layout.addWidget(title_label)

        parent_layout.addWidget(section_frame)

        return section_frame, section_layout

    def _create_navigation_section(self, parent_layout):
        """네비게이션 스타일 설정 섹션을 생성합니다."""
        section_frame, section_layout = self._create_section_frame(
            parent_layout, "📋 네비게이션 스타일"
        )

        # 현재 설정 가져오기
        current_style = self._get_navigation_style()

        # 라디오 버튼 그룹
        self.nav_button_group = QButtonGroup(self)

        # 일반 탭 스타일 라디오 버튼
        self.normal_radio = QRadioButton("일반 탭 (상단 탭뷰)")
        self.normal_radio.setChecked(current_style == "tab")
        self.nav_button_group.addButton(self.normal_radio, 0)
        section_layout.addWidget(self.normal_radio)

        # 트리메뉴 스타일 라디오 버튼
        self.tree_radio = QRadioButton("트리메뉴 스타일 (왼쪽 사이드바)")
        self.tree_radio.setChecked(current_style == "tree")
        self.nav_button_group.addButton(self.tree_radio, 1)
        section_layout.addWidget(self.tree_radio)

        # 설명 레이블
        description = QLabel(
            "• 일반 탭: 상단에 탭 바를 표시하는 전통적인 방식\n"
            "• 트리메뉴: 왼쪽에 계층적 메뉴를 표시하여 효율적인 탭 관리 제공\n"
            '  - 검색 관련 탭들을 "검색" 그룹으로 분류\n'
            '  - 도구 관련 탭들을 "도구" 그룹으로 분류'
        )
        description.setStyleSheet("color: #888888; font-size: 9pt;")
        description.setWordWrap(True)
        section_layout.addWidget(description)

    def _create_ui_style_section(self, parent_layout):
        """UI 스타일 설정 섹션을 생성합니다."""
        section_frame, section_layout = self._create_section_frame(
            parent_layout, "🎨 UI 스타일"
        )

        # 테마 설정
        theme_layout = QHBoxLayout()
        theme_label = QLabel("색상 테마:")
        theme_layout.addWidget(theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark (현재)", "Light", "Auto"])
        self.theme_combo.setCurrentIndex(0)
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()

        section_layout.addLayout(theme_layout)

    def _create_general_section(self, parent_layout):
        """일반 설정 섹션을 생성합니다."""
        section_frame, section_layout = self._create_section_frame(
            parent_layout, "🔧 일반 설정"
        )

        # 마지막 탭 복원 체크박스
        restore_last_tab = self._get_restore_last_tab_setting()
        self.restore_checkbox = QCheckBox("앱 시작 시 마지막 활성화된 탭 복원")
        self.restore_checkbox.setChecked(restore_last_tab)
        section_layout.addWidget(self.restore_checkbox)

        # 자동 저장 체크박스
        autosave = self._get_autosave_setting()
        self.autosave_checkbox = QCheckBox("검색 기록 자동 저장")
        self.autosave_checkbox.setChecked(autosave)
        section_layout.addWidget(self.autosave_checkbox)

        # -------------------
        # ✅ [위치 수정] 해외 도서관 설정을 탭별 자동화 설정 위로 이동
        # 해외 도서관 자동 번역 체크박스
        foreign_translation = self._get_foreign_auto_translation_setting()
        self.foreign_translation_checkbox = QCheckBox(
            "해외 도서관 검색 시 자동 번역 (NDL, BNE, BNF, DNB)"
        )
        self.foreign_translation_checkbox.setChecked(foreign_translation)
        section_layout.addWidget(self.foreign_translation_checkbox)
        # -------------------

        # --- 탭별 자동화 설정 (신규 추가) ---
        automation_frame = QFrame()
        automation_layout = QVBoxLayout(automation_frame)
        automation_layout.setContentsMargins(0, 10, 0, 0)

        automation_title = QLabel("탭별 자동화 설정")
        automation_font = QFont()
        automation_font.setBold(True)
        automation_title.setFont(automation_font)
        automation_layout.addWidget(automation_title)

        # 그리드 레이아웃으로 체크박스 정렬
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(10, 5, 0, 0)
        # ✅ [간격 수정] 수평 간격을 20에서 10으로 줄임
        grid_layout.setHorizontalSpacing(10)

        # -------------------
        # ✅ [레이아웃 수정] 헤더 위치 변경
        # 헤더 추가
        auto_search_label = QLabel("자동 검색")
        auto_switch_label = QLabel("자동 탭 전환")
        auto_search_label.setAlignment(Qt.AlignCenter)
        auto_switch_label.setAlignment(Qt.AlignCenter)
        grid_layout.addWidget(auto_search_label, 0, 0)
        grid_layout.addWidget(auto_switch_label, 0, 1)
        grid_layout.addWidget(QLabel(""), 0, 2)  # 빈 공간
        # -------------------

        # 설정할 탭 목록
        tabs_to_configure = {
            "nlk": "NLK",
            "ai_feed": "AI 피드",
            "ndl": "NDL",
            "western": "Western",
            "global": "Global",
            "dewey": "Dewey",
            "legal_deposit": "납본 ID 검색",
        }

        # 각 탭에 대한 체크박스 생성
        for i, (key, name) in enumerate(tabs_to_configure.items()):
            row = i + 1

            # -------------------
            # ✅ [레이아웃 수정] 체크박스를 탭 이름 앞으로 이동
            # 자동 검색 체크박스
            search_cb = QCheckBox()
            search_cb.setChecked(self._get_tab_automation_setting(key, "auto_search"))
            grid_layout.addWidget(search_cb, row, 0, Qt.AlignCenter)
            self.automation_checkboxes[f"{key}_auto_search"] = search_cb

            # 자동 탭 전환 체크박스
            switch_cb = QCheckBox()
            switch_cb.setChecked(self._get_tab_automation_setting(key, "auto_switch"))
            grid_layout.addWidget(switch_cb, row, 1, Qt.AlignCenter)
            self.automation_checkboxes[f"{key}_auto_switch"] = switch_cb

            # 탭 이름 레이블
            grid_layout.addWidget(QLabel(f"• {name}"), row, 2)
            # -------------------

        # -------------------
        # ✅ [핵심 수정] 컬럼 너비 비율 조정
        # 체크박스 컬럼(0, 1)은 늘리지 않고, 탭 이름 컬럼(2)이 남은 공간을 모두 차지하도록 설정
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 0)
        grid_layout.setColumnStretch(2, 1)
        # -------------------

        automation_layout.addLayout(grid_layout)
        section_layout.addWidget(automation_frame)

    def _create_marc_height_section(self, parent_layout):
        """MARC 추출 탭 입력창 높이 설정 섹션을 생성합니다."""
        section_frame, section_layout = self._create_section_frame(
            parent_layout, "📝 MARC 추출 탭 설정"
        )

        # 설명 레이블
        description = QLabel("MARC 추출탭 텍스트 입력창 높이:")
        description.setStyleSheet("color: #cccccc; font-size: 10pt;")
        section_layout.addWidget(description)

        # 그리드 레이아웃으로 체크박스 정렬
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(10, 5, 0, 0)
        grid_layout.setHorizontalSpacing(10)

        # 기본 높이 (60px) 체크박스
        current_height = self._get_marc_input_height_setting()
        self.marc_height_default_cb = QCheckBox()
        self.marc_height_default_cb.setChecked(current_height == 60)
        grid_layout.addWidget(self.marc_height_default_cb, 0, 0, Qt.AlignCenter)
        grid_layout.addWidget(QLabel("• 기본 (60px)"), 0, 1)

        # 확장 높이 (200px) 체크박스
        self.marc_height_extended_cb = QCheckBox()
        self.marc_height_extended_cb.setChecked(current_height == 200)
        grid_layout.addWidget(self.marc_height_extended_cb, 1, 0, Qt.AlignCenter)
        grid_layout.addWidget(QLabel("• 확장 (200px)"), 1, 1)

        # 컬럼 너비 비율 조정
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        section_layout.addLayout(grid_layout)

        # 체크박스 상호 배타적 동작 설정
        self.marc_height_default_cb.toggled.connect(
            lambda checked: self._on_marc_height_default_toggled(checked)
        )
        self.marc_height_extended_cb.toggled.connect(
            lambda checked: self._on_marc_height_extended_toggled(checked)
        )

        # 안내 메시지
        info_label = QLabel(
            "• 기본: 간단한 MARC 데이터 입력에 적합\n"
            "• 확장: 긴 MARC 데이터를 보기 편하게 입력\n"
            "• 변경 후 '설정 적용' 버튼을 눌러 저장하세요."
        )
        info_label.setStyleSheet("color: #888888; font-size: 9pt;")
        info_label.setWordWrap(True)
        section_layout.addWidget(info_label)

    def _create_save_restore_section(self, parent_layout):
        """저장/복원 버튼 섹션을 생성합니다."""
        # ✅ [수정] 스크롤 밖에 배치하므로 섹션 프레임 없이 직접 버튼 레이아웃 생성
        button_frame = QFrame()
        button_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {U.BACKGROUND_PRIMARY};
                border-top: 1px solid {U.WIDGET_BG_DEFAULT};
                padding: 10px;
            }}
        """
        )
        button_layout = QHBoxLayout(button_frame)

        # 설정 적용 버튼
        save_button = QPushButton("🔄 설정 적용")
        save_button.setStyleSheet(
            """
            QPushButton {
                background-color: #1e88e5;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:pressed {
                background-color: #1565c0;
            }
        """
        )
        save_button.clicked.connect(self._save_all_settings)
        button_layout.addWidget(save_button)

        # 기본값 복원 버튼
        reset_button = QPushButton("🔄 기본값 복원")
        reset_button.setStyleSheet(
            """
            QPushButton {
                background-color: #d32f2f;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #c62828;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
        """
        )
        reset_button.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(reset_button)

        # 재시작 안내 버튼
        restart_button = QPushButton("🔄 앱 재시작 안내")
        restart_button.setStyleSheet(
            """
            QPushButton {
                background-color: #388e3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #2e7d32;
            }
            QPushButton:pressed {
                background-color: #1b5e20;
            }
        """
        )
        restart_button.clicked.connect(self._show_restart_dialog)
        button_layout.addWidget(restart_button)

        # ✅ [수정] 프레임을 parent_layout에 추가
        parent_layout.addWidget(button_frame)

    # === 설정 처리 함수들 ===

    def _get_navigation_style(self):
        """현재 네비게이션 스타일을 가져옵니다."""
        if hasattr(self.app_instance, "db_manager") and self.app_instance.db_manager:
            return self.app_instance.db_manager.get_setting("navigation_style") or "tab"
        return "tab"

    def _get_restore_last_tab_setting(self):
        """마지막 탭 복원 설정을 가져옵니다."""
        if hasattr(self.app_instance, "db_manager") and self.app_instance.db_manager:
            value = self.app_instance.db_manager.get_setting("restore_last_tab")
            return value == "true" if value else True
        return True

    def _get_autosave_setting(self):
        """자동 저장 설정을 가져옵니다."""
        if hasattr(self.app_instance, "db_manager") and self.app_instance.db_manager:
            value = self.app_instance.db_manager.get_setting("autosave_history")
            return value == "true" if value else True
        return True

    def _get_tab_automation_setting(self, tab_key, setting_type):
        """탭별 자동화 설정을 가져옵니다."""
        if hasattr(self.app_instance, "db_manager") and self.app_instance.db_manager:
            setting_key = f"{tab_key}_{setting_type}"
            value = self.app_instance.db_manager.get_setting(setting_key)
            # 기본값은 True (활성화)
            return value == "true" if value else True
        return True

    def _get_foreign_auto_translation_setting(self):
        """해외 도서관 자동 번역 설정을 가져옵니다."""
        if hasattr(self.app_instance, "db_manager") and self.app_instance.db_manager:
            value = self.app_instance.db_manager.get_setting("foreign_auto_translation")
            return value == "true" if value else True
        return True

    def _get_marc_input_height_setting(self):
        """MARC 입력창 높이 설정을 가져옵니다."""
        if hasattr(self.app_instance, "db_manager") and self.app_instance.db_manager:
            value = self.app_instance.db_manager.get_setting("marc_input_height")
            # 값이 없으면 기본값 60 반환
            return int(value) if value else 60
        return 60

    def _on_marc_height_default_toggled(self, checked):
        """기본 높이 체크박스가 토글될 때 호출됩니다."""
        if checked:
            # 기본이 체크되면 확장을 해제
            self.marc_height_extended_cb.setChecked(False)
        elif not self.marc_height_extended_cb.isChecked():
            # 둘 다 해제되면 기본을 다시 체크
            self.marc_height_default_cb.setChecked(True)

    def _on_marc_height_extended_toggled(self, checked):
        """확장 높이 체크박스가 토글될 때 호출됩니다."""
        if checked:
            # 확장이 체크되면 기본을 해제
            self.marc_height_default_cb.setChecked(False)
        elif not self.marc_height_default_cb.isChecked():
            # 둘 다 해제되면 기본을 다시 체크
            self.marc_height_extended_cb.setChecked(True)

    def _save_all_settings(self):
        """모든 설정을 저장합니다."""
        if (
            not hasattr(self.app_instance, "db_manager")
            or not self.app_instance.db_manager
        ):
            QMessageBox.critical(
                self, "오류", "데이터베이스 연결을 확인할 수 없습니다."
            )
            return

        try:
            # 네비게이션 스타일 저장
            nav_style = "tree" if self.tree_radio.isChecked() else "tab"
            self.app_instance.db_manager.set_setting(
                "navigation_style", nav_style, "네비게이션 스타일 설정"
            )

            # 탭 복원 설정 저장
            restore_tab = "true" if self.restore_checkbox.isChecked() else "false"
            self.app_instance.db_manager.set_setting(
                "restore_last_tab", restore_tab, "마지막 탭 복원 설정"
            )

            # 자동 저장 설정 저장
            autosave = "true" if self.autosave_checkbox.isChecked() else "false"
            self.app_instance.db_manager.set_setting(
                "autosave_history", autosave, "자동 저장 설정"
            )

            # 해외 도서관 자동 번역 설정 저장
            foreign_translation = (
                "true" if self.foreign_translation_checkbox.isChecked() else "false"
            )
            self.app_instance.db_manager.set_setting(
                "foreign_auto_translation",
                foreign_translation,
                "해외 도서관 자동 번역 설정",
            )

            # -------------------
            # ✅ [추가] 탭별 자동화 설정 저장
            for key, checkbox in self.automation_checkboxes.items():
                value = "true" if checkbox.isChecked() else "false"
                description = f"탭 자동화 설정: {key}"
                self.app_instance.db_manager.set_setting(key, value, description)
            # -------------------

            # MARC 입력창 높이 설정 저장
            marc_height = 200 if self.marc_height_extended_cb.isChecked() else 60
            self.app_instance.db_manager.set_setting(
                "marc_input_height", str(marc_height), "MARC 입력창 높이 설정"
            )

            # 테마 설정 저장 (향후 구현)
            theme_value = self.theme_combo.currentText()
            self.app_instance.db_manager.set_setting(
                "ui_theme", theme_value, "UI 테마 설정"
            )

            QMessageBox.information(
                self,
                "성공",
                "모든 설정이 성공적으로 저장되었습니다.\n"
                "일부 설정은 앱을 재시작해야 적용됩니다.",
            )

            self.app_instance.log_message(
                "✅ 모든 설정이 성공적으로 저장되었습니다.", "INFO"
            )

        except Exception as e:
            QMessageBox.critical(
                self, "오류", f"설정 저장 중 오류가 발생했습니다:\n{str(e)}"
            )
            self.app_instance.log_message(f"❌ 설정 저장 실패: {e}", "ERROR")

    def _reset_to_defaults(self):
        """설정을 기본값으로 재설정합니다."""
        reply = QMessageBox.question(
            self,
            "설정 초기화 확인",
            "⚠️ 모든 설정을 기본값으로 초기화하시겠습니까?\n\n"
            "이 작업은 되돌릴 수 없습니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            if (
                hasattr(self.app_instance, "db_manager")
                and self.app_instance.db_manager
            ):
                # 설정 관련 키들 삭제 (기본값으로 복원)
                settings_to_reset = [
                    "navigation_style",
                    "restore_last_tab",
                    "autosave_history",
                    "ui_theme",
                    "foreign_auto_translation",
                    "marc_input_height",
                    # -------------------
                    # ✅ [추가] 자동화 관련 설정 키 추가
                    "nlk_auto_search",
                    "nlk_auto_switch",
                    "ai_feed_auto_search",
                    "ai_feed_auto_switch",
                    "ndl_auto_search",
                    "ndl_auto_switch",
                    "western_auto_search",
                    "western_auto_switch",
                    "global_auto_search",
                    "global_auto_switch",
                    "dewey_auto_search",
                    "dewey_auto_switch",
                    "legal_deposit_auto_search",
                    "legal_deposit_auto_switch",
                    # -------------------
                ]

                for setting_key in settings_to_reset:
                    self.app_instance.db_manager.delete_setting(setting_key)

            # UI 컨트롤들을 기본값으로 재설정
            self.normal_radio.setChecked(True)
            self.restore_checkbox.setChecked(True)
            self.autosave_checkbox.setChecked(True)
            self.foreign_translation_checkbox.setChecked(True)
            self.marc_height_default_cb.setChecked(True)
            self.marc_height_extended_cb.setChecked(False)
            self.theme_combo.setCurrentIndex(0)

            # -------------------
            # ✅ [추가] 자동화 체크박스 UI도 기본값(True)으로 리셋
            for checkbox in self.automation_checkboxes.values():
                checkbox.setChecked(True)
            # -------------------

            QMessageBox.information(
                self,
                "성공",
                "모든 설정이 기본값으로 복원되었습니다.\n재시작 후 완전히 적용됩니다.",
            )

            self.app_instance.log_message(
                "✅ 모든 설정이 기본값으로 복원되었습니다.", "INFO"
            )

        except Exception as e:
            QMessageBox.critical(
                self, "오류", f"설정 복원 중 오류가 발생했습니다:\n{str(e)}"
            )
            self.app_instance.log_message(f"❌ 설정 복원 실패: {e}", "ERROR")

    def _show_restart_dialog(self):
        """앱 재시작 안내 다이얼로그를 표시합니다."""
        QMessageBox.information(
            self,
            "재시작 안내",
            "일부 설정 변경사항을 완전히 적용하려면 앱을 재시작해주세요.\n\n"
            "• 네비게이션 스타일 변경\n"
            "• 테마 변경\n"
            "• UI 레이아웃 변경",
        )


def setup_settings_tab(config, app_instance):
    """설정 탭을 생성하는 팩토리 함수"""
    return QtSettingsTab(config, app_instance)
