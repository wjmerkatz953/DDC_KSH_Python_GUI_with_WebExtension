# -*- coding: utf-8 -*-
# 파일명: qt_TabView_KSH_Local.py
# 설명: KSH Local DB 검색 탭 (상단: 개념 DB, 하단: 서지 DB)
# 버전: 4.4.1 - HTML 뷰어 다중 테이블 지원 개선
# 생성일: 2025-09-30
# 수정일: 2025-10-29
#
# 변경 이력:
# v4.4.1 (2025-10-29)
# - [기능 추가] HTML 뷰어 다중 테이블 지원 개선
#   : last_clicked_table 속성 추가 ("table_view" | "biblio_table")
#   : _on_table_view_clicked(): 상단 개념 DB 테이블 클릭 시 기록
#   : _on_biblio_table_clicked(): 하단 서지 DB 테이블 클릭 시 기록
#   : HTML 뷰어가 마지막으로 클릭한 테이블 데이터를 정확히 표시
#
# v2.2.1 (2025-10-28)
# - [기능 추가] HTML 뷰어 지원을 위한 DataFrame 저장
#   : on_search_completed()에서 current_dataframe/biblio_dataframe 업데이트
#   : _on_title_search_completed()에서 biblio_dataframe 업데이트
#   : _on_biblio_search_completed()에서 biblio_dataframe 업데이트
#
# v2.2.0 (2025-10-18)
# - [기능 추가] QSplitter 자동 저장/복구 기능 추가
#   : self.results_splitter가 이미 인스턴스 변수로 정의되어 있어 추가 수정 불필요
#   : 앱 종료 시 개념 DB/서지 DB 분할 비율이 자동으로 DB에 저장되고 재시작 시 복구됨
#
# v2.1.0 (2025-10-02)
# - [버그 수정] QThread 강제 종료 문제 해결
#   : __init__에서 스레드 변수 초기화 추가 (라인 103-105)
#   : stop_flag를 매번 새로 생성하지 않고 재사용하도록 변경
#   : _cleanup_biblio_thread() 메서드 추가 (라인 659-670)
#   : _cleanup_concept_thread() 메서드 추가 (라인 672-683)
#   : cleanup_all_threads() 메서드 추가 (라인 685-689)
#   : closeEvent() 오버라이드 추가 (라인 691-694)
#   : 검색 시작 전 기존 스레드를 안전하게 정리하도록 개선 (라인 411-415, 483-487)
# - [효과] 연동 검색 중 탭 전환 또는 앱 종료 시 "QThread: Destroyed while thread is still running" 오류 해결

from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QComboBox,
    QSplitter,
    QTableView,
    QWidget,
    QFrame,
    QHeaderView,
    QVBoxLayout,
    QMessageBox,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QAbstractItemView,
)
from PySide6.QtCore import (
    Qt,
    QModelIndex,
    QThread,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
)
import pandas as pd
import threading
import re
from functools import partial  # ✅ [수정] partial 함수를 임포트합니다.
from qt_base_tab import BaseSearchTab, FastSearchResultModel
from qt_proxy_models import SmartNaturalSortProxyModel
from qt_utils import SelectAllLineEdit
from ui_constants import U
from qt_context_menus import setup_widget_context_menu
from qt_widget_events import ExcelStyleTableHeaderView, focus_on_first_table_view_item
from view_displays import adjust_qtableview_columns
from Search_KSH_Local import KshLocalSearcher


class BiblioSearchThread(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, db_manager, keyword, stop_flag):
        super().__init__()
        self.db_manager = db_manager
        self.keyword = keyword
        self.stop_flag = stop_flag
        self.searcher = KshLocalSearcher(db_manager)

    def run(self):
        try:
            if self.stop_flag.is_set():
                return
            final_keyword = re.sub(r"\[.*?\]|\(.*?\)", "", self.keyword).strip()
            df_biblio = self.searcher.search_biblio_by_subject(final_keyword)
            if df_biblio is None:
                df_biblio = pd.DataFrame()
            self.finished.emit(df_biblio)
        except Exception as e:
            import traceback

            self.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")


class TitleSearchThread(QThread):
    """✅ [신규 추가] 제목으로 서지 DB를 검색하는 전용 스레드"""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, db_manager, title_keyword, stop_flag):
        super().__init__()
        self.db_manager = db_manager
        self.title_keyword = title_keyword
        self.stop_flag = stop_flag
        self.searcher = KshLocalSearcher(db_manager)

    def run(self):
        try:
            if self.stop_flag.is_set():
                return
            # 제목으로 서지 검색
            df_biblio = self.searcher.search_biblio_by_title(self.title_keyword)
            if df_biblio is None:
                df_biblio = pd.DataFrame()
            self.finished.emit(df_biblio)
        except Exception as e:
            import traceback

            self.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")


# ==========================================================
# ✅ [신규 추가] 하단 -> 상단 연동 검색을 위한 스레드
# ==========================================================
class ConceptSearchThread(QThread):
    """상단 개념 DB만 검색하는 전용 스레드"""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, db_manager, search_query, stop_flag):
        super().__init__()
        self.db_manager = db_manager
        self.search_query = search_query
        self.stop_flag = stop_flag
        self.searcher = KshLocalSearcher(db_manager)

    def run(self):
        try:
            if self.stop_flag.is_set():
                return
            # -------------------
            # [수정] search_concepts는 컬럼명을 UI 헤더에 맞게 'DDC', '주제모음' 등으로
            # 변환해주는 래퍼(Wrapper) 함수입니다. 이 함수를 사용해야 데이터가 정상적으로 표시됩니다.
            df_concepts = self.searcher.search_concepts(keyword=self.search_query)
            # -------------------
            if df_concepts is None:
                df_concepts = pd.DataFrame()
            self.finished.emit(df_concepts)
        except Exception as e:
            import traceback

            self.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")


