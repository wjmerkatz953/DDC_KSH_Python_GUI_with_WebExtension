# -*- coding: utf-8 -*-
# 파일명: qt_widget_events.py
# 설명: Qt 위젯 이벤트 관련 유틸리티 함수들 (QTableWidget 30% 교체)
# 버전: 2.1.1 - Dark/Light 테마 전환 대응
# 생성일: 2025-09-24
# 수정일: 2025-10-27 - paintSection 메서드의 모든 색상을 UI_CONSTANTS로 동적 로드하여 테마 전환 대응

import json
from PySide6.QtWidgets import (
    QHeaderView,
    QMenu,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QCheckBox,
    QAbstractItemView,
    QWidgetAction,
    QTableView,
    QPushButton,
    QDialog,  # 👈 CustomTextFilterDialog의 기반 클래스
    QLineEdit,  # 👈 입력 필드
    QLabel,  # 👈 설명 텍스트
    QHBoxLayout,  # 👈 버튼 레이아웃
)
from PySide6.QtCore import Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QAction, QPainter, QPen, QFont, QColor
from qt_utils import apply_dark_title_bar, enable_modal_close_on_outside_click

# ✅ U는 제거 - paintSection에서 UI_CONSTANTS를 매번 import하여 테마 전환 대응


class CustomTextFilterDialog(QDialog):
    """텍스트 필터 입력을 위한 커스텀 다이얼로그 (한글 입력 완전 지원)"""

    def __init__(self, parent, column_name, current_filter=""):
        # -------------------
        # ✅ [핵심 수정 1] parent를 None으로 설정하여 독립 윈도우로 생성
        super().__init__(None)
        # -------------------

        self.setWindowTitle(f"텍스트 필터 - {column_name}")
        self.setFixedSize(400, 150)
        self.text = None

        # -------------------
        # ✅ [핵심 수정 2] 윈도우 플래그 명시적 설정 (모달이 아닌 일반 다이얼로그)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowCloseButtonHint
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
        )
        self.setModal(True)  # 모달로 설정하되, 위의 플래그로 IME 처리는 정상화
        # -------------------

        # 💡 다크 타이틀바 적용
        apply_dark_title_bar(self)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"'{column_name}' 컬럼에서 찾을 텍스트를 입력하세요:"))

        # -------------------
        # ✅ [핵심 수정 3] QLineEdit IME 속성 명시적 활성화
        self.input_line = QLineEdit()
        self.input_line.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.input_line.setInputMethodHints(Qt.ImhNone)
        # -------------------

        self.input_line.setText(current_filter)
        layout.addWidget(self.input_line)

        # -------------------
        # ✅ [핵심 수정 4] 다이얼로그 표시 후 포커스 설정 (더 긴 딜레이)
        def set_focus_after_show():
            self.input_line.setFocus()
            self.input_line.selectAll()
            self.activateWindow()  # 윈도우 활성화 추가

        QTimer.singleShot(100, set_focus_after_show)  # 0ms → 100ms로 변경
        # -------------------

        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("적용")
        self.cancel_button = QPushButton("취소")

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.ok_button.clicked.connect(self._accept)
        self.cancel_button.clicked.connect(self.reject)
        self.input_line.returnPressed.connect(self._accept)

        # -------------------
        # ✅ [핵심 수정 5] 부모 윈도우 중앙에 위치시키기 (멀티 모니터 대응)
        if parent:
            # parent가 QTableView인 경우, 실제 메인 윈도우를 찾아야 함
            main_window = None
            if hasattr(parent, "window"):
                main_window = parent.window()
            elif parent is not None:
                main_window = parent

            if main_window and hasattr(main_window, "geometry"):
                parent_rect = main_window.geometry()
                # 중앙 좌표 계산
                x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
                y = parent_rect.y() + (parent_rect.height() - self.height()) // 2
                self.move(x, y)
        enable_modal_close_on_outside_click(self)

    def _accept(self):
        """적용 버튼 클릭 처리"""
        self.text = self.input_line.text()
        self.accept()

    @staticmethod
    def getText(parent, column_name, current_filter=""):
        dialog = CustomTextFilterDialog(parent, column_name, current_filter)
        result = dialog.exec()
        return dialog.text, result == QDialog.Accepted


class NonClosingMenu(QMenu):
    """체크박스 메뉴에서 클릭해도 닫히지 않는 메뉴"""

    def mouseReleaseEvent(self, event):
        action = self.activeAction()
        if action and action.isCheckable():
            action.trigger()
        else:
            super().mouseReleaseEvent(event)


