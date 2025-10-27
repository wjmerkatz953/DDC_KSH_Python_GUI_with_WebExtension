"""파일명: qt_TabView_Dewey.py
설명: Dewey 분류 검색 탭 (전체 기능 리팩토링)
버전: v4.3.1
수정일: 2025-10-27

변경 이력:
v4.3.1 (2025-10-27)
- [기능 추가] 세로 헤더(행 번호) 표시 및 중앙 정렬 추가
- [기능 추가] API 상태 라벨 추가 (API 설정 버튼 옆)
v4.3.0 (2025-10-18)
- [기능 추가] QSplitter 자동 저장/복구 기능 추가
  : master_splitter → self.master_splitter (좌우 패널 분할: DDC 트리 vs KSH 검색)
  : content_splitter → self.left_content_splitter (DDC 트리와 상세 패널 분할)
  : content_splitter → self.right_content_splitter (KSH 테이블과 미리보기 패널 분할)
  : 앱 종료 시 세 개의 스플리터 크기가 자동으로 DB에 저장되고 재시작 시 복구됨

v4.2.0 (이전)
- QThread 클래스들(DeweySearchThread, DeweyRangeSearchThread, DeweyHundredsSearchThread)의 비즈니스 로직을 Search_Dewey.py로 분리했습니다.
- QtDeweySearchTab 클래스 내의 중복 헬퍼 함수(_get, _pick 등)를 제거하고 Search_Dewey.py의 함수를 사용하도록 통일했습니다.
"""

# --- 서드파티 라이브러리 import ---
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPen, QPolygon, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyledItemDelegate,
    QTableView,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

# --- 프로젝트 모듈 import ---
import qt_dewey_logic
from qt_base_tab import BaseSearchTab, FastSearchResultModel
from qt_context_menus import setup_widget_context_menu
from qt_custom_widgets import TripleClickLimitedTextBrowser
from qt_proxy_models import SmartNaturalSortProxyModel
from qt_widget_events import ExcelStyleTableHeaderView
from Search_Dewey import DeweyClient
from ui_constants import UI_CONSTANTS

# 메인 탭 클래스
# ========================================


def _as_list(value):
    """Helper to ensure a value is a list."""
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


