#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_constants.py - UI 관련 상수 정의 (Qt 전용)
버전: 3.0.2
생성일: 2025-09-23
변경일: 2025-10-27
- Western 탭 출처별 색상 상수 추가 (Dark/Light 테마별)
- Global 탭 전용 출처별 색상 상수 추가 (SOURCE_NDL, SOURCE_CINII, SOURCE_NLK)
"""
from path_utils import resource_path


class UI_CONSTANTS_DARK:
    """다크 테마 색상 상수"""

    BACKGROUND_PRIMARY = "#0e111a"
    BACKGROUND_SECONDARY = "#1b2236"
    BACKGROUND_TERTIARY = "#131722"
    WIDGET_BG_DEFAULT = "#1b2235"
    CORNER_STONE = "#1b2235"
    INPUT_WIDGET_BG = "#1a1f2e"  # 입력 위젯 전용 배경색

    TEXT_DEFAULT = "#bebebe"
    TEXT_SUBDUED = "#ADAAAA"
    TEXT_HIGHLIGHT = "#B1630A"
    TEXT_BUTTON = "#e0e0e0"
    TEXT_TAB_UNSELECTED = "#b1b1b1"  # 선택 안 된 탭 글씨

    ACCENT_BLUE = "#0072b3"  # 주 강조색 (VS Code 파란색)
    ACCENT_ORANGE = "#6a8a39"  # 보조 강조색 (경고/상태용 주황색)
    ACCENT_GREEN = "#4EC9B0"  # 성공/완료 상태 (VS Code 녹색)
    ACCENT_RED = "#D84040"  # 오류 상태 (VS Code 빨간색)
    ACCENT_YELLOW = "#ff7300"  # 경고 상태 (주황색)
    ACCENT_BLUE_HOVER = "#005a91"

    # Settings 탭 전용 버튼 색상
    BUTTON_PRIMARY = "#1e88e5"  # 설정 적용 버튼
    BUTTON_PRIMARY_HOVER = "#1976d2"
    BUTTON_PRIMARY_PRESSED = "#1565c0"
    BUTTON_DANGER = "#d32f2f"  # 기본값 복원 버튼
    BUTTON_DANGER_HOVER = "#c62828"
    BUTTON_DANGER_PRESSED = "#b71c1c"
    BUTTON_SUCCESS = "#388e3c"  # 재시작 안내 버튼
    BUTTON_SUCCESS_HOVER = "#2e7d32"
    BUTTON_SUCCESS_PRESSED = "#1b5e20"

    TEXT_STATUS_COMPLETE = ACCENT_GREEN

    BORDER_COLOR = "#555555"
    BORDER_LIGHT = "#141c31"  # 하드코딩 제거
    BORDER_MEDIUM = "#324880"  # 하드코딩 제거

    # Western 탭 출처별 색상 (Dark Theme)
    SOURCE_LC = "#C7DA72"
    SOURCE_HARVARD = "#99A1E6"
    SOURCE_MIT = "#8FB474"
    SOURCE_PRINCETON = "#E08A44"
    SOURCE_UPENN = "#B19CD9"
    SOURCE_CORNELL = "#D2B48C"
    SOURCE_DNB = TEXT_DEFAULT
    SOURCE_BNF = ACCENT_BLUE
    SOURCE_BNE = "#FFAE35"
    SOURCE_GOOGLE = "#2EDDC0"

    # Global 탭 전용 출처별 색상 (Dark Theme)
    SOURCE_NDL = "#FF6B9D"
    SOURCE_CINII = "#87CEEB"
    SOURCE_NLK = "#FFB347"


class UI_CONSTANTS_LIGHT:
    """라이트 테마 색상 상수"""

    BACKGROUND_PRIMARY = "#dbdbdb"
    BACKGROUND_SECONDARY = "#f5f5f5"
    BACKGROUND_TERTIARY = "#efefef"
    WIDGET_BG_DEFAULT = "#f0f0f0"
    INPUT_WIDGET_BG = "#cecccc"  # 입력 위젯 전용 배경색 (e8e8e8보다 살짝 어둡게)
    CORNER_STONE = "#1b2235"

    TEXT_DEFAULT = "#2c2c2c"
    TEXT_SUBDUED = "#4a4a4a"  # 설명 문구 색상 (더 어둡게 - 가독성 향상)
    TEXT_HIGHLIGHT = "#B1630A"
    TEXT_BUTTON = "#ffffff"  # 버튼 위 흰 글씨 유지

    ACCENT_BLUE = "#0072b3"  # 주 강조색 유지
    ACCENT_ORANGE = "#6a8a39"  # 보조 강조색 유지
    ACCENT_GREEN = "#047857"  # 성공/완료 상태 (Light 테마용 - 더 어두운 녹색)
    ACCENT_RED = "#C41E3A"  # 오류 상태 (Light 테마용 - 더 어두운 빨강)
    ACCENT_YELLOW = "#D97706"  # 경고 상태 (Light 테마용 - 더 어두운 주황)
    ACCENT_BLUE_HOVER = "#005a91"  # 호버 색상 유지

    # Settings 탭 전용 버튼 색상 (다크와 동일하게 유지)
    BUTTON_PRIMARY = "#1e88e5"
    BUTTON_PRIMARY_HOVER = "#1976d2"
    BUTTON_PRIMARY_PRESSED = "#1565c0"
    BUTTON_DANGER = "#d32f2f"
    BUTTON_DANGER_HOVER = "#c62828"
    BUTTON_DANGER_PRESSED = "#b71c1c"
    BUTTON_SUCCESS = "#388e3c"
    BUTTON_SUCCESS_HOVER = "#2e7d32"
    BUTTON_SUCCESS_PRESSED = "#1b5e20"

    TEXT_STATUS_COMPLETE = ACCENT_GREEN

    BORDER_COLOR = "#d0d0d0"
    BORDER_LIGHT = "#d1d1d1"
    BORDER_MEDIUM = "#b0b0b0"

    # Western 탭 출처별 색상 (Light Theme - 밝은 배경에 맞는 진한 색상)
    SOURCE_LC = "#6B8E23"  # 올리브 그린 (진하게)
    SOURCE_HARVARD = "#4A5FC1"  # 진한 파란색
    SOURCE_MIT = "#2E7D32"  # 진한 녹색
    SOURCE_PRINCETON = "#D84315"  # 진한 주황색
    SOURCE_UPENN = "#7B1FA2"  # 진한 보라색
    SOURCE_CORNELL = "#8D6E63"  # 진한 갈색
    SOURCE_DNB = TEXT_DEFAULT
    SOURCE_BNF = ACCENT_BLUE
    SOURCE_BNE = "#F57C00"  # 진한 오렌지
    SOURCE_GOOGLE = "#00897B"  # 진한 청록색

    # Global 탭 전용 출처별 색상 (Light Theme - 밝은 배경에 맞는 진한 색상)
    SOURCE_NDL = "#C2185B"  # 진한 핑크
    SOURCE_CINII = "#1976D2"  # 진한 하늘색
    SOURCE_NLK = "#F57C00"  # 진한 오렌지


# 기본 테마는 다크
_current_theme = "dark"
UI_CONSTANTS = UI_CONSTANTS_DARK


def set_theme(theme_name):
    """테마를 전환합니다. 'dark' 또는 'light'"""
    global UI_CONSTANTS, _current_theme
    if theme_name == "light":
        UI_CONSTANTS = UI_CONSTANTS_LIGHT
        _current_theme = "light"
    else:
        UI_CONSTANTS = UI_CONSTANTS_DARK
        _current_theme = "dark"


def get_current_theme():
    """현재 테마 이름을 반환합니다."""
    return _current_theme


def get_color(color_name):
    """현재 테마의 색상 값을 반환합니다."""
    return getattr(UI_CONSTANTS, color_name)


class UI_CONSTANTS_COMMON:
    """테마에 무관한 공통 상수"""

    CORNER_RADIUS_DEFAULT = 0
    TREEVIEW_ROW_HEIGHT_DEFAULT = 25
    QHEADER_BORDER = "#38373B"
    QTABLE_BORDER = "#316caa"

    # 하이라이트 색상 (검색/정렬용)
    HIGHLIGHT_COLOR_FIND = "#FFFF00"
    HIGHLIGHT_SELECTED = "#0072b3"
    HIGHLIGHT_SELECTED_RED = "#AD2E00"

    # 폰트
    FONT_FAMILY = "맑은 고딕"
    FONT_SIZE_SMALL = 9
    FONT_SIZE_NORMAL = 10
    FONT_SIZE_MEDIUM = 11
    FONT_SIZE_LARGE = 12
    FONT_SIZE_XLARGE = 13
    FONT_SIZE_XXLARGE = 14

    # 패딩
    PADDING_FRAME = 0
    PADDING_WIDGET_X = 5
    PADDING_WIDGET_Y = 0
    PADDING_SECTION_Y = 5
    PADDING_MAIN_FRAME = "10 10 10 10"

    # 로딩 화면
    LOADING_IMAGE_PATH = resource_path("loading.jpg")  # 로딩 이미지 경로
    LOADING_SCREEN_WIDTH = 900  # 로딩 화면 너비
    LOADING_SCREEN_HEIGHT = 900  # 로딩 화면 높이

    # 모서리 반경
    CORNER_RADIUS_BUTTON = 0  # 버튼 모서리 반경
    CORNER_RADIUS_ENTRY = 0  # 입력 필드 모서리 반경
    CORNER_RADIUS_TEXTBOX = 0  # 텍스트 상자 모서리 반경


# UI_CONSTANTS에 COMMON 속성 추가 (편의성)
for attr_name in dir(UI_CONSTANTS_COMMON):
    if not attr_name.startswith("_"):
        setattr(UI_CONSTANTS_DARK, attr_name, getattr(UI_CONSTANTS_COMMON, attr_name))
        setattr(UI_CONSTANTS_LIGHT, attr_name, getattr(UI_CONSTANTS_COMMON, attr_name))

# 테마별 추가 속성들
UI_CONSTANTS_DARK.TEXT_STATUS_READY = UI_CONSTANTS_DARK.TEXT_DEFAULT
UI_CONSTANTS_DARK.TEXT_STATUS_PROGRESS = UI_CONSTANTS_DARK.ACCENT_ORANGE
UI_CONSTANTS_DARK.TEXT_STATUS_ERROR = UI_CONSTANTS_DARK.ACCENT_RED
UI_CONSTANTS_DARK.TEXT_WARNING = UI_CONSTANTS_DARK.ACCENT_ORANGE
UI_CONSTANTS_DARK.TEXT_LLM_NEEDED = UI_CONSTANTS_DARK.BACKGROUND_TERTIARY
UI_CONSTANTS_DARK.WIDGET_BG_ERROR = "#8B0000"
UI_CONSTANTS_DARK.WIDGET_BG_LLM_NEEDED = "#1A2B50"
UI_CONSTANTS_DARK.SCROLLBAR_THUMB = "#1f1f1f"
UI_CONSTANTS_DARK.SCROLLBAR_ACTIVE_THUMB = "#1a2b50"

UI_CONSTANTS_LIGHT.TEXT_STATUS_READY = UI_CONSTANTS_LIGHT.TEXT_DEFAULT
UI_CONSTANTS_LIGHT.TEXT_STATUS_PROGRESS = UI_CONSTANTS_LIGHT.ACCENT_ORANGE
UI_CONSTANTS_LIGHT.TEXT_STATUS_ERROR = UI_CONSTANTS_LIGHT.ACCENT_RED
UI_CONSTANTS_LIGHT.TEXT_WARNING = UI_CONSTANTS_LIGHT.ACCENT_ORANGE
UI_CONSTANTS_LIGHT.TEXT_LLM_NEEDED = UI_CONSTANTS_LIGHT.BACKGROUND_TERTIARY
UI_CONSTANTS_LIGHT.WIDGET_BG_ERROR = "#FF6B6B"  # 라이트 테마용 에러 배경
UI_CONSTANTS_LIGHT.WIDGET_BG_LLM_NEEDED = "#D0E8FF"  # 라이트 테마용 LLM 배경
UI_CONSTANTS_LIGHT.SCROLLBAR_THUMB = "#c0c0c0"
UI_CONSTANTS_LIGHT.SCROLLBAR_ACTIVE_THUMB = "#a0a0a0"

# 단축 별칭
U = UI_CONSTANTS
