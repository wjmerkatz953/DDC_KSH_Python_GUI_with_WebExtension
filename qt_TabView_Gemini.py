# 파일: qt_TabView_Gemini.py

# -*- coding: utf-8 -*-
# 파일명: qt_TabView_Gemini.py
# 설명: Gemini 기반 계층적 DDC 분류 탭 (BaseSearchTab 상속 최종 버전)
# 버전: v2.2.0
# 수정: 2025-10-18 - QSplitter 자동 저장/복구 기능 추가
#       - splitter 변수를 self.main_splitter로 변경하여 인스턴스 변수화
#       - 앱 종료 시 스플리터 크기가 자동으로 DB에 저장되고 재시작 시 복구됨
# 이전: 2025-10-09 - 입력 영역 UI 표준화 및 중간 결과창 상시 표시

from PySide6.QtCore import Qt, Signal, QThread, Slot, QModelIndex, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QProgressBar,
    QTableView,
    QGroupBox,
    QHeaderView,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QFrame,
    QCheckBox,
    QLineEdit,
)
import pandas as pd
from qt_base_tab import (
    FastSearchResultModel,
)
from qt_proxy_models import SmartNaturalSortProxyModel
from view_displays import adjust_qtableview_columns
from qt_base_tab import BaseSearchTab
from qt_widget_events import ExcelStyleTableHeaderView
from ui_constants import U
from qt_Tab_configs import TAB_CONFIGURATIONS as tab_configs
from Search_Gemini import SearchGemini
import qt_api_settings  # ✅ API 설정 모듈 import


