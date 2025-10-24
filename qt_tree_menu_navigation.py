# -*- coding: utf-8 -*-
# 파일명: qt_tree_menu_navigation.py
# 버전: v1.0.2
# 설명: QTreeWidget 기반 사이드바 네비게이션
# 생성일: 2025-10-02
#
# 변경 이력:
# v1.0.2 (2025-10-02)
# - [수정] UI 상수(ui_constants.py)를 사용하도록 배경색 변경
# - [수정] BACKGROUND_PRIMARY, BACKGROUND_SECONDARY, ACCENT_BLUE 적용
# - [수정] 트리메뉴 영역, 트리위젯, 콘텐츠 영역 모두 일관된 색상 테마 적용
#
# v1.0.1 (2025-10-02)
# - [수정] tab_groups의 탭 이름을 qt_Tab_configs.py의 tab_name과 정확히 일치하도록 수정
# - [수정] "KSH Hybrid 검색" → "KSH Hybrid"
# - [수정] "KSH Local DB 검색" → "KSH Local"
# - [수정] "저자전거" → "저자전거 검색"
# - [수정] "AI Feed" → "AI 피드"
# - [수정] tab_class_map과 icon_map도 동일하게 업데이트
#
# v1.0.0 (2025-10-02)
# - Qt 트리메뉴 네비게이션 초기 구현
# - QTreeWidget 기반 사이드바
# - 동적 탭 생성 및 전환
# - 디버그 로깅 추가

