# -*- coding: utf-8 -*-
# 파일명: qt_isni_detailed_tab.py
# 설명: ISNI 상세 저작물 검색 탭 (BaseSearchTab 상속)
# 버전: 1.0.0
# 생성일: 2025-09-30

from PySide6.QtWidgets import QCheckBox, QPushButton, QLabel, QMessageBox
from PySide6.QtCore import Qt, QModelIndex
from qt_base_tab import BaseSearchTab
from qt_utils import SelectAllLineEdit, open_url_safely
from ui_constants import U
import re


class QtISNIDetailedSearchTab(BaseSearchTab):
    """
    ISNI 상세 저작물 검색 탭

    BaseSearchTab을 상속받아 ISNI 상세 저작물 검색 기능을 제공합니다.
    KAC 코드를 입력받아 해당 저자의 상세 저작물 정보를 검색합니다.
    """

    def __init__(self, config, app_instance):
        """
        ISNI 상세 탭 초기화

        Args:
            config (dict): qt_Tab_configs.py의 ISNI_DETAILED_SEARCH 설정
            app_instance: 메인 앱 인스턴스
        """
        # 부모 클래스 초기화 (모든 기본 UI와 기능은 여기서 자동 생성됨)
        super().__init__(config, app_instance)

    def create_input_section(self, parent_layout):
        """
        ✅ [완전 오버라이드] ISNI 상세 검색 전용 입력 섹션 생성

        표준 입력창(제목, 저자, ISBN, Year)을 사용하지 않고
        KAC 코드 전용 입력창만 생성합니다.
        """
        from PySide6.QtWidgets import QFrame, QGridLayout

        self.input_container = QFrame()
        self.input_layout = QGridLayout()
        self.input_container.setLayout(self.input_layout)
        self.input_layout.setContentsMargins(0, 4, 0, 0)  # Input과 TableView 수직 간격

        # KAC 코드 라벨
        kac_label = QLabel("KAC 코드:")

        # ✅ [통일] KAC 코드 입력창을 input_widgets["search_term"]으로 표준화
        self.input_widgets["search_term"] = SelectAllLineEdit()
        self.input_widgets["search_term"].setFixedHeight(32)
        self.input_widgets["search_term"].setPlaceholderText(
            "예: KAC201309056, KAC2019E8167"
        )

        # 검색/중지 버튼
        self.search_button = QPushButton("ISNI 상세 검색")
        self.stop_button = QPushButton("검색 취소")
        self.stop_button.setEnabled(False)

        # 레이아웃에 추가 (0행에 모두 배치)
        self.input_layout.addWidget(kac_label, 0, 0)
        self.input_layout.addWidget(self.input_widgets["search_term"], 0, 1)
        self.input_layout.addWidget(self.search_button, 0, 2)
        self.input_layout.addWidget(self.stop_button, 0, 3)

        # KAC 입력창이 늘어나도록 설정
        self.input_layout.setColumnStretch(1, 1)

        # KAC 입력창도 Enter 키로 검색 시작 가능하도록 연결
        self.input_widgets["search_term"].returnPressed.connect(self.start_search)

        parent_layout.addWidget(self.input_container)

    def get_search_params(self):
        """
        ✅ [오버라이드] KAC 코드 검색 파라미터 수집 및 유효성 검증

        Returns:
            dict: 검색 파라미터 또는 None (유효하지 않은 경우)
        """
        kac_code = self.input_widgets["search_term"].text().strip()

        # 1. 입력값 확인
        if not kac_code:
            QMessageBox.warning(self, "입력 오류", "KAC 코드를 입력해주세요.")
            return None

        # 2. KAC 코드 형식 검증 (알파벳과 숫자 모두 허용)
        if not re.match(r"^KAC[0-9A-Za-z]+$", kac_code):
            QMessageBox.warning(
                self,
                "입력 오류",
                "유효하지 않은 KAC 코드 형식입니다.\n(예: KAC201309056, KAC2019E8167)",
            )
            return None

        # 3. 검색 파라미터 반환
        return {
            "ac_control_no": kac_code,
            "app_instance": self.app_instance,
        }

    def setup_connections(self):
        """
        ✅ [오버라이드] 링크 열기를 위한 더블클릭 이벤트 연결
        """
        super().setup_connections()
        self.table_view.doubleClicked.connect(self._on_item_double_clicked)

        # ✅ primary_search_field 속성 설정 (BaseSearchTab.set_initial_focus()에서 사용)
        self.primary_search_field = self.input_widgets["search_term"]

    def _on_item_double_clicked(self, index: QModelIndex):
        """
        테이블 항목 더블클릭 시 '링크' 컬럼이면 URL 열기
        """
        if not index.isValid():
            return

        clicked_col_name = self.column_headers[index.column()]
        if clicked_col_name == "링크":
            # 프록시 모델을 통해 실제 소스 인덱스 가져오기
            source_index = self.proxy_model.mapToSource(index)
            row_data = self.table_model.get_row_data(source_index.row())

            if row_data:
                url = row_data.get("링크", "")
                if url and url.startswith("http"):
                    open_url_safely(url, self.app_instance)

    # ==================== 외부 호출용 Public 메서드 ====================

    def search_by_kac_code(self, kac_code):
        """
        ✅ [Public API] 외부에서 KAC 코드로 검색을 실행하는 메서드

        다른 탭(예: 간략 저작물 정보 탭)에서 KAC 코드를 받아
        이 탭으로 전환하고 검색을 바로 시작할 수 있습니다.

        Args:
            kac_code (str): KAC 코드 (예: "KAC201309056")
        """
        if not kac_code or not kac_code.startswith("KAC"):
            return

        # 1. 검색창에 KAC 코드 입력
        self.input_widgets["search_term"].setText(kac_code)

        # 2. 검색 시작
        self.start_search()
