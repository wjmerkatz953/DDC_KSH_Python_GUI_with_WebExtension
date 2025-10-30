# 파일명: qt_TabView_Western.py
# -*- coding: utf-8 -*-
# 설명: Western 통합 검색 UI 탭 (BaseSearchTab 상속)
# 버전: v1.0.1
# 수정일: 2025-10-27 - 델리게이트 테마 대응, Google Books API 설정 기능 추가

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyledItemDelegate, QCheckBox, QPushButton, QLabel
from qt_base_tab import BaseSearchTab, SelectAllLineEdit
from ui_constants import U


class WesternSourceColorDelegate(QStyledItemDelegate):
    """✅ 출처별로 행의 텍스트 색상을 다르게 표시하는 델리게이트 (테마 대응)"""

    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app_instance = app_instance

    def paint(self, painter, option, index):
        """✅ [10월 27일 작동 방식] palette.setColor + super().paint() 호출"""
        # ✅ [핵심] 매번 최신 UI_CONSTANTS 가져오기 (테마 변경 대응)
        from ui_constants import UI_CONSTANTS as U_CURRENT

        # 현재 행의 첫 번째 컬럼(출처)에서 값 가져오기
        source = index.siblingAtColumn(0).data(0)

        # 출처별 색상 매핑 (테마 변경 시마다 최신 UI 상수 사용)
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
        }

        # ✅ [10월 27일 방식] 출처에 해당하는 색상이 있으면 사용, 없으면 기본 텍스트 색상
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


class QtWesternSearchTab(BaseSearchTab):
    """Western 통합 검색 탭. Global 탭과 동일한 UI 구조를 가집니다."""

    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)

        # ✅ [10월 27일 방식] __init__에서 직접 델리게이트 설정
        self.color_delegate = WesternSourceColorDelegate(self.table_view, app_instance)
        self.table_view.setItemDelegate(self.color_delegate)

        # ✅ [추가] 초기 API 상태 업데이트
        self._update_api_status()

    # ✅ [추가] API 설정 버튼과 상태 라벨 추가
    def create_find_section(self, parent_layout):
        """✅ [오버라이드] 검색창 섹션에 API 설정 버튼 추가"""
        super().create_find_section(parent_layout)

        # API 설정 버튼 생성
        self.api_settings_button = QPushButton("⚙️ API 설정")
        self.api_settings_button.setFixedWidth(100)
        self.api_settings_button.clicked.connect(self._show_api_settings)

        # API 상태 라벨 생성
        self.api_status_label = QLabel("")
        self.api_status_label.setAlignment(Qt.AlignCenter)
        self.api_status_label.setFixedWidth(150)

        # 마지막에 추가된 bar_container 찾기
        bar_container = parent_layout.itemAt(parent_layout.count() - 1).widget()
        if bar_container:
            for i in range(bar_container.layout().count()):
                item = bar_container.layout().itemAt(i)
                if item and item.widget():
                    find_container = item.widget()
                    find_layout = find_container.layout()
                    if find_layout:
                        # HTML 버튼 다음에 API 버튼들 추가
                        find_layout.addWidget(self.api_settings_button)
                        find_layout.addWidget(self.api_status_label)

        # 초기 상태 업데이트
        self._update_api_status()

    def _show_api_settings(self):
        """API 설정 모달창을 표시합니다."""
        import qt_api_settings
        qt_api_settings.show_api_settings_modal(
            "Google Books", self.app_instance.db_manager, self.app_instance, parent_window=self
        )

        # 다이얼로그가 닫힌 후 상태 업데이트
        self._update_api_status()

    def _update_api_status(self):
        """API 상태 라벨을 업데이트합니다."""
        if not hasattr(self, "api_status_label"):
            return

        try:
            import qt_api_settings
            is_configured = qt_api_settings.check_api_configured(
                "Google Books", self.app_instance.db_manager
            )

            if is_configured:
                self.api_status_label.setText("API 상태: ✅ 설정됨")
                self.api_status_label.setProperty("api_status", "success")
                self.api_status_label.style().unpolish(self.api_status_label)
                self.api_status_label.style().polish(self.api_status_label)
            else:
                self.api_status_label.setText("API 상태: ❌ 미설정")
                self.api_status_label.setProperty("api_status", "error")
                self.api_status_label.style().unpolish(self.api_status_label)
                self.api_status_label.style().polish(self.api_status_label)

        except Exception as e:
            self.api_status_label.setText("API 상태: ❌ 오류")
            self.api_status_label.setProperty("api_status", "error")
            self.api_status_label.style().unpolish(self.api_status_label)
            self.api_status_label.style().polish(self.api_status_label)
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(f"❌ API 상태 확인 실패: {e}", "ERROR")

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

    def refresh_theme(self):
        """✅ [추가] 테마 변경 시 테이블 뷰를 다시 그려서 델리게이트 색상을 업데이트합니다."""
        if hasattr(self, 'table_view'):
            self.table_view.viewport().update()
