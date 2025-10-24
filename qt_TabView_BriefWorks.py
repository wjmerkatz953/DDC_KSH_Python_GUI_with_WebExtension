# 파일명: qt_TabView_BriefWorks.py
# -*- coding: utf-8 -*-
# 설명: 간략 저작물 정보 UI 탭 (BaseSearchTab 상속)

import re
from qt_base_tab import BaseSearchTab, SelectAllLineEdit
from qt_utils import open_url_safely
from PySide6.QtCore import QModelIndex  # ✅ [수정] QModelIndex 임포트 추가
from PySide6.QtWidgets import (
    QFrame,
    QRadioButton,
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
    QGridLayout,
)  # 👈 QGridLayout 추가


class QtBriefWorksSearchTab(BaseSearchTab):
    """간략 저작물 정보 탭. ISBN/ISNI/KAC 검색 유형 선택 UI를 가집니다."""

    def create_input_section(self, parent_layout):
        """간략 저작물 정보 탭 전용 입력 섹션을 생성합니다."""
        self.input_container = QFrame()
        self.input_layout = QGridLayout()
        self.input_container.setLayout(self.input_layout)
        self.input_layout.setContentsMargins(0, 4, 0, 0)  # Input과 TableView 수직 간격

        # 라디오 버튼 그룹
        radio_layout = QHBoxLayout()
        self.radio_group = QButtonGroup(self)
        self.radio_buttons = {}
        for search_type in ["ISBN", "ISNI", "KAC"]:
            radio = QRadioButton(search_type)
            self.radio_buttons[search_type] = radio
            self.radio_group.addButton(radio)
            radio_layout.addWidget(radio)
        self.radio_buttons["ISBN"].setChecked(True)  # 기본값

        # 검색창
        self.input_widgets["search_term"] = SelectAllLineEdit()
        self.input_widgets["search_term"].setFixedHeight(32)
        self.input_widgets["search_term"].setPlaceholderText("검색어를 입력하세요...")
        self.input_widgets["search_term"].returnPressed.connect(self.start_search)

        # 검색/중지 버튼
        self.search_button = QPushButton("저자 정보 검색")
        self.stop_button = QPushButton("검색 취소")
        self.stop_button.setEnabled(False)

        # 레이아웃에 추가
        self.input_layout.addLayout(radio_layout, 0, 0)
        self.input_layout.addWidget(self.input_widgets["search_term"], 0, 1)
        self.input_layout.addWidget(self.search_button, 0, 2)
        self.input_layout.addWidget(self.stop_button, 0, 3)
        self.input_layout.setColumnStretch(1, 1)
        parent_layout.addWidget(self.input_container)

    def _detect_search_pattern(self, query):
        """입력된 검색어의 패턴을 자동으로 인식하고 적절한 검색 타입을 반환합니다."""
        cleaned_isbn = query.replace("-", "").replace(" ", "")
        if cleaned_isbn.isdigit() and len(cleaned_isbn) in [10, 13]:
            return "ISBN", cleaned_isbn
        if re.match(r"^[0-9]{4}\s?[0-9]{4}\s?[0-9]{4}\s?[0-9]{3}[0-9X]$", query, re.I):
            return "ISNI", query.replace(" ", "").upper()
        if re.match(r"^KAC[0-9A-Z]{9}$", query, re.I):
            return "KAC", query.upper()
        return None, query

    def start_search(self):
        """검색 시작 전 패턴을 감지하고 라디오 버튼을 업데이트합니다."""
        query = self.input_widgets["search_term"].text().strip()
        if not query:
            QMessageBox.warning(self, "입력 오류", "검색어를 입력해주세요.")
            return

        detected_type, processed_query = self._detect_search_pattern(query)

        if detected_type:
            self.radio_buttons[detected_type].setChecked(True)
            self.input_widgets["search_term"].setText(processed_query)
            self.app_instance.log_message(
                f"정보: 검색 패턴 자동 인식 - {detected_type}: {processed_query}"
            )
            super().start_search()  # 부모의 검색 시작 메서드 호출
        else:
            QMessageBox.warning(
                self,
                "입력 오류",
                f"입력하신 '{query}'는 유효한 ISBN, ISNI, KAC 형식이 아닙니다.",
            )

    def get_search_params(self):
        """검색 파라미터를 수집합니다."""
        return {
            "search_type": self.radio_group.checkedButton().text(),
            "query_value": self.input_widgets["search_term"].text().strip(),
            "db_manager": self.app_instance.db_manager,
        }

    def setup_connections(self):
        """링크 열기를 위한 더블클릭 이벤트 연결"""
        super().setup_connections()
        self.table_view.doubleClicked.connect(self._on_item_double_clicked)

        # ✅ primary_search_field 속성 설정 (BaseSearchTab.set_initial_focus()에서 사용)
        self.primary_search_field = self.input_widgets["search_term"]

    def _on_item_double_clicked(self, index: QModelIndex):
        """테이블 항목 더블클릭 시 링크 열기"""
        if not index.isValid():
            return

        clicked_col_name = self.column_headers[index.column()]
        if clicked_col_name == "링크":
            source_index = self.proxy_model.mapToSource(index)
            row_data = self.table_model.get_row_data(source_index.row())
            if row_data:
                open_url_safely(row_data.get("링크", ""), self.app_instance)

    # ✅ [추가] 외부에서 KAC 코드로 검색을 실행하는 public 메서드
    def search_by_kac_code(self, kac_code):
        """KAC 코드를 입력창에 설정하고 검색을 바로 시작합니다."""
        if not kac_code or not kac_code.startswith("KAC"):
            return

        # 1. 'KAC' 라디오 버튼 선택
        self.radio_buttons["KAC"].setChecked(True)
        # 2. 검색창에 KAC 코드 입력
        self.input_widgets["search_term"].setText(kac_code)
        # 3. 검색 시작
        self.start_search()

    def on_search_completed(self, results):
        """
        검색 결과를 받아 '저자-저작물 목록'의 중첩 구조를
        테이블에 표시하기 위한 평탄한 데이터 리스트로 변환합니다.
        """
        flat_data = []
        if results and isinstance(results, list):
            for author_data in results:
                if not isinstance(author_data, dict):
                    continue

                # 데이터 추출 로직 (이전 단계에서 최종 확정된 로직)
                author_keys_lower = {k.lower(): v for k, v in author_data.items()}
                author_name = author_data.get("authorName", author_data.get("name"))
                if not author_name:
                    author_name = author_keys_lower.get(
                        "authorname", author_keys_lower.get("author_name", "")
                    )

                kac_code = author_keys_lower.get("kac", "")
                isni_code = author_keys_lower.get("isni", "")
                works = author_data.get("works", [])

                if not works:
                    flat_data.append(
                        {
                            # -------------------
                            # ✅ [핵심 수정] column_map의 새로운 Data Key (한글 Display Name) 사용
                            "저자명": author_name,
                            "KAC": kac_code,
                            "ISNI": isni_code,
                            # -------------------
                            "저작물 제목": "(저작물 정보 없음)",
                            "연도": "",
                            "링크": "",
                        }
                    )
                else:
                    for work in works:
                        title_year_match = re.match(
                            r"^(.+?)\s*\((\d{4}|연도 불명)\)$", work.get("display", "")
                        )
                        if title_year_match:
                            title = title_year_match.group(1).strip()
                            year = title_year_match.group(2)
                        else:
                            title = work.get("display", "")
                            year = ""

                        flat_data.append(
                            {
                                # -------------------
                                # ✅ [핵심 수정] column_map의 새로운 Data Key (한글 Display Name) 사용
                                "저자명": author_name,
                                "KAC": kac_code,
                                "ISNI": isni_code,
                                # -------------------
                                "저작물 제목": title,
                                "연도": year,
                                "링크": work.get("url", ""),
                            }
                        )

        super().on_search_completed(flat_data)
