# 파일명: qt_TabView_Western.py
# -*- coding: utf-8 -*-
# 설명: Western 통합 검색 UI 탭 (BaseSearchTab 상속)

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyledItemDelegate, QCheckBox
from qt_base_tab import BaseSearchTab, SelectAllLineEdit
from ui_constants import U


class WesternSourceColorDelegate(QStyledItemDelegate):
    """출처별로 행의 텍스트 색상을 다르게 표시하는 델리게이트"""

    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app_instance = app_instance  # ← 추가
        self.color_map = {
            "LC": QColor("#C7DA72"),
            "Harvard": QColor("#99A1E6"),
            "MIT": QColor("#8FB474"),
            "Princeton": QColor("#E08A44"),
            "UPenn": QColor("#B19CD9"),
            "Cornell": QColor("#D2B48C"),
            "DNB": QColor(U.TEXT_DEFAULT),
            "BNF": QColor(U.ACCENT_BLUE),
            "BNE": QColor("#FFAE35"),
            "Google": QColor("#2EDDC0"),
        }

    def paint(self, painter, option, index):
        source = index.siblingAtColumn(0).data(0)
        if source in self.color_map:
            option.palette.setColor(QPalette.ColorRole.Text, self.color_map[source])
        super().paint(painter, option, index)

    # -------------------
    # ✅ [핵심 추가] URL 클릭 처리
    def editorEvent(self, event, model, option, index):
        from PySide6.QtCore import QEvent
        from PySide6.QtCore import Qt as QtCore_Qt
        from qt_utils import open_url_safely
        import re

        if (
            event.type() == QEvent.MouseButtonRelease
            and event.button() == QtCore_Qt.LeftButton
        ):
            data = str(index.data(QtCore_Qt.DisplayRole) or "").strip()

            # URL 패턴 추출
            match = re.search(r'(https?://[^\s<>"]+|www\.[^\s<>"]+)', data)
            if match:
                url = match.group(0).strip()
                if url.startswith(("http://", "https://", "www.")):
                    open_url_safely(url, self.app_instance)
                    return True
        return super().editorEvent(event, model, option, index)


class QtWesternSearchTab(BaseSearchTab):
    """Western 통합 검색 탭. Global 탭과 동일한 UI 구조를 가집니다."""

    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)
        # -------------------
        # ✅ [수정] app_instance 전달
        self.color_delegate = WesternSourceColorDelegate(self.table_view, app_instance)
        # -------------------
        self.table_view.setItemDelegate(self.color_delegate)

    # -------------------
    # ✅ [수정 1] 'Year' 필드 생성을 제거하고, 'DDC' 필드만 추가하도록 변경
    def _create_extra_inputs(self):
        """DDC 입력창만 추가합니다. (Year는 부모 클래스가 생성)"""
        self.ddc_check = QCheckBox("DDC:")
        self.ddc_check.setChecked(True)
        self.ddc_check.setFixedHeight(32)
        self.input_widgets["ddc"] = SelectAllLineEdit()
        self.input_widgets["ddc"].setFixedHeight(32)
        self.input_widgets["ddc"].setPlaceholderText("e.g. 004.6")

        # 부모의 Year 필드(6,7) 다음에 DDC 필드를 배치 (8,9)
        self.input_layout.addWidget(self.ddc_check, 0, 8)
        self.input_layout.addWidget(self.input_widgets["ddc"], 0, 9)

        self.input_layout.setColumnStretch(9, 1)

    # ✅ [수정 2] 추가 버튼을 위한 메서드를 오버라이드
    def _create_extra_buttons(self):
        """버튼의 위치를 추가된 DDC 입력창 뒤로 재배치합니다."""
        self.input_layout.removeWidget(self.search_button)
        self.input_layout.removeWidget(self.stop_button)

        # DDC 필드(8,9) 다음인 컬럼 10, 11에 버튼을 다시 추가
        self.input_layout.addWidget(self.search_button, 0, 10)
        self.input_layout.addWidget(self.stop_button, 0, 11)

    # ✅ [수정 3] get_search_params 로직 단순화
    def get_search_params(self):
        """기본 파라미터에 DDC, db_manager를 추가하여 반환합니다."""
        params = super().get_search_params()

        ddc_text = self.input_widgets["ddc"].text().strip()

        # -------------------
        # ✅ [핵심 수정] params가 None인 경우 처리 개선
        if params is None:
            if self.ddc_check.isChecked() and ddc_text:
                params = {}
            else:
                return None

        # ✅ [핵심 수정] ddc_query는 항상 포함 (빈 문자열이라도)
        if self.ddc_check.isChecked() and ddc_text:
            params["ddc_query"] = ddc_text
        else:
            params["ddc_query"] = ""  # 빈 문자열로 설정
        # -------------------

        params["db_manager"] = self.app_instance.db_manager
        return params
