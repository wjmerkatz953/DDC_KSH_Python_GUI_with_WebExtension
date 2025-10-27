# -*- coding: utf-8 -*-
# 파일명: qt_base_tab.py
# 설명: 모든 검색 탭의 공통 기능과 UI를 정의하는 부모 클래스 (모델/뷰 아키텍처)
# 버전: 3.0.1 - 상세 정보 표시 버그 수정
# 생성일: 2025-09-25
# 수정일: 2025-10-02
#
# 변경 이력:
# v3.0.1 (2025-10-02)
# - [버그 수정] _update_detail_view 메서드에서 주석 처리된 content_lines.append() 활성화 (라인 1517)
#   : 선택 행 상세 정보 위젯에 2개 컬럼만 표시되던 문제 해결
#   : 이제 모든 컬럼의 정보가 정상적으로 표시됨

import re
import pandas as pd
from functools import partial # ✅ [수정] partial 함수를 임포트합니다.
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QCheckBox,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QTableView,  # ✅ QTableWidget → QTableView 변경
    QLabel,
    QFrame,
    QMessageBox,
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QApplication,  # ✅ 클립보드 사용을 위해 추가
)
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import (
    QThread,
    Signal,
    Qt,
    QUrl,
    QTimer,
    QModelIndex,
    QPropertyAnimation,
    QEasingCurve,
    QAbstractTableModel,
)

# --- 프로젝트 모듈 import ---
from ui_constants import U
from qt_proxy_models import SmartNaturalSortProxyModel
from qt_widget_events import (
    load_column_settings,
    save_column_settings,
    show_all_columns_utility,  # ✅ 이름 변경
    hide_all_columns_utility,  # ✅ 이름 변경
    ExcelStyleTableHeaderView,
    focus_on_first_table_view_item,
)
from view_displays import (
    show_in_dropdown_html_viewer,
    adjust_qtableview_columns,  # ✅ 추가
)
from qt_utils import (
    SearchThread,
    export_dataframe_to_excel,
    print_table_data,
    show_dataframe_statistics,
    open_url_safely,
    SelectAllLineEdit,
    linkify_text,
    UrlLinkDelegate,  # ✅ UrlLinkDelegate 임포트
)

# ✅ [새로 추가] PySide6 컨텍스트 메뉴 시스템
from qt_context_menus import setup_widget_context_menu, _format_text_for_detail_view
from qt_shortcuts import setup_shortcuts


class FastSearchResultModel(QAbstractTableModel):
    """빠른 검색 결과 모델 (사전 정렬 키 생성 로직 제거 버전)"""

    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.column_headers = headers
        self._data = []
        self.editable_columns = set()  # ✅ 편집 가능한 컬럼 인덱스 저장

    # -------------------
    def set_column_headers(self, headers):
        # -------------------
        """테이블의 컬럼 헤더를 설정합니다."""
        self.column_headers = headers

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.column_headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row >= len(self._data) or col >= len(self.column_headers):
            return None

        if role == Qt.DisplayRole or role == Qt.EditRole:
            return str(self._data[row].get(self.column_headers[col], ""))
        elif role == Qt.UserRole:
            return self._data[row]
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section < len(self.column_headers):
                return self.column_headers[section]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return str(section + 1)
        return None

    def clear_data(self):
        self.beginResetModel()
        self._data.clear()
        self.endResetModel()

    def add_multiple_rows(self, data_list, column_keys=None):
        if not data_list:
            return

        keys_to_use = column_keys if column_keys else self.column_headers
        mapping = dict(zip(keys_to_use, self.column_headers))

        final_data = []
        for result in data_list:
            display_row = {}
            if isinstance(result, dict):
                for data_key, display_header in mapping.items():
                    display_row[display_header] = result.get(data_key, "")
            else:
                for i, header in enumerate(self.column_headers):
                    value = ""
                    if isinstance(result, (list, tuple)) and i < len(result):
                        value = result[i] if result[i] is not None else ""
                    display_row[header] = value

            # ✅ [핵심] create_padded_sort_key() 호출 로직이 완전히 제거되었습니다.
            final_data.append(display_row)

        self.beginInsertRows(
            QModelIndex(), len(self._data), len(self._data) + len(final_data) - 1
        )
        self._data.extend(final_data)
        self.endInsertRows()

    def get_row_data(self, row):
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def flags(self, index):
        """✅ [수정] 편집 가능한 컬럼은 ItemIsEditable 플래그 추가"""
        if not index.isValid():
            return Qt.NoItemFlags

        base_flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

        # 편집 가능한 컬럼인지 확인
        if index.column() in self.editable_columns:
            return base_flags | Qt.ItemIsEditable

        return base_flags

    def set_editable_columns(self, columns: set):
        """편집 가능한 컬럼 설정"""
        self.editable_columns = columns

    def setData(self, index, value, role=Qt.EditRole):
        """✅ [신규 추가] 셀 편집 시 데이터 업데이트"""
        if not index.isValid() or role != Qt.EditRole:
            return False

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._data):
            return False

        # 컬럼 헤더 이름 가져오기
        if col >= len(self.column_headers):
            return False

        column_name = self.column_headers[col]

        # 데이터 업데이트
        self._data[row][column_name] = str(value)

        # 변경 사항 알림
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])

        return True

    # ✅ [추가] 컬럼별 필터를 설정하고 모델을 갱신하는 메서드
    def set_column_filters(self, filters: dict):
        self.column_filters = filters
        self.invalidateFilter()  # 필터를 다시 적용하도록 강제

    # ✅ [핵심 추가] 행을 보여줄지 결정하는 filterAcceptsRow 메서드 오버라이드
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        # 필터가 없으면 모든 행을 보여줍니다.
        if not self.column_filters:
            return True

        for column, text in self.column_filters.items():
            if not text:
                continue

            # 해당 행, 컬럼의 셀 데이터 가져오기
            index = self.sourceModel().index(source_row, column, source_parent)
            cell_data = str(self.sourceModel().data(index) or "").lower()

            # 컴마(,)로 구분된 여러 단어 처리 (OR 조건)
            if "," in text:
                terms = [t.strip().lower() for t in text.split(",") if t.strip()]
                # terms 중 하나라도 cell_data에 포함되어 있으면 매칭 성공
                if not any(term in cell_data for term in terms):
                    return False  # 모든 단어가 매칭되지 않으면 이 행은 숨김
            # 단일 단어 처리 (AND 조건)
            else:
                if text.lower() not in cell_data:
                    return False  # 단어가 포함되지 않으면 이 행은 숨김

        # 모든 필터 조건을 통과한 경우, 이 행은 보여줌
        return True


# DataFrame에서 빠르게 로드하는 편의 함수
def load_dataframe_to_model(model, dataframe, column_mapping=None):
    """
    DataFrame을 FastSearchResultModel에 빠르게 로드

    Args:
        model: FastSearchResultModel 인스턴스
        dataframe: pandas DataFrame
        column_mapping: {df_column: model_column} 매핑 (None이면 자동)
    """
    if dataframe.empty:
        model.clear_data()
        return

    # 컬럼 매핑 생성
    if column_mapping is None:
        # DataFrame 컬럼을 모델 헤더에 맞춰 자동 매핑
        column_mapping = {}
        for i, header in enumerate(model.column_headers):
            if header in dataframe.columns:
                column_mapping[header] = header
            elif i < len(dataframe.columns):
                column_mapping[dataframe.columns[i]] = header

    # DataFrame을 딕셔너리 리스트로 변환 (빠른 방법)
    data_list = []
    for _, row in dataframe.iterrows():
        row_data = {}
        for df_col, model_col in column_mapping.items():
            if df_col in row:
                row_data[model_col] = row[df_col]
        data_list.append(row_data)

    # 한 번에 모든 데이터 추가 (매우 빠름)
    model.clear_data()
    model.add_multiple_rows(data_list)


