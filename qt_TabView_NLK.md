# -*- coding: utf-8 -*-
# 파일명: qt_TabView_NLK.py
# 설명: NLK 검색 탭 (BaseSearchTab 상속)
# 버전: 1.0.4
# 생성일: 2025-09-29

from PySide6.QtWidgets import QCheckBox, QPushButton, QLabel
from PySide6.QtCore import Qt
from qt_base_tab import BaseSearchTab
from qt_utils import SelectAllLineEdit
from ui_constants import U
import qt_api_settings


class QtNLKSearchTab(BaseSearchTab):
    """
    NLK(국립중앙도서관) 검색 탭

    BaseSearchTab을 상속받아 NLK 전용 검색 기능을 제공합니다.
    기본 입력 필드(제목, 저자, ISBN, Year) 외에 DDC 분류 검색 필드를 추가로 제공합니다.
    """

    def __init__(self, config, app_instance):
        """
        NLK 탭 초기화

        Args:
            config (dict): qt_Tab_configs.py의 NLK_SEARCH 설정
            app_instance: 메인 앱 인스턴스
        """
        # 부모 클래스 초기화 (모든 기본 UI와 기능은 여기서 자동 생성됨)
        super().__init__(config, app_instance)

    def _create_extra_inputs(self):
        """
        ✅ [오버라이드] NLK 전용 추가 입력 필드 생성

        BaseSearchTab의 기본 입력 필드(제목, 저자, ISBN, Year) 외에
        DDC 분류 검색 필드를 추가합니다.

        추가되는 필드:
        - DDC: 듀이십진분류법 번호 검색
        """
        # DDC 체크박스 생성
        self.ddc_check = QCheckBox("DDC:")
        self.ddc_check.setChecked(True)

        # DDC 입력창 생성
        self.ddc_input = SelectAllLineEdit()
        self.ddc_input.setPlaceholderText("e.g. 004.6")

        # 레이아웃에 추가 (행=0, 컬럼=8,9)
        self.input_layout.addWidget(self.ddc_check, 0, 8)
        self.input_layout.addWidget(self.ddc_input, 0, 9)

        # DDC 입력창도 Enter 키로 검색 시작 가능하도록 연결
        self.ddc_input.returnPressed.connect(self.start_search)

        # ✅ 컬럼 stretch 조정 (DDC 입력창도 같은 비율로 확장)
        self.input_layout.setColumnStretch(9, 1)

    def _create_extra_buttons(self):
        """
        ✅ [오버라이드] 버튼 위치를 DDC 필드 이후로 조정

        BaseSearchTab에서 생성된 버튼(컬럼 8,9)을 컬럼 10,11로 이동합니다.
        """
        # 기존 버튼들을 레이아웃에서 제거
        self.input_layout.removeWidget(self.search_button)
        self.input_layout.removeWidget(self.stop_button)

        # DDC 필드(8,9) 다음인 컬럼 10,11에 다시 추가
        self.input_layout.addWidget(self.search_button, 0, 10)
        self.input_layout.addWidget(self.stop_button, 0, 11)

    def create_find_section(self, parent_layout):
        """
        ✅ [오버라이드] Find 섹션에 NLK 전용 API 버튼 추가

        BaseSearchTab의 find_section을 그대로 사용하되,
        API 설정 버튼과 상태 라벨을 추가합니다.
        """
        # 부모 클래스의 기본 Find 섹션 생성
        super().create_find_section(parent_layout)

        # ✅ API 설정 버튼 생성
        self.api_settings_button = QPushButton("⚙️ API 설정")
        self.api_settings_button.setFixedWidth(100)
        self.api_settings_button.clicked.connect(self._show_api_settings)

        # ✅ API 상태 라벨 생성
        self.api_status_label = QLabel("")
        self.api_status_label.setAlignment(Qt.AlignCenter)
        self.api_status_label.setFixedWidth(150)

        # ✅ 마지막에 추가된 bar_container 찾기
        bar_container = parent_layout.itemAt(parent_layout.count() - 1).widget()
        if bar_container:
            bar_layout = bar_container.layout()
            if bar_layout and bar_layout.count() >= 2:
                # bar_layout의 두 번째 항목이 find_container
                find_container = bar_layout.itemAt(1).widget()
                if find_container:
                    find_layout = find_container.layout()
                    if find_layout:
                        # HTML 버튼 다음에 API 버튼들 추가
                        find_layout.addWidget(self.api_settings_button)
                        find_layout.addWidget(self.api_status_label)

        # 초기 상태 업데이트
        self._update_api_status()

    def _show_api_settings(self):
        """API 설정 모달창을 표시합니다."""
        qt_api_settings.show_api_settings_modal(
            "NLK", self.app_instance.db_manager, self.app_instance, parent_window=self
        )

        # 다이얼로그가 닫힌 후 상태 업데이트
        self._update_api_status()

    def _update_api_status(self):
        """API 상태 라벨을 업데이트합니다."""
        if not hasattr(self, "api_status_label"):
            return

        try:
            is_configured = qt_api_settings.check_api_configured(
                "NLK", self.app_instance.db_manager
            )

            if is_configured:
                self.api_status_label.setText("API 상태: ✅ 설정됨")
                self.api_status_label.setStyleSheet(f"color: {U.ACCENT_GREEN};")
            else:
                self.api_status_label.setText("API 상태: ❌ 미설정")
                self.api_status_label.setStyleSheet(f"color: {U.ACCENT_RED};")

        except Exception as e:
            self.api_status_label.setText("API 상태: ❌ 오류")
            self.api_status_label.setStyleSheet(f"color: {U.ACCENT_RED};")
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(f"❌ API 상태 확인 실패: {e}", "ERROR")

    def get_search_params(self):
        """
        ✅ [오버라이드] NLK 검색에 필요한 파라미터를 수집합니다.

        BaseSearchTab의 기본 파라미터(title_query, author_query, isbn_query, year_query)에
        NLK 전용 파라미터(ddc_query, db_manager)를 추가합니다.

        주의: app_instance는 SearchThread가 자동으로 추가하므로 여기서 추가하지 않음!

        Returns:
            dict: 검색 파라미터 딕셔너리
        """
        # 부모 클래스의 기본 파라미터 가져오기
        params = super().get_search_params()

        if params is None:
            return None

        # ✅ NLK 전용 파라미터 추가
        params.update(
            {
                # DDC 검색어 추가
                "ddc_query": (
                    self.ddc_input.text().strip()
                    if hasattr(self, "ddc_check") and self.ddc_check.isChecked()
                    else ""
                ),
                # db_manager만 추가 (app_instance는 SearchThread가 자동 추가!)
                "db_manager": (
                    self.app_instance.db_manager
                    if hasattr(self.app_instance, "db_manager")
                    else None
                ),
            }
        )

        return params