from PySide6.QtWidgets import (
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QPushButton,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QCursor
from ui_constants import UI_CONSTANTS as U


class QtTreeMenuNavigation(QWidget):
    """Qt 트리메뉴 스타일 네비게이션 클래스"""

    def __init__(self, parent, app_instance, tab_configs):
        super().__init__(parent)
        self.app_instance = app_instance
        self.tab_configs = tab_configs
        self.current_tab_widget = None
        self.tab_widgets = {}  # 탭 이름 -> 위젯 매핑

        # 탭 그룹 정의 (qt_Tab_configs.py의 tab_name과 정확히 일치)
        self.tab_groups = {
            "검색": [
                "MARC 추출",
                "NLK 검색",
                "NDL + CiNii 검색",
                "Western 검색",
                "Global 통합검색",
                "납본 ID 검색",
            ],
            "저작물/저자": [
                "저자전거 검색",
                "상세 저작물 정보",
                "간략 저작물 정보",
            ],
            "주제어": [
                "KSH Hybrid",
                "KSH Local",
            ],
            "분류/AI": ["Dewey 분류 검색", "AI 피드"],
            "편집": ["MARC 로직 편집"],
            "도구": ["🐍 Python"],  # ✅ [추가] Python 탭 그룹
            "설정": ["설정"],
        }

        self.setup_ui()

    def setup_ui(self):
        """트리메뉴 UI를 구성합니다."""
        # 메인 레이아웃 (수평 분할)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 스플리터로 좌우 분할
        splitter = QSplitter(Qt.Horizontal)

        # === 왼쪽: 트리메뉴 영역 ===
        tree_frame = QFrame()
        tree_frame.setFrameShape(QFrame.StyledPanel)
        tree_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {U.BACKGROUND_PRIMARY};
                border-right: 1px solid #3d3d3d;
            }}
        """)
        tree_frame.setMinimumWidth(200)
        tree_frame.setMaximumWidth(350)

        tree_layout = QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(5, 5, 5, 5)
        tree_layout.setSpacing(5)

        # 헤더 (제목 + 펼치기/접기 버튼)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 0, 5, 0)

        title_label = QLabel("📋 메뉴")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # 전체 펼치기/접기 버튼
        self.expand_button = QPushButton("📂")
        self.expand_button.setFixedSize(30, 24)
        self.expand_button.clicked.connect(self.toggle_expand_all)
        self.all_expanded = True
        header_layout.addWidget(self.expand_button)

        tree_layout.addLayout(header_layout)

        # 트리 위젯
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {U.BACKGROUND_PRIMARY};
                border: none;
                outline: none;
                color: #cccccc;
                font-size: 10pt;
            }}
            QTreeWidget::item {{
                padding: 4px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {U.BACKGROUND_SECONDARY};
                color: #ffffff;
            }}
            QTreeWidget::item:selected {{
                background-color: {U.ACCENT_BLUE};
                color: #ffffff;
            }}
        """)

        # 트리 항목 클릭 이벤트 연결
        self.tree.itemClicked.connect(self.on_tree_item_clicked)
        self.tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)

        tree_layout.addWidget(self.tree)

        # === 오른쪽: 콘텐츠 영역 ===
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {U.BACKGROUND_PRIMARY};
            }}
        """)
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # 스플리터에 추가
        splitter.addWidget(tree_frame)
        splitter.addWidget(self.content_frame)
        splitter.setStretchFactor(0, 0)  # 트리메뉴는 고정
        splitter.setStretchFactor(1, 1)  # 콘텐츠는 확장

        main_layout.addWidget(splitter)

        # 트리 채우기
        self.populate_tree()

        # 첫 번째 탭 표시
        QTimer.singleShot(100, self.show_first_tab)

    def populate_tree(self):
        """트리에 항목들을 추가합니다."""
        self.tree_item_map = {}  # QTreeWidgetItem -> 탭 이름 매핑

        # 그룹 아이콘 매핑
        group_icons = {
            "검색": "🔍",
            "저작물/저자": "📋",
            "주제어": "🔤",
            "분류/AI": "📊",
            "편집": "✏️",
            "도구": "🔧",  # ✅ [추가] 도구 그룹 아이콘
            "설정": "⚙️",
        }

        # 탭 이름 -> config 매핑 생성
        tab_name_to_config = {}
        for key, config in self.tab_configs.items():
            tab_name = config.get("tab_name", "")
            if tab_name:
                tab_name_to_config[tab_name] = config

        for group_name, tab_names in self.tab_groups.items():
            # 그룹 아이템 추가
            icon = group_icons.get(group_name, "📁")
            group_item = QTreeWidgetItem([f"{icon} {group_name}"])
            group_item.setExpanded(True)  # 기본적으로 펼침
            self.tree.addTopLevelItem(group_item)

            # 탭 아이템 추가
            for tab_name in tab_names:
                # config에서 해당 탭 찾기
                if tab_name in tab_name_to_config:
                    config = tab_name_to_config[tab_name]
                    tab_icon = self.get_tab_icon(tab_name)
                    child_item = QTreeWidgetItem([f"{tab_icon} {tab_name}"])
                    group_item.addChild(child_item)
                    self.tree_item_map[child_item] = tab_name

    def get_tab_icon(self, tab_name):
        """탭 이름에 따른 아이콘을 반환합니다."""
        icon_map = {
            # 검색 관련
            "KSH Local": "💾",
            "KSH Hybrid": "🔄",
            "NDL + CiNii 검색": "🗾",
            "Western 검색": "🇩🇪",
            "Global 통합검색": "🇫🇷",
            "납본 ID 검색": "🇪🇸",
            "NLK 검색": "🇰🇷",
            "저자전거 검색": "👤",
            "상세 저작물 정보": "📋",
            "간략 저작물 정보": "🔢",
            "Dewey 분류 검색": "📊",
            "AI 피드": "✨",
            "MARC 추출": "⚡",
            "MARC 로직 편집": "✏️",
            "🐍 Python": "🐍",  # ✅ [추가] Python 탭 아이콘
            "설정": "⚙️",
        }
        return icon_map.get(tab_name, "📄")

    def on_tree_item_clicked(self, item, column):
        """트리 아이템 클릭 이벤트 처리"""
        # 그룹 아이템인 경우 (자식이 있으면)
        if item.childCount() > 0:
            return

        # 리프 노드(탭) 클릭
        if item in self.tree_item_map:
            tab_name = self.tree_item_map[item]
            self.show_tab(tab_name)

    def on_tree_item_double_clicked(self, item, column):
        """트리 아이템 더블클릭 이벤트 처리 (그룹 펼치기/접기)"""
        if item.childCount() > 0:
            item.setExpanded(not item.isExpanded())

    def show_tab(self, tab_name):
        """지정된 탭을 표시합니다."""
        self.app_instance.log_message(f"🔍 [DEBUG] show_tab 호출: '{tab_name}'", "DEBUG")

        # 이미 생성된 탭인지 확인
        if tab_name in self.tab_widgets:
            tab_widget = self.tab_widgets[tab_name]
            self.app_instance.log_message(f"✅ [DEBUG] 기존 탭 재사용: '{tab_name}'", "DEBUG")
        else:
            # 탭 위젯 생성
            self.app_instance.log_message(f"🔨 [DEBUG] 새 탭 생성 시도: '{tab_name}'", "DEBUG")
            tab_widget = self.create_tab_widget(tab_name)
            if tab_widget is None:
                self.app_instance.log_message(
                    f"⚠️ '{tab_name}' 탭을 생성할 수 없습니다.", "WARNING"
                )
                return
            self.tab_widgets[tab_name] = tab_widget
            self.app_instance.log_message(f"✅ [DEBUG] 탭 생성 성공: '{tab_name}'", "DEBUG")

        # 현재 탭 숨기기
        if self.current_tab_widget:
            self.current_tab_widget.hide()
            self.content_layout.removeWidget(self.current_tab_widget)

        # 새 탭 표시
        self.content_layout.addWidget(tab_widget)
        tab_widget.show()
        self.current_tab_widget = tab_widget

        self.app_instance.log_message(f"ℹ️ '{tab_name}' 탭으로 전환되었습니다.", "INFO")

    def create_tab_widget(self, tab_name):
        """탭 위젯을 생성합니다."""
        # qt_main_app.py의 tab_class_map 참조
        from qt_TabView_NDL import QtNDLSearchTab
        from qt_TabView_Global import QtGlobalSearchTab
        from qt_TabView_Western import QtWesternSearchTab
        from qt_TabView_LegalDeposit import QtLegalDepositSearchTab
        from qt_TabView_AIFeed import QtAIFeedSearchTab
        from qt_TabView_KACAuthorities import QtKACAuthoritiesSearchTab
        from qt_TabView_BriefWorks import QtBriefWorksSearchTab
        from qt_TabView_KSH_Lite import QtKshHyridSearchTab
        from qt_TabView_ISNI_Detailed import QtISNIDetailedSearchTab
        from qt_TabView_NLK import QtNLKSearchTab
        from qt_TabView_KSH_Local import QtKSHLocalSearchTab
        from qt_TabView_MARC_Extractor import QtMARCExtractorTab
        from qt_TabView_MARC_Editor import QtMARCEditorTab
        from qt_TabView_Dewey import QtDeweySearchTab
        from qt_TabView_Settings import QtSettingsTab
        from qt_TabView_Python import QtPythonTab  # ✅ [추가] Python 탭 임포트

        # 탭 이름 -> 클래스 매핑 (qt_Tab_configs.py의 tab_name과 일치)
        tab_class_map = {
            "NLK 검색": QtNLKSearchTab,
            "NDL + CiNii 검색": QtNDLSearchTab,
            "Western 검색": QtWesternSearchTab,
            "Global 통합검색": QtGlobalSearchTab,
            "납본 ID 검색": QtLegalDepositSearchTab,
            "AI 피드": QtAIFeedSearchTab,
            "저자전거 검색": QtKACAuthoritiesSearchTab,
            "간략 저작물 정보": QtBriefWorksSearchTab,
            "상세 저작물 정보": QtISNIDetailedSearchTab,
            "KSH Hybrid": QtKshHyridSearchTab,
            "KSH Local": QtKSHLocalSearchTab,
            "MARC 추출": QtMARCExtractorTab,
            "MARC 로직 편집": QtMARCEditorTab,
            "Dewey 분류 검색": QtDeweySearchTab,
            "🐍 Python": QtPythonTab,  # ✅ [추가] Python 탭 매핑
            "설정": QtSettingsTab,
        }

        # 해당 탭의 config 찾기
        tab_config = None
        for key, config in self.tab_configs.items():
            if config.get("tab_name") == tab_name:
                tab_config = config
                self.app_instance.log_message(
                    f"✅ [DEBUG] Config 찾음: '{tab_name}' -> {key}", "DEBUG"
                )
                break

        if tab_config is None:
            self.app_instance.log_message(
                f"❌ [DEBUG] Config 없음: '{tab_name}'", "ERROR"
            )
            self.app_instance.log_message(
                f"📋 [DEBUG] 사용 가능한 탭: {[c.get('tab_name') for c in self.tab_configs.values()]}",
                "DEBUG",
            )

        if tab_name in tab_class_map:
            if tab_config is None:
                self.app_instance.log_message(
                    f"⚠️ [DEBUG] Config 없이 탭 생성 시도: '{tab_name}'", "WARNING"
                )
                # Config 없어도 최소 설정으로 시도
                tab_config = {"tab_name": tab_name}

            TabClass = tab_class_map[tab_name]
            try:
                self.app_instance.log_message(
                    f"🔨 [DEBUG] 탭 클래스 인스턴스화: {TabClass.__name__}", "DEBUG"
                )
                widget = TabClass(tab_config, self.app_instance)
                self.app_instance.log_message(
                    f"✅ [DEBUG] 탭 인스턴스화 성공: '{tab_name}'", "DEBUG"
                )
                return widget
            except Exception as e:
                import traceback

                self.app_instance.log_message(
                    f"❌ '{tab_name}' 탭 생성 실패: {e}\n{traceback.format_exc()}", "ERROR"
                )
                return None
        else:
            self.app_instance.log_message(
                f"❌ [DEBUG] tab_class_map에 없음: '{tab_name}'", "ERROR"
            )
            return None

    def show_first_tab(self):
        """첫 번째 탭을 표시합니다."""
        # 첫 번째 그룹의 첫 번째 탭 찾기
        if self.tree.topLevelItemCount() > 0:
            first_group = self.tree.topLevelItem(0)
            if first_group.childCount() > 0:
                first_child = first_group.child(0)
                if first_child in self.tree_item_map:
                    tab_name = self.tree_item_map[first_child]
                    self.tree.setCurrentItem(first_child)
                    self.show_tab(tab_name)
                    first_group.setExpanded(True)

    def toggle_expand_all(self):
        """전체 펼치기/접기 토글"""
        if self.all_expanded:
            # 모든 그룹 접기
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                item.setExpanded(False)
            self.expand_button.setText("📁")
            self.all_expanded = False
            self.app_instance.log_message("ℹ️ 모든 메뉴 그룹을 접었습니다.", "INFO")
        else:
            # 모든 그룹 펼치기
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                item.setExpanded(True)
            self.expand_button.setText("📂")
            self.all_expanded = True
            self.app_instance.log_message("ℹ️ 모든 메뉴 그룹을 펼쳤습니다.", "INFO")

    def select_tab_by_name(self, tab_name):
        """프로그램적으로 탭을 선택합니다."""
        for item, name in self.tree_item_map.items():
            if name == tab_name:
                self.tree.setCurrentItem(item)
                self.show_tab(tab_name)
                # 부모 그룹 펼치기
                parent = item.parent()
                if parent:
                    parent.setExpanded(True)
                break

    def get_current_tab(self):
        """현재 선택된 탭 이름을 반환합니다."""
        current_item = self.tree.currentItem()
        if current_item in self.tree_item_map:
            return self.tree_item_map[current_item]
        return None


def create_tree_menu_navigation(parent, app_instance, tab_configs):
    """트리메뉴 네비게이션을 생성하는 팩토리 함수"""
    return QtTreeMenuNavigation(parent, app_instance, tab_configs)