class ExcelStyleTableHeaderView(QHeaderView):
    """
    ✅ [모델/뷰 완전 호환] QTableView + QStandardItemModel용 Excel 스타일 헤더뷰.
    모든 기능(5단계 영역, 커서, 고급 필터)을 모델/뷰 아키텍처에 맞게 이식했습니다.
    """

    def __init__(
        self,
        orientation,
        parent=None,
        column_headers=None,
        callbacks=None,
        tab_instance=None,
    ):
        super().__init__(orientation, parent)

        # ✅ [모델/뷰 전환] QTableWidget → QTableView 참조
        self.table_view = parent
        self.column_headers = column_headers if column_headers is not None else []
        self.callbacks = callbacks if callbacks is not None else {}
        # ✅ [핵심 수정] 부모 탭 인스턴스를 직접 저장
        self.tab_instance = tab_instance
        self.column_filters = {}
        self.current_sort_column = -1
        self.sort_ascending = True

        # ✅ [추가] 컬럼 조작 기능 활성화
        self.setSectionsClickable(True)  # 클릭 가능
        self.setSectionsMovable(True)  # 순서 변경 가능
        self.setContextMenuPolicy(Qt.CustomContextMenu)  # 우클릭 메뉴
        self.setMouseTracking(True)  # 마우스 추적

        # ✅ [중요] 크기 조절 모드 설정
        self.setSectionResizeMode(QHeaderView.Interactive)  # 사용자가 크기 조절 가능

        # ✅ [핵심 추가] 자동 정렬 방지 설정
        self.setSortIndicatorShown(False)  # 정렬 인디케이터 숨김

        # ✅ [추가] 테이블 자체의 정렬 비활성화
        if hasattr(parent, "setSortingEnabled"):
            parent.setSortingEnabled(False)

        # 시그널 연결
        self.customContextMenuRequested.connect(self.show_header_context_menu)

        # ✅ [모델/뷰 전환] 모델 참조 초기화
        self._initialize_model_reference()

        # ✅ [추가] 중앙 클릭 추적 플래그
        self._center_click_column = None

    def _initialize_model_reference(self):
        """✅ [새로운 메서드] 테이블 뷰의 모델 참조를 초기화"""
        if self.table_view and hasattr(self.table_view, "model"):
            self.table_model = self.table_view.model()

    def get_table_model(self):
        """✅ [새로운 메서드] 현재 테이블 모델을 안전하게 반환"""
        if not self.table_model and self.table_view:
            self.table_model = self.table_view.model()
        return self.table_model

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        mouse_pos = self.mapFromGlobal(self.cursor().pos())
        is_hovered = rect.contains(mouse_pos)

        # ✅ 테마 전환 대응: UI_CONSTANTS를 매번 다시 가져와서 현재 테마 색상 적용
        from ui_constants import UI_CONSTANTS

        # 1. 배경 그리기
        if is_hovered:
            painter.fillRect(rect, QColor(UI_CONSTANTS.ACCENT_BLUE))
        else:
            painter.fillRect(
                rect, QColor(UI_CONSTANTS.QHEADER_BG)
            )  # 테이블뷰 컬럼 헤더 배경색상

        # 2. 테두리 그리기
        pen = QPen(QColor(UI_CONSTANTS.QHEADER_BORDER))
        pen.setWidth(0.5)
        painter.setPen(pen)
        # 왼쪽 경계선
        painter.drawLine(rect.topLeft(), rect.bottomLeft())
        # 오른쪽 경계선
        painter.drawLine(rect.topRight(), rect.bottomRight())

        # 3. 헤더 텍스트 가져오기
        header_text = self.model().headerData(logicalIndex, Qt.Horizontal)
        if header_text is None:
            header_text = ""

        painter.setPen(QColor(UI_CONSTANTS.TEXT_BUTTON) if not is_hovered else Qt.white)
        painter.setFont(
            QFont(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL, QFont.Bold)
        )

        # 4. 5구역 아이콘 및 텍스트 위치 계산 (공간 절약형 중앙 정렬 로직)

        # [핵심 수정 1] 공간 절약 및 중앙 정렬: 아이콘/텍스트 묶음을 하나로 중앙에 배치
        FONT_METRICS = painter.fontMetrics()

        # (1) 정렬 인디케이터 및 번호가 차지하는 공간의 총 너비 계산
        SORT_INDICATOR_SPACE = 10
        TEXT_PADDING_LEFT = 5

        sort_info = None
        if hasattr(self.table_view, "proxy_model"):
            for col, order in self.table_view.proxy_model.sort_keys:
                if col == logicalIndex:
                    sort_info = (col, order)
                    break

        # 정렬 활성화 여부
        is_column_being_sorted = (
            logicalIndex == self.current_sort_column or sort_info is not None
        )

        # 정렬이 활성화된 경우만 아이콘 공간을 확보
        reserved_icon_width = SORT_INDICATOR_SPACE if is_column_being_sorted else 0

        # (2) 텍스트 제목의 실제 픽셀 너비 측정
        header_text_width = FONT_METRICS.horizontalAdvance(header_text)

        # (3) 전체 콘텐츠 묶음 너비 (아이콘 + 간격 + 텍스트)
        total_content_width = (
            reserved_icon_width
            + (TEXT_PADDING_LEFT if is_column_being_sorted else 0)
            + header_text_width
        )

        # (4) 중앙 정렬을 위한 시작 오프셋 계산 (전체 섹션 너비 - 전체 내용 너비) / 2
        start_offset = max(0, (rect.width() - total_content_width) // 2)

        # (5) 아이콘 영역: 중앙 정렬 시작 위치에 배치
        sort_icon_rect = QRect(
            rect.x() + start_offset, rect.top(), SORT_INDICATOR_SPACE, rect.height()
        )

        # (6) 텍스트 영역: 아이콘 영역 바로 옆에 배치
        text_start_x = (
            rect.x()
            + start_offset
            + reserved_icon_width
            + (TEXT_PADDING_LEFT if is_column_being_sorted else 0)
        )
        # 텍스트가 짤리지 않도록 너비에 1px 여유분 추가
        text_rect = QRect(text_start_x, rect.y(), header_text_width + 1, rect.height())

        # filter_icon_pos = int(rect.width() * 0.85)
        # filter_icon_rect = QRect(
        #    rect.x() + filter_icon_pos - 9, rect.top(), 18, rect.height()
        # )

        # 5. 정렬 아이콘 그리기 (순서 번호와 함께)

        # 현재 컬럼이 정렬 기준 목록에 있거나 (멀티 정렬), 단일 정렬 컬럼인 경우
        if is_column_being_sorted:

            # 멀티 정렬 정보가 있을 경우 해당 정보를 사용하고, 없으면 현재 인스턴스 변수 사용
            if sort_info:
                sort_ascending = sort_info[1] == Qt.AscendingOrder
            else:
                sort_ascending = self.sort_ascending

            # [핵심 해결 2] 아이콘 폰트 설정 유지 (기울임 방지)
            icon_font = QFont(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL)
            icon_font.setItalic(False)

            sort_color = (
                QColor(UI_CONSTANTS.ACCENT_GREEN)
                if is_hovered
                else QColor(UI_CONSTANTS.ACCENT_BLUE)
            )
            painter.setPen(sort_color)
            painter.setFont(icon_font)

            sort_symbol = "▲" if sort_ascending else "▼"

            # [추가] 멀티 정렬 시 정렬 순서 번호 표시 (선택사항)
            if sort_info and len(self.table_view.proxy_model.sort_keys) > 1:
                # 정렬 순서 번호 찾기
                sort_index = [
                    k[0] for k in self.table_view.proxy_model.sort_keys
                ].index(logicalIndex) + 1
                # 요청하신 포맷: ▲(1)
                sort_symbol = f"{sort_symbol}({sort_index})"

            # [핵심] 아이콘을 정의된 SORT_INDICATOR_SPACE 영역 중앙에 그립니다.
            painter.drawText(sort_icon_rect, Qt.AlignCenter, sort_symbol)

        # 6. 헤더 텍스트 그리기 (아이콘 영역 이후)
        painter.setPen(QColor(UI_CONSTANTS.TEXT_BUTTON) if not is_hovered else Qt.white)
        painter.setFont(
            QFont(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL, QFont.Bold)
        )

        # [핵심] 텍스트는 자신의 영역(text_rect)에서 좌측 정렬되어 아이콘 옆에 붙습니다.
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, header_text)

        # 7. 필터 라인 그리기
        if logicalIndex in self.column_filters and self.column_filters[logicalIndex]:
            pen = QPen(QColor(UI_CONSTANTS.ACCENT_RED))
            pen.setWidth(4)
            painter.setPen(pen)
            # 상단에 라인을 그립니다.
            painter.drawLine(rect.topLeft(), rect.topRight())

        painter.restore()

    def mousePressEvent(self, event):
        """✅ [단순화] 5구역 처리 로직 최적화"""
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        column = self.logicalIndexAt(pos)

        if column < 0:
            super().mousePressEvent(event)
            return

        # ✅ 클릭 위치 계산 (중복 제거)
        section_pos = self.sectionViewportPosition(column)
        section_width = self.sectionSize(column)
        click_x = pos.x() - section_pos
        click_ratio = click_x / section_width if section_width > 0 else 0

        print(f"🔍 클릭: 컬럼{column}, 비율{click_ratio:.1%}")

        # ✅ [핵심 개선] 5구역별 처리 단순화
        if click_ratio < 0.05 or click_ratio > 0.95:
            # 구역 1, 5: 크기 조절
            super().mousePressEvent(event)

        elif 0.05 <= click_ratio <= 0.25:
            # 구역 2: 정렬
            self.sort_by_column(column)

        elif 0.25 <= click_ratio <= 0.75:
            # 구역 3: 드래그앤드롭
            print("📝 드래그 영역 클릭 - 드래그앤드롭 허용")
            super().mousePressEvent(event)

        elif 0.75 <= click_ratio <= 0.95:
            # --- [핵심 수정] ---
            # 구역 4: 필터
            # 1. 빈 메뉴를 먼저 생성합니다.
            filter_menu = NonClosingMenu(self)

            # 2. 최적화된 populate 메서드를 호출하여 내용물을 채웁니다.
            #    이 메서드는 내부에 '개수 제한' 로직을 포함하고 있습니다.
            self._populate_value_filter_menu(filter_menu, column)

            # 3. 완성된 메뉴를 마우스 위치에 표시합니다.
            filter_menu.exec(event.globalPos())
            # --------------------

    def mouseMoveEvent(self, event):
        """[성능 개선] 마우스 드래그 중에는 Qt 기본 로직에 위임하여 성능 확보"""
        # 1. 마우스를 드래그하여 리사이즈하는 중일 때
        if event.buttons() == Qt.LeftButton:
            # 우리의 복잡한 페인팅 로직을 건너뛰고, Qt의 최적화된
            # C++ 기본 이벤트 핸들러를 호출하여 부드러운 리사이징을 보장합니다.
            super().mouseMoveEvent(event)
            return

        # 2. 마우스를 드래그 없이 그냥 움직일 때
        # 커서 모양 변경과 호버(hover) 효과를 위해 최소한의 업데이트만 수행합니다.
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        column = self.logicalIndexAt(pos)

        if column >= 0:
            section_pos = self.sectionViewportPosition(column)
            section_width = self.sectionSize(column)
            relative_pos = pos.x() - section_pos
            click_ratio = relative_pos / section_width if section_width > 0 else 0

            # 5개 구역에 따라 적절한 마우스 커서 모양으로 변경
            if click_ratio < 0.05 or click_ratio > 0.95:
                self.setCursor(Qt.SizeHorCursor)  # 양옆 크기 조절
            elif 0.05 <= click_ratio <= 0.25:
                self.setCursor(Qt.SizeVerCursor)  # 정렬
            elif 0.25 <= click_ratio <= 0.75:
                self.setCursor(Qt.SizeAllCursor)  # 이동
            else:  # 0.75 ~ 0.95
                self.setCursor(Qt.CrossCursor)  # 필터
        else:
            self.setCursor(Qt.ArrowCursor)  # 기본 커서

        # 호버 효과(배경색 변경 등)를 위해 뷰포트를 업데이트합니다.
        # 마우스 드래그 중에는 이 코드가 실행되지 않으므로 안전합니다.
        self.viewport().update()

    def mouseDoubleClickEvent(self, event):
        """✅ [추가] 더블클릭으로 정렬 해제"""
        if event.button() == Qt.LeftButton:
            pos = (
                event.position().toPoint()
                if hasattr(event, "position")
                else event.pos()
            )
            column = self.logicalIndexAt(pos)

            if column >= 0:
                section_pos = self.sectionViewportPosition(column)
                section_width = self.sectionSize(column)
                click_x = pos.x() - section_pos
                click_ratio = click_x / section_width if section_width > 0 else 0

                # ✅ [수정] 정렬/텍스트 영역에서만 정렬 해제
                if 0.05 <= click_ratio <= 0.75:  # 구역 2~3 (정렬+텍스트)
                    self.clear_sort()
                    return
                else:
                    # 다른 영역은 기본 동작
                    super().mouseDoubleClickEvent(event)
                    return

        super().mouseDoubleClickEvent(event)

    def sectionResizeEvent(self, logicalIndex, oldSize, newSize):
        """✅ [개선] 컬럼 크기 변경 시 즉시 업데이트"""
        # 기본 동작 수행
        super().sectionResizeEvent(logicalIndex, oldSize, newSize)

        # ✅ 즉시 화면 갱신으로 부드러운 리사이즈
        if hasattr(self, "table_view") and self.table_view:
            self.table_view.viewport().update()
            # 추가적으로 헤더도 업데이트
            self.viewport().update()

        # 크기 변경 로그
        column_name = (
            self.column_headers[logicalIndex]
            if logicalIndex < len(self.column_headers)
            else f"컬럼{logicalIndex}"
        )
        print(f"📏 실시간 크기 변경: '{column_name}' {oldSize}px → {newSize}px")

    def sectionMoved(self, logicalIndex, oldVisualIndex, newVisualIndex):
        """✅ [개선] 컬럼 순서 변경 시 즉시 업데이트"""
        # 기본 동작 수행
        super().sectionMoved(logicalIndex, oldVisualIndex, newVisualIndex)

        # ✅ 즉시 화면 갱신
        if hasattr(self, "table_view") and self.table_view:
            self.table_view.viewport().update()
            self.viewport().update()

        # 순서 변경 로그
        column_name = (
            self.column_headers[logicalIndex]
            if logicalIndex < len(self.column_headers)
            else f"컬럼{logicalIndex}"
        )
        print(f"🔀 컬럼 순서 변경: '{column_name}' {oldVisualIndex} → {newVisualIndex}")

    def show_filter_menu(self, column_index):
        """✅ [완전 수정] 수평 스크롤바 포함 필터 메뉴 객체를 반환"""

        if column_index >= len(self.column_headers):
            print(f"❌ 필터 실패: 유효하지 않은 컬럼 인덱스 {column_index}")
            return None

        column_name = self.column_headers[column_index]
        print(f"✅ 필터 메뉴 객체 생성: '{column_name}' 컬럼")

        # 메뉴 생성 (exec()가 아닌 객체 반환이 목적)
        menu = NonClosingMenu(self)
        menu.setTitle(f"값 목록으로 필터: {column_name}")

        # 텍스트 필터 및 필터 지우기 (기본 옵션)
        text_filter_action = menu.addAction(f"🔍 {column_name} 텍스트 필터...")
        text_filter_action.triggered.connect(
            lambda: self.show_text_filter_dialog(column_index, column_name)
        )

        clear_filter_action = menu.addAction("🗑️ 필터 지우기")
        clear_filter_action.triggered.connect(
            lambda: self.clear_column_filter(column_index)
        )
        clear_filter_action.setEnabled(column_index in self.column_filters)

        menu.addSeparator()

        # 고유 값 수집
        unique_values = self.get_unique_values_from_model(column_index)

        if not unique_values:
            no_data_action = menu.addAction("📋 데이터가 없습니다")
            no_data_action.setEnabled(False)

        # ✅ [핵심] QWidgetAction과 QScrollArea를 사용한 수평/수직 스크롤 지원
        widget_action = QWidgetAction(menu)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        # ✅ [수정] 수평 스크롤바도 표시하고 15행 제한
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 수평 스크롤바
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 수직 스크롤바
        scroll_area.setMaximumHeight(15 * 28)  # 15행 제한
        scroll_area.setMinimumWidth(300)  # 최소 너비 설정

        scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; } "
            "QWidget { background: transparent; }"
        )

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 5, 10, 5)
        content_layout.setSpacing(5)

        # 현재 필터 상태 확인
        current_filters = self.column_filters.get(column_index, [])
        if isinstance(current_filters, str):
            current_filters = [current_filters]

        is_currently_filtered = column_index in self.column_filters and bool(
            self.column_filters[column_index]
        )

        # (전체 선택) 체크박스
        select_all_cb = QCheckBox("✅ (전체 선택)")
        all_selected = not is_currently_filtered or len(current_filters) == len(
            unique_values
        )
        select_all_cb.setChecked(all_selected)
        content_layout.addWidget(select_all_cb)

        # (전체 해제) 체크박스
        deselect_all_cb = QCheckBox("❌ (전체 해제)")
        deselect_all_cb.setChecked(False)
        content_layout.addWidget(deselect_all_cb)

        # 개별 값 체크박스들
        checkboxes = []

        for value in sorted(unique_values):
            # ✅ [수정] 긴 텍스트는 제한하지 않고 수평 스크롤로 해결
            display_text = str(value)
            cb = QCheckBox(display_text)
            cb.original_value = value  # 원본 값 저장

            # 체크 상태 결정
            if is_currently_filtered:
                is_checked = value in current_filters
            else:
                is_checked = True  # 필터가 없으면 모든 값 선택 상태

            cb.setChecked(is_checked)
            checkboxes.append(cb)
            content_layout.addWidget(cb)

        # [핵심 수정] 전체 선택/해제 연동 로직
        def handle_select_all(checked):
            """'전체 선택' 처리: '전체 해제'를 끄고 모든 항목을 선택"""
            if checked:
                # 1. 다른 마스터 체크박스를 끈다.
                deselect_all_cb.setChecked(False)
                # 2. 모든 개별 항목을 켠다.
                for cb in checkboxes:
                    cb.setChecked(True)

        def handle_deselect_all(checked):
            """'전체 해제' 처리: '전체 선택'을 끄고 모든 항목을 해제"""
            if checked:
                # 1. 다른 마스터 체크박스를 끈다.
                select_all_cb.setChecked(False)
                # 2. 모든 개별 항목을 끈다.
                for cb in checkboxes:
                    cb.setChecked(False)

        select_all_cb.toggled.connect(handle_select_all)
        deselect_all_cb.toggled.connect(handle_deselect_all)

        # 스크롤 영역에 위젯 설정
        scroll_area.setWidget(content_widget)
        widget_action.setDefaultWidget(scroll_area)
        menu.addAction(widget_action)

        # 하단 적용/취소 버튼
        menu.addSeparator()
        apply_action = menu.addAction("🔧 적용")
        cancel_action = menu.addAction("❌ 취소")

        # 적용 동작
        def apply_filter():
            selected_values = []
            for cb in checkboxes:
                if cb.isChecked():
                    selected_values.append(cb.original_value)

            if selected_values and len(selected_values) < len(unique_values):
                self.column_filters[column_index] = selected_values
                print(
                    f"✅ 필터 적용: '{column_name}' - {len(selected_values)}개 값 선택"
                )
            else:
                if column_index in self.column_filters:
                    del self.column_filters[column_index]
                print(f"🗑️ 필터 제거: '{column_name}' - 모든 값 선택됨")

            self.apply_filters()
            self.viewport().update()
            menu.close()

        def cancel_filter():
            menu.close()

        apply_action.triggered.connect(apply_filter)
        cancel_action.triggered.connect(cancel_filter)

        # 메뉴 표시
        return menu  # 👈 메뉴 객체를 반환하도록 변경

    # ===== AFTER (수정 후: show_text_filter_dialog 메서드 추가) =====
    def show_text_filter_dialog(self, column_index, column_name):
        """✅ [새로 추가] 텍스트 필터 다이얼로그"""

        # [핵심 수정] NameError 방지를 위해 current_filter 변수를 초기화하고 정의합니다.
        current_filter = ""
        if column_index in self.column_filters:
            filters = self.column_filters[column_index]
            if isinstance(filters, str):
                current_filter = filters
            elif isinstance(filters, list) and len(filters) == 1:
                current_filter = str(filters[0])

        # 새로 정의된 커스텀 다이얼로그를 사용합니다.
        text, ok = CustomTextFilterDialog.getText(
            self.table_view,  # HeaderView가 아닌 QTableView를 parent로 전달
            column_name,
            current_filter,  # 👈 current_filter 변수 사용
        )

        if ok and text.strip():
            # 텍스트 필터 적용
            self.column_filters[column_index] = text.strip()
            self.apply_filters()
            self.viewport().update()
            print(f"✅ 텍스트 필터 적용: '{column_name}' = '{text.strip()}'")
        elif ok and not text.strip():
            # 빈 텍스트 입력 시 필터 제거
            if column_index in self.column_filters:
                del self.column_filters[column_index]
                self.apply_filters()
                self.viewport().update()
                print(f"🗑️ 텍스트 필터 제거: '{column_name}'")

    def get_unique_values_from_model(self, column_index):
        """[버그 수정] Proxy 모델 뒤의 Source 모델에 직접 접근하여 고유값을 초고속으로 추출합니다."""
        try:
            # -------------------
            # ✅ [핵심 수정 1] 프록시 모델 여부를 확인하여 적절한 모델 선택
            model = self.table_view.model()
            if not model:
                return []

            # 프록시 모델인 경우 sourceModel()을 호출, 아니면 직접 사용
            if hasattr(model, 'sourceModel'):
                source_model = model.sourceModel()
                if not source_model:
                    return []
            else:
                # QStandardItemModel을 직접 사용하는 경우 (예: MARC_Extractor)
                source_model = model
            # -------------------

            # ✅ [핵심 수정 2] Pandas 의존성 제거 및 성능 향상
            # DataFrame을 매번 생성하는 대신, 모델을 직접 순회하고 set을 사용합니다.
            unique_values = set()
            for row in range(source_model.rowCount()):
                index = source_model.index(row, column_index)
                value = source_model.data(index, Qt.DisplayRole)
                if value is not None and value != "":
                    unique_values.add(str(value))

            result = sorted(list(unique_values))

            # 컬럼 이름 로깅
            column_name = (
                source_model.headerData(column_index, Qt.Horizontal)
                or f"컬럼 {column_index}"
            )
            print(
                f"🚀 모델 직접 순회 방식으로 컬럼 '{column_name}' 고유값 초고속 추출: {len(result)}개"
            )
            return result
            # -------------------
        except Exception as e:
            import traceback

            print(f"❌ 고유값 추출 실패: {e}\n{traceback.format_exc()}")
            return []

    def debug_filter_state(self):
        """✅ [디버깅] 현재 필터 상태 상세 출력"""
        print("=" * 50)
        print("🔍 필터 상태 디버깅")
        print(
            f"📊 테이블뷰 존재: {hasattr(self, 'table_view') and self.table_view is not None}"
        )

        if hasattr(self, "table_view") and self.table_view and self.table_view.model():
            model = self.table_view.model()
            print(f"📊 모델 존재: True")
            print(f"📊 전체 행 수: {model.rowCount()}")
            print(f"📊 전체 컬럼 수: {model.columnCount()}")

            # 현재 필터 상태
            print(f"📊 활성 필터 개수: {len(self.column_filters)}")
            for col_idx, filter_vals in self.column_filters.items():
                col_name = (
                    self.column_headers[col_idx]
                    if col_idx < len(self.column_headers)
                    else f"컬럼{col_idx}"
                )
                print(
                    f"   - {col_name} (컬럼 {col_idx}): {len(filter_vals) if isinstance(filter_vals, list) else 1}개 값"
                )

            # 현재 보이는 행 수 계산
            visible_count = 0
            for row in range(model.rowCount()):
                if not self.table_view.isRowHidden(row):
                    visible_count += 1
            print(f"📊 현재 보이는 행 수: {visible_count}")

        print("=" * 50)

    def apply_filters(self):
        """✅ [완전 수정] QTableView 모델/뷰 아키텍처에 맞는 필터 적용"""
        if not hasattr(self, "table_view") or not self.table_view:
            return

        model = self.table_view.model()
        if not model:
            return

        if not self.column_filters:
            # 필터가 없으면 모든 행 표시
            for row in range(model.rowCount()):
                self.table_view.setRowHidden(row, False)
            print("🗑️ 모든 필터 제거 - 전체 행 표시")
            return

        visible_count = 0

        # 모든 행에 대해 필터 조건 검사
        for row in range(model.rowCount()):
            should_show = True

            # 모든 활성 필터 조건을 AND로 검사
            for col_index, filter_values in self.column_filters.items():
                if col_index >= model.columnCount():
                    continue

                # 모델에서 데이터 가져오기
                index = model.index(row, col_index)
                cell_text = str(model.data(index, Qt.DisplayRole) or "")

                if isinstance(filter_values, str):
                    # 텍스트 필터 (부분 매칭)
                    if filter_values.lower() not in cell_text.lower():
                        should_show = False
                        break
                elif isinstance(filter_values, list):
                    # 체크박스 필터 (완전 매칭)
                    if cell_text not in filter_values:
                        should_show = False
                        break

            # 행 표시/숨김 설정
            self.table_view.setRowHidden(row, not should_show)
            if should_show:
                visible_count += 1

        print(
            f"🔍 필터 적용 완료: {visible_count}개 행 표시, {len(self.column_filters)}개 필터 활성"
        )

        # 뷰 업데이트
        self.table_view.viewport().update()

    # ===== AFTER (수정 후: show_all_rows 메서드 추가) =====
    def show_all_rows(self):
        """✅ [새로 추가] 모든 행을 표시 (필터 제거 시 사용)"""
        if not hasattr(self, "table_view") or not self.table_view:
            return

        model = self.table_view.model()
        if not model:
            return

        # 모든 행을 표시
        for row in range(model.rowCount()):
            self.table_view.setRowHidden(row, False)

        # 뷰 업데이트
        self.table_view.viewport().update()
        print("👁️ 모든 행 표시 완료")

    def sort_by_column(self, logical_index):
        """✅ [성능 개선] 캐싱을 지원하는 프록시 모델의 sort()를 직접 호출"""
        print(f"🔄 최적화된 정렬 요청: 컬럼 {logical_index}")

        if self.current_sort_column == logical_index:
            self.sort_ascending = not self.sort_ascending
        else:
            self.current_sort_column = logical_index
            self.sort_ascending = True

        sort_order = Qt.AscendingOrder if self.sort_ascending else Qt.DescendingOrder

        if hasattr(self, "table_view") and self.table_view:
            model = self.table_view.model()

            # [핵심 수정] 모델(프록시 모델)의 sort 함수를 직접 호출하여
            # 우리가 구현한 캐싱 로직(_build_sort_key_cache)이 실행되도록 강제합니다.
            if hasattr(model, "sort"):
                # 이 호출이 SmartNaturalSortProxyModel의 오버라이드된 sort 메서드를 실행시킴
                model.sort(logical_index, sort_order)
                print(
                    f"✅ 프록시 모델의 최적화된 sort() 호출 완료: 컬럼 {logical_index}, "
                    f"{'오름차순' if self.sort_ascending else '내림차순'}"
                )

            else:
                # 프록시 모델이 없는 경우를 위한 예외 처리 (기존 코드 유지)
                self.table_view.sortByColumn(logical_index, sort_order)

        elif hasattr(self, "table_widget") and self.table_widget:
            self.table_widget.sortItems(logical_index, sort_order)
        else:
            print("❌ 정렬 실패: 테이블 위젯을 찾을 수 없음")

        self.viewport().update()

    def apply_sort_to_table(self, column, ascending):
        """✅ [새로 추가] 실제 테이블 정렬 적용"""
        if hasattr(self.table_view, "sortByColumn"):
            # QTableView의 경우
            sort_order = Qt.AscendingOrder if ascending else Qt.DescendingOrder
            self.table_view.sortByColumn(column, sort_order)
        elif hasattr(self.table_widget, "sortByColumn"):
            # QTableWidget의 경우
            sort_order = Qt.AscendingOrder if ascending else Qt.DescendingOrder
            self.table_widget.sortByColumn(column, sort_order)

    def show_header_context_menu(self, position):
        """✅ [완전 복원] 헤더 우클릭 컨텍스트 메뉴"""
        logical_index = self.logicalIndexAt(position)
        menu = NonClosingMenu(self)

        if logical_index >= 0:
            column_name = (
                self.column_headers[logical_index]
                if logical_index < len(self.column_headers)
                else f"컬럼 {logical_index}"
            )
            sort_asc_action = menu.addAction(f"📈 {column_name} 오름차순 정렬")
            sort_desc_action = menu.addAction(f"📉 {column_name} 내림차순 정렬")
            clear_sort_action = menu.addAction("🔄 정렬 해제")
            clear_sort_action.setEnabled(self.current_sort_column != -1)
            menu.addSeparator()
            hide_column_action = menu.addAction(f"👁️‍🗨️ '{column_name}' 컬럼 숨기기")

            # 시그널 연결 (필터 부분 제외)
            sort_asc_action.triggered.connect(
                lambda: self._sort_column(logical_index, True)
            )
            sort_desc_action.triggered.connect(
                lambda: self._sort_column(logical_index, False)
            )
            clear_sort_action.triggered.connect(self.clear_sort)
            hide_column_action.triggered.connect(
                lambda: self.hide_column(logical_index)
            )

        # 컬럼 표시/숨기기 체크박스 섹션
        menu.addSeparator()
        columns_menu = NonClosingMenu("📋 컬럼 표시/숨기기", self)
        menu.addMenu(columns_menu)

        # 전체 선택/해제 옵션 추가
        select_all_action = QAction("✅ 전체 표시", columns_menu)
        select_all_action.triggered.connect(
            lambda: (
                self.callbacks.get("show_all", lambda: None)()
                if self.callbacks
                else None
            )
        )
        columns_menu.addAction(select_all_action)

        deselect_all_action = QAction("⬜ 전체 숨기기", columns_menu)
        deselect_all_action.triggered.connect(
            lambda: (
                self.callbacks.get("hide_all", lambda: None)()
                if self.callbacks
                else None
            )
        )
        columns_menu.addAction(deselect_all_action)

        columns_menu.addSeparator()

        # 각 컬럼별 체크박스
        for i in range(len(self.column_headers)):
            column_name = self.column_headers[i]
            is_visible = not self.isSectionHidden(i)

            column_action = QAction(column_name, columns_menu)
            column_action.setCheckable(True)
            column_action.setChecked(is_visible)
            column_action.triggered.connect(
                lambda checked, col=i: self.toggle_column_visibility(col, checked)
            )
            columns_menu.addAction(column_action)

        # [핵심 수정] 필터링 관련 컨텍스트 메뉴 구성 (두 가지 경로 지원)
        menu.addSeparator()
        if logical_index >= 0:
            # 1. 텍스트 필터 (클릭 시 다이얼로그)
            text_filter_action = menu.addAction(f"🔍 '{column_name}' 텍스트 필터...")
            text_filter_action.triggered.connect(
                lambda: self.show_text_filter_dialog(logical_index, column_name)
            )

        if logical_index >= 0:
            column_name = self.column_headers[logical_index]
            # 1. 텍스트 필터 (클릭 시 다이얼로그)
            text_filter_action = menu.addAction(f"🔍 '{column_name}' 텍스트 필터...")
            text_filter_action.triggered.connect(
                lambda: self.show_text_filter_dialog(logical_index, column_name)
            )

            # 2. 값 목록 필터 (비어있는 Sub Menu를 먼저 생성)
            # [수정] 메뉴 제목에서 직접 추가했던 화살표(▶)를 제거합니다.
            value_filter_menu = QMenu(f"값 목록으로 필터: {column_name}", menu)

            # 3. [핵심] 메뉴가 표시되기 직전(aboutToShow)에 내용물을 채우는 함수를 연결
            value_filter_menu.aboutToShow.connect(
                lambda menu=value_filter_menu, col=logical_index: self._populate_value_filter_menu(
                    menu, col
                )
            )

            menu.addMenu(value_filter_menu)

            # 4. 컬럼 필터 지우기
            clear_column_filter_action = menu.addAction(
                f"🗑️ '{column_name}' 필터 지우기"
            )
            clear_column_filter_action.setEnabled(logical_index in self.column_filters)
            clear_column_filter_action.triggered.connect(
                lambda: self.clear_column_filter(logical_index)
            )

        # 전체 컬럼 옵션
        menu.addSeparator()
        show_all_action = menu.addAction("👁️ 모든 컬럼 표시")
        hide_all_action = menu.addAction("🙈 모든 컬럼 숨기기")

        menu.addSeparator()
        save_settings_action = menu.addAction("💾 컬럼 설정 저장")
        load_settings_action = menu.addAction("📂 컬럼 설정 불러오기")

        menu.addSeparator()
        clear_all_filters_action = menu.addAction("🗑️ 모든 필터 지우기")
        clear_all_filters_action.setEnabled(len(self.column_filters) > 0)

        # 콜백 함수 연결
        if self.callbacks:
            if "show_all" in self.callbacks:
                show_all_action.triggered.connect(self.callbacks["show_all"])
            if "hide_all" in self.callbacks:
                hide_all_action.triggered.connect(self.callbacks["hide_all"])
            if "save" in self.callbacks:
                save_settings_action.triggered.connect(self.callbacks["save"])
            if "load" in self.callbacks:
                load_settings_action.triggered.connect(self.callbacks["load"])

        clear_all_filters_action.triggered.connect(self.clear_all_filters)

        menu.exec(self.mapToGlobal(position))

    # ✅ [새로 구현] 컬럼 표시/숨기기 메서드들
    def hide_column(self, column_index):
        """컬럼 숨기기"""
        if hasattr(self, "table_view") and self.table_view:
            self.table_view.setColumnHidden(column_index, True)
        elif hasattr(self, "table_widget") and self.table_widget:
            self.table_widget.setColumnHidden(column_index, True)

    def toggle_column_visibility(self, column_index, visible):
        """컬럼 표시/숨기기 토글"""
        if hasattr(self, "table_view") and self.table_view:
            self.table_view.setColumnHidden(column_index, not visible)
        elif hasattr(self, "table_widget") and self.table_widget:
            self.table_widget.setColumnHidden(column_index, not visible)

    # ✅  정렬 해제 메서드
    def clear_sort(self):
        """정렬 해제 및 원래 순서 복원"""
        if hasattr(self, "current_sort_column"):
            self.current_sort_column = -1
            self.sort_ascending = True

        # 프록시 모델 정렬 해제
        if hasattr(self, "table_view") and self.table_view:
            model = self.table_view.model()
            if hasattr(model, "sort"):
                # 원본 순서로 복원 (행 인덱스 순)
                model.sort(-1, Qt.AscendingOrder)

            # BaseSearchTab의 reset_table_order 콜백 호출
            if "clear_sort" in getattr(self, "callbacks", {}):
                self.callbacks["clear_sort"]()

        # 헤더 업데이트
        self.viewport().update()
        print("🔄 정렬 해제: 원래 순서로 복원")

    def _sort_column(self, column_index, ascending):
        """정렬 헬퍼 메서드"""
        self.current_sort_column = column_index
        self.sort_ascending = ascending

        sort_order = Qt.AscendingOrder if ascending else Qt.DescendingOrder
        if self.table_view:
            self.table_view.sortByColumn(column_index, sort_order)

        self.viewport().update()

    def clear_column_filter(self, column_index):
        """✅ [완전 수정] 특정 컬럼의 필터를 제거"""
        if column_index in self.column_filters:
            column_name = (
                self.column_headers[column_index]
                if column_index < len(self.column_headers)
                else f"컬럼{column_index}"
            )
            del self.column_filters[column_index]
            self.apply_filters()

            # 헤더 다시 그리기 (필터 아이콘 업데이트)
            if hasattr(self, "viewport"):
                self.viewport().update()
            elif hasattr(self, "table_view"):
                self.table_view.viewport().update()

            print(f"🗑️ 필터 제거 완료: '{column_name}'")

    def clear_all_filters(self):
        """✅ [모델/뷰 호환] 모든 필터를 제거"""
        self.column_filters.clear()
        self.apply_filters()

        # 헤더 다시 그리기
        self.viewport().update()

    def get_active_filters_count(self):
        """현재 활성화된 필터 개수 반환"""
        return len(self.column_filters)

    def get_filter_summary(self):
        """현재 필터 상태 요약 반환"""
        if not self.column_filters:
            return "필터 없음"

        summary_parts = []
        for col_idx, filter_values in self.column_filters.items():
            column_name = (
                self.column_headers[col_idx]
                if col_idx < len(self.column_headers)
                else f"컬럼{col_idx}"
            )
            if isinstance(filter_values, list):
                summary_parts.append(f"{column_name}({len(filter_values)}개)")
            else:
                summary_parts.append(f"{column_name}(텍스트)")

        return "필터: " + ", ".join(summary_parts)

    def _populate_value_filter_menu(self, menu, column_index):
        """[성능 개선] 필터 메뉴가 표시되기 직전에 내용물을 채우며, 표시할 항목 수를 제한합니다."""
        # 이미 메뉴 내용이 채워져 있다면 다시 실행하지 않습니다 (최초 1회만 실행).
        if menu.actions():
            return

        # 표시할 필터 항목의 최대 개수를 상수로 정의합니다.
        MAX_FILTER_ITEMS = 1000

        column_name = self.column_headers[column_index]
        menu.setTitle(f"값 목록으로 필터: {column_name}")

        # '텍스트 필터'와 '필터 지우기'는 항상 표시되는 기본 옵션입니다.
        text_filter_action = menu.addAction(f"🔍 '{column_name}' 텍스트 필터...")
        text_filter_action.triggered.connect(
            lambda: self.show_text_filter_dialog(column_index, column_name)
        )

        clear_filter_action = menu.addAction("🗑️ 필터 지우기")
        clear_filter_action.triggered.connect(
            lambda: self.clear_column_filter(column_index)
        )
        clear_filter_action.setEnabled(column_index in self.column_filters)

        menu.addSeparator()

        # Pandas를 이용해 고유값을 초고속으로 추출합니다.
        unique_values = self.get_unique_values_from_model(column_index)

        # 1. 고유값이 없는 경우
        if not unique_values:
            no_data_action = menu.addAction("📋 데이터가 없습니다")
            no_data_action.setEnabled(False)
            return

        # 2. 고유값이 너무 많아(MAX_FILTER_ITEMS 초과) 목록을 표시할 수 없는 경우
        if len(unique_values) > MAX_FILTER_ITEMS:
            info_action = menu.addAction(
                f"ℹ️ 고유값이 너무 많습니다 ({len(unique_values)}개)"
            )
            info_action.setEnabled(False)

            guide_action = menu.addAction("👉 '텍스트 필터'를 이용해주세요.")
            guide_action.setEnabled(False)
            return

        # 3. 고유값 개수가 적당하여 체크박스 목록을 생성하는 경우
        widget_action = QWidgetAction(menu)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setMaximumHeight(15 * 28)  # 최대 15개 항목 높이
        scroll_area.setMinimumWidth(300)
        scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; } "
            "QWidget { background: transparent; }"
        )

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 5, 10, 5)
        content_layout.setSpacing(5)

        current_filters = self.column_filters.get(column_index, [])
        if isinstance(current_filters, str):
            current_filters = [current_filters]

        is_currently_filtered = column_index in self.column_filters and bool(
            self.column_filters[column_index]
        )

        # '전체 선택'과 '전체 해제'를 위한 마스터 체크박스 생성
        select_all_cb = QCheckBox("✅ (전체 선택)")
        all_selected = not is_currently_filtered or len(current_filters) == len(
            unique_values
        )
        select_all_cb.setChecked(all_selected)
        content_layout.addWidget(select_all_cb)

        deselect_all_cb = QCheckBox("❌ (전체 해제)")
        deselect_all_cb.setChecked(False)
        content_layout.addWidget(deselect_all_cb)

        # 개별 값 체크박스 목록 생성
        checkboxes = []
        for value in sorted(unique_values):
            display_text = str(value)
            cb = QCheckBox(display_text)
            cb.original_value = value
            if is_currently_filtered:
                is_checked = value in current_filters
            else:
                is_checked = True  # 필터가 없으면 모든 항목이 선택된 것으로 간주
            cb.setChecked(is_checked)
            checkboxes.append(cb)
            content_layout.addWidget(cb)

        # '전체 선택'/'전체 해제' 체크박스의 동작 정의
        def handle_select_all(checked):
            if checked:
                deselect_all_cb.setChecked(False)
                for cb in checkboxes:
                    cb.setChecked(True)

        def handle_deselect_all(checked):
            if checked:
                select_all_cb.setChecked(False)
                for cb in checkboxes:
                    cb.setChecked(False)

        select_all_cb.toggled.connect(handle_select_all)
        deselect_all_cb.toggled.connect(handle_deselect_all)

        # 스크롤 가능한 위젯을 메뉴에 추가
        scroll_area.setWidget(content_widget)
        widget_action.setDefaultWidget(scroll_area)
        menu.addAction(widget_action)

        # '적용'과 '취소' 버튼 추가
        menu.addSeparator()
        apply_action = menu.addAction("🔧 적용")
        cancel_action = menu.addAction("❌ 취소")

        # '적용' 버튼 클릭 시 필터 실행
        def apply_filter():
            selected_values = [cb.original_value for cb in checkboxes if cb.isChecked()]

            # 모든 항목이 선택되거나 아무것도 선택되지 않은 경우는 필터링하지 않음
            if selected_values and len(selected_values) < len(unique_values):
                self.column_filters[column_index] = selected_values
            else:
                if column_index in self.column_filters:
                    del self.column_filters[column_index]

            self.apply_filters()
            self.viewport().update()
            menu.close()

        apply_action.triggered.connect(apply_filter)
        cancel_action.triggered.connect(lambda: menu.close())


