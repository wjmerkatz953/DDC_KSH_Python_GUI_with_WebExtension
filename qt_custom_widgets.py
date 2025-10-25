# -*- coding: utf-8 -*-
# 파일명: qt_custom_widgets.py
# 설명: 정확한 텍스트 선택을 제공하는 커스텀 위젯
# 생성일: 2025-10-01
# 수정일: 2025-10-03 - URL 커서 변경 delegate 추가

from PySide6.QtWidgets import QTextBrowser, QStyledItemDelegate
from PySide6.QtCore import Qt, QEvent, QRect
from PySide6.QtGui import QTextCursor, QMouseEvent, QCursor, QPainter, QPalette, QColor
import time
import re


class TripleClickLimitedTextBrowser(QTextBrowser):
    """정확한 텍스트 선택을 제공하는 위젯
    - URL 좌클릭으로 열기
    - 드래그 선택 정상 작동
    - 트리플 클릭 = 텍스트 끝까지만 선택
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.document().setDocumentMargin(0)
        self._click_count = 0
        self._last_click_time = 0
        self._triple_click_pos = None


    def mousePressEvent(self, event: QMouseEvent):
        """클릭 카운트 추적 - 링크는 제외"""
        if event.button() == Qt.LeftButton:
            # ✅ 링크를 클릭했는지 확인
            cursor = self.cursorForPosition(event.pos())
            anchor = cursor.charFormat().anchorHref()

            # 링크를 클릭했다면 카운트 추적 없이 바로 부모 클래스로 전달
            if anchor:
                super().mousePressEvent(event)
                return

            # 링크가 아닌 경우에만 클릭 카운트 추적
            current_time = time.time()

            if current_time - self._last_click_time < 0.5:
                self._click_count += 1
            else:
                self._click_count = 1

            self._last_click_time = current_time

            if self._click_count == 3:
                self._triple_click_pos = event.pos()

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """트리플 클릭 후 선택 범위를 클릭한 블록으로만 제한 - 링크는 제외"""
        # ✅ 링크를 클릭했는지 확인
        cursor = self.cursorForPosition(event.pos())
        anchor = cursor.charFormat().anchorHref()

        # 링크를 클릭했다면 트리플 클릭 처리 없이 바로 부모 클래스로 전달
        if anchor:
            super().mouseReleaseEvent(event)
            return

        super().mouseReleaseEvent(event)

        if self._triple_click_pos and self._click_count >= 3:
            # 클릭한 위치의 블록 정보 가져오기
            click_cursor = self.cursorForPosition(self._triple_click_pos)
            click_block = click_cursor.block()

            # 현재 선택된 영역 확인
            current_cursor = self.textCursor()

            # 선택 시작 블록과 끝 블록 확인
            start_block = self.document().findBlock(current_cursor.selectionStart())
            end_block = self.document().findBlock(current_cursor.selectionEnd())

            # 여러 블록이 선택된 경우, 클릭한 블록만 선택
            if start_block != end_block:
                new_cursor = QTextCursor(click_block)
                new_cursor.select(QTextCursor.BlockUnderCursor)
                self.setTextCursor(new_cursor)

            self._triple_click_pos = None
            self._click_count = 0

    def contextMenuEvent(self, event):
        print("[DEBUG] contextMenuEvent triggered")
        if self.viewport():
            self.viewport().customContextMenuRequested.emit(event.pos())



class URLHoverDelegate(QStyledItemDelegate):
    """URL 위에 마우스 hover 시 커서를 손가락 모양으로 변경하고, URL을 파란색으로 표시하며, 클릭 시 열기"""

    def __init__(self, table_view, app_instance=None):
        super().__init__(table_view)
        self.table_view = table_view
        self.app_instance = app_instance
        self.url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')

        # UI 상수에서 ACCENT_BLUE 색상 가져오기
        from ui_constants import UI_CONSTANTS

        self.link_color = QColor(UI_CONSTANTS.ACCENT_BLUE)

        # viewport에 event filter 설치
        if self.table_view and self.table_view.viewport():
            self.table_view.viewport().installEventFilter(self)
            self.table_view.viewport().setMouseTracking(True)

    def paint(self, painter, option, index):
        """URL 텍스트를 파란색으로 표시"""
        data = str(index.data(Qt.DisplayRole) or "").strip()

        # URL로 인식되면 파란색 링크 스타일 적용
        if self._is_url_text(data):
            option.palette.setColor(QPalette.Text, self.link_color)

        super().paint(painter, option, index)

    def eventFilter(self, obj, event):
        """viewport의 마우스 이벤트 필터링 - hover와 클릭 처리"""
        try:
            viewport = self.table_view.viewport()
        except RuntimeError:
            return super().eventFilter(obj, event)

        if obj == viewport:
            if event.type() == QEvent.MouseMove:
                # 마우스 위치에서 index 가져오기
                index = self.table_view.indexAt(event.pos())

                if index.isValid():
                    # 셀 내용 가져오기
                    cell_text = str(index.data(Qt.DisplayRole) or "")

                    # URL이 있는지 확인
                    if self.url_pattern.search(cell_text):
                        self.table_view.viewport().setCursor(
                            QCursor(Qt.PointingHandCursor)
                        )
                    else:
                        self.table_view.viewport().setCursor(QCursor(Qt.ArrowCursor))
                else:
                    self.table_view.viewport().setCursor(QCursor(Qt.ArrowCursor))

            elif (
                event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.LeftButton
            ):
                # URL 클릭 시 열기
                index = self.table_view.indexAt(event.pos())
                if index.isValid():
                    data = str(index.data(Qt.DisplayRole) or "").strip()
                    column_name = (
                        self.table_view.model().headerData(
                            index.column(), Qt.Horizontal, Qt.DisplayRole
                        )
                        or ""
                    )

                    pure_url = self._extract_pure_url(data, column_name)
                    if self._is_url_text(pure_url):
                        from qt_utils import open_url_safely

                        open_url_safely(pure_url, self.app_instance)
                        return True

        return super().eventFilter(obj, event)

    def _extract_pure_url(self, data, column_name):
        """데이터와 컬럼 이름을 기반으로 URL을 추출"""
        # KSH 마크업/HTML 태그 제거
        clean_data = re.sub(r"▼[a-zA-Z0-9].*?▲", "", data)
        clean_data = re.sub(r"<[^>]+>", "", clean_data).strip().rstrip(".")

        # URL 패턴 추출
        match = self.url_pattern.search(clean_data)

        if (
            "링크" in column_name
            or "URL" in column_name
            or "link" in column_name.lower()
        ):
            # 명시적인 링크 컬럼
            if match:
                return match.group(0).strip()
            return ""
        else:
            # 일반 컬럼
            if match:
                return match.group(0).strip()
            return ""

    def _is_url_text(self, text):
        """URL 패턴을 확인"""
        if not text or len(text) < 4:
            return False
        return bool(self.url_pattern.search(text))
