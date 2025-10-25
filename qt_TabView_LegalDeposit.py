# 파일명: qt_TabView_LegalDeposit.py
# -*- coding: utf-8 -*-
# 설명: 납본 ID 검색 UI 탭 (BaseSearchTab 상속)

from PySide6.QtWidgets import QCheckBox
from qt_base_tab import BaseSearchTab, SelectAllLineEdit


class QtLegalDepositSearchTab(BaseSearchTab):
    """납본 ID 검색 탭. 출판사, 연도 입력 필드를 추가합니다."""

    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)

    def _create_extra_inputs(self):
        """출판사 입력창을 추가합니다 (Year는 부모 클래스에서 상속)."""
        self.publisher_check = QCheckBox("Publisher:")
        self.publisher_check.setChecked(True)
        self.publisher_check.setFixedHeight(32)

        self.input_widgets["publisher"] = SelectAllLineEdit()
        self.input_widgets["publisher"].setFixedHeight(32)
        self.input_widgets["publisher"].setPlaceholderText("Enter Publisher")

        # 그리드 레이아웃에 추가 (Year 다음인 8-9번 열에 배치)
        self.input_layout.addWidget(self.publisher_check, 0, 8)
        self.input_layout.addWidget(self.input_widgets["publisher"], 0, 9)

        # 입력창 너비가 유연하게 조절되도록 설정
        self.input_layout.setColumnStretch(9, 1)

    def _create_standard_buttons(self):
        """버튼의 위치를 Publisher 입력창 뒤로 재배치합니다."""
        super()._create_standard_buttons()
        self.input_layout.removeWidget(self.search_button)
        self.input_layout.removeWidget(self.stop_button)
        self.input_layout.addWidget(self.search_button, 0, 10)
        self.input_layout.addWidget(self.stop_button, 0, 11)

    def get_search_params(self):
        """기본 파라미터에 출판사, 연도, db_manager를 추가하여 반환합니다."""
        params = super().get_search_params()
        if params is None:
            # 기본 검색어가 하나도 없으면 추가 검색어 확인
            if not (
                self.publisher_check.isChecked()
                and self.input_widgets["publisher"].text().strip()
            ) and not (
                self.year_check.isChecked()
                and self.input_widgets["year"].text().strip()
            ):
                return None
            else:
                params = {}  # 추가 검색어 단독 검색을 위해 빈 딕셔너리로 시작

        if self.publisher_check.isChecked():
            params["publisher_query"] = self.input_widgets["publisher"].text().strip()
        if self.year_check.isChecked():
            params["year_query"] = self.input_widgets["year"].text().strip()

        params["db_manager"] = self.app_instance.db_manager
        return params
