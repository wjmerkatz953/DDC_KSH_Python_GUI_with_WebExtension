# -*- coding: utf-8 -*-
# 파일명: qt_TabView_NDL.py
# 설명: NDL + CiNii 통합 검색 탭 (BaseSearchTab 상속 구조 완벽 적용)
# 버전: 2.0.2
# 생성일: 2025-09-29
# 수정일: 2025-10-30 - 출처별 색상 복원 (10월 27일 패턴) + Find 매치 하이라이트 기능 추가

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyledItemDelegate
from qt_base_tab import BaseSearchTab
from ui_constants import U


class SourceColorDelegate(QStyledItemDelegate):
    """✅ 출처별 색상을 적용하는 델리게이트 (NDL 탭의 고유 기능 + 매치 하이라이트)"""

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

            # 출처별 색상 매핑 (테마 변경 시마다 최신 UI 상수 사용)
            color_map = {
                "NDL": QColor(U_CURRENT.TEXT_DEFAULT),
                "CiNii": QColor(U_CURRENT.ACCENT_BLUE),
            }

            # 출처에 해당하는 색상이 있으면 사용, 없으면 기본 텍스트 색상
            text_color = color_map.get(source, QColor(U_CURRENT.TEXT_DEFAULT))
            option.palette.setColor(QPalette.ColorRole.Text, text_color)

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


class QtNDLSearchTab(BaseSearchTab):
    """
    NDL + CiNii 통합 검색 탭

    BaseSearchTab을 상속받아 NLK 탭과 동일한 구조로 작동합니다.
    모든 검색/결과 처리는 부모 클래스에 위임하고,
    이 클래스는 NDL 탭만의 고유 기능(출처별 색상)만 담당합니다.
    """

    def __init__(self, config, app_instance):
        """NDL 탭 초기화"""
        # 1. 부모 클래스의 모든 UI와 기능을 먼저 생성합니다.
        super().__init__(config, app_instance)

        # 2. 이 탭의 고유 기능인 '색상 델리게이트'를 생성하고 테이블 뷰에 적용합니다.
        # -------------------
        # ✅ [수정] app_instance 전달
        self.color_delegate = SourceColorDelegate(self.table_view, app_instance)
        # -------------------
        self.table_view.setItemDelegate(self.color_delegate)

        # 3. 부모의 get_search_params를 오버라이드하여 db_manager를 추가합니다.

    def get_search_params(self):
        """✅ [오버라이드] NDL 검색에 db_manager 파라미터를 추가합니다."""
        params = super().get_search_params()
        if params is None:
            return None

        # NDL 검색은 db_manager(용어집)가 필요하므로 파라미터에 추가해줍니다.
        params["db_manager"] = self.app_instance.db_manager
        return params

    def refresh_theme(self):
        """✅ [추가] 테마 변경 시 테이블 뷰를 다시 그려서 델리게이트 색상을 업데이트합니다."""
        if hasattr(self, 'table_view'):
            self.table_view.viewport().update()