# ===== 🔥 NEW: QTableView 호환 함수들 =====


def setup_table_view_sorting(view, app_instance=None):
    """QTableView에 정렬 기능을 자동으로 추가"""
    try:
        if not isinstance(view, QTableView):
            if app_instance:
                app_instance.log_message("경고: QTableView만 지원됩니다.", "WARNING")
            return

        # 정렬 활성화
        view.setSortingEnabled(True)

        # 헤더가 ExcelStyleTableHeaderView인지 확인
        header = view.horizontalHeader()
        if hasattr(header, "sort_by_column"):
            header._sorting_setup_complete = True

        if app_instance:
            app_instance.log_message("QTableView 정렬 기능이 활성화되었습니다.", "INFO")

    except Exception as e:
        if app_instance:
            app_instance.log_message(f"경고: QTableView 정렬 설정 실패: {e}", "WARNING")


def sort_table_view_by_column(view, column, ascending=True, app_instance=None):
    """QTableView를 지정된 컬럼으로 정렬 (프록시 모델 호환)"""
    try:
        if not isinstance(view, QTableView):
            return False

        model = view.model()
        if not model:
            return False

        # ✅ 프록시 모델이든 일반 모델이든 모두 호환
        sort_order = Qt.AscendingOrder if ascending else Qt.DescendingOrder

        # Qt 표준 방식으로 정렬 (프록시 모델이 자동으로 처리)
        view.sortByColumn(column, sort_order)

        # 로깅
        if app_instance:
            column_name = (
                model.headerData(column, Qt.Horizontal) if model else f"컬럼 {column}"
            )
            sort_direction = "오름차순" if ascending else "내림차순"
            app_instance.log_message(
                f"🔄 정렬 완료: {column_name} ({sort_direction})", "INFO"
            )

        return True

    except Exception as e:
        if app_instance:
            app_instance.log_message(f"오류: QTableView 정렬 실패: {e}", "ERROR")
        return False


