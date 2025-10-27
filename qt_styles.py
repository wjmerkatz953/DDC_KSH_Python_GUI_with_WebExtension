#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qt_styles.py - Qt 스타일시트 정의
버전: 3.0.2
생성일: 2025-09-23
수정일: 2025-10-27
- 세로 헤더 스타일 추가 (행 번호 중앙 정렬)
- API 상태 라벨 속성 선택자 스타일 추가
"""


def get_app_stylesheet():
    """현재 테마에 맞는 스타일시트를 반환합니다."""
    from ui_constants import UI_CONSTANTS as U

    return f"""
    /* ✅ [추가] 타이틀바를 포함한 전체 창 배경색을 어둡게 설정 */
    QMainWindow {{
        background-color: {U.BACKGROUND_PRIMARY};
    }}
    /* ✅ [추가] DDC 검색 트리뷰의 화살표 아이콘 색상을 ACCENT_BLUE로 변경 */
    QTreeView::branch:has-children:!has-siblings:closed,
    QTreeView::branch:closed:has-children:has-siblings {{
        border-image: none;
        /* ACCENT_BLUE 색상을 사용한 SVG 아이콘 */
        image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><polyline points="4,2 8,5 4,8" stroke="{U.ACCENT_BLUE}" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>');
    }}

    QTreeView::branch:open:has-children:!has-siblings,
    QTreeView::branch:open:has-children:has-siblings  {{
        border-image: none;
        /* ACCENT_BLUE 색상을 사용한 SVG 아이콘 */
        image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><polyline points="2,4 5,8 8,4" stroke="{U.ACCENT_BLUE}" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>');
    }}

    /* QTabWidget 스타일 추가 */
    QTabWidget::pane {{
        border: none;
        border-top: none;
    }}
    QTabBar::tab {{
        background: {U.BACKGROUND_PRIMARY};
        color: {U.TEXT_DEFAULT};
        padding: 6px 10px;         /* 탭바 높이 조절 5px */
        border: 0px solid {U.ACCENT_BLUE};
        margin-bottom: 0px;
    }}
    QTabBar::tab:hover {{
        background: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
    }}
    QTabBar::tab:selected {{
        background: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
        border: 0px solid {U.ACCENT_BLUE};
    }}
    /* ✅ [핵심 추가] 상세 정보 다이얼로그 전용 스타일 */
    QDialog#DetailDialog {{
        background-color: {U.WIDGET_BG_DEFAULT};
        border: 0px solid {U.ACCENT_BLUE};
    }}
    /* 이하 기존 스타일 */
    QWidget {{
        background-color: {U.BACKGROUND_PRIMARY};
        color: {U.TEXT_DEFAULT};
        font-family: "{U.FONT_FAMILY}";
        font-size: {U.FONT_SIZE_NORMAL}pt;
    }}
    QLabel {{
        color: {U.TEXT_DEFAULT};
        background-color: transparent;
    }}
    /* ✅ [추가] API 상태 라벨 스타일 (테마 대응) */
    QLabel[api_status="success"] {{
        color: {U.ACCENT_GREEN};
    }}
    QLabel[api_status="error"] {{
        color: {U.ACCENT_RED};
    }}
    QScrollArea {{
        background-color: {U.BACKGROUND_PRIMARY};
        border: none;
    }}
    QFrame {{
        background-color: {U.BACKGROUND_PRIMARY};
        color: {U.TEXT_DEFAULT};
    }}
    /* ✅ [추가] 설정탭 섹션 프레임 전용 스타일 */
    QFrame#SettingsSectionFrame {{
        background-color: {U.BACKGROUND_PRIMARY};
        border: 0.6px solid {U.BORDER_LIGHT};
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
    }}
    /* 모든 QGroupBox에 적용될 기본 스타일 */
    QGroupBox {{
        background-color: {U.WIDGET_BG_DEFAULT};
        border: 0.5px solid {U.BORDER_LIGHT};
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        margin-top: 0px;
    }}
    /* ✅ [추가] 이름이 'BottomPanelGroup'인 QGroupBox에만 적용될 특별 스타일 */
    /* 기본 스타일을 덮어씁니다(Override). */
    QGroupBox#BottomPanelGroup {{
        margin-top: 0px; /* Find 영역과 하단 패널 사이의 간격을 0으로 설정 */
    }}
    /* ✅ [추가] 서지 DB 그룹박스는 상단 여백 제거 */
    QGroupBox#BiblioGroupBox {{
        margin-top: 0px;
    }}
    QGroupBox QLabel, QGroupBox QCheckBox {{
        background-color: transparent;
        border: none;
    }}
    QGroupBox::title {{
        top: 3px;
        padding-left: 2px;
        padding-right: 2px;
        margin-left: 0px;
    }}
    QTextEdit {{
        background-color: {U.BACKGROUND_PRIMARY};
        border: 0.8px solid {U.BORDER_MEDIUM};
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        padding: 6px 6px 6px 6px;
    }}

    /* ✅ [추가] MARC 추출 탭 & Gemini 탭 입력 위젯 전용 스타일 그룹 */
    /* MARC_Gemini 그룹: MARC 추출 탭과 Gemini 탭의 입력 위젯 배경색을 별도로 조절 */
    QTextEdit#MARC_Gemini_Input {{
        background-color: {U.INPUT_WIDGET_BG};
        border: 0.8px solid {U.BORDER_MEDIUM};
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        padding: 6px 6px 6px 6px;
    }}
    QLineEdit {{
        background-color: {U.INPUT_WIDGET_BG};
        border: 0.6px solid {U.BORDER_LIGHT};
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        padding: 6px 6px 6px 6px;
    }}
    QLineEdit:focus, QTextEdit:focus {{         /* 선택한 Find, Entry 필드 테두리 색상 */
        border: 1px solid {U.HIGHLIGHT_SELECTED};
    }}
    QCheckBox::indicator {{
        background-color: transparent;
        border: 1px solid {U.TEXT_SUBDUED};
        width: 16px;
        height: 16px;
        border-radius: 4px;
    }}
    QCheckBox::indicator:checked {{
        background-color: {U.ACCENT_BLUE};
        border: 1px solid {U.ACCENT_BLUE};
    }}

    /* ✅ [추가] QRadioButton 커스텀 스타일 - 선택/미선택 상태를 명확히 구분 */
    QRadioButton {{
        spacing: 6px;
        color: {U.TEXT_DEFAULT};
    }}
    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 5px;
        border: 2px solid {U.TEXT_SUBDUED};
        background-color: {U.BACKGROUND_PRIMARY};
    }}
    QRadioButton::indicator:hover {{
        border: 2px solid {U.ACCENT_BLUE};
    }}
    QRadioButton::indicator:checked {{
        border: 2px solid {U.ACCENT_BLUE};
        background-color: {U.ACCENT_BLUE};
        /* 중앙 점 효과를 위한 radial gradient */
        background: qradialgradient(
            cx:0.5, cy:0.5, radius:0.5,
            fx:0.5, fy:0.5,
            stop:0 {U.BACKGROUND_PRIMARY},
            stop:0.4 {U.BACKGROUND_PRIMARY},
            stop:0.5 {U.ACCENT_BLUE},
            stop:1 {U.ACCENT_BLUE}
        );
    }}
    QRadioButton::indicator:checked:hover {{
        border: 2px solid {U.ACCENT_BLUE_HOVER};
        background: qradialgradient(
            cx:0.5, cy:0.5, radius:0.5,
            fx:0.5, fy:0.5,
            stop:0 {U.BACKGROUND_PRIMARY},
            stop:0.4 {U.BACKGROUND_PRIMARY},
            stop:0.5 {U.ACCENT_BLUE_HOVER},
            stop:1 {U.ACCENT_BLUE_HOVER}
        );
    }}
    QPushButton {{
        background-color: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
        border: none;
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        padding: 8px 12px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {U.SCROLLBAR_ACTIVE_THUMB};
    }}
    QPushButton:disabled {{
        background-color: {U.BACKGROUND_TERTIARY};
        color: {U.TEXT_SUBDUED};
    }}
    /* ProgressBar 컨테이너 */
    QProgressBar {{
        background-color: {U.WIDGET_BG_DEFAULT};
        border: 1px solid {U.BORDER_LIGHT};
        border-radius: 5px;
        color: {U.ACCENT_BLUE};
        font-weight: bold;
        height: 14px;
        padding: 0px;
        text-align: center;
    }}
    /* 채워지는 바(Chunk) – 그라데이션 + 은은한 글로우 */
    QProgressBar::chunk {{
        border-radius: 8px;
        background: qlineargradient(
            x1:0 y1:0, x2:1 y2:0,
            stop:0   rgba( 70,161,255,0.60),
            stop:0.5 rgba( 34,205,246,0.95),
            stop:1   rgba( 70,161,255,0.60)
        );
        border: 1px solid rgba(50,180,255,0.35);
        margin: 1px;
    }}
    QHeaderView::section {{
        background-color: {U.BACKGROUND_PRIMARY};
        color: {U.TEXT_BUTTON};
        padding: 0px 3px 0px 3px; /* 상: 0px, 우: 3px, 하: 0px, 좌: 3px */
        margin-bottom: 0px;
        border: none;
        font-weight: bold;
        text-align: center;
    }}
    QHeaderView::section:hover {{
        background-color: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
    }}
    QTreeWidget::item:selected {{
        background-color: {U.HIGHLIGHT_SELECTED};
        color: {U.TEXT_BUTTON};
    }}
    /* ✅ [추가] QTreeView 스타일 */
    QTreeView {{
        background-color: {U.BACKGROUND_PRIMARY};
        color: {U.TEXT_DEFAULT};
        border: none;
    }}
    QTreeView::item {{
        color: {U.TEXT_DEFAULT};
    }}
    QTreeView::item:selected {{
        background-color: {U.HIGHLIGHT_SELECTED};
        color: {U.TEXT_BUTTON};
    }}
    QTreeView::item:hover {{
        background-color: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
    }}
    /* ✅ [신규 추가] QTableView 스타일 */
    QTableView {{
        background-color: {U.BACKGROUND_PRIMARY};
        border: 0px solid {U.BACKGROUND_TERTIARY};
        alternate-background-color: {U.BACKGROUND_PRIMARY};
        gridline-color: {U.BACKGROUND_TERTIARY};
        selection-background-color: {U.HIGHLIGHT_SELECTED};
        show-decoration-selected: 1;
    }}

    QTableView::item {{
        padding: 4px;
        border: none;
        background-color: {U.BACKGROUND_PRIMARY};
    }}

    QTableView::item:alternate {{
        background-color: {U.BACKGROUND_PRIMARY};
    }}

    QTableView::item:hover {{
        background-color: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
    }}

    QTableView::item:selected {{
        background-color: {U.HIGHLIGHT_SELECTED};
        color: {U.TEXT_BUTTON};
    }}

    QTableView::item:selected:alternate {{
        background-color: {U.HIGHLIGHT_SELECTED};
        color: {U.TEXT_BUTTON};
    }}

    /* ✅ [추가] 세로 헤더(행 번호) 스타일 */
    QHeaderView::section:vertical {{
        background-color: {U.BACKGROUND_PRIMARY};
        color: {U.TEXT_SUBDUED};
        border: none;
        padding: 0 5px; /* 좌우 여백을 5px로 설정 */
        text-align: center; /* 👈 [핵심] 텍스트를 가운데로 정렬합니다. */
    }}
    /* ✅ [추가] 테이블 뷰 좌측 상단 코너 위젯 스타일 */
    QTableView QTableCornerButton::section {{
        background-color: {U.CORNER_STONE}; /* 👈 이 부분의 색상을 수정하면 됩니다. */
        border: none;
    }}
    /* 스크롤바 스타일 */
    QScrollBar:vertical {{
        border: none;
        background: {U.BACKGROUND_PRIMARY};
        width: 12px;
        margin: 0px;
    }}

    QScrollBar::handle:vertical {{
        background: {U.ACCENT_BLUE};
        min-height: 20px;
        border-radius: 6px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {U.ACCENT_BLUE_HOVER};
    }}

    QScrollBar:horizontal {{
        border: none;
        background: {U.BACKGROUND_PRIMARY};
        height: 12px;
        margin: 0px;
    }}

    QScrollBar::handle:horizontal {{
        background: {U.ACCENT_BLUE};
        min-width: 20px;
        border-radius: 6px;
        margin: 2px;
        border: none;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {U.ACCENT_BLUE_HOVER};
    }}

    QScrollBar::add-line, QScrollBar::sub-line,
    QScrollBar::add-page, QScrollBar::sub-page,
    QScrollBar::corner {{
        border: none;
        background: none;
        width: 0px;
        height: 0px;
    }}

    QScrollBar::corner {{
        background: {U.BACKGROUND_SECONDARY};
        border: none;
        margin: 0px;
    }}

    /* ✅ [수정] 드롭다운 메뉴 스타일 (최소 너비 추가) */
    QMenu {{
        background-color: {U.BACKGROUND_TERTIARY};
        border: none;
        min-width: 200px; /* 👈 이 줄을 추가하여 메뉴의 최소 너비를 설정합니다. */
    }}

    /* ✅ [추가] 메뉴 구분선 스타일 */
    QMenu::separator {{
        height: 1px;
        background-color: {U.TEXT_BUTTON};  /* 눈에 잘 띄는 색상으로 변경 */
        margin: 5px 0px;
    }}

    /* ✅ [추가] 드롭다운 메뉴 배경색 및 아이템 스타일 */
    QMenu {{
        background-color: {U.BACKGROUND_TERTIARY}; /* 메뉴 전체 배경색 */
        border: none;
        padding-left: 10px; /* ✅ [추가] 메뉴 전체의 왼쪽에 10px 여백을 줍니다.*/
    }}

    QMenu::item {{
        background-color: transparent;
        /* ✅ [수정] padding-left 값을 늘려 왼쪽 여백을 확보합니다. */
        padding: 5px 5px 5px 10px; /* 상, 우, 하, 좌 */
    }}
    QMenu::item:selected {{
        background-color: {U.WIDGET_BG_DEFAULT}; /* 선택된 아이템 배경색 */
    }}

    /* [핵심 추가] 메뉴바 스타일 */
    QMenuBar {{
        background-color: {U.BACKGROUND_PRIMARY};
        color: {U.TEXT_DEFAULT};
        spacing: 5px; /* 메뉴 아이템 간 간격 */
    }}

    QMenuBar::item {{
        background: transparent;
        padding: 4px 10px;
        border-radius: 1px;
    }}

    QMenuBar::item:selected {{ /* 마우스 올렸을 때 */
        background-color: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
    }}

    /* ✅ [추가] 탭 위젯의 탭들을 중앙 정렬합니다. */
    QTabWidget::tab-bar {{
        alignment: center;
        margin-bottom: 10px;
    }}

    /* ✅ [핵심 수정] 모든 HTML 렌더링 위젯 내부의 하이퍼링크(<a> 태그) 스타일을 정의합니다. */
    QTextBrowser a, QTextEdit a {{
        color: {U.ACCENT_BLUE} !important; /* 링크 색상을 강조색으로 강제 적용 */
        text-decoration: underline !important; /* ✅ 밑줄 표시하여 링크임을 명확히 함 */
    }}
    a {{ /* 일반 a 태그 폴백 */
        color: {U.ACCENT_BLUE};
        text-decoration: underline;
    }}
    /* ✅ [추가] 인라인 편집 시 QLineEdit 스타일 */
    QTableView QLineEdit {{
        padding: 2px 4px;
        border: 1px solid {U.ACCENT_BLUE};
        background-color: {U.INPUT_WIDGET_BG};
        color: {U.TEXT_DEFAULT};
    }}

    /* ✅ [추가] DDC 탭 전용 버튼/입력필드 스타일 */
    QLineEdit#DeweyEntry {{
        background-color: {U.INPUT_WIDGET_BG};
        color: {U.TEXT_DEFAULT};
        border: 0.4px solid {U.ACCENT_BLUE};
        padding: 4px;
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
    }}
    QPushButton#DeweyButton {{
        background-color: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
        border: none;
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        padding: 3px;
        font-weight: bold;
        text-align: center; /* 버튼 내부 텍스트 중앙 정렬 */
        height: 32px; /* 높이 고정 (QLabel과 맞추기) */
    }}
    QPushButton#DeweyButton:hover {{
        background-color: {U.SCROLLBAR_ACTIVE_THUMB};
    }}
    QPushButton#DeweyButton:disabled {{
        background-color: {U.BACKGROUND_TERTIARY};
        color: {U.TEXT_SUBDUED};
    }}
    QPushButton#DeweyCancelButton {{
        background-color: {U.ACCENT_RED};
        color: {U.TEXT_BUTTON};
        border: none;
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        padding: 3px;
        font-weight: bold;
        text-align: center;
    }}
    QPushButton#DeweyCancelButton:hover {{
        background-color: #FF5555;
    }}
    QPushButton#DeweyCancelButton:disabled {{
        background-color: {U.BACKGROUND_TERTIARY};
        color: {U.TEXT_SUBDUED};
    }}
    QPushButton#DeweyInterlockButton {{
        background-color: {U.ACCENT_RED}; /* 기본 OFF 상태 색상 */
        color: {U.TEXT_BUTTON};
        border: none;
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        padding: 6px;
        font-weight: bold;
    }}
    QPushButton#DeweyInterlockButton:checked {{
        background-color: {U.ACCENT_BLUE}; /* ON 상태 색상을 ACCENT_BLUE로 변경 */
    }}
    QPushButton#DeweyInterlockButton:hover:checked {{
        background-color: {U.SCROLLBAR_ACTIVE_THUMB}; /* 호버 색상을 SCROLLBAR_ACTIVE_THUMB 변경 */
    }}
    QPushButton#DeweyInterlockButton:hover:!checked {{
        background-color: {U.SCROLLBAR_ACTIVE_THUMB}; /* 호버 색상을 SCROLLBAR_ACTIVE_THUMB 변경 */
    }}
    QComboBox#DeweyCombo {{
        background-color: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
        border: none;
        padding-left: 20px;
        padding-right: 20px;
        padding-top: 6px;
        padding-bottom: 6px;
    }}
    QComboBox#DeweyCombo:hover {{
        background-color: {U.SCROLLBAR_ACTIVE_THUMB};
    }}
    QComboBox#DeweyCombo::drop-down {{
        border: none;
        width: 0px;
    }}

    QComboBox#DeweyCombo QAbstractItemView {{
        background-color: {U.BACKGROUND_SECONDARY};
        color: {U.TEXT_DEFAULT};
        selection-background-color: {U.SCROLLBAR_ACTIVE_THUMB};
        border: 1px solid {U.BORDER_COLOR};
    }}
    QTextEdit#DeweyDetailText {{
        background-color: {U.BACKGROUND_PRIMARY};
        color: {U.TEXT_DEFAULT};
        border: 0px solid {U.ACCENT_BLUE}; /* 테두리 제거 */
        padding: 5px; /* 약간의 내부 패딩 */
    }}

    /* ✅ QComboBox 스타일 - 확실한 방법 */
    QComboBox {{
        background-color: {U.INPUT_WIDGET_BG};
        border: 0.6px solid {U.BORDER_LIGHT};
        border-radius: {U.CORNER_RADIUS_DEFAULT}px;
        padding: 6px 20px 6px 6px;  /* 우측에 화살표 공간 */
        min-height: 20px;
        font-size: {U.FONT_SIZE_NORMAL}pt;
    }}

    QComboBox:focus {{
        border: 1px solid {U.HIGHLIGHT_SELECTED};
    }}

    /* 드롭다운 리스트 */
    QComboBox QAbstractItemView {{
        background-color: {U.INPUT_WIDGET_BG};
        border: 1px solid {U.HIGHLIGHT_SELECTED};
        selection-background-color: {U.HIGHLIGHT_SELECTED};
        selection-color: {U.TEXT_BUTTON};
        outline: none;
    }}

    QComboBox QAbstractItemView::item {{
        min-height: 20px;
        padding: 4px 8px;
    }}

    QComboBox QAbstractItemView::item:hover {{
        background-color: {U.ACCENT_BLUE};
        color: {U.TEXT_BUTTON};
    }}
"""


# 하위 호환성을 위한 변수 (모듈 import 시 자동 생성)
APP_STYLESHEET = get_app_stylesheet()
