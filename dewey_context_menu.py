# -*- coding: utf-8 -*-
"""
파일명: dewey_context_menu.py
설명: Dewey 탭 전용 컨텍스트 메뉴 바인딩 (기존 로직/주석 불변, 추가만)
의존: qt_context_menus의 범용 함수, dewey_copy_manager.DeweyCopyManager
"""

from __future__ import annotations
from typing import Any
import re
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QMenu, QAction, QTreeView, QTableView, QTextEdit

from qt_context_menus import (
    setup_widget_context_menu,  # 텍스트 위젯 표준 컨텍스트 메뉴
    show_qtableview_context_menu,  # QTableView 범용 컨텍스트 메뉴
    show_cell_detail_dialog,  # 셀 상세 보기
    open_url_safely,  # URL 열기 유틸
)
from dewey_copy_manager import DeweyCopyManager


def _parse_ddc_code_from_text(text: str) -> str:
    """
    트리/라벨에 표시된 텍스트에서 DDC 코드만 뽑아낸다.
    - 예: "025.042 — Web sites" → "025.042"
    - 실패 시 원문 반환
    """
    m = re.search(r"^\s*([\d]{1,3}(?:\.[\d]+)?)", text or "")
    return m.group(1) if m else (text or "").strip()


def _open_webdewey_for(owner: Any, code_text: str) -> None:
    """
    WebDewey(또는 DLD API 기반 페이지)에 안전하게 연결.
    - 기존 open_url_safely 유틸 사용
    """
    code = _parse_ddc_code_from_text(code_text)
    if not code:
        return
    # 기본적으로 OCLC DDC Linked Data 진입 URL로 연결
    url = f"https://id.oclc.org/worldcat/ddc/api/url?ddc={code}"
    open_url_safely(url, getattr(owner, "app_instance", None))


def _build_tree_menu(owner: Any, pos: QPoint) -> None:
    """
    왼쪽 DDC 트리 전용 컨텍스트 메뉴.
    - 복사(코드/전체/경로), WebDewey 열기
    """
    tree: QTreeView = getattr(owner, "dewey_context_tree", None)
    if tree is None or tree.selectionModel() is None:
        return

    idxs = tree.selectionModel().selectedIndexes()
    if not idxs:
        return

    idx = idxs[0]
    text = str(idx.data(Qt.DisplayRole) or "")

    menu = QMenu(tree)
    menu.setTitle("DDC 트리")

    mgr = DeweyCopyManager(owner)

    act_copy_line = QAction("📋 이 줄 복사", menu)
    act_copy_line.triggered.connect(mgr.copy_selected_tree_line)
    menu.addAction(act_copy_line)

    act_copy_code = QAction("🔢 코드만 복사", menu)
    act_copy_code.triggered.connect(mgr.copy_tree_code_only)
    menu.addAction(act_copy_code)

    act_copy_path = QAction("🧭 계층 경로 복사", menu)
    act_copy_path.triggered.connect(mgr.copy_tree_hierarchy_path)
    menu.addAction(act_copy_path)

    menu.addSeparator()

    act_open_webdewey = QAction("🌐 WebDewey에서 열기", menu)
    act_open_webdewey.triggered.connect(lambda: _open_webdewey_for(owner, text))
    menu.addAction(act_open_webdewey)

    menu.exec(tree.viewport().mapToGlobal(pos))


def _build_table_menu(owner: Any, table: QTableView, pos: QPoint) -> None:
    """
    오른쪽 KSH 결과 테이블 전용 컨텍스트 메뉴(기본 메뉴 + Dewey 추가 옵션).
    - 기본 범용 메뉴는 재사용(show_qtableview_context_menu)
    - 추가: CSV/Markdown/행 복사 빠른 액션
    """
    # 먼저 범용 메뉴 호출 (정렬/필터/링크열기/상세보기/복사 등)
    index = table.indexAt(pos)
    row, col = index.row(), index.column()
    if row < 0 or col < 0:
        return

    # 범용 메뉴 표시
    show_qtableview_context_menu(
        table, row, col, pos, getattr(owner, "app_instance", None)
    )

    # 사용자가 범용 메뉴를 닫은 뒤, 추가 단축 액션을 신속히 쓰고 싶을 수 있어
    # 컨텍스트 메뉴를 다시 띄우지 않고 바로 실행 가능한 함수들도 제공.
    # (여기선 실제 팝업을 두 번 띄우지 않도록, 추가 팝업은 생략하고 매니저만 노출)
    # -> 호출자는 단축키(QShortcut)로 묶어 쓰면 됨.
    # 별도 메뉴가 필요하면 아래 주석을 풀어서 사용 가능.
    #
    # mgr = DeweyCopyManager(owner)
    # quick = QMenu(table)
    # quick.setTitle("빠른 복사")
    # a1 = QAction("CSV로 복사", quick); a1.triggered.connect(mgr.copy_ksh_selection_csv); quick.addAction(a1)
    # a2 = QAction("Markdown 테이블로 복사", quick); a2.triggered.connect(mgr.copy_ksh_selection_markdown); quick.addAction(a2)
    # a3 = QAction("선택 평문 복사", quick); a3.triggered.connect(mgr.copy_ksh_selection_plain); quick.addAction(a3)
    # quick.exec(table.viewport().mapToGlobal(pos))


def setup_dewey_context_menu(owner: Any) -> None:
    """
    Dewey 탭(=owner) 안의 관련 위젯들에 컨텍스트 메뉴를 연결한다.
    - 기존 위젯/메서드/주석은 변경하지 않고 signal만 추가 연결
    """
    # 좌측: DDC 트리
    tree: QTreeView = getattr(owner, "dewey_context_tree", None)
    if tree is not None:
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(lambda p: _build_tree_menu(owner, p))

    # 우측: KSH 결과 테이블
    table: QTableView = getattr(owner, "ksh_table", None)
    if table is not None:
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda p: _build_table_menu(owner, table, p)
        )

    # 텍스트 영역(세부/프리뷰)은 프로젝트의 표준 컨텍스트 메뉴 유틸 재사용
    detail: QTextEdit = getattr(owner, "dewey_detail_text", None)
    if detail is not None:
        setup_widget_context_menu(detail, getattr(owner, "app_instance", None))

    preview: QTextEdit = getattr(owner, "dewey_preview_text", None)
    if preview is not None:
        setup_widget_context_menu(preview, getattr(owner, "app_instance", None))

    # DDC 입력창에도 표준 컨텍스트 메뉴
    entry = getattr(owner, "dewey_ddc_entry", None)
    if entry is not None:
        setup_widget_context_menu(entry, getattr(owner, "app_instance", None))