def focus_on_first_table_view_item(view, app_instance=None):
    """QTableView의 첫 번째 셀에 포커스를 맞춤"""
    try:
        if not isinstance(view, QTableView):
            return False

        model = view.model()
        if model and model.rowCount() > 0 and model.columnCount() > 0:
            first_index = model.index(0, 0)
            view.setCurrentIndex(first_index)
            view.setFocus()

            if app_instance:
                app_instance.log_message("첫 번째 셀에 포커스를 설정했습니다.", "INFO")
            return True

        return False

    except Exception as e:
        if app_instance:
            app_instance.log_message(f"오류: 첫 번째 셀 포커스 실패: {e}", "ERROR")
        return False


def setup_table_view_find(view, app_instance=None):
    """QTableView에서 텍스트 검색 기능 설정"""
    try:
        if not isinstance(view, QTableView):
            if app_instance:
                app_instance.log_message("경고: QTableView만 지원됩니다.", "WARNING")
            return

        # 검색 기능은 별도 구현 필요
        # 현재는 placeholder
        if app_instance:
            app_instance.log_message("QTableView 검색 기능 설정 완료", "INFO")

    except Exception as e:
        if app_instance:
            app_instance.log_message(f"경고: QTableView 검색 설정 실패: {e}", "ERROR")


