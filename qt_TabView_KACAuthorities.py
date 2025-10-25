# 파일명: qt_TabView_KACAuthorities.py
# -*- coding: utf-8 -*-
# 설명: 저자전거 검색 UI 탭 (BaseSearchTab 상속)


from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QMessageBox,
    QGridLayout,
)  # 👈 QGridLayout 추가
from qt_base_tab import BaseSearchTab, SelectAllLineEdit
from qt_utils import open_url_safely
from PySide6.QtCore import QModelIndex


class QtKACAuthoritiesSearchTab(BaseSearchTab):
    """저자전거 검색 탭. 고유한 입력창 레이아웃과 더블클릭 기능을 가집니다."""

    def create_input_section(self, parent_layout):
        """저자전거 탭 전용 입력 섹션을 생성합니다."""
        self.input_container = QFrame()
        # ✅ [수정] self.input_layout을 사용하기 전에 QGridLayout으로 생성합니다.
        self.input_layout = QGridLayout()
        self.input_container.setLayout(self.input_layout)
        self.input_layout.setContentsMargins(0, 4, 0, 0)  # Input과 TableView 수직 간격

        # 위젯 생성
        label = QLabel("검색어:")
        self.input_widgets["search_term"] = SelectAllLineEdit()
        self.input_widgets["search_term"].setPlaceholderText(
            "인명 또는 KAC 코드를 입력하세요 (복수 입력 시 쉼표로 구분)"
        )
        self.input_widgets["search_term"].returnPressed.connect(self.start_search)

        self.search_button = QPushButton("저자전거 검색")
        self.stop_button = QPushButton("검색 중지")
        self.stop_button.setEnabled(False)

        # 레이아웃에 추가
        self.input_layout.addWidget(label, 0, 0)
        self.input_layout.addWidget(self.input_widgets["search_term"], 0, 1)
        self.input_layout.addWidget(self.search_button, 0, 2)
        self.input_layout.addWidget(self.stop_button, 0, 3)
        self.input_layout.setColumnStretch(1, 1)  # 검색창이 너비를 모두 차지하도록
        parent_layout.addWidget(self.input_container)

    # ✅ [핵심 수정] BaseSearchTab의 setup_connections()가 연결하는 더블클릭 이벤트 (부모)를
    # 오버라이드하고, KAC 탭의 모든 더블클릭 처리를 이 함수로 통일합니다.
    def setup_connections(self):
        """이벤트 연결 설정 (더블클릭 포함)"""
        super().setup_connections()
        # super()는 이미 BaseSearchTab._on_table_item_double_clicked에 연결되어 있으므로,
        # KAC 탭의 더블클릭 처리를 이 함수로 대체해야 합니다.

        # BaseSearchTab의 연결을 끊고 (안전하게), 이 탭의 _on_item_double_clicked에 연결합니다.
        # BaseSearchTab은 _on_table_item_double_clicked에 연결되어 있습니다.
        try:
            self.table_view.doubleClicked.disconnect(self._on_table_item_double_clicked)
        except TypeError:
            # 연결된 시그널이 없을 경우 pass (안전 장치)
            pass

        # KAC 탭 전용 더블클릭 로직을 연결합니다.
        self.table_view.doubleClicked.connect(self._on_item_double_clicked)

        # ✅ primary_search_field 속성 설정 (BaseSearchTab.set_initial_focus()에서 사용)
        self.primary_search_field = self.input_widgets["search_term"]

    def get_search_params(self):
        """검색 파라미터를 수집합니다."""
        search_term = self.input_widgets["search_term"].text().strip()
        if not search_term:
            QMessageBox.warning(self, "입력 오류", "검색할 내용을 입력해주세요.")
            return None
        # -------------------
        # ✅ [수정] app_instance를 파라미터에 추가합니다.
        return {
            "search_term": search_term,
            "app_instance": self.app_instance,
            "db_manager": self.app_instance.db_manager,
        }

    def _on_item_double_clicked(self, index: QModelIndex):
        """테이블 항목 더블클릭 시 링크 열기, KAC 연동 기능, 또는 상세 모달 표시"""
        if not index.isValid():
            return

        clicked_col_name = self.column_headers[index.column()]
        source_index = self.proxy_model.mapToSource(index)
        row_data = self.table_model.get_row_data(source_index.row())

        if not row_data:
            return

        # 1. '전체 저작물' 컬럼 처리 (최우선)
        if clicked_col_name == "전체 저작물":
            kac_code = row_data.get("제어번호", "")
            if kac_code and kac_code.startswith("KAC"):
                # 연동 검색 실행 (상세 모달 방지)
                self.app_instance.main_window.handle_kac_to_brief_works_search(kac_code)
                return  # <-- 이벤트 완료 및 상세 모달 방지
            else:
                QMessageBox.warning(
                    self, "데이터 오류", "유효한 KAC 코드를 찾을 수 없습니다."
                )
                return  # <-- 이벤트 완료 및 상세 모달 방지

        # 2. 링크 컬럼 처리
        link_columns = ["상세 링크", "저작물 목록 링크"]
        if clicked_col_name in link_columns:
            url = row_data.get(clicked_col_name, "")
            open_url_safely(url, self.app_instance)
            return  # <-- 이벤트 완료 및 상세 모달 방지

        # 3. 그 외 컬럼은 부모의 기본 상세 모달 로직을 명시적으로 호출 (재사용)
        from qt_context_menus import show_cell_detail_dialog

        # 셀 값 가져오기
        column_name = self.column_headers[index.column()]
        cell_value = self.table_model.data(source_index)  # 소스 인덱스로 실제 값 가져옴
        show_cell_detail_dialog(cell_value, column_name, self.app_instance)
        # return은 생략하거나 False를 반환하여 부모의 다른 로직이 있다면 실행되도록 하지만,
        # 여기서는 이미 모든 이벤트를 처리했으므로 명시적으로 이벤트 소비를 끝냅니다.
        return
