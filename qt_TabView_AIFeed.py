# 파일명: qt_TabView_AIFeed.py
# -*- coding: utf-8 -*-
# 설명: AI 피드 검색 UI 탭 (API 설정 기능 추가)

from PySide6.QtWidgets import QPushButton, QMessageBox, QLabel  # 👈 [1] QLabel 추가
from PySide6.QtCore import Qt  # 👈 [1] Qt 추가
from qt_base_tab import BaseSearchTab
import qt_api_settings  # 👈 [1] qt_api_settings 임포트 추가
from ui_constants import U  # 👈 [1] ui_constants 임포트 추가


class QtAIFeedSearchTab(BaseSearchTab):
    """AI 피드 검색 탭. Gemini 분류를 위한 데이터 수집 및 전송 기능 포함."""

    def create_find_section(self, parent_layout):
        """기본 찾기 섹션에 'AI 피드 전송'과 'API 설정' 버튼 등을 추가합니다."""
        # 1. 부모 클래스의 기본 찾기 섹션을 먼저 생성
        super().create_find_section(parent_layout)

        # 2. 'AI 피드 전송' 버튼 생성
        self.send_ai_feed_button = QPushButton("🤖 AI 피드 전송")
        self.send_ai_feed_button.clicked.connect(self._send_to_ai_feed)

        # ✅ [추가] 3. API 설정 버튼 생성 (NLK 탭 로직 모방)
        self.api_settings_button = QPushButton("⚙️ API 설정")
        self.api_settings_button.setFixedWidth(100)
        self.api_settings_button.clicked.connect(self._show_api_settings)

        # ✅ [추가] 4. API 상태 라벨 생성 (NLK 탭 로직 모방)
        self.api_status_label = QLabel("")
        self.api_status_label.setAlignment(Qt.AlignCenter)
        self.api_status_label.setFixedWidth(150)

        # 5. 찾기 섹션의 레이아웃에 버튼들 추가
        bar_container = parent_layout.itemAt(parent_layout.count() - 1).widget()
        if bar_container and hasattr(bar_container, "layout"):
            bar_layout = bar_container.layout()
            if bar_layout and bar_layout.count() >= 2:
                find_container = bar_layout.itemAt(1).widget()
                if find_container and hasattr(find_container, "layout"):
                    find_layout = find_container.layout()
                    # HTML 버튼 다음에 버튼들을 순서대로 추가
                    find_layout.addWidget(self.send_ai_feed_button)
                    find_layout.addWidget(self.api_settings_button)  # ✅ 추가
                    find_layout.addWidget(self.api_status_label)  # ✅ 추가

        # ✅ [추가] 6. 초기 API 상태 업데이트
        self._update_api_status()

    # ✅ [추가] API 설정 창을 여는 메서드 (NLK 탭 로직 모방)
    def _show_api_settings(self):
        """API 설정 모달창을 표시합니다."""
        qt_api_settings.show_api_settings_modal(
            "네이버",
            self.app_instance.db_manager,
            self.app_instance,
            parent_window=self,
        )
        # 다이얼로그가 닫힌 후 상태 업데이트
        self._update_api_status()

    # ✅ [추가] API 상태 라벨을 업데이트하는 메서드 (NLK 탭 로직 모방)
    def _update_api_status(self):
        """API 상태 라벨을 업데이트합니다."""
        if not hasattr(self, "api_status_label"):
            return
        try:
            is_configured = qt_api_settings.check_api_configured(
                "네이버", self.app_instance.db_manager
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

    # ✅ [추가] AI 피드 탭 전용 파라미터 생성 메서드
    def get_search_params(self):
        """
        부모 클래스에서 파라미터를 받은 후, Naver 검색에 불필요한
        'year_query'를 제거하여 반환합니다.
        """
        # 1. 먼저 부모 클래스의 메서드를 호출해 기본 파라미터(제목, 저자, ISBN 등)를 가져옵니다.
        params = super().get_search_params()
        if not params:
            return None

        # 2. Naver 검색 함수가 받지 않는 'year_query' 키를 삭제합니다.
        if "year_query" in params:
            del params["year_query"]

        # 3. db_manager를 추가합니다.
        params["db_manager"] = self.app_instance.db_manager

        return params

    def _send_to_ai_feed(self):
        """'분류 정보 취합' 준비는 검색 직후 완료됨. 버튼은 '전송만' 수행."""
        # [안전 장치]
        if self.table_model.rowCount() == 0:
            QMessageBox.warning(self, "전송 오류", "전송할 검색 결과가 없습니다.")
            return

        # ✅ 'AI-Feed Merge' 행이 있으면 그 행을 우선 선택
        try:
            src_col = self.table_model.header_labels.index("검색소스") \
                if hasattr(self.table_model, "header_labels") else -1
        except Exception:
            src_col = -1

        preferred_row = -1
        if src_col >= 0:
            for r in range(self.table_model.rowCount()):
                idx = self.table_model.index(r, src_col)
                if idx.isValid():
                    val = str(self.table_model.data(idx) or "")
                    if val.strip() == "AI-Feed Merge":
                        preferred_row = r
                        break

        # 선택 적용(가능한 경우)
        try:
            if preferred_row >= 0 and hasattr(self, "table_view"):
                self.table_view.clearSelection()
                self.table_view.selectRow(preferred_row)
        except Exception:
            pass  # 선택 실패해도 전송은 계속

        # ✅ 전송만 수행 (재수집/재비교 없음)
        from qt_data_transfer_manager import handle_ai_feed_to_gemini
        handle_ai_feed_to_gemini(self)