# ===== 범용 함수들 (QTableView 지원 추가) =====


def save_column_settings(tab_name, column_headers, widget, app_instance=None):
    """컬럼 설정을 데이터베이스에 저장 (QTableView 전용)"""
    if not widget or not tab_name or not column_headers:
        return

    try:
        # QTableView 전용으로, 분기 로직 제거
        header = widget.horizontalHeader()

        column_settings = {}
        for i, column_name in enumerate(column_headers):
            column_settings[column_name] = {
                "width": header.sectionSize(i),
                "hidden": header.isSectionHidden(i),
                # -------------------
                # ✅ [핵심 추가] 컬럼의 실제 표시 순서(visualIndex) 저장
                "visual_index": header.visualIndex(i),
                # -------------------
            }

        # 기존 설정 불러오기
        settings_str = app_instance.db_manager.get_setting("column_settings")
        if settings_str:
            all_settings = json.loads(settings_str)
        else:
            all_settings = {}

        all_settings[tab_name] = column_settings

        # 저장
        app_instance.db_manager.set_setting("column_settings", json.dumps(all_settings))

        if app_instance:
            app_instance.log_message(
                f"💾 {tab_name} 컬럼 설정이 저장되었습니다. (순서 포함)", "COMPLETE"
            )

    except Exception as e:
        if app_instance:
            app_instance.log_message(f"❌ 컬럼 설정 저장 실패: {e}", "ERROR")