class GeminiWorker(QThread):
    progress = Signal(int)
    intermediate_update = Signal(list)
    finished_success = Signal(object)
    failed = Signal(str)

    def __init__(self, db_manager, bundle_text, app_instance=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.bundle_text = bundle_text
        self.app_instance = app_instance
        self._stop = False

    def stop(self):
        self._stop = True

    def _intermediate_callback(self, rows):
        if self._stop:
            return
        self.intermediate_update.emit(rows)

    def run(self):
        try:
            from search_query_manager import SearchQueryManager

            engine = SearchGemini(self.db_manager, self.app_instance)
            query_manager = SearchQueryManager(self.db_manager)

            self.progress.emit(0)
            result = engine.classify_ddc_with_hierarchical_validation(
                self.bundle_text, intermediate_callback=self._intermediate_callback
            )
            if self._stop:
                return
            if not isinstance(result, dict) or "error" in result:
                self.failed.emit(
                    result.get(
                        "error", "Gemini 분류 중 알 수 없는 오류가 발생했습니다."
                    )
                )
                return

            rows = []
            classifications = result.get("classifications", [])
            overall_desc = result.get("overallDescription", "")

            # nan 값 제거
            if overall_desc and str(overall_desc).lower() not in ["nan", "none"]:
                overall_desc = overall_desc
            else:
                overall_desc = ""

            if classifications and overall_desc:
                rows.append(
                    {
                        "순위": "전체 설명",
                        "DDC 분류번호": "",
                        "분류 해설": overall_desc,
                        "DDC실제의미": "",
                        "LC Catalog Links": "",
                    }
                )

            for i, rec in enumerate(classifications):
                ddc_number = rec.get("ddcNumber", "")
                # nan, N/A, None 값 처리
                if not ddc_number or str(ddc_number).lower() in ["nan", "n/a", "none"]:
                    ddc_number = ""

                lc_link = (
                    f"https://lccn.loc.gov/search/?q={ddc_number}&format=web"
                    if ddc_number
                    else ""
                )
                ddc_meaning = ""
                if ddc_number:
                    ddc_meaning = (
                        query_manager.get_ddc_description_cached(ddc_number) or ""
                    )

                rows.append(
                    {
                        "순위": f"{i+1}순위",
                        "DDC 분류번호": ddc_number,
                        "분류 해설": rec.get("reason", ""),
                        "DDC실제의미": ddc_meaning,
                        "LC Catalog Links": lc_link,
                    }
                )
            self.progress.emit(100)
            self.finished_success.emit(pd.DataFrame(rows))  # ✅ DataFrame으로 결과 전달
        except Exception as e:
            import traceback

            self.failed.emit(f"계층적 분류 중 예외: {e}\n{traceback.format_exc()}")


class QtGeminiTab(BaseSearchTab):
    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)
        self.worker = None
        # progress_bar를 항상 보이도록 설정
        if hasattr(self, "progress_bar"):
            self.progress_bar.setVisible(False)

    def create_input_section(self, parent_layout):
        """입력 영역을 MARC 추출 탭 스타일로 재정의합니다."""
        # --- 부모 클래스가 기대하지만 사용하지 않는 위젯 (오류 방지용) ---
        self.title_check = QCheckBox()
        self.title_check.setVisible(False)
        self.author_check = QCheckBox()
        self.author_check.setVisible(False)
        self.isbn_check = QCheckBox()
        self.isbn_check.setVisible(False)
        self.year_check = QCheckBox()
        self.year_check.setVisible(False)
        self.input_widgets["title"] = QLineEdit()
        self.input_widgets["title"].setVisible(False)
        self.input_widgets["author"] = QLineEdit()
        self.input_widgets["author"].setVisible(False)
        self.input_widgets["isbn"] = QLineEdit()
        self.input_widgets["isbn"].setVisible(False)
        self.input_widgets["year"] = QLineEdit()
        self.input_widgets["year"].setVisible(False)

        # --- MARC 추출 탭 스타일의 UI 생성 ---
        input_bar_frame = QFrame()
        input_bar_frame.setMaximumHeight(60)  # ✅ 프레임 전체 높이 제한
        input_bar_frame.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )  # ✅ 수직 고정
        input_bar_layout = QHBoxLayout(input_bar_frame)
        input_bar_layout.setContentsMargins(0, 4, 0, 0)
        input_bar_layout.setSpacing(4)  # ✅ 버튼 간격 설정

        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("텍스트를 여기에 붙여넣으세요...")
        self.input_edit.setMaximumHeight(60)  # ✅ 한 줄 스타일을 위한 높이 제한
        self.input_edit.setFont(QFont("Consolas", 9))
        self.input_edit.setStyleSheet(
            "QTextEdit { "
            "border: 0px solid #6495ED; "
            "background-color: #1a1f2e; "
            "border-radius: 0px; "
            "}"
        )
        input_bar_layout.addWidget(self.input_edit)

        # ✅ 표준 버튼 및 전용 버튼 생성
        self.search_button = QPushButton("DDC 분류 시작")
        self.stop_button = QPushButton("검색 중지")
        self.stop_button.setEnabled(False)
        self.btn_clear_input = QPushButton("입력 지우기")
        self.btn_clear_results = QPushButton("결과 지우기")

        input_bar_layout.addWidget(self.search_button)
        input_bar_layout.addWidget(self.stop_button)
        input_bar_layout.addWidget(self.btn_clear_input)
        input_bar_layout.addWidget(self.btn_clear_results)

        input_bar_layout.setStretch(0, 1)  # 입력창이 너비를 모두 차지하도록 설정
        parent_layout.addWidget(input_bar_frame)

    def create_results_section(self, parent_layout):
        self.main_splitter = QSplitter(Qt.Vertical)

        self.intermediate_group = QGroupBox(
            "🔍 계층적 검색 결과 (DB에서 추출된 DDC 후보군)"
        )
        # ❌ self.intermediate_group.setVisible(False) 제거
        inter_layout = QVBoxLayout(self.intermediate_group)
        inter_layout.setContentsMargins(6, 20, 6, 0)
        self.inter_table = QTableView()
        self.inter_table.setSortingEnabled(True)  # 정렬 기능 활성화

        # 중간 결과용 설정
        _cfg = tab_configs.get("GEMINI_DDC_SEARCH", {})
        intermediate_column_map = _cfg.get("intermediate_column_map", [])
        self.intermediate_column_keys = [c[0] for c in intermediate_column_map]
        self.intermediate_column_headers = [c[1] for c in intermediate_column_map]

        # -------------------
        # ✅ [핵심 수정] Proxy 모델을 생성하고 테이블에 연결하여 다른 탭과 구조를 통일합니다.
        self.inter_model = FastSearchResultModel(self.intermediate_column_headers, self)
        self.inter_proxy = SmartNaturalSortProxyModel()  # 1. Proxy 모델 생성
        self.inter_proxy.setSourceModel(self.inter_model)  # 2. Proxy에 원본 모델 연결
        self.inter_table.setModel(self.inter_proxy)  # 3. 테이블에 Proxy 모델 연결
        # -------------------

        # ExcelStyleTableHeaderView 설정
        inter_header = ExcelStyleTableHeaderView(
            Qt.Horizontal,
            self.inter_table,
            column_headers=self.intermediate_column_headers,
            tab_instance=self,
        )
        self.inter_table.setHorizontalHeader(inter_header)
        inter_header.setStretchLastSection(
            True
        )  # 마지막 컬럼이 남은 공간을 채우도록 설정

        # 중간 결과 테이블 컨텍스트 메뉴 활성화
        self.inter_table.setContextMenuPolicy(Qt.CustomContextMenu)

        inter_layout.addWidget(self.inter_table)
        self.main_splitter.addWidget(self.intermediate_group)

        super().create_results_section(self.main_splitter)

        if self.main_splitter.count() > 1:
            final_results_group = self.main_splitter.widget(1)
            if isinstance(final_results_group, QGroupBox):
                final_results_group.setTitle("📊 DDC 추천 결과")
                # ✅ 최종 결과 그룹박스의 레이아웃에 상단 여백 추가
                if final_results_group.layout():
                    final_results_group.layout().setContentsMargins(6, 20, 6, 6)

        parent_layout.addWidget(self.main_splitter)
        self.main_splitter.setSizes([400, 200])  # 중간 결과:최종 결과 = 2:1

    def create_find_section(self, parent_layout):
        """✅ [신규 추가] NLK 탭과 동일한 API 설정 버튼 추가"""
        # 부모 클래스의 find 섹션 먼저 생성
        super().create_find_section(parent_layout)

        # ✅ API 설정 버튼 생성
        self.api_settings_button = QPushButton("⚙️ API 설정")
        self.api_settings_button.setFixedWidth(100)
        self.api_settings_button.clicked.connect(self._show_api_settings)

        # ✅ API 상태 라벨 생성
        self.api_status_label = QLabel("")
        self.api_status_label.setAlignment(Qt.AlignCenter)
        self.api_status_label.setFixedWidth(150)

        # ✅ 마지막에 추가된 bar_container 찾기
        bar_container = parent_layout.itemAt(parent_layout.count() - 1).widget()
        if bar_container:
            bar_layout = bar_container.layout()
            if bar_layout and bar_layout.count() >= 2:
                # bar_layout의 두 번째 항목이 find_container
                find_container = bar_layout.itemAt(1).widget()
                if find_container:
                    find_layout = find_container.layout()
                    if find_layout:
                        # HTML 버튼 다음에 API 버튼들 추가
                        find_layout.addWidget(self.api_settings_button)
                        find_layout.addWidget(self.api_status_label)

        # 초기 상태 업데이트
        self._update_api_status()

    def _show_api_settings(self):
        """API 설정 모달창을 표시합니다."""
        qt_api_settings.show_api_settings_modal(
            "GEMINI",
            self.app_instance.db_manager,
            self.app_instance,
            parent_window=self,
        )

        # 다이얼로그가 닫힌 후 상태 업데이트
        self._update_api_status()

    def _update_api_status(self):
        """API 상태 라벨을 업데이트합니다."""
        if not hasattr(self, "api_status_label"):
            return

        try:
            is_configured = qt_api_settings.check_api_configured(
                "GEMINI", self.app_instance.db_manager
            )

            if is_configured:
                self.api_status_label.setText("API 상태: ✅ 설정됨")
                self.api_status_label.setStyleSheet(f"color: {U.ACCENT_GREEN};")
            else:
                self.api_status_label.setText("API 상태: ❌ 미설정")
                self.api_status_label.setStyleSheet(f"color: {U.ACCENT_RED};")

        except Exception as e:
            self.api_status_label.setText("API 상태: ❌ 오류")
            self.api_status_label.setStyleSheet(f"color: {U.ACCENT_RED};")
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(f"❌ API 상태 확인 실패: {e}", "ERROR")

    def setup_connections(self):
        super().setup_connections()
        # ✅ 버튼 연결: DDC 분류 시작 버튼을 start_search와 연결
        self.search_button.clicked.connect(self.start_search)
        self.stop_button.clicked.connect(self.stop_search)
        self.btn_clear_input.clicked.connect(self.input_edit.clear)
        self.btn_clear_results.clicked.connect(self.on_clear_results)

        # 중간 결과 테이블 컨텍스트 메뉴 연결
        self.inter_table.customContextMenuRequested.connect(
            self.on_inter_table_context_menu
        )
        # 중간 결과 테이블 더블클릭 연결
        self.inter_table.doubleClicked.connect(self.on_inter_table_double_click)

        # ✅ 중간 결과 테이블의 선택 변경 시 상세 정보 업데이트
        self.inter_table.selectionModel().currentChanged.connect(
            self._update_detail_view_from_intermediate
        )

    def start_search(self):
        bundle_text = self.input_edit.toPlainText().strip()
        if not bundle_text:
            QMessageBox.warning(
                self, "입력 필요", "저자정보/목차/서평을 한 번에 붙여넣어 주세요."
            )
            return
        self._stop_worker_if_running()
        self.on_clear_results()

        # UI 상태 업데이트
        self.search_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.is_searching = True
        self.progress_bar.setValue(0)
        self.status_label.setText("Gemini DDC 분류 시작...")

        self.worker = GeminiWorker(
            self.app_instance.db_manager, bundle_text, self.app_instance, self
        )
        self.worker.progress.connect(self.update_progress_bar)
        self.worker.intermediate_update.connect(self._on_intermediate_rows)
        self.worker.finished_success.connect(self.on_search_completed)
        self.worker.failed.connect(self.on_search_failed)
        self.worker.start()

    def stop_search(self):
        """검색 중지"""
        self._stop_worker_if_running()
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.is_searching = False
        self.status_label.setText("검색이 중지되었습니다.")
        self.progress_bar.setValue(0)

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def on_search_completed(self, result_df):
        """검색 완료 처리 - 최종 결과를 하단 테이블에 표시"""
        # UI 상태 복원
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.is_searching = False
        self.progress_bar.setValue(100)

        # 결과가 DataFrame인지 확인
        if result_df is None or (hasattr(result_df, "empty") and result_df.empty):
            self.status_label.setText("DDC 분류 결과가 없습니다.")
            return

        # 하단 테이블에 결과 표시
        self.table_model.clear_data()
        records = result_df.to_dict("records")
        self.table_model.add_multiple_rows(records, column_keys=None)

        # 테이블 컬럼 조정
        from view_displays import adjust_qtableview_columns

        adjust_qtableview_columns(
            table_view=self.table_view,
            current_dataframe=result_df,
            column_keys=self.column_keys,
            column_headers=self.column_headers,
        )

        self.status_label.setText(f"✅ DDC 분류 완료 - {len(result_df)}개 추천")
        self.app_instance.log_message(
            f"✅ Gemini DDC 분류 완료: {len(result_df)}개 결과", "INFO"
        )

    def on_search_failed(self, error_message):
        """검색 실패 처리"""
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.is_searching = False
        self.progress_bar.setValue(0)
        self.status_label.setText(f"❌ 오류: {error_message}")
        self.app_instance.log_message(
            f"❌ Gemini DDC 분류 실패: {error_message}", "ERROR"
        )
        QMessageBox.critical(self, "DDC 분류 실패", error_message)

    def on_clear_results(self):
        # 중간 결과 테이블 clear_data 사용 (통일성)
        self.inter_model.clear_data()
        if self.table_model:
            self.table_model.clear_data()
        # ❌ self.intermediate_group.setVisible(False) 제거
        self.status_label.setText("결과가 지워졌습니다.")

    def on_inter_table_context_menu(self, position):
        """중간 결과 테이블 셀 컨텍스트 메뉴"""
        index = self.inter_table.indexAt(position)
        if not index.isValid():
            return

        from qt_context_menus import show_qtableview_context_menu

        show_qtableview_context_menu(
            table_view=self.inter_table,
            row=index.row(),
            column=index.column(),
            pos=position,
            app_instance=self.app_instance,
        )

    def on_inter_table_double_click(self, index: QModelIndex):
        """중간 결과 테이블 더블클릭 시 셀 상세보기 다이얼로그 표시"""
        if not index.isValid():
            return

        from qt_context_menus import show_cell_detail_dialog

        # 컬럼명 가져오기
        column_name = (
            self.intermediate_column_headers[index.column()]
            if index.column() < len(self.intermediate_column_headers)
            else "Unknown"
        )
        cell_value = self.inter_model.data(index, Qt.DisplayRole) or ""

        # 상세보기 다이얼로그 표시
        show_cell_detail_dialog(cell_value, column_name, self.app_instance)

    @Slot(list)
    def _on_intermediate_rows(self, rows):
        """중간 결과 업데이트 (한국어/영어 검색 결과 모두 표시)"""
        # FastSearchResultModel의 add_multiple_rows 사용 (통일성)
        self.inter_model.clear_data()
        self.inter_model.add_multiple_rows(
            rows, column_keys=self.intermediate_column_keys
        )

        if self.inter_model.rowCount() > 0:
            df = pd.DataFrame(rows)
            adjust_qtableview_columns(
                table_view=self.inter_table,
                current_dataframe=df,
                column_keys=self.intermediate_column_keys,
                column_headers=self.intermediate_column_headers,
            )

    def _stop_worker_if_running(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        self.worker = None

    def _update_detail_view_from_intermediate(self, current, previous=None):
        """중간 결과 테이블의 선택된 행을 상세 정보 뷰에 표시합니다."""
        _ = previous  # unused
        if not current.isValid():
            if hasattr(self.app_instance, "main_window"):
                self.app_instance.main_window.detail_display.clear()
            return

        # 중간 결과 테이블은 proxy model을 사용하지 않으므로 직접 접근
        row_data = self.inter_model.get_row_data(current.row())
        if not row_data:
            return

        # 포맷팅 로직 적용
        from ui_constants import UI_CONSTANTS
        import re

        U = UI_CONSTANTS
        header_style = f"color: {U.ACCENT_GREEN}; font-weight: bold;"
        url_pattern = re.compile(r'(https?://[^\s<>"]+|www\.[^\s<>"]+)')

        content_lines = []
        for col in range(self.inter_model.columnCount()):
            column_name = (
                self.inter_model.headerData(col, Qt.Horizontal, Qt.DisplayRole) or ""
            )
            value_content = (
                self.inter_model.data(
                    self.inter_model.index(current.row(), col), Qt.DisplayRole
                )
                or ""
            )

            # U+2029 문자 제거
            value_content = str(value_content).replace("\u2029", "")

            # KSH/URL 형식 체크
            is_ksh_content = "▼a" in value_content and "▲" in value_content
            is_url_content = bool(url_pattern.search(str(value_content)))

            styled_header = f'▶ <span style="{header_style}">{column_name}:</span>'

            if is_ksh_content:
                # KSH 형식: 강제 줄바꿈
                value_html = str(value_content).replace("\n", "<br>")
                content_lines.append(f"{styled_header}<br>{value_html}<br>")
            elif is_url_content:
                # URL 링크 변환
                def make_link(match):
                    url = match.group(0)
                    if not url.startswith("http"):
                        url = "http://" + url
                    return f'<a href="{url}" style="color: {U.ACCENT_BLUE};">{match.group(0)}</a>'

                value_html = url_pattern.sub(make_link, str(value_content))
                content_lines.append(f"{styled_header} {value_html}<br>")
            else:
                # 일반 텍스트
                value_html = str(value_content).replace("\n", "<br>")
                content_lines.append(f"{styled_header} {value_html}<br>")

        final_html = "".join(content_lines)

        if hasattr(self.app_instance, "main_window"):
            self.app_instance.main_window.detail_display.setHtml(final_html)

    # ✅ [수정] 다른 탭으로부터 데이터를 수신하는 단일 메서드
    def receive_data(self, title=None, author=None, isbn=None, year=None, switch_priority=False, **kwargs):
        """
        AI 피드 탭 등 다른 탭에서 전송된 데이터를 수신합니다.

        Gemini 탭은 기본 파라미터는 무시하고, kwargs에서 text와 start_search_now를 추출합니다.
        """
        # kwargs에서 Gemini 전용 파라미터 추출
        text = kwargs.get('text', None)
        start_search_now = kwargs.get('start_search_now', False)

        if text and hasattr(self, "input_edit"):
            # 1. 메인 윈도우의 탭을 Gemini 탭으로 전환
            if hasattr(self.app_instance, "main_window"):
                self.app_instance.main_window.switch_to_tab_by_name("Gemini DDC 분류")

            # 2. 전송받은 텍스트를 입력창에 설정
            self.input_edit.setPlainText(text)
            self.app_instance.log_message(
                "✅ AI 피드로부터 데이터를 수신하여 입력창에 설정했습니다.", "INFO"
            )

            # -------------------
            # 3. start_search_now 플래그가 True일 때만 자동 검색 시작
            if start_search_now:
                self.app_instance.log_message(
                    "➡️ AI 피드 연동: 자동 검색을 시작합니다.", "INFO"
                )
                QTimer.singleShot(100, self.start_search)
            # -------------------

    def closeEvent(self, event):
        self._stop_worker_if_running()
        super().closeEvent(event)
