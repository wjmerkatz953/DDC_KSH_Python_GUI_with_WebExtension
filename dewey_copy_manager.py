# -*- coding: utf-8 -*-
"""
파일명: dewey_copy_manager.py
설명: Dewey 탭 전용 복사 기능 모음 (기존 로직/주석 불변, 추가만)
의존: qt_copy_feedback.copy_to_clipboard_with_feedback, qt_context_menus 유틸 일부
"""

from __future__ import annotations
import re
from typing import Any, Optional
from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import QTableView, QTreeView, QApplication

from qt_copy_feedback import copy_to_clipboard_with_feedback, show_copy_feedback

# 선택 영역 → Markdown/CSV/일반 텍스트 복사용(이미 앱에 존재하는 유틸)
from qt_context_menus import (
    # 선택 셀들을 CSV로 직렬화해서 클립보드로
    copy_tableview_as_csv,
    # 선택 셀들을 Markdown 테이블로 직렬화해서 클립보드로
    copy_tableview_as_markdown,
    # 선택 범위를 평문으로 복사
    copy_tableview_selection,
    # 한 행 전체를 키-값 라인으로 복사
    copy_tableview_row_data,
)


class DeweyCopyManager:
    """
    Dewey 탭 내부에서만 쓰는 복사 동작을 한 곳에 모은 경량 매니저.
    - 기존 탭/모델 로직은 수정하지 않고, 여기서만 호출함.
    """

    def __init__(self, owner: Any):
        # owner는 QtDeweySearchTab (혹은 그와 동일한 필드를 가진 객체) 이어야 함
        self.owner = owner

    # ---------- 공통 도우미 ----------
    def _emit_feedback(self, text: str) -> None:
        try:
            show_copy_feedback(self.owner, text)
        except Exception:
            pass

    # ---------- DDC 입력창 ----------
    def copy_ddc_from_entry(self) -> None:
        """DDC 입력창의 코드 텍스트를 그대로 복사."""
        try:
            entry = getattr(self.owner, "dewey_ddc_entry", None)
            if entry is None:
                return
            code = (entry.text() or "").strip()
            if not code:
                return
            copy_to_clipboard_with_feedback(
                code, getattr(self.owner, "app_instance", None)
            )
        except Exception:
            pass

    # ---------- 트리(계층) ----------
    def copy_selected_tree_line(self) -> None:
        """
        트리에서 선택된 항목의 '표시 텍스트 한 줄'을 복사.
        (예: "025.042 — Web sites")
        """
        try:
            tree: QTreeView = getattr(self.owner, "dewey_context_tree", None)
            if tree is None or tree.selectionModel() is None:
                return
            idxs = tree.selectionModel().selectedIndexes()
            if not idxs:
                return
            idx: QModelIndex = idxs[0]
            model = idx.model()
            text = str(model.data(idx, Qt.DisplayRole) or "")
            if text:
                copy_to_clipboard_with_feedback(
                    text, getattr(self.owner, "app_instance", None)
                )
        except Exception:
            pass

    def copy_tree_hierarchy_path(self) -> None:
        """
        선택 항목부터 루트까지의 경로를 ' > ' 로 이어 복사.
        - 각 노드의 표시 텍스트를 사용
        """
        try:
            tree: QTreeView = getattr(self.owner, "dewey_context_tree", None)
            if tree is None or tree.selectionModel() is None:
                return
            idxs = tree.selectionModel().selectedIndexes()
            if not idxs:
                return
            model = tree.model()
            cur = idxs[0]
            parts = []
            while cur.isValid():
                parts.append(str(model.data(cur, Qt.DisplayRole) or ""))
                cur = cur.parent()
            parts.reverse()
            line = " > ".join([p for p in parts if p])
            if line:
                copy_to_clipboard_with_feedback(
                    line, getattr(self.owner, "app_instance", None)
                )
        except Exception:
            pass

    def copy_tree_code_only(self) -> None:
        """
        선택 항목의 DDC 코드만 복사.
        - 표시 텍스트에서 선행 숫자/소수점 패턴을 추출 (가장 보편적 케이스)
        """
        try:
            tree: QTreeView = getattr(self.owner, "dewey_context_tree", None)
            if tree is None or tree.selectionModel() is None:
                return
            idxs = tree.selectionModel().selectedIndexes()
            if not idxs:
                return
            idx: QModelIndex = idxs[0]
            text = str(idx.data(Qt.DisplayRole) or "")
            # "025.042 — Web sites" 또는 "025.0422" 등에서 코드만 추출
            m = re.search(r"^\s*([\d]{1,3}(?:\.[\d]+)?)", text)
            code = m.group(1) if m else text.strip()
            if code:
                copy_to_clipboard_with_feedback(
                    code, getattr(self.owner, "app_instance", None)
                )
        except Exception:
            pass

    # ---------- 우측 KSH 테이블 ----------
    def copy_ksh_selection_plain(self) -> None:
        """KSH Results 테이블의 선택 영역을 평문으로 복사."""
        try:
            table: QTableView = getattr(self.owner, "ksh_table", None)
            if table is None:
                return
            copy_tableview_selection(table, getattr(self.owner, "app_instance", None))
        except Exception:
            pass

    def copy_ksh_selection_csv(self) -> None:
        """KSH Results 테이블의 선택 영역을 CSV로 복사."""
        try:
            table: QTableView = getattr(self.owner, "ksh_table", None)
            if table is None:
                return
            copy_tableview_as_csv(table, getattr(self.owner, "app_instance", None))
        except Exception:
            pass

    def copy_ksh_selection_markdown(self) -> None:
        """KSH Results 테이블의 선택 영역을 Markdown 테이블로 복사."""
        try:
            table: QTableView = getattr(self.owner, "ksh_table", None)
            if table is None:
                return
            copy_tableview_as_markdown(table, getattr(self.owner, "app_instance", None))
        except Exception:
            pass

    def copy_ksh_row(self, row: Optional[int] = None) -> None:
        """현재 선택 행(또는 지정 행) 전체를 복사."""
        try:
            table: QTableView = getattr(self.owner, "ksh_table", None)
            if table is None or table.selectionModel() is None:
                return
            if row is None:
                sel = table.selectionModel().selectedRows()
                if not sel:
                    return
                row = sel[0].row()
            copy_tableview_row_data(
                table, row, getattr(self.owner, "app_instance", None)
            )
        except Exception:
            pass