def load_column_settings(tab_name, column_headers, widget, app_instance=None):
    """저장된 컬럼 설정을 불러옴 (QTreeWidget, QTableWidget, QTableView 모두 지원)"""
    if not widget or not tab_name or not column_headers:
        if app_instance:
            app_instance.log_message(
                "컬럼 설정 불러오기: 필수 매개변수가 누락되었습니다.", "INFO"
            )
        return

    try:
        # settings 테이블에서 컬럼 설정 가져오기
        settings_str = app_instance.db_manager.get_setting("column_settings")
        if not settings_str:
            app_instance.log_message(
                f"ℹ️ {tab_name} 저장된 컬럼 설정이 없습니다.", "INFO"
            )
            return

        all_settings = json.loads(settings_str)
        if tab_name not in all_settings:
            app_instance.log_message(f"ℹ️ {tab_name} 탭의 설정이 없습니다.", "INFO")
            return

        tab_settings = all_settings[tab_name]

        # QTableView 전용으로, 분기 로직 제거
        header = widget.horizontalHeader()

        # -------------------
        # ✅ [1단계] 먼저 컬럼 순서를 복원 (visual_index 정보가 있는 경우)
        for i, column_name in enumerate(column_headers):
            if column_name in tab_settings:
                col_setting = tab_settings[column_name]
                saved_visual_index = col_setting.get("visual_index")

                if saved_visual_index is not None:
                    current_visual_index = header.visualIndex(i)
                    if current_visual_index != saved_visual_index:
                        # 저장된 위치로 컬럼 이동
                        header.moveSection(current_visual_index, saved_visual_index)
        # -------------------

        # [2단계] 그 다음 너비와 숨김 상태 적용
        for i, column_name in enumerate(column_headers):
            if column_name in tab_settings:
                col_setting = tab_settings[column_name]
                header.setSectionHidden(i, col_setting.get("hidden", False))
                header.resizeSection(i, col_setting.get("width", 100))

        app_instance.log_message(
            f"🔄 {tab_name} 저장된 컬럼 설정을 불러왔습니다. (순서 포함)", "COMPLETE"
        )

    except Exception as e:
        app_instance.log_message(f"❌ 컬럼 설정 불러오기 실패: {e}", "ERROR")


