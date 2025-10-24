# 파일명: qt_TabView_KSH_Lite.py
# -*- coding: utf-8 -*-
# 설명: KHS Hybrid 검색 UI 탭 (BaseSearchTab 상속, CTK 버전 포팅)

import re
from PySide6.QtWidgets import (
    QFrame,
    QCheckBox,
    QHBoxLayout,
    QMessageBox,
    QGridLayout,
)
from PySide6.QtCore import QModelIndex
from qt_base_tab import BaseSearchTab
from qt_utils import (
    SelectAllLineEdit,
    KshHyperlinkDelegate,
)
from text_utils import clean_ksh_search_input


class QtKshHyridSearchTab(BaseSearchTab):
    """KSH Hybird 검색 탭. CTK 버전의 특수 기능을 PySide6로 포팅합니다."""

    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)

        # -------------------
        # ✅ [리팩토링] 복잡한 더블클릭 함수 대신, 델리게이트를 필요한 컬럼에 적용
        delegate = KshHyperlinkDelegate(self.table_view)

        # 링크 기능이 필요한 모든 컬럼의 '인덱스'를 찾아 델리게이트를 설정
        link_columns = [
            "전체 목록 검색 결과",
            "동의어/유사어(UF)",
            "상위어",
            "하위어",
            "관련어",
            "외국어",
        ]
        for i, col_name in enumerate(self.column_headers):
            if col_name in link_columns:
                self.table_view.setItemDelegateForColumn(i, delegate)

        # 마우스 오버 효과는 없지만, 클릭 감지를 위해 설정
        self.table_view.setMouseTracking(True)
        # -------------------

        # ✅ 숨겨진 URL 컬럼을 UI에서 보이지 않게 처리
        self.table_view.horizontalHeader().setHidden(True)
        for i, col_name in enumerate(self.column_headers):
            if col_name.startswith("_url"):
                self.table_view.setColumnHidden(i, True)
        self.table_view.horizontalHeader().setHidden(False)

        # ✅ primary_search_field 속성 설정 (BaseSearchTab.set_initial_focus()에서 사용)
        self.primary_search_field = self.input_widgets["search_term"]

    def create_input_section(self, parent_layout):
        """✅ [오버라이드] KHS Hybrid 탭 전용의 복잡한 입력 UI를 생성합니다."""
        self.input_container = QFrame()
        self.input_layout = QGridLayout(self.input_container)
        self.input_container.setLayout(self.input_layout)
        self.input_layout.setContentsMargins(0, 4, 0, 0)  # Input과 TableView 수직 간격

        # 체크박스 그룹 (Pro/Lite) - qt_base_tab.py 스타일
        checkbox_layout = QHBoxLayout()

        # Pro 체크박스
        self.pro_check = QCheckBox("Pro")
        self.pro_check.setFixedHeight(32)
        self.pro_check.setChecked(False)
        checkbox_layout.addWidget(self.pro_check)

        # Lite 체크박스 (기본 선택)
        self.lite_check = QCheckBox("Lite")
        self.lite_check.setFixedHeight(32)
        self.lite_check.setChecked(True)
        checkbox_layout.addWidget(self.lite_check)

        # 상호 배타적 동작 (하나만 선택 가능)
        self.pro_check.toggled.connect(lambda checked: self.lite_check.setChecked(not checked) if checked else None)
        self.lite_check.toggled.connect(lambda checked: self.pro_check.setChecked(not checked) if checked else None)

        # 검색창
        self.input_widgets["search_term"] = SelectAllLineEdit()
        self.input_widgets["search_term"].setFixedHeight(32)
        self.input_widgets["search_term"].setPlaceholderText(
            "검색할 KSH 주제어를 입력하세요"
        )
        self.input_widgets["search_term"].returnPressed.connect(self.start_search)

        # 검색/중지 버튼 (부모 클래스의 것을 그대로 사용)
        self._create_standard_buttons()

        # 레이아웃에 위젯 추가
        self.input_layout.addLayout(checkbox_layout, 0, 0)
        self.input_layout.addWidget(self.input_widgets["search_term"], 0, 1)
        self.input_layout.addWidget(self.search_button, 0, 2)
        self.input_layout.addWidget(self.stop_button, 0, 3)
        self.input_layout.setColumnStretch(1, 1)  # 검색창이 남는 공간 모두 차지
        parent_layout.addWidget(self.input_container)

    def start_search(self):
        """[수정] 중앙 집중화된 db_manager의 전처리 로직을 사용합니다."""
        raw_query = self.input_widgets["search_term"].text().strip()

        if not raw_query:
            QMessageBox.warning(self, "입력 오류", "검색어를 입력해주세요.")
            return

        # -------------------
        # ✅ [핵심 수정] SearchQueryManager를 임포트하고 인스턴스를 생성합니다.
        from search_query_manager import SearchQueryManager

        sqm = SearchQueryManager(self.app_instance.db_manager)

        # ✅ [핵심 수정] sqm 인스턴스를 통해 preprocess_search_term을 호출합니다.
        search_term = sqm.preprocess_search_term(raw_query)
        # -------------------

        # 전처리된 검색어를 다시 UI에 반영 (사용자 피드백)
        self.input_widgets["search_term"].setText(search_term)
        super().start_search()  # 전처리 후, 부모의 검색 시작 메서드 호출

    def get_search_params(self):
        """✅ [오버라이드] KHS Hybrid 검색에 필요한 파라미터를 구성합니다."""
        search_term = self.input_widgets["search_term"].text().strip()
        if not search_term:
            return None

        # -------------------
        # ✅ [핵심 수정] 현재 선택된 체크박스에 따라 검색 모드 결정
        search_mode = "Pro" if self.pro_check.isChecked() else "Lite"
        # -------------------

        # 검색어와 함께 검색 모드를 파라미터에 추가하여 반환합니다.
        return {"search_term": search_term, "search_mode": search_mode}