class QtDeweySearchTab(BaseSearchTab):
    def __init__(self, config, app_instance):
        self.ksh_column_keys = [
            "ksh",
            "title",
            "ddc",
            "ddc_label",
            "kdc",
            "publication_year",
            "identifier",
            "data_type",
            "source_file",
        ]
        self.ksh_column_headers = [
            "KSH",
            "서명/매칭",
            "DDC",
            "DDC Label",  # ✅ [신규] DDC Label 컬럼 추가
            "KDC",
            "발행년",
            "Identifier",
            "자료유형",
            "소스파일",
        ]

        self.dewey_search_thread = None
        self.ksh_search_thread = None
        self.is_interlock_enabled = True

        super().__init__(config, app_instance)

        self.dewey_client = DeweyClient(self.app_instance.db_manager)

        self._dewey_nav_back_stack = []
        self._dewey_nav_forward_stack = []
        self._dewey_nav_current = None
        self._dewey_nav_debounce_timer = QTimer(self)
        self._dewey_nav_debounce_timer.setSingleShot(True)

        self._init_search_history_db()
        self._search_history = []

        self._update_api_status()
        self._update_nav_buttons()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            6, UI_CONSTANTS.PADDING_FRAME, 6, UI_CONSTANTS.PADDING_FRAME
        )
        main_layout.setSpacing(UI_CONSTANTS.PADDING_WIDGET_Y)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAlignment(Qt.AlignCenter)

        # 레이아웃을 생성하고
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(6, 2, 6, 0)

        # 1. progress_bar를 progress_layout에 추가합니다.
        progress_layout.addWidget(self.progress_bar)

        # 2. 완성된 progress_layout을 main_layout에 추가합니다.
        main_layout.addLayout(progress_layout)

        self.progress_bar.setVisible(False)

        self.master_splitter = QSplitter(Qt.Orientation.Horizontal)
        left_pane_container = self._create_left_pane()
        right_pane_container = self._create_right_pane()

        self.master_splitter.addWidget(left_pane_container)
        self.master_splitter.addWidget(right_pane_container)
        self.master_splitter.setSizes([600, 800])

        main_layout.addWidget(self.master_splitter, 1)

        QTimer.singleShot(100, self._load_search_history)

    def _create_left_pane(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        controls_frame = self._create_ddc_controls_panel()
        self.left_content_splitter = QSplitter(Qt.Orientation.Vertical)
        top_left_panel = self._create_context_tree_panel()
        bottom_left_panel = self._create_detail_panel()
        self.left_content_splitter.addWidget(top_left_panel)
        self.left_content_splitter.addWidget(bottom_left_panel)
        self.left_content_splitter.setSizes([500, 300])

        layout.addWidget(controls_frame)
        layout.addWidget(self.left_content_splitter, 1)
        return container

    def _create_right_pane(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        controls_frame = self._create_ksh_controls_panel()
        self.right_content_splitter = QSplitter(Qt.Orientation.Vertical)
        top_right_panel = self._create_ksh_table_panel()
        bottom_right_panel = self._create_ksh_preview_panel()

        self.right_content_splitter.addWidget(top_right_panel)
        self.right_content_splitter.addWidget(bottom_right_panel)
        self.right_content_splitter.setSizes([500, 300])

        layout.addWidget(controls_frame)
        layout.addWidget(self.right_content_splitter, 1)
        return container

    def _create_ddc_controls_panel(self):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 3, 0, 0)

        layout.addWidget(QLabel("DDC 코드:"))
        self.dewey_ddc_entry = QLineEdit()
        self.dewey_ddc_entry.setObjectName("DeweyEntry")  # ✅ 오브젝트 이름 추가
        self.dewey_ddc_entry.setFixedHeight(32)
        self.dewey_ddc_entry.setPlaceholderText("예: 025.042")

        self.dewey_classify_button = QPushButton("Search")
        self.dewey_classify_button.setObjectName("DeweyButton")  # ✅ 오브젝트 이름 추가
        self.dewey_classify_button.setFixedWidth(60)
        self.dewey_classify_button.setFixedHeight(32)

        self.dewey_classify_cancel_button = QPushButton("Cancel")
        self.dewey_classify_cancel_button.setObjectName(
            "DeweyCancelButton"
        )  # ✅ 오브젝트 이름 추가
        self.dewey_classify_cancel_button.setFixedHeight(32)
        self.dewey_classify_cancel_button.setFixedWidth(50)
        self.dewey_classify_cancel_button.setEnabled(False)
        # ✅ qt_styles.py 파일에서 버튼 스타일 정의 중 DeweyButton
        self.dewey_nav_back_button = QPushButton("Prev")
        self.dewey_nav_back_button.setObjectName("DeweyButton")  # ✅ 오브젝트 이름 추가
        self.dewey_nav_back_button.setFixedHeight(32)
        self.dewey_nav_back_button.setFixedWidth(50)

        self.dewey_nav_forward_button = QPushButton("Next")
        self.dewey_nav_forward_button.setObjectName(
            "DeweyButton"
        )  # ✅ 오브젝트 이름 추가
        self.dewey_nav_forward_button.setFixedHeight(32)
        self.dewey_nav_forward_button.setFixedWidth(50)

        self.expand_all_button = QPushButton("▼Open")
        self.expand_all_button.setObjectName("DeweyButton")  # ✅ 오브젝트 이름 추가
        self.expand_all_button.setToolTip("현재 로드된 모든 항목을 펼칩니다.")
        self.expand_all_button.setFixedHeight(32)
        self.expand_all_button.setFixedWidth(60)

        self.collapse_all_button = QPushButton("▲Close")
        self.collapse_all_button.setObjectName("DeweyButton")  # ✅ 오브젝트 이름 추가
        self.collapse_all_button.setToolTip("모든 항목을 접습니다.")
        self.collapse_all_button.setFixedHeight(32)
        self.collapse_all_button.setFixedWidth(60)

        self.dewey_history_combo = QComboBox()
        self.dewey_history_combo.setObjectName("DeweyCombo")  # ✅ 오브젝트 이름 추가
        self.dewey_history_combo.setFixedHeight(32)
        self.dewey_history_combo.setFixedWidth(100)
        self.dewey_history_combo.setMaxVisibleItems(15)
        self.dewey_history_combo.addItem("검색 내역")

        layout.addWidget(self.dewey_ddc_entry, 1)
        layout.addWidget(self.dewey_classify_button)
        layout.addWidget(self.dewey_classify_cancel_button)
        layout.addWidget(self.dewey_nav_back_button)
        layout.addWidget(self.expand_all_button)
        layout.addWidget(self.collapse_all_button)
        layout.addWidget(self.dewey_nav_forward_button)
        layout.addWidget(self.dewey_history_combo)

        self.app_instance.dewey_ddc_entry = self.dewey_ddc_entry
        self.app_instance.dewey_classify_button = self.dewey_classify_button
        self.app_instance.dewey_nav_back_button = self.dewey_nav_back_button
        self.app_instance.dewey_classify_cancel_button = (
            self.dewey_classify_cancel_button
        )
        self.app_instance.dewey_nav_forward_button = self.dewey_nav_forward_button

        return frame

    def _create_ksh_controls_panel(self):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 3, 0, 0)

        self.dewey_ksh_search_entry = QLineEdit()
        self.dewey_ksh_search_entry.setObjectName("DeweyEntry")  # ✅ 오브젝트 이름 추가
        self.dewey_ksh_search_entry.setFixedHeight(32)
        self.dewey_ksh_search_entry.setPlaceholderText("KSH 검색어 입력...")

        self.dewey_ksh_search_button = QPushButton("Search")
        self.dewey_ksh_search_button.setObjectName(
            "DeweyButton"
        )  # ✅ 오브젝트 이름 추가
        self.dewey_ksh_search_button.setFixedHeight(32)
        self.dewey_ksh_search_button.setFixedWidth(70)

        self.dewey_ksh_cancel_button = QPushButton("Cancel")
        self.dewey_ksh_cancel_button.setObjectName(
            "DeweyCancelButton"
        )  # ✅ 오브젝트 이름 추가
        self.dewey_ksh_cancel_button.setFixedWidth(50)
        self.dewey_ksh_cancel_button.setFixedHeight(32)
        self.dewey_ksh_cancel_button.setEnabled(False)

        self.dewey_api_button = QPushButton("API 설정")
        self.dewey_api_button.setObjectName("DeweyButton")  # ✅ 오브젝트 이름 추가
        self.dewey_api_button.setFixedWidth(70)
        self.dewey_api_button.setFixedHeight(32)

        # ✅ [추가] API 상태 라벨 생성
        self.api_status_label = QLabel("")
        self.api_status_label.setAlignment(Qt.AlignCenter)
        self.api_status_label.setFixedWidth(150)

        # ✅ [추가] 연동검색 ON/OFF 버튼
        self.dewey_interlock_button = QPushButton("연동검색 ON")
        self.dewey_interlock_button.setObjectName(
            "DeweyInterlockButton"
        )  # ✅ 오브젝트 이름 추가
        self.dewey_interlock_button.setCheckable(True)
        self.dewey_interlock_button.setChecked(True)
        self.dewey_interlock_button.setFixedHeight(32)
        self.dewey_interlock_button.setFixedWidth(100)

        layout.addWidget(self.dewey_ksh_search_entry, 1)
        layout.addWidget(self.dewey_ksh_search_button)
        layout.addWidget(self.dewey_ksh_cancel_button)
        layout.addWidget(self.dewey_interlock_button)
        layout.addWidget(self.dewey_api_button)
        layout.addWidget(self.api_status_label)

        self.app_instance.dewey_ksh_search_entry = self.dewey_ksh_search_entry
        self.app_instance.dewey_ksh_search_button = self.dewey_ksh_search_button
        self.app_instance.dewey_ksh_cancel_button = self.dewey_ksh_cancel_button
        self.app_instance.dewey_api_button = self.dewey_api_button

        return frame

    def _create_context_tree_panel(self):
        group = QGroupBox()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.dewey_context_tree = QTreeView()
        self.dewey_context_tree.setCursor(Qt.CursorShape.ArrowCursor)
        self.dewey_context_model = QStandardItemModel()
        self.dewey_context_tree.setModel(self.dewey_context_model)
        self.dewey_context_tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        setup_widget_context_menu(self.dewey_context_tree, self.app_instance)

        self.dewey_context_model.setHorizontalHeaderLabels(["DDC Hierarchy"])

        # ✅ 헤더 스타일을 다른 탭과 통일 (WIDGET_BG_DEFAULT 사용)
        tree_header = self.dewey_context_tree.header()
        tree_header.setStretchLastSection(True)
        tree_header.setStyleSheet(
            f"""
            QHeaderView::section {{
                background-color: {UI_CONSTANTS.WIDGET_BG_DEFAULT};
                color: {UI_CONSTANTS.TEXT_BUTTON};
                padding: 0px 3px 0px 3px;
                border: none;
                font-weight: bold;
                text-align: center;
            }}
            QHeaderView::section:hover {{
                background-color: {UI_CONSTANTS.ACCENT_BLUE};
                color: {UI_CONSTANTS.TEXT_BUTTON};
            }}
        """
        )
        self.dewey_context_tree.setHeaderHidden(False)

        self.dewey_context_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

        self.dewey_context_tree.setItemsExpandable(True)
        self.dewey_context_tree.setRootIsDecorated(True)

        # ✅ 전역 스타일 사용 (테마 전환 대응) - inline setStyleSheet 제거
        # 전역 qt_styles.py의 QTreeView 스타일이 자동으로 적용됨

        class BrightArrowDelegate(QStyledItemDelegate):
            def paint(self, painter, option, index):
                super().paint(painter, option, index)

                if index.model().hasChildren(index):
                    painter.save()

                    # ✅ UI_CONSTANTS 사용 (테마 대응)
                    from ui_constants import UI_CONSTANTS as U

                    arrow_color = QColor(U.TEXT_SUBDUED)
                    painter.setPen(QPen(arrow_color, 2))

                    arrow_x = option.rect.left() - 12
                    arrow_y = option.rect.top() + option.rect.height() // 2

                    tree_view = option.widget
                    if tree_view and tree_view.isExpanded(index):
                        # 열린 노드: 아래쪽 방향 삼각형 ▼
                        points = [
                            QPoint(arrow_x, arrow_y + 3),  # 아래쪽 꼭짓점
                            QPoint(arrow_x - 6, arrow_y - 3),  # 왼쪽 위
                            QPoint(arrow_x + 6, arrow_y - 3),  # 오른쪽 위
                        ]
                    else:
                        # 닫힌 노드: 오른쪽 방향 삼각형 ▶
                        points = [
                            QPoint(arrow_x - 3, arrow_y - 6),
                            QPoint(arrow_x + 3, arrow_y),
                            QPoint(arrow_x - 3, arrow_y + 6),
                        ]

                    painter.setBrush(arrow_color)
                    painter.drawPolygon(QPolygon(points))

                    painter.restore()

        self.dewey_context_tree.setItemDelegate(BrightArrowDelegate(self))

        layout.addWidget(self.dewey_context_tree)

        self.app_instance.dewey_context_tree = self.dewey_context_tree

        return group

    def _create_detail_panel(self):
        group = QGroupBox("DDC 상세 정보")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 20, 0, 0)

        self.dewey_detail_text = QTextEdit()
        self.dewey_detail_text.setObjectName("DeweyDetailText")  # ✅ 오브젝트 이름 추가
        self.dewey_detail_text.setReadOnly(True)
        self.dewey_detail_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        detail_font = QFont(
            UI_CONSTANTS.FONT_FAMILY,
            (
                UI_CONSTANTS.FONT_SIZE_XLARGE
                if hasattr(UI_CONSTANTS, "FONT_SIZE_XLARGE")
                else 10
            ),
        )
        self.dewey_detail_text.setFont(detail_font)

        layout.addWidget(self.dewey_detail_text)
        setup_widget_context_menu(self.dewey_detail_text, self.app_instance)
        self.app_instance.dewey_detail_text = self.dewey_detail_text

        return group

    def _create_ksh_table_panel(self):
        group = QGroupBox()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.ksh_table = QTableView()
        self.ksh_model = FastSearchResultModel(self.ksh_column_headers)
        self.ksh_proxy = SmartNaturalSortProxyModel()
        self.ksh_proxy.setSourceModel(self.ksh_model)
        self.ksh_table.setModel(self.ksh_proxy)

        self.ksh_table.setSortingEnabled(False)
        self.ksh_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems
        )
        self.ksh_table.setAlternatingRowColors(True)

        header = ExcelStyleTableHeaderView(
            Qt.Orientation.Horizontal,
            self.ksh_table,
            self.ksh_column_headers,
            self.get_header_callbacks(),
            self,
        )
        self.ksh_table.setHorizontalHeader(header)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        # ✅ [추가] 세로 헤더(행 번호) 표시 및 정렬 설정
        self.ksh_table.verticalHeader().setVisible(True)
        self.ksh_table.verticalHeader().setDefaultAlignment(Qt.AlignCenter)

        setup_widget_context_menu(self.ksh_table, self.app_instance)

        self.table_view = self.ksh_table

        layout.addWidget(self.ksh_table)
        return group

    def _create_ksh_preview_panel(self):
        from PySide6.QtWidgets import QGroupBox

        group = QGroupBox("KSH 미리보기")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 20, 0, 0)

        self.dewey_preview_text = TripleClickLimitedTextBrowser()
        self.dewey_preview_text.setObjectName(
            "DeweyDetailText"
        )  # ✅ 오브젝트 이름 추가
        self.dewey_preview_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        preview_font = QFont(
            UI_CONSTANTS.FONT_FAMILY,
            (
                UI_CONSTANTS.FONT_SIZE_XLARGE
                if hasattr(UI_CONSTANTS, "FONT_SIZE_XLARGE")
                else 10
            ),
        )
        self.dewey_preview_text.setFont(preview_font)

        layout.addWidget(self.dewey_preview_text)
        setup_widget_context_menu(self.dewey_preview_text, self.app_instance)
        self.app_instance.dewey_preview_text = self.dewey_preview_text

        return group

    def setup_connections(self):
        self.search_button = self.dewey_ksh_search_button
        self.stop_button = self.dewey_ksh_cancel_button
        self.clear_all_filters_button = QPushButton()
        self.html_viewer_button = QPushButton()
        # ✅ BaseSearchTab의 더블클릭 핸들러가 proxy_model, table_model, column_headers를 참조하므로 설정
        self.proxy_model = self.ksh_proxy
        self.table_model = self.ksh_model
        self.column_headers = self.ksh_column_headers
        super().setup_connections()

        self.dewey_classify_button.clicked.connect(
            lambda: qt_dewey_logic._navigate_to_code(
                self, self.dewey_ddc_entry.text().strip(), add_to_history=True
            )
        )
        self.dewey_ddc_entry.returnPressed.connect(
            lambda: qt_dewey_logic._navigate_to_code(
                self, self.dewey_ddc_entry.text().strip(), add_to_history=True
            )
        )

        self.dewey_ddc_entry.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.dewey_ddc_entry.customContextMenuRequested.connect(
            lambda pos: qt_dewey_logic._on_ddc_entry_context_menu(self, pos)
        )

        self.dewey_classify_cancel_button.clicked.connect(
            lambda: qt_dewey_logic._cancel_fetch_dewey(self)
        )
        self.dewey_ksh_search_button.clicked.connect(
            lambda: qt_dewey_logic._start_ksh_search(self)
        )
        self.dewey_ksh_search_entry.returnPressed.connect(
            lambda: qt_dewey_logic._start_ksh_search(self)
        )
        self.dewey_ksh_cancel_button.clicked.connect(
            lambda: qt_dewey_logic._cancel_ksh_search(self)
        )

        self.dewey_api_button.clicked.connect(
            lambda: qt_dewey_logic._show_api_settings(self)
        )
        self.dewey_interlock_button.toggled.connect(
            lambda checked: qt_dewey_logic._on_interlock_toggled(self, checked)
        )

        self.dewey_nav_back_button.clicked.connect(
            lambda: qt_dewey_logic._nav_go_back(self)
        )
        self.dewey_nav_forward_button.clicked.connect(
            lambda: qt_dewey_logic._nav_go_forward(self)
        )
        self.dewey_history_combo.currentIndexChanged.connect(
            lambda index: qt_dewey_logic._on_history_selected(self, index)
        )

        self.expand_all_button.clicked.connect(self.dewey_context_tree.expandAll)
        self.collapse_all_button.clicked.connect(self.dewey_context_tree.collapseAll)
        self.dewey_context_tree.expanded.connect(
            lambda index: qt_dewey_logic._on_tree_expand(self, index)
        )
        self.dewey_context_tree.collapsed.connect(
            lambda index: qt_dewey_logic._on_tree_collapse(self, index)
        )
        self.dewey_context_tree.doubleClicked.connect(
            lambda index: qt_dewey_logic._open_selected_ddc(self, index)
        )
        self.dewey_context_tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.dewey_context_tree.customContextMenuRequested.connect(
            lambda pos: qt_dewey_logic._on_dewey_context_tree_right_click(self, pos)
        )

        self.ksh_table.selectionModel().selectionChanged.connect(
            lambda: qt_dewey_logic._on_ksh_selection_changed(self)
        )

        self.primary_search_field = self.dewey_ddc_entry

    # ========================================
    # Delegating methods to dewey_logic
    # ========================================

    def _update_api_status(self):
        """API 상태 업데이트"""
        qt_dewey_logic._update_api_status(self)

    def _update_nav_buttons(self):
        """네비게이션 버튼 상태 업데이트"""
        qt_dewey_logic._update_nav_buttons(self)

    def _init_search_history_db(self):
        """검색 히스토리 DB 초기화"""
        qt_dewey_logic._init_search_history_db(self)

    def _load_search_history(self):
        """검색 히스토리 로드"""
        qt_dewey_logic._load_search_history(self)

    def _add_to_search_history(self, code: str):
        """검색 히스토리에 추가"""
        qt_dewey_logic._add_to_search_history(self, code)

    def _navigate_to_code(self, raw_code: str, add_to_history: bool):
        """DDC 코드로 네비게이션"""
        qt_dewey_logic._navigate_to_code(self, raw_code, add_to_history)

    def _start_fetch_dewey(self):
        """DDC 검색 시작"""
        qt_dewey_logic._start_fetch_dewey(self)

    def _finalize_fetch_dewey(self):
        """DDC 검색 종료 처리"""
        qt_dewey_logic._finalize_fetch_dewey(self)

    def _on_ddc_search_finished(self, result):
        """DDC 검색 완료 핸들러"""
        qt_dewey_logic._on_ddc_search_finished(self, result)

    def _on_ddc_search_failed(self, error_message):
        """DDC 검색 실패 핸들러"""
        qt_dewey_logic._on_ddc_search_failed(self, error_message)

    def _start_ksh_search(self):
        """KSH 검색 시작"""
        qt_dewey_logic._start_ksh_search(self)

    def _start_dewey_tab_ksh_search(self):
        """Dewey 탭 KSH 검색 시작"""
        qt_dewey_logic._start_dewey_tab_ksh_search(self)

    def _cancel_ksh_search(self):
        """KSH 검색 취소"""
        qt_dewey_logic._cancel_ksh_search(self)

    def _on_ksh_search_completed(self, df_results):
        """KSH 검색 완료 핸들러"""
        qt_dewey_logic._on_ksh_search_completed(self, df_results)

    def _on_ksh_search_failed(self, error_message):
        """KSH 검색 실패 핸들러"""
        qt_dewey_logic._on_ksh_search_failed(self, error_message)

    def _finalize_ksh_search(self):
        """KSH 검색 종료 처리"""
        qt_dewey_logic._finalize_ksh_search(self)

    def _update_hundreds_display(
        self,
        main_code,
        main_label,
        detailed_range,
        major_divisions,
        special_ranges,
        main_ctx,
    ):
        """백의 자리 검색 결과 표시"""
        qt_dewey_logic._update_hundreds_display(
            self,
            main_code,
            main_label,
            detailed_range,
            major_divisions,
            special_ranges,
            main_ctx,
        )

    def _update_range_results_display(
        self, main_code, main_label, range_results, main_ctx
    ):
        """범위 검색 결과 표시"""
        qt_dewey_logic._update_range_results_display(
            self, main_code, main_label, range_results, main_ctx
        )

    def _populate_ui_from_context(self, ctx, hierarchy_data, path_codes):
        """컨텍스트로부터 UI 채우기"""
        qt_dewey_logic._populate_ui_from_context(self, ctx, hierarchy_data, path_codes)

    def _populate_context_hierarchical(self, ctx, hierarchy_data, path_codes):
        """계층적으로 컨텍스트 채우기"""
        qt_dewey_logic._populate_context_hierarchical(
            self, ctx, hierarchy_data, path_codes
        )

    def _fill_detail_text(self, ctx):
        """상세 정보 텍스트 채우기"""
        qt_dewey_logic._fill_detail_text(self, ctx)

    def _update_range_navigation(self, main_code):
        """범위 네비게이션 업데이트"""
        qt_dewey_logic._update_range_navigation(self, main_code)

    def _add_dummy_child(self, item):
        """더미 자식 추가 (Lazy Loading용)"""
        qt_dewey_logic._add_dummy_child(self, item)

    def _on_lazy_load_finished(self, parent_item, result):
        """Lazy Load 완료 핸들러"""
        qt_dewey_logic._on_lazy_load_finished(self, parent_item, result)

    def _on_lazy_load_failed(self, parent_item, error):
        """Lazy Load 실패 핸들러"""
        qt_dewey_logic._on_lazy_load_failed(self, parent_item, error)

    def _copy_table_selection(self):
        """테이블 선택 복사"""
        return qt_dewey_logic._copy_table_selection(self)

    def _copy_tree_selection(self, side="left"):
        """트리 선택 복사"""
        qt_dewey_logic._copy_tree_selection(self, side)

    def handle_copy(self):
        """복사 처리"""
        qt_dewey_logic.handle_copy(self)

    def start_search(self):
        """검색 시작 (BaseSearchTab 오버라이드)"""
        qt_dewey_logic.start_search(self)

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
        다른 탭으로부터 데이터 수신

        Dewey 탭은 기본 파라미터 외에 ddc 파라미터를 추가로 수신합니다.
        """
        # kwargs에서 ddc 파라미터 추출 (data_transfer_manager에서 전송됨)
        ddc = kwargs.pop("ddc", None)  # ✅ [수정] pop으로 제거하면서 추출
        qt_dewey_logic.receive_data(
            self, ddc, isbn, author, title, switch_priority=switch_priority, **kwargs
        )


# ========================================
# Public Entry Point
# ========================================
def setup_dewey_search_tab_ui(config, app_instance, parent_widget=None):
    """
    Public entry point for creating Dewey Search Tab

    Args:
        config: Tab configuration dictionary
        app_instance: Application instance
        parent_widget: Parent QWidget to attach this tab to (optional)

    Returns:
        QtDeweySearchTab instance
    """
    tab = QtDeweySearchTab(config, app_instance, parent_widget)
    return tab