def show_all_columns_utility(
    widget, tab_name=None, column_headers=None, app_instance=None
):
    """✅ [이름 변경] 독립 유틸리티 함수 - 모든 컬럼 표시"""
    try:
        if hasattr(widget, "setColumnHidden"):
            if hasattr(widget, "columnCount"):
                # QTableWidget
                column_count = widget.columnCount()
            else:
                # QTableView
                column_count = (
                    len(column_headers)
                    if column_headers
                    else widget.model().columnCount()
                )

            for i in range(column_count):
                widget.setColumnHidden(i, False)

        if app_instance and hasattr(app_instance, "log_message"):
            app_instance.log_message("👁️ 모든 컬럼을 표시했습니다.", "INFO")

        return True
    except Exception as e:
        print(f"❌ 모든 컬럼 표시 실패: {e}")
        return False


def hide_all_columns_utility(
    widget, tab_name=None, column_headers=None, app_instance=None
):
    """✅ [이름 변경] 독립 유틸리티 함수 - 첫 번째 컬럼 제외하고 모든 컬럼 숨기기"""
    try:
        if hasattr(widget, "setColumnHidden"):
            if hasattr(widget, "columnCount"):
                # QTableWidget
                column_count = widget.columnCount()
            else:
                # QTableView
                column_count = (
                    len(column_headers)
                    if column_headers
                    else widget.model().columnCount()
                )

            # 첫 번째 컬럼 제외하고 모두 숨기기
            for i in range(1, column_count):
                widget.setColumnHidden(i, True)

        if app_instance and hasattr(app_instance, "log_message"):
            app_instance.log_message(
                "🙈 첫 번째 컬럼 외 모든 컬럼을 숨겼습니다.", "INFO"
            )

        return True
    except Exception as e:
        print(f"❌ 컬럼 숨기기 실패: {e}")
        return False
