# 파일명: qt_TabView_Global.py
# -*- coding: utf-8 -*-
# 버전: v1.0.1 (2025-10-27) - 델리게이트 테마 대응 추가, refresh_theme() 메서드 추가
# 설명: Global 통합 검색 UI 탭 (BaseSearchTab 상속)

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyledItemDelegate, QCheckBox, QGridLayout
from qt_base_tab import BaseSearchTab, SelectAllLineEdit
from ui_constants import U


class GlobalSourceColorDelegate(QStyledItemDelegate):
    """✅ [수정] 출처별로 행의 텍스트 색상을 다르게 표시하는 델리게이트 (테마 대응 + 매치 하이라이트)"""

    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app_instance = app_instance
        self.search_text = ""  # ✅ [추가] Find 검색어 저장

    def set_search_text(self, text):
        """✅ [추가] Find 검색어 설정"""
        self.search_text = text.lower() if text else ""

    def paint(self, painter, option, index):
        """✅ [10월 27일 작동 방식] palette.setColor + super().paint() 호출 + 매치 하이라이트"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QStyle
        # ✅ [핵심] 테마 변경 대응: 매번 최신 UI_CONSTANTS 가져오기
        from ui_constants import UI_CONSTANTS as U_CURRENT

        # 현재 셀 텍스트 가져오기
        cell_text = str(index.data(0) or "")

        # 선택 여부 확인
        is_selected = option.state & QStyle.StateFlag.State_Selected

        # ✅ [추가] 매치 하이라이트: Find 검색어와 매치되면 빨간색 배경
        if self.search_text and self.search_text in cell_text.lower():
            # 직접 배경과 텍스트 그리기
            painter.save()

            if is_selected:
                # 선택된 셀: 기본 선택 색상 사용 (구분 가능하도록)
                painter.fillRect(option.rect, QColor(U_CURRENT.HIGHLIGHT_SELECTED))
                painter.setPen(QColor(U_CURRENT.TEXT_BUTTON))
            else:
                # 선택되지 않은 매치 셀: 빨간색 배경
                painter.fillRect(option.rect, QColor(U_CURRENT.ACCENT_RED))
                painter.setPen(QColor("#FFFFFF"))

            text_rect = option.rect.adjusted(4, 0, -4, 0)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, cell_text)
            painter.restore()
        else:
            # 출처별 색상 적용
            source = index.siblingAtColumn(0).data(0)

            color_map = {
                "LC": QColor(U_CURRENT.SOURCE_LC),
                "Harvard": QColor(U_CURRENT.SOURCE_HARVARD),
                "MIT": QColor(U_CURRENT.SOURCE_MIT),
                "Princeton": QColor(U_CURRENT.SOURCE_PRINCETON),
                "UPenn": QColor(U_CURRENT.SOURCE_UPENN),
                "Cornell": QColor(U_CURRENT.SOURCE_CORNELL),
                "DNB": QColor(U_CURRENT.SOURCE_DNB),
                "BNF": QColor(U_CURRENT.SOURCE_BNF),
                "BNE": QColor(U_CURRENT.SOURCE_BNE),
                "Google": QColor(U_CURRENT.SOURCE_GOOGLE),
                "NDL": QColor(U_CURRENT.SOURCE_NDL),
                "CiNii": QColor(U_CURRENT.SOURCE_CINII),
                "NLK": QColor(U_CURRENT.SOURCE_NLK),
            }

            text_color = color_map.get(source, QColor(U_CURRENT.TEXT_DEFAULT))
            option.palette.setColor(QPalette.ColorRole.Text, text_color)

            super().paint(painter, option, index)

    # -------------------
    # ✅ [핵심 추가] URL 클릭 처리 (Western과 동일)
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


class QtGlobalSearchTab(BaseSearchTab):
    """Global 통합 검색 탭. DDC, Year 입력 필드와 출처별 색상 기능을 추가합니다."""

    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)
        # -------------------
        # ✅ [수정] app_instance 전달
        self.color_delegate = GlobalSourceColorDelegate(self.table_view, app_instance)
        # -------------------
        self.table_view.setItemDelegate(self.color_delegate)

    def refresh_theme(self):
        """✅ [추가] 테마 변경 시 테이블 뷰를 다시 그려서 델리게이트 색상을 업데이트합니다."""
        if hasattr(self, 'table_view'):
            self.table_view.viewport().update()

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

    # ✅ [수정 2] NLK 탭과 동일한 방식으로, 추가 버튼을 위한 메서드를 오버라이드
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
        # 부모 클래스가 title, author, isbn, year 파라미터를 모두 처리해줍니다.
        params = super().get_search_params()

        # DDC 단독 검색을 위한 처리
        ddc_text = self.input_widgets["ddc"].text().strip()
        if params is None:
            if self.ddc_check.isChecked() and ddc_text:
                params = {}  # DDC 단독 검색을 위해 빈 딕셔너리로 시작
            else:
                return None  # 모든 입력이 비었으면 검색 중단

        # -------------------
        # ✅ [핵심 수정] ddc_query는 항상 포함 (빈 문자열이라도)
        if self.ddc_check.isChecked() and ddc_text:
            params["ddc_query"] = ddc_text
        else:
            params["ddc_query"] = ""  # 빈 문자열로 설정
        # -------------------

        params["db_manager"] = self.app_instance.db_manager
        return params