class QtKSHLocalSearchTab(BaseSearchTab):
    def __init__(self, config, app_instance):
        column_map_bottom = config.get("column_map_bottom", [])
        self.biblio_keys = [col[0] for col in column_map_bottom]
        self.biblio_headers = [col[1] for col in column_map_bottom]

        self.auto_search_enabled = False
        self.current_search_type = None  # ✅ [추가] 검색 유형 저장 변수
        self._last_selected_row = None  # ✅ [추가] 마지막 선택 행 저장 (상단)
        self._last_selected_biblio_row = None  # ✅ [추가] 마지막 선택 행 저장 (하단)
        # ✅ [추가] 최근 클릭된 테이블 추적 (HTML 뷰어용)
        self.last_clicked_table = None  # "table_view" or "biblio_table"

        # ✅ [신규 추가] 스레드 관리 변수 초기화
        self.stop_flag = threading.Event()
        self.biblio_search_thread = None
        self.concept_search_thread = None
        self.title_search_thread = None  # ✅ [추가] 제목 검색 스레드

        self.biblio_model = FastSearchResultModel(self.biblio_headers)
        self.biblio_proxy = SmartNaturalSortProxyModel()
        self.biblio_proxy.setSourceModel(self.biblio_model)
        self.biblio_table = QTableView()
        self.biblio_table.setModel(self.biblio_proxy)

        # ✅ [추가] URL hover 시 커서 변경 + 파란색 표시 + 클릭 시 열기 delegate 설정
        from qt_custom_widgets import URLHoverDelegate

        self.biblio_table.setItemDelegate(
            URLHoverDelegate(self.biblio_table, app_instance)
        )
        self.biblio_table.setMouseTracking(True)

        # ✅ [핵심 추가] 내부 컬럼 목록을 저장하여 숨김 처리할 때 사용
        self.internal_columns = ["_concept_id"]

        super().__init__(config, app_instance)

        # ✅ [핵심 추가] _concept_id를 column_headers에 추가 (숨김 처리용)
        if "_concept_id" not in self.column_headers:
            self.column_headers.append("_concept_id")
            self.table_model.column_headers.append("_concept_id")

        editable_cols = config.get("editable_columns_top", [])
        self.editable_columns = {
            self.column_headers.index(col)
            for col in editable_cols
            if col in self.column_headers
        }

        # ✅ [추가] 테이블 모델에 편집 가능 컬럼 설정
        if hasattr(self, "table_model"):
            self.table_model.set_editable_columns(self.editable_columns)
            # ✅ [핵심 추가] QTableView 편집 트리거 활성화
            self.table_view.setEditTriggers(
                QAbstractItemView.DoubleClicked
                | QAbstractItemView.EditKeyPressed
                | QAbstractItemView.AnyKeyPressed
            )

        # ✅ [추가] 데이터 변경 시 DB 저장 시그널 연결
        if hasattr(self, "table_model"):
            self.table_model.dataChanged.connect(self._on_cell_data_changed)

        # ✅ [핵심 추가] 인라인 편집 시 텍스트가 잘리지 않도록 행 높이 조정
        self.table_view.verticalHeader().setDefaultSectionSize(32)  # 행 높이 32px
        self.table_view.verticalHeader().setMinimumSectionSize(28)  # 최소 28px

        self.load_categories()

    # ✅ [1번 수정] KSH Hybrid 탭의 방식을 복사하여 입력 섹션을 안정적으로 재구성합니다.

    def create_input_section(self, parent_layout):
        self.input_container = QFrame()
        self.input_layout = QGridLayout(self.input_container)
        self.input_container.setLayout(self.input_layout)
        self.input_layout.setContentsMargins(0, 4, 0, 0)  # Input과 TableView 수직 간격

        # ✅ [추가] 첫 번째 체크박스 - 통합검색용
        self.unified_check = QCheckBox("통합:")
        self.unified_check.setChecked(True)
        self.unified_check.setFixedHeight(32)  # ✅ BaseSearchTab과 동일한 높이

        # ✅ [통일] 검색어 입력창을 input_widgets["search_term"]으로 표준화
        self.input_widgets["search_term"] = SelectAllLineEdit()
        self.input_widgets["search_term"].setFixedHeight(32)
        self.input_widgets["search_term"].setPlaceholderText(
            "KSH 주제명, DDC/KSH 코드 입력"
        )
        self.input_widgets["search_term"].returnPressed.connect(self.start_search)

        # ✅ [추가] 두 번째 체크박스 - 제목검색용
        self.title_check = QCheckBox("제목:")
        self.title_check.setChecked(False)
        self.title_check.setFixedHeight(32)  # ✅ BaseSearchTab과 동일한 높이

        # ✅ [추가] 제목 검색 입력창
        self.input_widgets["title"] = SelectAllLineEdit()
        self.input_widgets["title"].setFixedHeight(32)
        self.input_widgets["title"].setPlaceholderText("서지 제목 검색")
        self.input_widgets["title"].returnPressed.connect(self.start_search)

        # 카테고리 콤보박스
        self.category_combo = QComboBox()
        # [추가] 콤보박스의 높이를 32px로 고정합니다.
        self.category_combo.setFixedHeight(32)
        self.category_combo.addItem("전체")

        super()._create_standard_buttons()
        self.search_button.setFixedWidth(100)
        self.search_button.setText("통합 검색")

        # ✅ [레이아웃 구성] 체크박스 - 입력필드 - 체크박스 - 입력필드 - 버튼들
        self.input_layout.addWidget(self.unified_check, 0, 0)
        self.input_layout.addWidget(self.input_widgets["search_term"], 0, 1)
        self.input_layout.addWidget(self.title_check, 0, 2)
        self.input_layout.addWidget(self.input_widgets["title"], 0, 3)
        self.input_layout.addWidget(self.category_combo, 0, 4)
        self.input_layout.addWidget(self.search_button, 0, 5)
        self.input_layout.addWidget(self.stop_button, 0, 6)

        # ✅ [중요] 입력필드 3개의 비율을 1:1:1로 설정
        self.input_layout.setColumnStretch(1, 1)  # 통합 검색 필드 (1번 컬럼)
        self.input_layout.setColumnStretch(3, 1)  # 제목 검색 필드 (3번 컬럼)
        self.input_layout.setColumnStretch(4, 1)  # 카테고리 콤보박스 (4번 컬럼)

        # ✅ [추가] 체크박스 상호배타적 동작 설정
        self.unified_check.toggled.connect(self._on_unified_check_toggled)
        self.title_check.toggled.connect(self._on_title_check_toggled)

        parent_layout.addWidget(self.input_container)

    def create_results_section(self, parent_layout):
        temp_container = QWidget()
        temp_layout = QVBoxLayout()
        temp_container.setLayout(temp_layout)
        super().create_results_section(temp_layout)

        self.results_splitter = QSplitter(Qt.Vertical)

        concept_container = QGroupBox("📚 KSH 개념 DB 검색 결과")
        concept_layout = QVBoxLayout(concept_container)
        concept_layout.setContentsMargins(0, 0, 0, 0)  # ✅ 추가: 상, 우, 하, 좌 여백
        concept_layout.addWidget(self.table_view)

        self.results_splitter.addWidget(concept_container)

        biblio_container = self._create_biblio_section()
        self.results_splitter.addWidget(biblio_container)

        self.results_splitter.setSizes([500, 500])
        parent_layout.addWidget(self.results_splitter, 1)

    def _create_biblio_section(self):
        biblio_container = QGroupBox("📖 서지 DB 검색 결과")
        biblio_container.setObjectName("BiblioGroupBox")  # ✅ 추가
        biblio_layout = QVBoxLayout(biblio_container)
        biblio_layout.setContentsMargins(0, 0, 0, 0)  # ✅ 추가: 상, 우, 하, 좌 여백
        self.biblio_table.setSortingEnabled(False)
        self.biblio_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems
        )
        self.biblio_table.setAlternatingRowColors(True)

        # 헤더 객체 생성
        # ✅ [수정] tab_instance를 5번째 파라미터로 전달하여 헤더 컨텍스트 메뉴 활성화
        biblio_header_obj = ExcelStyleTableHeaderView(
            Qt.Horizontal,
            self.biblio_table,
            self.biblio_headers,
            None,  # callbacks
            self,  # tab_instance
        )
        self.biblio_table.setHorizontalHeader(biblio_header_obj)

        # -------------------
        # ✅ [핵심 수정] 상단 테이블 및 다른 탭과 동일한 헤더/뷰 설정을 추가합니다.
        header = self.biblio_table.horizontalHeader()

        # 컬럼 너비 상호작용 및 크기 설정
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)  # 마지막 컬럼을 남은 공간에 꽉 채웁니다.
        header.setMinimumSectionSize(60)
        header.setDefaultSectionSize(150)  # 모든 컬럼의 기본 너비를 150px로 설정합니다.

        # 컬럼 이동 및 클릭 기능 활성화
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)

        # 부드러운 스크롤 적용
        self.biblio_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.biblio_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        # -------------------

        setup_widget_context_menu(self.biblio_table, self.app_instance)

        biblio_layout.addWidget(self.biblio_table)
        return biblio_container

    def create_find_section(self, parent_layout):
        """[오버라이드] NLK 탭 방식을 사용하여 '자동검색' 버튼을 안정적으로 추가합니다."""
        # 1. 부모 클래스의 메서드를 호출하여 기본 Find 섹션을 먼저 생성합니다.
        super().create_find_section(parent_layout)

        # 2. '자동검색' 버튼을 생성합니다.
        self.auto_search_toggle = QPushButton("왼쪽 클릭 자동검색 OFF")
        self.auto_search_toggle.setCheckable(True)
        self.auto_search_toggle.setChecked(False)
        self.auto_search_toggle.setFixedWidth(180)
        self.auto_search_toggle.clicked.connect(self.toggle_auto_search)

        # 3. 부모가 생성한 레이아웃에 접근하여 버튼을 추가합니다.
        # parent_layout의 마지막 위젯이 super()가 만든 bar_container 입니다.
        bar_container = parent_layout.itemAt(parent_layout.count() - 1).widget()
        if bar_container:
            # ✅ F7 키 기능을 위해 self 변수에 참조를 저장하는 것을 잊지 않습니다.
            self.find_area_container = bar_container

            bar_layout = bar_container.layout()
            if bar_layout and bar_layout.count() >= 2:
                # bar_layout의 두 번째 위젯이 find_container 입니다.
                find_container = bar_layout.itemAt(1).widget()
                if find_container:
                    find_layout = find_container.layout()
                    if find_layout:
                        # 'HTML로 보기' 버튼 다음에 '자동검색' 버튼을 추가합니다.
                        find_layout.addWidget(self.auto_search_toggle)

    # -------------------
    # ✅ [핵심 추가] BaseSearchTab의 on_search_completed 메서드를 오버라이드합니다.
    def on_search_completed(self, results):
        """[오버라이드] KSH Local 탭 전용 검색 완료 처리기. 두 개의 테이블을 모두 업데이트합니다."""
        try:
            # UI 상태 초기화 및 프로그레스바 애니메이션
            self.is_searching = False
            self.search_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.animation = QPropertyAnimation(self.progress_bar, b"value")
            self.animation.setDuration(800)
            self.animation.setStartValue(self.progress_bar.value())
            self.animation.setEndValue(100)
            self.animation.setEasingCurve(QEasingCurve.InOutCubic)
            self.animation.start()

            # 결과 튜플 분해 (df_concepts, df_biblio, search_type)
            if isinstance(results, tuple) and len(results) == 3:
                df_concepts, df_biblio, search_type = results
                self.current_search_type = search_type
                self.app_instance.log_message(
                    f"✅ 검색 유형 감지: '{search_type}'", "DEBUG"
                )
            else:
                self.app_instance.log_message(
                    "❌ 예상치 못한 검색 결과 형식입니다.", "ERROR"
                )
                df_concepts, df_biblio, self.current_search_type = (
                    pd.DataFrame(),
                    pd.DataFrame(),
                    None,
                )

            # ✅ [핵심 추가] HTML 뷰어/추출 기능을 위해 current_dataframe 업데이트
            # 상단 개념 DB를 기본으로 설정 (나중에 포커스된 테이블로 자동 전환 가능)
            self.current_dataframe = df_concepts.copy() if not df_concepts.empty else pd.DataFrame()
            # ✅ [추가] 하단 서지 DB도 별도 변수에 저장
            self.biblio_dataframe = df_biblio.copy() if not df_biblio.empty else pd.DataFrame()

            # 상단 개념 DB 테이블 업데이트
            self.table_model.clear_data()
            if not df_concepts.empty:
                self.proxy_model.invalidate()
                records_concepts = df_concepts.to_dict("records")
                # -------------------
                # ✅ [버그 수정] 데이터의 컬럼 순서(df_cols) 대신, UI에 정의된 컬럼 순서를 사용하도록
                # column_keys를 None으로 전달하여 add_multiple_rows가 self.column_headers를 사용하게 합니다.
                df_cols = df_concepts.columns.tolist()
                self.table_model.add_multiple_rows(records_concepts, column_keys=None)
                self.proxy_model.pre_analyze_all_columns()
                adjust_qtableview_columns(
                    self.table_view, df_concepts, df_cols, self.column_headers
                )
                # -------------------

            # 하단 서지 DB 테이블 업데이트
            self.biblio_model.clear_data()
            if not df_biblio.empty:
                self.biblio_proxy.invalidate()
                records_biblio = df_biblio.to_dict("records")
                self.biblio_model.add_multiple_rows(
                    records_biblio, column_keys=self.biblio_keys
                )
                self.biblio_proxy.pre_analyze_all_columns()
                adjust_qtableview_columns(
                    self.biblio_table, df_biblio, self.biblio_keys, self.biblio_headers
                )

            # 상태 메시지 및 포커스 설정
            total_results = len(df_concepts) + len(df_biblio)
            if total_results > 0:
                self.status_label.setText(
                    f"검색 완료: 총 {total_results}개 결과 (상단 {len(df_concepts)}, 하단 {len(df_biblio)})"
                )

                # 검색 유형에 따라 포커스 설정
                if self.current_search_type in ["ddc", "ksh"] and not df_biblio.empty:
                    focus_on_first_table_view_item(
                        self.biblio_table, self.app_instance
                    )  # DDC/KSH 검색은 하단에 포커스
                elif not df_concepts.empty:
                    focus_on_first_table_view_item(
                        self.table_view, self.app_instance
                    )  # 그 외에는 상단에 포커스
                elif not df_biblio.empty:
                    focus_on_first_table_view_item(self.biblio_table, self.app_instance)

            else:
                self.status_label.setText("검색 결과가 없습니다.")

        except Exception as e:
            self.app_instance.log_message(
                f"❌ KSH Local 검색 완료 처리 중 오류: {e}", "ERROR"
            )
            import traceback

            self.app_instance.log_message(traceback.format_exc(), "ERROR")
            self.reset_search_ui()

    # -------------------

    def get_search_params(self):
        """[수정] 제목 검색과 통합 검색을 구분하여 처리"""
        # ✅ [핵심 추가] 제목 검색이 활성화된 경우
        if self.title_check.isChecked():
            title_keyword = self.input_widgets["title"].text().strip()
            if not title_keyword:
                QMessageBox.warning(self, "입력 오류", "제목을 입력해주세요.")
                return None

            # 제목 검색을 위한 특별한 파라미터
            return {
                "search_mode": "title",
                "title_keyword": title_keyword,
                "db_manager": self.app_instance.db_manager,
            }

        # ✅ [기존] 통합 검색이 활성화된 경우
        search_term = self.input_widgets["search_term"].text().strip()
        main_category = self.category_combo.currentText()

        # ✅ [수정] 검색어와 카테고리 모두 없으면 오류
        if not search_term and (not main_category or main_category == "전체"):
            QMessageBox.warning(
                self, "입력 오류", "검색어를 입력하거나 카테고리를 선택해주세요."
            )
            return None

        # ✅ [수정] 검색어가 있으면 카테고리는 무시 (전체로 검색)
        # 단, 콤보박스는 사용자가 선택한 값 유지
        if search_term:
            main_category = "전체"

        return {
            "search_mode": "unified",
            "search_term": search_term,
            "main_category": main_category,
            "db_manager": self.app_instance.db_manager,
        }

    def start_search(self):
        """[오버라이드] 제목 검색과 통합 검색을 구분하여 처리"""
        if self.is_searching:
            return

        search_params = self.get_search_params()
        if not search_params:
            return

        # ✅ [핵심 추가] 제목 검색 모드
        if search_params.get("search_mode") == "title":
            title_keyword = search_params.get("title_keyword", "")
            if title_keyword:
                self._start_title_search(title_keyword)
            return

        # ✅ [기존] 통합 검색 모드 - 부모 클래스의 검색 로직 사용
        super().start_search()

    # ✅ [신규 추가] 체크박스 상호배타적 동작 메서드
    def _on_unified_check_toggled(self, checked):
        """통합 검색 체크박스가 토글되면 제목 검색 체크박스를 해제"""
        if checked:
            self.title_check.setChecked(False)
            self.input_widgets["search_term"].setEnabled(True)
            self.input_widgets["title"].setEnabled(False)

    def _on_title_check_toggled(self, checked):
        """제목 검색 체크박스가 토글되면 통합 검색 체크박스를 해제"""
        if checked:
            self.unified_check.setChecked(False)
            self.input_widgets["search_term"].setEnabled(False)
            self.input_widgets["title"].setEnabled(True)

    # ✅ [신규 추가] 제목 검색 시작 메서드
    def _start_title_search(self, title_keyword):
        """제목으로 서지 DB를 검색하는 스레드를 시작합니다."""
        # 기존 스레드 정리
        self._cleanup_title_thread()

        # stop_flag 초기화
        self.stop_flag.clear()

        # 상단 개념 DB 테이블 초기화
        self.table_model.clear_data()

        # 하단 서지 DB 테이블 초기화
        self.biblio_model.clear_data()

        self.status_label.setText(f"'{title_keyword}' 제목으로 서지 DB 검색 중...")
        self.search_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.title_search_thread = TitleSearchThread(
            self.app_instance.db_manager, title_keyword, self.stop_flag
        )
        self.title_search_thread.finished.connect(self._on_title_search_completed)
        self.title_search_thread.error.connect(
            lambda msg: self.app_instance.log_message(
                f"❌ 제목 검색 실패: {msg}", "ERROR"
            )
        )
        self.title_search_thread.start()

    def _on_title_search_completed(self, df_biblio):
        """제목 검색 완료 시 하단 서지 테이블만 업데이트합니다."""
        # 검색 버튼 상태 복원
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        # 프로그레스바 애니메이션
        self.animation = QPropertyAnimation(self.progress_bar, b"value")
        self.animation.setDuration(800)
        self.animation.setStartValue(self.progress_bar.value())
        self.animation.setEndValue(100)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.start()

        # ✅ [추가] HTML 뷰어/추출 기능을 위해 biblio_dataframe 업데이트
        self.biblio_dataframe = df_biblio.copy() if df_biblio is not None and not df_biblio.empty else pd.DataFrame()
        # ✅ [추가] 제목 검색 시 상단은 비움
        self.current_dataframe = pd.DataFrame()

        # 하단 서지 테이블만 업데이트
        self.biblio_model.clear_data()
        if df_biblio is not None and not df_biblio.empty:
            self.biblio_proxy.invalidate()
            records = df_biblio.to_dict("records")
            self.biblio_model.add_multiple_rows(records, column_keys=self.biblio_keys)
            self.biblio_proxy.pre_analyze_all_columns()
            adjust_qtableview_columns(
                self.biblio_table, df_biblio, self.biblio_keys, self.biblio_headers
            )
            self.status_label.setText(f"제목 검색 완료 - {len(df_biblio)}개 결과")
            focus_on_first_table_view_item(self.biblio_table, self.app_instance)
        else:
            self.status_label.setText("제목 검색 결과가 없습니다.")

    # ===== AFTER (수정 후: setup_connections) =====
    def setup_connections(self):
        from functools import partial  # ✅ partial 임포트

        super().setup_connections()
        # create_input_section에서 이미 returnPressed를 연결했으므로 중복 제거
        # self.input_widgets["search_term"].returnPressed.connect(self.start_search)
        self.category_combo.currentTextChanged.connect(self.on_category_select)
        self.table_view.clicked.connect(self.on_concept_single_click)
        self.biblio_table.doubleClicked.connect(self.on_biblio_double_click)
        # -------------------
        # ✅ [신규 추가] 하단 서지 테이블 클릭 시 상단 컨셉 검색 연동
        self.biblio_table.clicked.connect(self.on_biblio_single_click)
        # -------------------
        # ✅ [핵심 추가] 두 번째 테이블(biblio_table)의 선택 변경 시그널 연결
        if self.biblio_table and self.biblio_table.selectionModel():
            biblio_handler = partial(
                self._update_detail_view,
                proxy_model=self.biblio_proxy,
                table_model=self.biblio_model,
            )
            self.biblio_table.selectionModel().currentChanged.connect(biblio_handler)
        # -------------------

        # ✅ [추가] 테이블 클릭 시 last_clicked_table 업데이트 (HTML 뷰어용)
        self.table_view.clicked.connect(self._on_table_view_clicked)
        self.biblio_table.clicked.connect(self._on_biblio_table_clicked)

        # ✅ primary_search_field 속성 설정 (BaseSearchTab.set_initial_focus()에서 사용)
        self.primary_search_field = self.input_widgets["search_term"]

    def on_category_select(self, category):
        self.input_widgets["search_term"].clear()
        if category != "전체":
            self.start_search()

    # ✅ [핵심 수정] CTk 버전의 로직을 적용하여 검색 유형에 따라 분기 처리합니다.
    def on_concept_single_click(self, index: QModelIndex):
        """상단 테이블 클릭 시, 자동 검색이 켜져 있고 '키워드/카테고리' 검색 결과일 때만 서지 DB를 검색합니다."""
        if not self.auto_search_enabled or not index.isValid():
            return

        # DDC 또는 KSH 코드 검색 결과에서는 이 기능을 실행하지 않음
        if self.current_search_type not in ["keyword", "category"]:
            self.app_instance.log_message(
                f"ℹ️ DDC/KSH 코드 검색 결과에서는 자동 서지 검색을 실행하지 않습니다. (검색타입: {self.current_search_type})",
                "INFO",
            )
            return

        source_index = self.proxy_model.mapToSource(index)
        current_row = source_index.row()

        # ✅ [추가] 같은 행을 다시 클릭한 경우 검색 생략
        if self._last_selected_row == current_row:
            return

        # ✅ [추가] 편집 가능한 셀을 클릭한 경우 검색 생략
        if source_index.column() in self.editable_columns:
            return

        self._last_selected_row = current_row

        row_data = self.table_model.get_row_data(current_row)
        if row_data:
            subject = row_data.get("주제명", "")
            if subject:
                match = re.search(r"▼a(.*?)(▼0|$)", subject)
                clean_subject = match.group(1).strip() if match else subject.strip()
                if clean_subject:
                    self._start_biblio_search(clean_subject)

    def _start_biblio_search(self, subject_name):
        # ✅ [핵심 수정] 기존 스레드 정리
        self._cleanup_biblio_thread()

        # ✅ [수정] stop_flag를 리셋하지 말고 기존 것을 재사용
        self.stop_flag.clear()  # 플래그만 초기화

        self.status_label.setText(f"'{subject_name}' 관련 서지 데이터 검색 중...")
        self.biblio_model.clear_data()
        self.biblio_search_thread = BiblioSearchThread(
            self.app_instance.db_manager, subject_name, self.stop_flag
        )
        self.biblio_search_thread.finished.connect(self._on_biblio_search_completed)
        self.biblio_search_thread.error.connect(
            lambda msg: self.app_instance.log_message(msg, "ERROR")
        )
        self.biblio_search_thread.start()

    def _on_biblio_search_completed(self, df_biblio):
        # ✅ [추가] HTML 뷰어/추출 기능을 위해 biblio_dataframe 업데이트
        self.biblio_dataframe = df_biblio.copy() if df_biblio is not None and not df_biblio.empty else pd.DataFrame()

        self.biblio_model.clear_data()
        if df_biblio is not None and not df_biblio.empty:
            records = df_biblio.to_dict("records")
            self.biblio_model.add_multiple_rows(records, column_keys=self.biblio_keys)
            adjust_qtableview_columns(
                table_view=self.biblio_table,
                current_dataframe=df_biblio,
                column_keys=self.biblio_keys,
                column_headers=self.biblio_headers,
            )
            self.status_label.setText(f"서지 검색 완료 - {len(df_biblio)}개 결과 표시")
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(
                    f"✅ 하단 서지 테이블에 {len(df_biblio)}개 결과 표시 완료", "INFO"
                )
        else:
            self.status_label.setText("관련 서지 정보가 없습니다.")

    # ==========================================================
    # ✅ [신규 추가] 하단 -> 상단 연동 검색 기능 메서드
    # ==========================================================
    def on_biblio_single_click(self, index: QModelIndex):
        """하단 서지 테이블 클릭 시, 'DDC' 검색 결과일 때만 상단 개념 DB를 연동 검색합니다."""
        if self.current_search_type != "ddc":
            return

        if not index.isValid():
            return

        source_index = self.biblio_proxy.mapToSource(index)
        current_row = source_index.row()

        # ✅ [추가] 같은 행을 다시 클릭한 경우 검색 생략
        if self._last_selected_biblio_row == current_row:
            return

        self._last_selected_biblio_row = current_row

        row_data = self.biblio_model.get_row_data(current_row)
        if not row_data:
            return

        ksh_labeled_content = row_data.get("KSH 라벨", "")
        if not ksh_labeled_content:
            return

        # KSH 마크업에서 주제명들 추출
        subject_names = []
        ksh_pattern = r"▼a([^▼]+)▼0KSH\d+▲"
        matches = re.findall(ksh_pattern, str(ksh_labeled_content))
        for match in matches:
            clean_subject = match.strip()
            if clean_subject and clean_subject not in subject_names:
                subject_names.append(clean_subject)

        if subject_names:
            search_query = ", ".join(subject_names)
            self.app_instance.log_message(
                f"🔗 연동 검색 시작: '{search_query}'", "INFO"
            )
            self._start_concept_search(search_query)

    def _start_concept_search(self, search_query):
        """상단 개념 DB만 검색하는 스레드를 시작합니다."""
        # ✅ [핵심 수정] 기존 스레드 정리
        self._cleanup_concept_thread()

        # ✅ [수정] stop_flag를 리셋하지 말고 기존 것을 재사용
        self.stop_flag.clear()  # 플래그만 초기화

        self.status_label.setText(f"'{search_query}' 개념 DB 검색 중...")
        # 기존 검색 버튼 비활성화
        self.search_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.concept_search_thread = ConceptSearchThread(
            self.app_instance.db_manager, search_query, self.stop_flag
        )
        self.concept_search_thread.finished.connect(self._on_concept_search_completed)
        self.concept_search_thread.error.connect(
            lambda msg: self.app_instance.log_message(
                f"❌ 연동 검색 실패: {msg}", "ERROR"
            )
        )
        self.concept_search_thread.start()

    def _on_concept_search_completed(self, df_concepts):
        """연동 검색 완료 시 상단 테이블만 업데이트합니다."""
        # 검색 버튼 상태 복원
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        self.table_model.clear_data()  # 상단 테이블만 초기화
        if df_concepts is not None and not df_concepts.empty:
            self.proxy_model.invalidate()
            records = df_concepts.to_dict("records")
            # -------------------
            # [일관성 적용 2] 연동 검색 경로: 주 검색과 '완벽하게 동일한 방식'으로 column_keys를 사용해 매핑합니다.
            df_cols = df_concepts.columns.tolist()
            self.table_model.add_multiple_rows(records, column_keys=df_cols)
            # -------------------
            self.proxy_model.pre_analyze_all_columns()
            adjust_qtableview_columns(
                self.table_view, df_concepts, df_cols, self.column_headers
            )
            self.status_label.setText(f"연동 검색 완료 - {len(df_concepts)}개 결과")
            focus_on_first_table_view_item(self.table_view, self.app_instance)
        else:
            self.status_label.setText("연동 검색 결과가 없습니다.")

    # ==========================================================

    def load_categories(self):
        try:
            searcher = KshLocalSearcher(self.app_instance.db_manager)
            categories = searcher.db.get_ksh_categories()
            for cat in categories:
                if cat and cat != "전체":
                    self.category_combo.addItem(cat)
        except Exception as e:
            self.app_instance.log_message(f"카테고리 로드 실패: {e}", "ERROR")

    def toggle_auto_search(self):
        self.auto_search_enabled = self.auto_search_toggle.isChecked()
        text = "ON" if self.auto_search_enabled else "OFF"
        self.auto_search_toggle.setText(f"왼쪽 클릭 자동검색 {text}")

    def on_biblio_double_click(self, index: QModelIndex):
        """하단 biblio 테이블 더블 클릭 시 셀 상세보기 다이얼로그 표시"""
        if not index.isValid():
            return

        from qt_context_menus import show_cell_detail_dialog

        source_index = self.biblio_proxy.mapToSource(index)
        row_data = self.biblio_model.get_row_data(source_index.row())

        if row_data:
            # 컬럼명 가져오기
            column_name = (
                self.biblio_headers[source_index.column()]
                if source_index.column() < len(self.biblio_headers)
                else "Unknown"
            )
            cell_value = self.biblio_model.data(source_index, Qt.DisplayRole) or ""

            # 상세보기 다이얼로그 표시
            show_cell_detail_dialog(cell_value, column_name, self.app_instance)

    def _on_cell_data_changed(self, top_left, bottom_right, roles):
        """✅ [신규 추가] 셀 데이터 변경 시 DB에 저장 + 콤보박스 새로고침"""
        if Qt.EditRole not in roles and Qt.DisplayRole not in roles:
            return

        # ✅ [수정] top_left의 모델이 프록시인지 확인
        if hasattr(top_left.model(), "mapToSource"):
            # 프록시 모델이면 소스로 매핑
            source_top_left = top_left.model().mapToSource(top_left)
        else:
            # 이미 소스 모델이면 그대로 사용
            source_top_left = top_left

        row = source_top_left.row()
        col = source_top_left.column()

        # 행 데이터 가져오기
        row_data = self.table_model.get_row_data(row)
        if not row_data:
            return

        # concept_id 가져오기 (필수)
        concept_id = row_data.get("_concept_id", "")
        if not concept_id:
            self.app_instance.log_message(
                "경고: concept_id가 없어 DB에 저장할 수 없습니다.", "WARNING"
            )
            return

        # 컬럼명과 새 값 가져오기
        column_name = self.column_headers[col]
        new_value = row_data.get(column_name, "")

        # ✅ [핵심] 통합 메서드로 DB 저장
        searcher = KshLocalSearcher(self.app_instance.db_manager)
        success = searcher.update_field(concept_id, column_name, new_value)

        # 결과 로깅
        if success:
            self.app_instance.log_message(
                f"✅ DB 저장 완료: {column_name} = '{new_value}' (concept_id: {concept_id})",
                "INFO",
            )

            # ✅ [핵심 추가] "주제모음" 컬럼이 변경되었으면 콤보박스 새로고침
            if column_name == "주제모음":
                self.reload_categories()
        else:
            self.app_instance.log_message(
                f"❌ DB 저장 실패: {column_name} (concept_id: {concept_id})", "ERROR"
            )

    def reload_categories(self):
        """✅ [신규 메서드] 카테고리 콤보박스를 DB에서 다시 로드"""
        try:
            # 현재 선택된 카테고리 저장
            current_selection = self.category_combo.currentText()

            # 콤보박스 초기화
            self.category_combo.clear()
            self.category_combo.addItem("전체")

            # DB에서 카테고리 다시 로드
            searcher = KshLocalSearcher(self.app_instance.db_manager)
            categories = searcher.db.get_ksh_categories()

            for cat in categories:
                if cat and cat != "전체":
                    self.category_combo.addItem(cat)

            # 이전 선택 복원 (가능하면)
            if current_selection in categories:
                self.category_combo.setCurrentText(current_selection)
            else:
                self.category_combo.setCurrentText("전체")

            self.app_instance.log_message(
                f"🔄 카테고리 콤보박스 새로고침 완료: {len(categories)}개", "INFO"
            )

        except Exception as e:
            self.app_instance.log_message(f"❌ 카테고리 새로고침 실패: {e}", "ERROR")

    def _hide_internal_columns(self):
        """내부 관리용 컬럼을 숨깁니다."""
        model = self.table_model
        if not model:
            return

        for col_name in self.internal_columns:
            try:
                # 컬럼 헤더에서 이름으로 인덱스를 찾습니다.
                col_index = model.column_headers.index(col_name)

                # QTableView에서 컬럼을 숨깁니다.
                self.table_view.setColumnHidden(col_index, True)

                self.app_instance.log_message(
                    f"ℹ️ 내부 컬럼 '{col_name}'를 숨겼습니다.", "DEBUG"
                )

            except ValueError:
                # 컬럼이 모델에 존재하지 않으면 건너뜁니다.
                continue

    # ===== 스레드 정리 메서드 =====
    def _cleanup_biblio_thread(self):
        """서지 검색 스레드를 안전하게 중지하고 정리합니다."""
        if (
            self.biblio_search_thread is not None
            and self.biblio_search_thread.isRunning()
        ):
            # 중지 플래그 설정
            self.stop_flag.set()
            # 스레드가 종료될 때까지 최대 2초 대기
            self.biblio_search_thread.wait(2000)
            if self.biblio_search_thread.isRunning():
                # 강제 종료 (권장하지 않지만 마지막 수단)
                self.biblio_search_thread.terminate()
                self.biblio_search_thread.wait()
            self.biblio_search_thread = None

    def _cleanup_concept_thread(self):
        """개념 검색 스레드를 안전하게 중지하고 정리합니다."""
        if (
            self.concept_search_thread is not None
            and self.concept_search_thread.isRunning()
        ):
            # 중지 플래그 설정
            self.stop_flag.set()
            # 스레드가 종료될 때까지 최대 2초 대기
            self.concept_search_thread.wait(2000)
            if self.concept_search_thread.isRunning():
                # 강제 종료 (권장하지 않지만 마지막 수단)
                self.concept_search_thread.terminate()
                self.concept_search_thread.wait()
            self.concept_search_thread = None

    def _cleanup_title_thread(self):
        """제목 검색 스레드를 안전하게 중지하고 정리합니다."""
        if (
            self.title_search_thread is not None
            and self.title_search_thread.isRunning()
        ):
            # 중지 플래그 설정
            self.stop_flag.set()
            # 스레드가 종료될 때까지 최대 2초 대기
            self.title_search_thread.wait(2000)
            if self.title_search_thread.isRunning():
                # 강제 종료 (권장하지 않지만 마지막 수단)
                self.title_search_thread.terminate()
                self.title_search_thread.wait()
            self.title_search_thread = None

    def cleanup_all_threads(self):
        """탭 종료 시 모든 스레드를 정리합니다."""
        self._cleanup_biblio_thread()
        self._cleanup_concept_thread()
        self._cleanup_title_thread()  # ✅ [추가] 제목 검색 스레드 정리
        self.app_instance.log_message("✅ KSH Local 탭: 모든 스레드 정리 완료", "INFO")

    def _on_table_view_clicked(self, index):
        """상단 개념 테이블 클릭 시 최근 클릭 테이블 기록"""
        self.last_clicked_table = "table_view"

    def _on_biblio_table_clicked(self, index):
        """하단 서지 테이블 클릭 시 최근 클릭 테이블 기록"""
        self.last_clicked_table = "biblio_table"

    def closeEvent(self, event):
        """위젯 종료 시 호출되는 이벤트 핸들러"""
        self.cleanup_all_threads()
        super().closeEvent(event)
