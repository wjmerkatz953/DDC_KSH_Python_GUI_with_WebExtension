#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_constants.py - UI 관련 상수 정의 (Qt 전용)
버전: 2.0.0
생성일: 2025-09-23
"""
from path_utils import resource_path


class UI_CONSTANTS:
    BACKGROUND_PRIMARY = "#0e111a"
    BACKGROUND_SECONDARY = "#1b2236"
    BACKGROUND_TERTIARY = "#131722"
    WIDGET_BG_DEFAULT = "#1b2235"

    TEXT_DEFAULT = "#b1b1b1"
    TEXT_SUBDUED = "#ADAAAA"
    TEXT_HIGHLIGHT = "#B1630A"
    TEXT_BUTTON = "#cacfda"

    ACCENT_BLUE = "#0072b3"  # 주 강조색 (VS Code 파란색)
    ACCENT_ORANGE = "#6a8a39"  # 보조 강조색 (경고/상태용 주황색)
    ACCENT_GREEN = "#4EC9B0"  # 성공/완료 상태 (VS Code 녹색)
    ACCENT_RED = "#D84040"  # 오류 상태 (VS Code 빨간색)
    ACCENT_YELLOW = "#ff7300"  # 오류 상태 (VS Code 빨간색)
    ACCENT_BLUE_HOVER = "#005a91"

    TEXT_STATUS_COMPLETE = ACCENT_GREEN

    BORDER_COLOR = "#555555"

    CORNER_RADIUS_DEFAULT = 0
    TREEVIEW_ROW_HEIGHT_DEFAULT = 25

    QTABLE_BORDER = "#316caa"

    # 하이라이트 색상 (검색/정렬용)
    HIGHLIGHT_COLOR_FIND = "#FFFF00"
    HIGHLIGHT_SELECTED = "#AD2E00"

    # 상태 색상
    TEXT_STATUS_READY = TEXT_DEFAULT  # 준비 상태 텍스트
    TEXT_STATUS_PROGRESS = ACCENT_ORANGE  # 진행 중 상태 텍스트
    TEXT_STATUS_COMPLETE = ACCENT_GREEN  # 완료 상태 텍스트
    TEXT_STATUS_ERROR = ACCENT_RED  # 오류 상태 텍스트
    TEXT_WARNING = ACCENT_ORANGE  # 경고 텍스트
    TEXT_LLM_NEEDED = BACKGROUND_TERTIARY  # LLM 필요 텍스트
    TEXT_BUTTON = "#cacfda"  # 버튼 텍스트 색상 정의

    WIDGET_BG_DEFAULT = "#1b2235"
    WIDGET_BG_ERROR = "#8B0000"  # 오류 배경용 더 어두운 빨간색
    WIDGET_BG_LLM_NEEDED = "#1A2B50"  # LLM 필요 배경용 더 어두운 청록색
    # 어두운 회색 스크롤바 썸 (CTkScrollableFrame용)
    SCROLLBAR_THUMB = "#1f1f1f"
    # 호버 시 더 밝은 회색 (CTkScrollableFrame용)
    SCROLLBAR_ACTIVE_THUMB = "#1a2b50"

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

    # 모서리 반경 (Customtkinter 전용)
    CORNER_RADIUS_DEFAULT = 0  # VS Code처럼 각진 디자인
    CORNER_RADIUS_BUTTON = 0  # 버튼 모서리 반경
    CORNER_RADIUS_ENTRY = 0  # 입력 필드 모서리 반경
    CORNER_RADIUS_TEXTBOX = 0  # 텍스트 상자 모서리 반경


# 단축 별칭
U = UI_CONSTANTS