class BaseSearchTab(QWidget):
    def __init__(self, config, app_instance):
        super().__init__()
        self.config = config
        self.app_instance = app_instance
        self.tab_name = config.get("tab_name", "Unknown Search")
        # ✅ [추가] 탭의 고유 설정 키를 저장합니다 (오류 수정)
        self.tab_key = config.get("tab_key")

        column_map = config.get("column_map", [])
        self.column_keys = [item[0] for item in column_map]
        self.column_headers = [item[1] for item in column_map]

        self.search_function = config.get("search_function", None)
        self.input_widgets = {}

        # ✅ [모델/뷰 전환] QTableWidget → QTableView + Model
        self.table_view = None
        self.table_model = None

        # [수정 1] proxy_model 변수를 맨 위에서 먼저 초기화합니다.
        self.proxy_model = None

        self.current_dataframe = pd.DataFrame()
        self.search_thread = None
        self.is_searching = False

        self.setup_ui()
        self.setup_connections()
        setup_shortcuts(self, self.app_instance)

        # ✅ [핵심 수정] UrlLinkDelegate의 생성자 호출 방식을 수정하여
        # Qt가 인식하는 parent 인자만 QStyledItemDelegate.__init__으로 전달되도록 합니다.
        self.table_view.setItemDelegate(
            UrlLinkDelegate(
                parent=self.table_view,
                app_instance=self.app_instance,  # <--- UrlLinkDelegate 내부에서만 사용됩니다.
            )
        )

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(6, U.PADDING_FRAME, 6, U.PADDING_FRAME)

        self.create_input_section(main_layout)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAlignment(Qt.AlignCenter)

        # 레이아웃을 생성하고
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(6, 2, 6, 2)  # ✅ 상하 여백 축소 (4,5 → 2,2)

        # 1. progress_bar를 progress_layout에 추가합니다.
        progress_layout.addWidget(self.progress_bar)

        # 2. 완성된 progress_layout을 main_layout에 추가합니다.
        main_layout.addLayout(progress_layout)

        self.progress_bar.setVisible(False)
        self.create_results_section(main_layout)
        main_layout.addSpacing(4)  # 👈 TableView와 Find 사이 여백
        self.create_find_section(main_layout)

        # ✅ [수정] 위젯이 존재하는 경우에만 컨텍스트 메뉴를 설정하도록 변경
        if "title" in self.input_widgets:
            setup_widget_context_menu(self.input_widgets["title"], self.app_instance)
        if "author" in self.input_widgets:
            setup_widget_context_menu(self.input_widgets["author"], self.app_instance)
        if "isbn" in self.input_widgets:
            setup_widget_context_menu(self.input_widgets["isbn"], self.app_instance)

    def create_input_section(self, parent_layout):
        """UI의 '입력 섹션'을 조립하는 메인 메서드"""
        self.input_container = QFrame()
        self.input_layout = QGridLayout(self.input_container)
        self.input_layout.setContentsMargins(
            6, 4, 0, 0  # ✅ 하단 여백
        )  # 좌상우하 검색어 필드 아래 여백

        self._create_standard_inputs()
        self._create_extra_inputs()
        self._create_standard_buttons()
        self._create_extra_buttons()
        self._create_status_message_area()

        # ✅ [수정] 4개의 입력창(제목, 저자, ISBN, Year)이 모두 공간을 나눠 갖도록 수정
        self.input_layout.setColumnStretch(1, 1)  # 제목 입력창
        self.input_layout.setColumnStretch(3, 1)  # 저자 입력창
        self.input_layout.setColumnStretch(5, 1)  # ISBN 입력창
        self.input_layout.setColumnStretch(7, 1)  # Year 입력창

        parent_layout.addWidget(self.input_container)

    def _create_standard_inputs(self):
        """(공통) 기본 입력창 (제목, 저자, ISBN) 생성"""

        # [핵심] 모든 위젯의 행(row) 번호를 0으로 통일하여 한 줄에 배치
        self.title_check = QCheckBox("제목:")
        self.title_check.setChecked(True)
        self.title_check.setFixedHeight(32)  # ✅ 체크박스 높이도 맞춤
        self.input_widgets["title"] = SelectAllLineEdit()
        self.input_widgets["title"].setFixedHeight(32)  # ✅ 높이 조절
        self.input_layout.addWidget(self.title_check, 0, 0)
        self.input_layout.addWidget(self.input_widgets["title"], 0, 1)

        self.author_check = QCheckBox("저자:")
        self.author_check.setChecked(True)
        self.author_check.setFixedHeight(32)  # ✅ 체크박스 높이도 맞춤
        self.input_widgets["author"] = SelectAllLineEdit()
        self.input_widgets["author"].setFixedHeight(32)  # ✅ 높이 조절
        self.input_layout.addWidget(self.author_check, 0, 2)
        self.input_layout.addWidget(self.input_widgets["author"], 0, 3)

        self.isbn_check = QCheckBox("ISBN:")
        self.isbn_check.setChecked(True)
        self.isbn_check.setFixedHeight(32)  # ✅ 체크박스 높이도 맞춤
        self.input_widgets["isbn"] = SelectAllLineEdit()
        self.input_widgets["isbn"].setFixedHeight(32)  # ✅ 높이 조절
        self.input_layout.addWidget(self.isbn_check, 0, 4)
        self.input_layout.addWidget(self.input_widgets["isbn"], 0, 5)

        self.year_check = QCheckBox("Year:")
        self.year_check.setChecked(True)
        self.year_check.setFixedHeight(32)  # ✅ 체크박스 높이도 맞춤
        self.input_widgets["year"] = SelectAllLineEdit()
        self.input_widgets["year"].setPlaceholderText("e.g. 2024")
        self.input_widgets["year"].setFixedHeight(32)  # ✅ 높이 조절
        self.input_layout.addWidget(self.year_check, 0, 6)
        self.input_layout.addWidget(self.input_widgets["year"], 0, 7)

    def _create_standard_buttons(self):
        """(공통) 기본 버튼 (검색, 중지) 생성"""

        # [핵심] 버튼들도 모두 0번 행에 배치
        self.search_button = QPushButton("검색 시작")
        self.stop_button = QPushButton("검색 중지")
        self.stop_button.setEnabled(False)
        self.input_layout.addWidget(self.search_button, 0, 8)
        self.input_layout.addWidget(self.stop_button, 0, 9)

    # [핵심] 아래 함수들을 자식 클래스에서 '오버라이딩'하여 사용합니다.
    def _create_extra_inputs(self):
        """(확장용) 추가 입력창을 위한 빈 메서드"""
        pass  # 기본적으로는 아무것도 하지 않음

    def _create_extra_buttons(self):
        """(확장용) 추가 버튼을 위한 빈 메서드"""
        pass  # 기본적으로는 아무것도 하지 않음

    def _create_status_message_area(self):
        """(확장용) 상태 메시지를 위한 빈 메서드"""
        pass  # 기본적으로는 아무것도 하지 않음

    def create_results_section(self, parent_layout):
        """✅ [네이티브 정렬] 프록시 모델을 사용한 결과 섹션 생성"""
        results_group = QGroupBox()
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(
            U.PADDING_FRAME, U.PADDING_FRAME, U.PADDING_FRAME, U.PADDING_FRAME
        )  # 테이블뷰를 감싼 그룹박스 내부 패딩

        # 1. 기본 테이블 뷰와 모델 생성
        self.table_view = QTableView()

        # ✅ [핵심 수정] 모델을 먼저 생성하고, 헤더를 나중에 설정하는 방식으로 변경
        self.table_view = QTableView()
        self.table_model = FastSearchResultModel(self.column_headers)

        # 2. ✅ 스마트 자연 정렬 프록시 모델 생성
        self.proxy_model = SmartNaturalSortProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        # 👈 [핵심] 세로 헤더(행 번호)의 기본 정렬을 가운데로 설정합니다.
        self.table_view.verticalHeader().setDefaultAlignment(Qt.AlignCenter)

        # 3. ✅ 뷰에 프록시 모델 연결 (핵심!)
        self.table_view.setModel(self.proxy_model)

        # 4. 세로 헤더 중앙 정렬
        self.table_view.verticalHeader().setDefaultAlignment(Qt.AlignCenter)

        # 5. Excel 스타일 헤더 설정
        header = ExcelStyleTableHeaderView(
            Qt.Horizontal,
            self.table_view,
            self.column_headers,
            self.get_header_callbacks(),  # ✅ [버그 수정] 누락된 콜백 인자 다시 추가
            self,  # ✅ 탭 인스턴스(self)를 tab_instance 인자로 전달
        )
        self.table_view.setHorizontalHeader(header)

        # ✅ [추가] URL hover 시 커서 변경 + 파란색 표시 + 클릭 시 열기 delegate 설정
        from qt_custom_widgets import URLHoverDelegate

        self.table_view.setItemDelegate(
            URLHoverDelegate(self.table_view, self.app_instance)
        )
        self.table_view.setMouseTracking(True)  # 마우스 이동 추적 활성화

        # 6. 테이블 뷰 설정
        self.setup_table_view_selection()
        self.table_view.setAlternatingRowColors(True)

        # 7. ✅ Qt 네이티브 정렬 활성화
        self.table_view.setSortingEnabled(False)

        results_layout.addWidget(self.table_view)
        parent_layout.addWidget(results_group)
        setup_widget_context_menu(self.table_view, self.app_instance)
        # ✅ [핵심 추가] 앱 시작 시 저장된 컬럼 설정 자동 로드
        self.load_column_settings_action()

    def create_find_section(self, parent_layout):
        """✅ [수정] 상태표시줄과 Find 영역을 한 행에 배치 (요청사항 반영)"""

        # 전체 바를 위한 컨테이너와 레이아웃
        bar_container = QFrame()
        bar_layout = QHBoxLayout(bar_container)
        bar_layout.setContentsMargins(0, 0, 0, 0)  # Find 영역 좌우 여백 좌상우하

        # 1. 왼쪽: 상태 표시줄 (1/3 차지)
        self.status_label = QLabel("준비 완료")
        self.status_label.setStyleSheet(
            f"color: {U.TEXT_HIGHLIGHT}; padding: 0px; font-weight: 650; font-style: italic;"
        )
        # [핵심 추가] 텍스트를 수평/수직 모두 중앙으로 정렬합니다.
        self.status_label.setAlignment(Qt.AlignCenter)
        bar_layout.addWidget(self.status_label, 1)  # Stretch factor 1

        # 2. 오른쪽: Find 및 버튼 영역 (2/3 차지)
        find_container = QFrame()

        # ✅ F7 기능을 위해 Find 영역 컨테이너의 참조를 저장합니다.
        self.find_area_container = bar_container
        find_layout = QHBoxLayout(find_container)
        find_layout.setContentsMargins(0, 0, 0, 0)

        find_layout.addWidget(QLabel("Find:"))
        self.find_entry = QLineEdit()
        find_layout.addWidget(self.find_entry)  # Stretch factor는 부모가 관리

        self.find_prev_button = QPushButton("▲")
        self.find_prev_button.setToolTip("이전 찾기 (Shift+F3)")
        self.find_next_button = QPushButton("▼")
        self.find_next_button.setToolTip("다음 찾기 (F3)")
        self.clear_all_filters_button = QPushButton("🗑️ 모든 필터 지우기")
        self.html_viewer_button = QPushButton("HTML로 보기")

        find_layout.addWidget(self.find_prev_button)
        find_layout.addWidget(self.find_next_button)
        find_layout.addWidget(self.clear_all_filters_button)
        find_layout.addWidget(self.html_viewer_button)

        bar_layout.addWidget(find_container, 2)  # Stretch factor 2

        parent_layout.addWidget(bar_container)

    def setup_connections(self):
        """이벤트 연결을 설정합니다."""
        # 검색 버튼 연결
        self.search_button.clicked.connect(self.start_search)
        self.stop_button.clicked.connect(self.stop_search)

        # Enter 키 검색 시작
        # ✅ [수정] 위젯이 존재하는 경우에만 Enter 키 이벤트를 연결하도록 변경
        if "title" in self.input_widgets:
            self.input_widgets["title"].returnPressed.connect(self.start_search)
        if "author" in self.input_widgets:
            self.input_widgets["author"].returnPressed.connect(self.start_search)
        if "isbn" in self.input_widgets:
            self.input_widgets["isbn"].returnPressed.connect(self.start_search)

        # Find 기능 연결
        if hasattr(self, "find_entry"):
            self.find_entry.returnPressed.connect(self.find_in_results)
        if hasattr(self, "find_prev_button"):
            self.find_prev_button.clicked.connect(self.find_previous)
        if hasattr(self, "find_next_button"):
            self.find_next_button.clicked.connect(self.find_next)

        # 기능 버튼 연결
        self.clear_all_filters_button.clicked.connect(self.clear_all_filters_action)
        self.html_viewer_button.clicked.connect(self.show_html_viewer)

        # ✅ [핵심 추가] 테이블 뷰 더블클릭 이벤트 연결
        if self.table_view:
            # ❗ 함수 이름을 _on_table_item_double_clicked로 명확히 정의합니다.
            self.table_view.doubleClicked.connect(self._on_table_item_double_clicked)

        # [핵심 추가] 테이블 뷰의 현재 항목 변경 시그널을 상세 정보 업데이트 메서드에 연결
        if self.table_view and self.table_view.selectionModel():
            # ✅ partial을 사용해 일반화된 함수에 현재 탭의 기본 모델을 전달
            handler = partial(self._update_detail_view,
                              proxy_model=self.proxy_model,
                              table_model=self.table_model)
            self.table_view.selectionModel().currentChanged.connect(handler)

    # ✅ [신규 추가] MARC 추출 데이터를 수신하는 표준 메서드
    def receive_data(
        self,
        title=None,
        author=None,
        isbn=None,
        year=None,
        switch_priority=False,
        **kwargs,
    ):
        """
        다른 탭(주로 MARC 추출)에서 전송된 데이터를 해당 탭의 표준 입력 필드에 설정하고,
        'NLK 검색' 탭일 경우에만 자동으로 검색을 시작합니다.
        """
        received_data = False
        # ✅ [추가] 자동 검색 및 탭 전환을 위한 플래그 초기화
        self._auto_search_triggered = False
        self._switch_priority = switch_priority

        if title and "title" in self.input_widgets:
            self.input_widgets["title"].setText(str(title))
            received_data = True

        if author and "author" in self.input_widgets:
            self.input_widgets["author"].setText(str(author))
            received_data = True

        if isbn and "isbn" in self.input_widgets:
            self.input_widgets["isbn"].setText(str(isbn))
            received_data = True

        if year and "year" in self.input_widgets:
            self.input_widgets["year"].setText(str(year))
            received_data = True

        if received_data:
            # ✅ [핵심 수정] 탭 이름을 직접 비교하는 대신, DB에 저장된 사용자 설정을 확인
            auto_search_enabled = True  # 기본값
            if self.tab_key and hasattr(self.app_instance, "db_manager"):
                setting_key = f"{self.tab_key}_auto_search"
                value = self.app_instance.db_manager.get_setting(setting_key)
                if value is not None:
                    auto_search_enabled = value == "true"

            if auto_search_enabled:
                self.app_instance.log_message(
                    f"✅ 데이터 수신: '{self.tab_name}' 탭에서 자동 검색을 시작합니다 (설정 활성화).",
                    "INFO",
                )
                self._auto_search_triggered = True
                QTimer.singleShot(200, self.start_search)
            else:
                # 다른 탭들은 로그만 남기고 자동 검색은 시작하지 않음
                self.app_instance.log_message(
                    f"✅ 데이터 수신: '{self.tab_name}' 탭에 데이터가 설정되었습니다 (자동 검색 비활성).",
                    "INFO",
                )

    # === 테이블 설정 및 이벤트 처리 ===

    def setup_table_view_selection(self):
        """✅ [최종] 끊김 없는 부드러운 컬럼 리사이즈"""
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectItems)

        header = self.table_view.horizontalHeader()

        # 핵심: Interactive 모드 + 실시간 업데이트
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        # 안정성 확보
        header.setMinimumSectionSize(60)
        header.setDefaultSectionSize(150)

        # 기능 활성화
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)

        # 부드러운 스크롤
        self.table_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table_view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        # ✅ 수평 스크롤바 항상 표시 (모든 탭 통일)
        self.table_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

    def _on_table_item_clicked(self, index: QModelIndex):
        """✅ [모델/뷰 전환] 테이블 항목 클릭 시 컬럼 인덱스 저장"""
        if index.isValid():
            # ✅ 클릭된 컬럼 저장
            self.table_view._last_clicked_column = index.column()

            # 디버그 로그
            if hasattr(self.app_instance, "log_message"):
                header_name = (
                    self.column_headers[index.column()]
                    if index.column() < len(self.column_headers)
                    else f"Col_{index.column()}"
                )
                self.app_instance.log_message(
                    f"🔍 컬럼 클릭 추적: {index.column()}번째 컬럼 '{header_name}'",
                    "DEBUG",
                )

        # ❗ 부모 클래스에서 상세 모달을 띄우는 기본 함수를 명시적으로 정의합니다.

    def _on_table_item_double_clicked(self, index: QModelIndex):
        """기본 더블클릭 이벤트: 셀 상세 정보 모달 표시"""
        if not index.isValid():
            return

        # 프록시 모델을 통해 실제 소스 인덱스 가져오기
        source_index = self.proxy_model.mapToSource(index)
        column = source_index.column()
        row = source_index.row()

        # 컬럼명 가져오기
        column_name = (
            self.column_headers[column]
            if column < len(self.column_headers)
            else f"컬럼 {column}"
        )

        # KSH Local 탭의 편집 가능 컬럼인지 확인 (편집 모드 충돌 방지)
        is_ksh_local_tab = (
            hasattr(self, "editable_columns") and len(self.editable_columns) > 0
        )
        is_editable_column = column in getattr(self, "editable_columns", set())

        if is_ksh_local_tab and is_editable_column:
            # KSH Local 탭의 편집 가능 컬럼 → 인라인 편집 활성화 (상세 모달 방지)
            return

        # 나머지 모든 셀: 상세 정보 모달 표시
        from qt_context_menus import show_cell_detail_dialog

        # 셀 값 가져오기
        # QAbstractTableModel의 data 메서드는 QModelIndex를 인자로 받습니다.
        cell_value = self.table_model.data(source_index)
        show_cell_detail_dialog(cell_value, column_name, self.app_instance)

    # === 검색 기능 ===

    def start_search(self):
        """검색을 시작합니다."""
        if self.is_searching:
            return

        if not self.search_function:
            QMessageBox.warning(self, "오류", "검색 함수가 정의되지 않았습니다.")
            return

        search_params = self.get_search_params()
        if not search_params:
            return

        search_params["app_instance"] = self.app_instance

        self.is_searching = True
        self.search_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)  # 👈 0~100 범위로 변경
        self.progress_bar.setValue(0)  # 👈 0%에서 시작하도록 설정

        # [핵심 수정] Main Window 대신 자체 status_label을 직접 업데이트합니다.
        self.status_label.setText("검색 중...")

        self.search_thread = SearchThread(
            self.search_function, search_params, self.app_instance
        )
        self.search_thread.search_completed.connect(self.on_search_completed)
        self.search_thread.search_failed.connect(self.on_search_failed)
        self.search_thread.start()

    def stop_search(self):
        """검색을 중지합니다."""
        if self.search_thread:
            self.search_thread.cancel_search()
        self.reset_search_ui()

    def reset_search_ui(self):
        """검색 UI 상태를 초기화합니다."""
        self.is_searching = False
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(True)

    def get_search_params(self):
        """검색 매개변수를 수집합니다."""
        params = {}

        # 기본값 먼저 설정
        params["title_query"] = ""
        params["author_query"] = ""
        params["isbn_query"] = ""
        params["year_query"] = ""

        if self.title_check.isChecked():
            title = self.input_widgets["title"].text().strip()
            if title:
                params["title_query"] = title

        if self.author_check.isChecked():
            author = self.input_widgets["author"].text().strip()
            if author:
                params["author_query"] = author

        if self.isbn_check.isChecked():
            isbn = self.input_widgets["isbn"].text().strip()
            if isbn:
                params["isbn_query"] = isbn

        # -------------------
        # ✅ [추가] year_query 실제 입력값 수집
        if self.year_check.isChecked():
            year = self.input_widgets["year"].text().strip()
            if year:
                params["year_query"] = year
        # -------------------

        if not any(
            [
                params.get("title_query"),
                params.get("author_query"),
                params.get("isbn_query"),
                params.get("year_query"),
            ]
        ):
            QMessageBox.information(self, "알림", "검색할 내용을 입력해주세요.")
            return None

        return params

    def on_search_completed(self, results):
        """[진단 모드] 검색 완료 시 호출되는 슬롯 - 모든 단계를 로그로 추적"""
        try:
            # --- self.reset_search_ui() 또는 기존 코드 대신 아래 코드를 넣습니다. ---
            self.is_searching = False
            self.search_button.setEnabled(True)
            self.stop_button.setEnabled(False)

            self.app_instance.log_message("▶️ on_search_completed: 진입", "DEBUG")

            # 🔥 [핵심] 애니메이션으로 부드럽게 100%로 채우기
            self.animation = QPropertyAnimation(self.progress_bar, b"value")
            self.animation.setDuration(800)
            self.animation.setStartValue(self.progress_bar.value())
            self.animation.setEndValue(100)
            self.animation.setEasingCurve(QEasingCurve.InOutCubic)
            self.animation.start()

            data_list = []
            self.app_instance.log_message(
                "▶️ on_search_completed: 결과 타입 확인 시작", "DEBUG"
            )
            if isinstance(results, pd.DataFrame):
                self.current_dataframe = results
                if not results.empty:
                    data_list = results.to_dict("records")
            elif isinstance(results, list) and results:
                self.current_dataframe = pd.DataFrame(results)
                data_list = results
            else:
                self.current_dataframe = pd.DataFrame()
            self.app_instance.log_message(
                f"▶️ on_search_completed: 데이터 리스트 변환 완료 ({len(data_list)}개)",
                "DEBUG",
            )

            if data_list:
                self.app_instance.log_message(
                    "▶️ on_search_completed: 모델 업데이트 시작", "DEBUG"
                )
                if hasattr(self, "table_model") and self.table_model:
                    self.app_instance.log_message("...모델 데이터 초기화", "DEBUG")
                    self.table_model.clear_data()

                    if self.proxy_model and hasattr(self.proxy_model, "invalidate"):
                        self.app_instance.log_message("...프록시 모델 무효화", "DEBUG")
                        self.proxy_model.invalidate()

                    self.app_instance.log_message("...add_multiple_rows 호출", "DEBUG")
                    # ✅ [핵심 수정] column_keys 대신 None을 전달하여 모든 데이터 포함
                    self.table_model.add_multiple_rows(data_list, column_keys=None)
                    self.app_instance.log_message("...add_multiple_rows 완료", "DEBUG")

                    if self.proxy_model and hasattr(
                        self.proxy_model, "pre_analyze_all_columns"
                    ):
                        self.app_instance.log_message(
                            "...pre_analyze_all_columns 호출", "DEBUG"
                        )
                        self.proxy_model.pre_analyze_all_columns()
                        self.app_instance.log_message(
                            "...pre_analyze_all_columns 완료", "DEBUG"
                        )

                self.app_instance.log_message(
                    "▶️ on_search_completed: UI 업데이트 시작", "DEBUG"
                )
                self.app_instance.log_message("...컬럼 너비 조정", "DEBUG")
                adjust_qtableview_columns(
                    table_view=self.table_view,
                    current_dataframe=self.current_dataframe,
                    column_keys=self.column_keys,
                    column_headers=self.column_headers,
                )
                self.app_instance.log_message("...컬럼 너비 조정 완료", "DEBUG")

                self.app_instance.log_message("...첫 항목 포커스", "DEBUG")
                focus_on_first_table_view_item(self.table_view, self.app_instance)
                self.app_instance.log_message("...첫 항목 포커스 완료", "DEBUG")

                # -------------------
                # ✅ [핵심 수정] 탭 전환 전, DB에 저장된 사용자 설정을 확인하는 로직 추가

                # 1. DB에서 현재 탭의 "자동 탭 전환" 설정 값을 가져옴
                auto_switch_enabled = True  # 기본값은 True
                if self.tab_key and hasattr(self.app_instance, "db_manager"):
                    setting_key = f"{self.tab_key}_auto_switch"
                    value = self.app_instance.db_manager.get_setting(setting_key)
                    # 설정값이 존재하면 그 값을 따르고, 없으면 기본값(True) 사용
                    if value is not None:
                        auto_switch_enabled = value == "true"

                # 2. 모든 조건(자동검색, 우선순위, 사용자설정)이 맞을 때만 탭 전환
                if (
                    getattr(self, "_auto_search_triggered", False)
                    and getattr(self, "_switch_priority", False)  # 우선순위 확인
                    and auto_switch_enabled  # ✅ 사용자 설정 확인
                    and hasattr(self.app_instance, "main_window")
                ):
                    self.app_instance.main_window.switch_to_tab_by_name(self.tab_name)
                    self.app_instance.log_message(
                        f"✅ 검색 결과({len(data_list)}건)가 있어 우선순위 탭 '{self.tab_name}'(으)로 자동 전환합니다.",
                        "INFO",
                    )

                # 플래그들은 항상 초기화
                self._auto_search_triggered = False
                self._switch_priority = False
                # -------------------

                self.app_instance.log_message(
                    f"✅ 검색 완료: {len(data_list)}개 결과", "INFO"
                )
                self.status_label.setText(f"검색 완료: {len(data_list)}개 결과")

            else:
                if hasattr(self, "table_model") and self.table_model:
                    self.table_model.clear_data()
                self.app_instance.log_message("ℹ️ 검색 결과가 없습니다.", "INFO")
                self.status_label.setText("검색 결과가 없습니다.")
                # -------------------
                # ✅ [추가] 결과가 없을 때도 플래그는 초기화
                if getattr(self, "_auto_search_triggered", False):
                    self._auto_search_triggered = False
                if getattr(self, "_switch_priority", False):
                    self._switch_priority = False
                # -------------------

            self.app_instance.log_message("▶️ on_search_completed: 정상 종료", "DEBUG")

        except Exception as e:
            self.app_instance.log_message(
                f"❌ on_search_completed 내부에서 치명적 오류 발생: {e}", "ERROR"
            )
            self.current_dataframe = pd.DataFrame()
            self.reset_search_ui()
            # -------------------
            # ✅ [추가] 에러 발생 시에도 플래그는 초기화
            if getattr(self, "_auto_search_triggered", False):
                self._auto_search_triggered = False
            if getattr(self, "_switch_priority", False):
                self._switch_priority = False
            # -------------------

    def on_search_failed(self, error_msg):
        """검색 실패 이벤트 처리"""
        self.reset_search_ui()
        # [핵심 수정] 상태 메시지를 직접 업데이트합니다.
        self.status_label.setText("검색 실패")
        QMessageBox.critical(
            self, "검색 오류", f"검색 중 오류가 발생했습니다:\n{error_msg}"
        )

        # 로그 메시지
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(
                f"❌ {self.tab_name} 검색 실패: {error_msg}", "ERROR"
            )

    # === 데이터 관리 ===

    def update_table_data(self, data_list):
        """✅ [모델/뷰 전환] 완전히 새로운 데이터 업데이트 방식"""
        if not data_list:
            self.table_model.clear_data()
            return

        # ✅ [성능 함정 해결] 1. 데이터 입력 전에 정렬 기능을 잠시 끕니다.
        self.table_view.setSortingEnabled(False)

        # DataFrame 업데이트 (호환성 유지)
        self.current_dataframe = pd.DataFrame(data_list)

        # ✅ [핵심 변경] 모델에 데이터 추가
        self.table_model.clear_data()
        self.table_model.add_multiple_rows(data_list, self.column_keys)

        # 컬럼 너비 조정 (기존 함수 재사용)
        adjust_qtableview_columns(
            table_view=self.table_view,
            current_dataframe=self.current_dataframe,
            column_keys=self.column_keys,
            column_headers=self.column_headers,
        )

        # ✅ 5존 커스텀 헤더의 적상 작동을 위해 아래 자체 정렬 기능은 절대 켜지 말 것.
        # self.table_view.setSortingEnabled(False)

    # === 선택 및 복사 관련 ===

    def get_selected_items_count(self):
        """✅ [모델/뷰 전환] 현재 선택된 셀의 개수를 반환"""
        selection_model = self.table_view.selectionModel()
        if not selection_model:
            return 0

        selected_indexes = selection_model.selectedIndexes()
        return len(selected_indexes)

    def get_selected_items_info(self):
        """✅ [모델/뷰 전환] 현재 선택된 항목들의 정보를 반환"""
        selection_model = self.table_view.selectionModel()
        if not selection_model:
            return {"selected_count": 0, "selected_text": ""}

        selected_indexes = selection_model.selectedIndexes()
        selected_count = len(selected_indexes)

        if selected_count == 0:
            return {"selected_count": 0, "selected_text": ""}

        # 첫 번째 선택된 셀의 텍스트
        first_index = selected_indexes[0]
        item = self.table_model.itemFromIndex(first_index)
        selected_text = item.text() if item else ""

        return {
            "selected_count": selected_count,
            "selected_text": selected_text,
        }

    # === 편의 기능들 ===

    # ✅ [완전 복원] Find 관련 메서드들
    def find_in_results(self):
        """Enter 키로 다음 찾기"""
        self.find_next()

    def find_next(self):
        """다음 항목 찾기"""
        search_text = self.find_entry.text().strip()
        if not search_text:
            return

        # QTableView에서 찾기 구현
        self._find_in_table_view(search_text, "forward")

    def find_previous(self):
        """이전 항목 찾기"""
        search_text = self.find_entry.text().strip()
        if not search_text:
            return

        # QTableView에서 찾기 구현
        self._find_in_table_view(search_text, "backward")

    def _find_in_table_view(self, search_text, direction="forward"):
        """✅ [새로 구현] QTableView에서 텍스트 찾기"""
        if not hasattr(self, "table_view") or not self.table_view.model():
            return

        model = self.table_view.model()
        current_selection = self.table_view.currentIndex()

        start_row = current_selection.row() if current_selection.isValid() else 0
        start_col = current_selection.column() if current_selection.isValid() else 0

        # 검색 범위 설정
        row_count = model.rowCount()
        col_count = model.columnCount()

        found = False
        search_lower = search_text.lower()

        if direction == "forward":
            # 다음 찾기: 현재 위치부터 끝까지, 그다음 처음부터 현재까지
            for row in range(start_row, row_count):
                start_column = start_col + 1 if row == start_row else 0
                for col in range(start_column, col_count):
                    index = model.index(row, col)
                    cell_text = str(model.data(index, Qt.DisplayRole) or "").lower()
                    if search_lower in cell_text:
                        self.table_view.setCurrentIndex(index)
                        self.table_view.scrollTo(index)
                        found = True
                        break
                if found:
                    break

            # 찾지 못했으면 처음부터 현재 위치까지 검색
            if not found:
                for row in range(0, start_row + 1):
                    end_column = start_col if row == start_row else col_count
                    for col in range(0, end_column):
                        index = model.index(row, col)
                        cell_text = str(model.data(index, Qt.DisplayRole) or "").lower()
                        if search_lower in cell_text:
                            self.table_view.setCurrentIndex(index)
                            self.table_view.scrollTo(index)
                            found = True
                            break
                    if found:
                        break

        else:  # backward
            # 이전 찾기: 현재 위치부터 처음까지, 그다음 끝부터 현재까지
            for row in range(start_row, -1, -1):
                end_column = start_col if row == start_row else col_count
                for col in range(end_column - 1, -1, -1):
                    index = model.index(row, col)
                    cell_text = str(model.data(index, Qt.DisplayRole) or "").lower()
                    if search_lower in cell_text:
                        self.table_view.setCurrentIndex(index)
                        self.table_view.scrollTo(index)
                        found = True
                        break
                if found:
                    break

            # 찾지 못했으면 끝부터 현재 위치까지 검색
            if not found:
                for row in range(row_count - 1, start_row - 1, -1):
                    start_column = start_col if row == start_row else -1
                    for col in range(col_count - 1, start_column, -1):
                        index = model.index(row, col)
                        cell_text = str(model.data(index, Qt.DisplayRole) or "").lower()
                        if search_lower in cell_text:
                            self.table_view.setCurrentIndex(index)
                            self.table_view.scrollTo(index)
                            found = True
                            break
                    if found:
                        break

        if not found:
            QMessageBox.information(
                self, "찾기", f"'{search_text}'를 찾을 수 없습니다."
            )

    def clear_all_filters_action(self):
        """✅ [복원] 모든 필터 지우기 버튼"""
        if hasattr(self, "table_view"):
            header = self.table_view.horizontalHeader()
            if hasattr(header, "clear_all_filters"):
                header.clear_all_filters()
                self.app_instance.log_message("🗑️ 모든 필터가 지워졌습니다.", "INFO")
            else:
                self.app_instance.log_message(
                    "❌ 필터 기능을 찾을 수 없습니다.", "ERROR"
                )

    def show_html_viewer(self):
        """✅ [수정] HTML로 보기 = 드롭다운 HTML 뷰어"""
        try:
            if hasattr(self, "current_dataframe") and not self.current_dataframe.empty:

                show_in_dropdown_html_viewer(
                    app_instance=self.app_instance,
                    dataframe=self.current_dataframe,
                    title=f"{self.tab_name} 검색 결과",
                    columns_to_display=self.column_keys,
                    display_names=self.column_headers,
                    link_column_name="상세 링크",
                )

                self.app_instance.log_message(
                    "🌐 HTML 뷰어에서 데이터를 표시했습니다.", "INFO"
                )

            else:
                QMessageBox.information(self, "알림", "표시할 데이터가 없습니다.")
                self.app_instance.log_message("⚠️ 표시할 데이터가 없습니다.", "WARNING")

        except Exception as e:
            QMessageBox.critical(
                self, "오류", f"HTML 뷰어 표시 중 오류가 발생했습니다:\n{e}"
            )
            self.app_instance.log_message(f"❌ HTML 뷰어 표시 실패: {e}", "ERROR")

    # === 헤더 콜백 함수들 ===

    def get_header_callbacks(self):
        """헤더에서 사용할 콜백 함수들을 반환합니다."""
        return {
            "show_all": self.show_all_columns,  # ✅ 인스턴스 메서드 사용
            "hide_all": self.hide_all_columns,  # ✅ 인스턴스 메서드 사용
            "save": self.save_column_settings_action,
            "load": self.load_column_settings_action,
            "clear_sort": self.reset_table_order,  # 👈 [핵심 추가] 정렬 해제 시 테이블 순서 재정렬을 위한 콜백
        }

    def show_all_columns(self):
        """모든 컬럼을 표시합니다 - BaseSearchTab 인스턴스 메서드"""
        if hasattr(self, "table_view"):
            # ✅ [수정] 독립 함수 호출 (이름 변경된 함수 사용)

            show_all_columns_utility(
                widget=self.table_view,
                column_headers=self.column_headers,
                app_instance=self.app_instance,
            )

    def hide_all_columns(self):
        """첫 번째 컬럼을 제외하고 모두 숨깁니다 - BaseSearchTab 인스턴스 메서드"""
        if hasattr(self, "table_view"):
            # ✅ [수정] 독립 함수 호출 (이름 변경된 함수 사용)

            hide_all_columns_utility(
                widget=self.table_view,
                column_headers=self.column_headers,
                app_instance=self.app_instance,
            )

    def save_column_settings_action(self):
        """✅ [복원] 현재 컬럼 설정을 파일에 저장하는 동작"""
        try:
            save_column_settings(
                self.config.get("tab_name", "UNKNOWN"),
                self.column_headers,
                self.table_view,  # QTableWidget → QTableView 변경
                self.app_instance,
            )
        except Exception as e:
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(f"❌ 컬럼 설정 저장 실패: {e}", "ERROR")

    def load_column_settings_action(self):
        """✅ [복원] 파일에서 컬럼 설정을 불러오는 동작"""
        try:
            load_column_settings(
                self.config.get("tab_name", "UNKNOWN"),
                self.column_headers,
                self.table_view,  # QTableWidget → QTableView 변경
                self.app_instance,
            )
        except Exception as e:
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(
                    f"❌ 컬럼 설정 불러오기 실패: {e}", "ERROR"
                )

    # === 호환성 메서드들 (기존 코드와의 호환성 유지) ===

    def open_link_in_column(self, url):
        """[수정] 공용 함수를 호출하여 링크 열기 기능"""
        open_url_safely(url, self.app_instance)  # 👈 app_instance 전달

    # === 고급 기능 ===

    def copy_selected_as_markdown(self):
        """✅ [모델/뷰 전환] 선택된 데이터를 마크다운 테이블 형식으로 복사"""
        selection_model = self.table_view.selectionModel()
        if not selection_model:
            return

        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(self, "알림", "복사할 데이터를 선택해주세요.")
            return

        try:
            # 선택된 영역의 행과 열 범위 계산
            rows = sorted(set(index.row() for index in selected_indexes))
            cols = sorted(set(index.column() for index in selected_indexes))

            # 마크다운 테이블 헤더 생성
            markdown_lines = []

            # 헤더 행
            header_line = (
                "| " + " | ".join(self.column_headers[col] for col in cols) + " |"
            )
            markdown_lines.append(header_line)

            # 구분선
            separator_line = "| " + " | ".join("---" for _ in cols) + " |"
            markdown_lines.append(separator_line)

            # 데이터 행들
            for row in rows:
                row_data = []
                for col in cols:
                    item = self.table_model.item(row, col)
                    cell_text = item.text() if item else ""
                    # 마크다운에서 파이프 문자 이스케이프
                    cell_text = cell_text.replace("|", "\\|")
                    row_data.append(cell_text)

                data_line = "| " + " | ".join(row_data) + " |"
                markdown_lines.append(data_line)

            # 클립보드에 복사
            markdown_text = "\n".join(markdown_lines)
            clipboard = QApplication.clipboard()
            clipboard.setText(markdown_text)

            # 성공 메시지
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(
                    f"📋 마크다운 테이블 복사 완료: {len(rows)}행 x {len(cols)}열",
                    "INFO",
                )

        except Exception as e:
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(f"❌ 마크다운 복사 실패: {e}", "ERROR")
            QMessageBox.critical(
                self, "오류", f"마크다운 복사 중 오류가 발생했습니다:\n{e}"
            )

    def copy_selected_as_text(self):
        """✅ [모델/뷰 전환] 선택된 데이터를 탭 구분 텍스트로 복사"""
        selection_model = self.table_view.selectionModel()
        if not selection_model:
            return

        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            return

        try:
            # 선택된 영역을 행별로 정리
            rows_data = {}
            for index in selected_indexes:
                row = index.row()
                col = index.column()
                if row not in rows_data:
                    rows_data[row] = {}

                item = self.table_model.item(row, col)
                rows_data[row][col] = item.text() if item else ""

            # 텍스트 생성
            text_lines = []
            for row in sorted(rows_data.keys()):
                row_cells = []
                for col in sorted(rows_data[row].keys()):
                    row_cells.append(rows_data[row][col])
                text_lines.append("\t".join(row_cells))

            # 클립보드에 복사
            text_content = "\n".join(text_lines)
            clipboard = QApplication.clipboard()
            clipboard.setText(text_content)

            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(
                    f"📋 텍스트 복사 완료: {len(rows_data)}행", "INFO"
                )

        except Exception as e:
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(f"❌ 텍스트 복사 실패: {e}", "ERROR")

    def export_to_excel(self):
        """[수정] 공용 함수를 호출하여 현재 데이터를 Excel로 내보내기"""
        export_dataframe_to_excel(
            self, self.current_dataframe, self.tab_name, self.app_instance
        )

    def print_table_data(self):
        """[수정] 공용 함수를 호출하여 테이블 데이터 인쇄"""
        print_table_data(
            self,
            self.table_model,
            self.tab_name,
            self.column_headers,
            self.app_instance,
        )

    # === 통계 및 분석 기능 ===

    def show_data_statistics(self):
        """[수정] 공용 함수를 호출하여 데이터 통계 정보 표시"""
        show_dataframe_statistics(
            self, self.current_dataframe, self.tab_name, self.app_instance
        )

    # === 필터링 및 검색 고급 기능 ===

    def advanced_filter_dialog(self):
        """✅ [새로운 기능] 고급 필터 대화상자"""
        # TODO: 고급 필터 기능 구현
        QMessageBox.information(self, "개발 중", "고급 필터 기능은 현재 개발 중입니다.")

    def quick_filter_by_column(self, column_index, filter_value):
        """✅ [새로운 기능] 특정 컬럼 값으로 빠른 필터링"""
        # TODO: 프록시 모델을 이용한 필터링 구현
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(
                f"🔍 빠른 필터: {self.column_headers[column_index]} = '{filter_value}'",
                "INFO",
            )

    # === 접근성 및 사용성 개선 ===

    def toggle_row_numbers(self):
        """✅ [새로운 기능] 행 번호 표시/숨기기 토글"""
        vertical_header = self.table_view.verticalHeader()
        is_visible = vertical_header.isVisible()
        vertical_header.setVisible(not is_visible)

        if hasattr(self.app_instance, "log_message"):
            status = "표시" if not is_visible else "숨김"
            self.app_instance.log_message(f"🔢 행 번호 {status}", "INFO")

    def reset_column_widths(self):
        """✅ [새로운 기능] 컬럼 너비 초기화"""
        if hasattr(self, "table_view"):
            header = self.table_view.horizontalHeader()
            for i in range(len(self.column_headers)):
                header.resizeSection(i, 150)  # 기본 150px로 재설정

            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(
                    "📏 컬럼 너비가 초기화되었습니다.", "INFO"
                )

    def auto_resize_columns(self):
        """✅ [새로운 기능] 내용에 맞게 컬럼 너비 자동 조정"""
        if hasattr(self, "table_view"):
            self.table_view.resizeColumnsToContents()

            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(
                    "📐 컬럼 너비가 내용에 맞게 조정되었습니다.", "INFO"
                )

    # [새로 추가] 탭 변경 시 포커스를 설정하는 메서드
    def set_initial_focus(self):
        """탭이 활성화될 때 primary_search_field에 포커스를 설정합니다."""
        # 1순위: primary_search_field 속성이 있으면 우선 사용
        if hasattr(self, "primary_search_field"):
            widget = self.primary_search_field
            if widget and widget.isVisible() and widget.isEnabled():
                QTimer.singleShot(0, lambda: widget.setFocus())
                return

        # 2순위: input_widgets의 'title' 필드 (기존 호환성)
        if (
            "title" in self.input_widgets
            and self.input_widgets["title"].isVisible()
            and self.input_widgets["title"].isEnabled()
        ):
            QTimer.singleShot(0, lambda: self.input_widgets["title"].setFocus())

        # [핵심 추가] 테이블 순서를 원본대로 복원하는 메서드

    def reset_table_order(self):
        """정렬을 해제하고 테이블의 행 순서를 원본 순서(DataFrame)대로 복원합니다."""
        if not self.current_dataframe.empty:
            # DataFrame을 리스트 형태로 변환하여 update_table_data로 재로드
            data_list = self.current_dataframe.to_dict("records")
            self.update_table_data(data_list)
            self.app_instance.log_message(
                "🔄 테이블 행 순서를 원본대로 복원했습니다.", "INFO"
            )
        else:
            self.app_instance.log_message("ℹ️ 복원할 데이터가 없습니다.", "INFO")

    # ✅ [추가] Find 영역의 표시 상태를 토글하는 메서드를 추가합니다.
    def toggle_find_area_visibility(self):
        """Find 영역의 보이기/숨기기 상태를 전환합니다."""
        if hasattr(self, "find_area_container"):
            is_visible = self.find_area_container.isVisible()
            self.find_area_container.setVisible(not is_visible)
            if hasattr(self.app_instance, "log_message"):
                status = "숨김" if is_visible else "표시"
                self.app_instance.log_message(
                    f"ℹ️ 찾기(Find) 영역을 {status} 처리했습니다. (F7)", "INFO"
                )

    def _update_detail_view(self, current, previous, proxy_model, table_model):
        """[일반화] 선택된 행이 변경될 때 메인 윈도우의 상세 정보 뷰를 업데이트합니다."""
        if not current.isValid():
            if hasattr(self.app_instance, "main_window"):
                self.app_instance.main_window.detail_display.clear()
            return

        # QStandardItemModel 또는 FastSearchResultModel에서 행 데이터 가져오기
        source_index = proxy_model.mapToSource(current)
        row_data = table_model.get_row_data(source_index.row())
        if not row_data:
            return

        model = table_model # 인자로 받은 table_model 사용
        row = source_index.row()

        # ✅ [수정] 포맷팅 로직 적용 시작

        # ❗ UI 상수 임포트
        from ui_constants import UI_CONSTANTS

        U = UI_CONSTANTS

        # ✅ [추가] 컬럼명 스타일 정의
        header_style = f"color: {U.ACCENT_GREEN}; font-weight: bold;"

        # ❗ URL 패턴 확인을 위한 정규식
        url_pattern = re.compile(r'(https?://[^\s<>"]+|www\.[^\s<>"]+)')

        content_lines = []
        for col in range(model.columnCount()):
            column_name = model.headerData(col, Qt.Horizontal, Qt.DisplayRole) or ""
            value_content = model.data(model.index(row, col), Qt.DisplayRole) or ""
            # ✅ [핵심 수정 1] U+2029 (PARAGRAPH SEPARATOR) 문자를 즉시 제거
            value_content = str(value_content).replace("\u2029", "")

            # 1. KAC/KSH 형식 특별 처리 (무조건 줄바꿈 강제)
            is_ksh_content = "▼a" in value_content and "▲" in value_content
            is_url_content = bool(url_pattern.search(str(value_content)))

            # ✅ [수정] 헤더 스타일 적용 (▶와 텍스트 사이에 공백 없음)
            styled_header = f'▶ <span style="{header_style}">{column_name}:</span>'

            if is_ksh_content or is_url_content:
                # KSH/URL이 포함된 경우 무조건 줄바꿈 (\n) 삽입
                if is_ksh_content:
                    value_content = value_content.replace("▲; ▼a", "▲\n▼a").replace(
                        "▲, ▼a", "▲\n▼a"
                    )

                # ❗ 스타일 적용된 헤더와 값 사이에 \n 삽입
                formatted_line = f"{styled_header}\n{value_content}"
                content_lines.append(formatted_line)
            else:
                # KSH 형식이 아닐 경우 - _format_text_for_detail_view 사용
                formatted_value = _format_text_for_detail_view(value_content)

                if "\n" in formatted_value:
                    # 줄바꿈이 있으면 \n 삽입
                    formatted_line = f"{styled_header}\n{formatted_value}"
                else:
                    # 줄바꿈이 없으면 공백 한 칸으로 구분
                    formatted_line = f"{styled_header} {formatted_value}"

                content_lines.append(formatted_line)

        final_text = "\n".join(content_lines)

        # 메인 윈도우의 상세 정보 뷰에 텍스트 설정 (HTML 조립 단계)
        if hasattr(self.app_instance, "main_window"):
            main_window = self.app_instance.main_window
            if hasattr(main_window, "detail_display"):

                U = UI_CONSTANTS  # UI 상수 가져오기

                # 1. 텍스트를 줄 단위로 분리합니다.
                lines = final_text.split("\n")
                html_lines = []

                # 2. 각 줄에 대해 링크화 및 HTML 포맷을 적용합니다.
                for line in lines:
                    # ✅ [수정] 불필요한 빈 줄 발생 방지 및 라인 정리
                    temp_line = line.strip()
                    if not temp_line:
                        continue

                    # HTML 태그 이스케이프 문제 해결
                    if '<span style="' in line:
                        linked_line = line
                    else:
                        linked_line = linkify_text(line)

                    # 3. 링크 태그에 인라인 스타일을 강제 적용합니다.
                    link_style = (
                        f'style="color: {U.ACCENT_BLUE}; text-decoration: none;"'
                    )
                    linked_line = linked_line.replace(
                        "<a href=", f"<a {link_style} href="
                    )

                    # ✅ [핵심 수정 2] 트리플 클릭 공백 해결: \r, \xa0, \u2029 등을 제거하고 최종 strip() 적용
                    linked_line = (
                        linked_line.replace("\r", "")  # Carriage Return 제거
                        .replace("\u2029", "")  # PARAGRAPH SEPARATOR 재확인 및 제거
                        .replace("\xa0", " ")  # Non-Breaking Space를 일반 공백으로
                        .strip()
                    )

                    # 4. 각 줄을 추가
                    html_lines.append(linked_line)

                # 5. 최종 HTML - 각 줄을 독립된 테이블로 (완전 분리)
                tables = [
                    f'<table cellspacing="0" cellpadding="0" style="border:none;margin:0;padding:0;"><tr><td style="padding:0;border:none;">{line}</td></tr></table>'
                    for line in html_lines
                ]
                final_html = "".join(tables)
                main_window.detail_display.setHtml(final_html)
