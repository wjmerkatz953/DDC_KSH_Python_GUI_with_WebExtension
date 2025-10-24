# 파일명: run_template.py
# 설명: PySide6 표준 탭 템플릿의 단독 실행 버전.
#       - 가상(Mock) 백엔드 함수를 포함하여 다른 파일 없이 즉시 테스트 가능합니다.

import sys
import time
import pandas as pd
import threading
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QCheckBox,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QFrame,
    QMessageBox,
    QTreeWidgetItemIterator,
)
from PySide6.QtCore import QThread, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices

# -----------------------------------------------------------------------------
# 🚀 실행을 위한 가상(Mock) 함수들
# - 실제 프로젝트에서는 이 부분 대신 기존 모듈을 import 합니다.
# -----------------------------------------------------------------------------


def search_lc_orchestrated(title_query, author_query, isbn_query, app_instance):
    """실제 search_lc_orchestrated를 흉내 내는 가상 함수"""
    app_instance.log_message(
        f"가상 검색 시작: title='{title_query}', author='{author_query}', isbn='{isbn_query}'"
    )
    time.sleep(2)  # 네트워크 딜레이 흉내

    # 검색어에 따라 다른 가상 데이터 반환
    if "python" in title_query.lower():
        return [
            {
                "제목": "Automate the Boring Stuff with Python",
                "저자": "Al Sweigart",
                "출판 연도": "2019",
                "ISBN": "978-1593279929",
                "082 필드": "005.133",
                "출처": "LC_Mock",
                "상세 링크": "https://www.amazon.com/dp/1593279922",
            },
            {
                "제목": "Python for Data Analysis",
                "저자": "Wes McKinney",
                "출판 연度": "2017",
                "ISBN": "978-1491957660",
                "082 필드": "005.74",
                "출처": "LC_Mock",
                "상세 링크": "https://www.amazon.com/dp/1491957660",
            },
        ]
    elif isbn_query:
        return [
            {
                "제목": "The Pragmatic Programmer",
                "저자": "David Thomas",
                "출판 연도": "2019",
                "ISBN": isbn_query,
                "082 필드": "005.1",
                "출처": "LC_Mock",
                "상세 링크": "https://www.amazon.com/dp/0135957052",
            },
        ]
    else:
        # 기본 가상 데이터
        return [
            {
                "제목": "Designing Data-Intensive Applications",
                "저자": "Martin Kleppmann",
                "출판 연도": "2017",
                "ISBN": "978-1449373320",
                "082 필드": "005.74",
                "출처": "LC_Mock",
                "상세 링크": "https://www.amazon.com/dp/1449373321",
            },
            {
                "제목": "Clean Code: A Handbook of Agile Software Craftsmanship",
                "저자": "Robert C. Martin",
                "출판 연도": "2008",
                "ISBN": "978-0132350884",
                "082 필드": "005.1",
                "출처": "LC_Mock",
                "상세 링크": "https://www.amazon.com/dp/0132350884",
            },
            {
                "제목": "The Mythical Man-Month: Essays on Software Engineering",
                "저자": "Frederick P. Brooks Jr.",
                "출판 연도": "1995",
                "ISBN": "978-0201835953",
                "082 필드": "005.1",
                "출처": "LC_Mock",
                "상세 링크": "https://www.amazon.com/dp/0201835959",
            },
        ]


def show_in_html_viewer(app_instance, dataframe, **kwargs):
    """가상 HTML 뷰어 함수"""
    QMessageBox.information(
        None,
        "HTML Viewer",
        f"HTML 뷰어가 호출되었습니다.\n데이터 {len(dataframe)}건을 표시합니다.",
    )
    app_instance.log_message("가상 HTML 뷰어 호출 완료", "COMPLETE")


def show_in_dropdown_html_viewer(app_instance, dataframe, **kwargs):
    """가상 상세 뷰어 함수"""
    QMessageBox.information(
        None,
        "상세 뷰어",
        f"상세 뷰어가 호출되었습니다.\n데이터 {len(dataframe)}건을 표시합니다.",
    )
    app_instance.log_message("가상 상세 뷰어 호출 완료", "COMPLETE")


# -----------------------------------------------------------------------------
# 템플릿 코드 시작
# -----------------------------------------------------------------------------


class SearchThread(QThread):
    """검색을 백그라운드에서 수행하는 범용 스레드"""

    results_ready = Signal(list)
    error_occurred = Signal(str)
    progress_update = Signal(int)

    def __init__(self, search_function, app_instance, **kwargs):
        super().__init__()
        self.search_function = search_function
        self.app_instance = app_instance
        self.kwargs = kwargs
        self.is_cancelled = False

    def run(self):
        try:
            self.kwargs["app_instance"] = self.app_instance
            results = self.search_function(**self.kwargs)
            if not self.is_cancelled:
                self.results_ready.emit(results)
        except Exception as e:
            if not self.is_cancelled:
                self.error_occurred.emit(f"검색 중 오류 발생: {e}")

    def cancel(self):
        self.is_cancelled = True
        if hasattr(self.app_instance, "stop_search_flag"):
            self.app_instance.stop_search_flag.set()


class QtStandardTab(QWidget):
    """PySide6 기반 표준 탭 템플릿"""

    def __init__(self, app_instance, tab_name="LC"):
        super().__init__()
        self.app_instance = app_instance
        self.tab_name = tab_name
        self.search_thread = None
        self.is_searching = False
        self.find_results = []
        self.current_find_index = -1
        self.last_find_term = ""
        self.results_df = pd.DataFrame()
        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.create_input_section(layout)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)
        self.create_results_section(layout)
        self.create_find_section(layout)

    def create_input_section(self, parent_layout):
        input_group = QGroupBox("검색 조건")
        input_layout = QGridLayout()
        self.title_check = QCheckBox("제목:")
        self.title_check.setChecked(True)
        self.title_entry = QLineEdit()
        self.title_entry.setPlaceholderText("e.g., python")
        input_layout.addWidget(self.title_check, 0, 0)
        input_layout.addWidget(self.title_entry, 0, 1)
        self.author_check = QCheckBox("저자:")
        self.author_check.setChecked(True)
        self.author_entry = QLineEdit()
        input_layout.addWidget(self.author_check, 0, 2)
        input_layout.addWidget(self.author_entry, 0, 3)
        self.isbn_check = QCheckBox("ISBN:")
        self.isbn_check.setChecked(True)
        self.isbn_entry = QLineEdit()
        input_layout.addWidget(self.isbn_check, 0, 4)
        input_layout.addWidget(self.isbn_entry, 0, 5)
        self.search_button = QPushButton(f"{self.tab_name} 검색")
        input_layout.addWidget(self.search_button, 0, 6)
        self.cancel_button = QPushButton("검색 취소")
        self.cancel_button.setEnabled(False)
        input_layout.addWidget(self.cancel_button, 0, 7)
        input_layout.setColumnStretch(1, 1)
        input_layout.setColumnStretch(3, 1)
        input_layout.setColumnStretch(5, 1)
        input_group.setLayout(input_layout)
        parent_layout.addWidget(input_group)

    def create_results_section(self, parent_layout):
        results_group = QGroupBox("검색 결과")
        results_layout = QVBoxLayout()
        self.tree_widget = QTreeWidget()
        self.column_headers = [
            "제목",
            "저자",
            "출판 연도",
            "ISBN",
            "082 필드",
            "출처",
            "상세 링크",
        ]
        self.tree_widget.setHeaderLabels(self.column_headers)
        results_layout.addWidget(self.tree_widget)
        results_group.setLayout(results_layout)
        parent_layout.addWidget(results_group, 1)

    def create_find_section(self, parent_layout):
        find_group = QGroupBox("결과 내 찾기 및 도구")
        find_layout = QHBoxLayout()
        self.find_entry = QLineEdit()
        self.find_entry.setPlaceholderText("결과 내에서 찾을 단어 입력...")
        find_layout.addWidget(self.find_entry, 1)
        self.find_prev_button = QPushButton("▲ 이전")
        find_layout.addWidget(self.find_prev_button)
        self.find_next_button = QPushButton("▼ 다음")
        find_layout.addWidget(self.find_next_button)
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        find_layout.addWidget(separator)
        self.html_viewer_button = QPushButton("HTML 뷰어")
        find_layout.addWidget(self.html_viewer_button)
        self.pandas_viewer_button = QPushButton("상세 뷰어")
        find_layout.addWidget(self.pandas_viewer_button)
        find_group.setLayout(find_layout)
        parent_layout.addWidget(find_group)

    def setup_connections(self):
        self.search_button.clicked.connect(self.start_search)
        self.cancel_button.clicked.connect(self.cancel_search)
        self.title_entry.returnPressed.connect(self.start_search)
        self.author_entry.returnPressed.connect(self.start_search)
        self.isbn_entry.returnPressed.connect(self.start_search)
        self.find_entry.returnPressed.connect(self.find_next)
        self.find_prev_button.clicked.connect(self.find_prev)
        self.find_next_button.clicked.connect(self.find_next)
        self.html_viewer_button.clicked.connect(self.open_html_viewer)
        self.pandas_viewer_button.clicked.connect(self.open_pandas_viewer)
        self.tree_widget.itemDoubleClicked.connect(self.on_item_double_clicked)

    def start_search(self):
        if self.is_searching:
            return
        search_params = {
            "title_query": (
                self.title_entry.text().strip() if self.title_check.isChecked() else ""
            ),
            "author_query": (
                self.author_entry.text().strip()
                if self.author_check.isChecked()
                else ""
            ),
            "isbn_query": (
                self.isbn_entry.text().strip() if self.isbn_check.isChecked() else ""
            ),
        }
        if not any(search_params.values()):
            QMessageBox.warning(self, "입력 오류", "검색어를 하나 이상 입력해주세요.")
            return
        self.is_searching = True
        self.search_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.tree_widget.clear()
        self.results_df = pd.DataFrame()
        self.search_thread = SearchThread(
            search_function=search_lc_orchestrated,
            app_instance=self.app_instance,
            **search_params,
        )
        self.search_thread.results_ready.connect(self.on_search_complete)
        self.search_thread.error_occurred.connect(self.on_search_error)
        self.search_thread.start()

    def cancel_search(self):
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.cancel()

    def on_search_complete(self, results):
        self.progress_bar.setVisible(False)
        self.is_searching = False
        self.search_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self.search_thread and self.search_thread.is_cancelled:
            self.app_instance.log_message(
                f"{self.tab_name} 검색이 사용자에 의해 취소되었습니다.", "WARNING"
            )
            return
        self.app_instance.log_message(
            f"{self.tab_name} 검색 완료. {len(results)}건 발견.", "COMPLETE"
        )
        if results:
            self.results_df = pd.DataFrame(results)
            self.populate_tree_widget()
        else:
            self.results_df = pd.DataFrame()

    def on_search_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.is_searching = False
        self.search_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.app_instance.log_message(error_msg, "ERROR")
        QMessageBox.critical(self, "검색 오류", error_msg)

    def populate_tree_widget(self):
        self.tree_widget.clear()
        if self.results_df.empty:
            return
        for _, row in self.results_df.iterrows():
            values = [str(row.get(col, "")) for col in self.column_headers]
            item = QTreeWidgetItem(values)
            self.tree_widget.addTopLevelItem(item)
        if self.tree_widget.topLevelItemCount() > 0:
            self.tree_widget.scrollToItem(self.tree_widget.topLevelItem(0))

    def on_item_double_clicked(self, item, column):
        try:
            link_column_index = self.column_headers.index("상세 링크")
            if column == link_column_index:
                url = item.text(column)
                if url and url.startswith("http"):
                    QDesktopServices.openUrl(QUrl(url))
        except ValueError:
            pass

    def find_next(self):
        self._find_in_tree(direction=1)

    def find_prev(self):
        self._find_in_tree(direction=-1)

    def _find_in_tree(self, direction):
        search_term = self.find_entry.text().strip().lower()
        if not search_term:
            return
        if search_term != self.last_find_term:
            self.last_find_term = search_term
            self.find_results = []
            iterator = QTreeWidgetItemIterator(self.tree_widget)
            while iterator.value():
                item = iterator.value()
                for i in range(item.columnCount()):
                    if search_term in item.text(i).lower():
                        self.find_results.append(item)
                        break
                iterator += 1
            self.current_find_index = -1
            if not self.find_results:
                self.app_instance.log_message(
                    f"'{search_term}'을(를) 결과에서 찾을 수 없습니다.", "WARNING"
                )
                return
        if not self.find_results:
            return
        if self.current_find_index != -1:
            self.find_results[self.current_find_index].setSelected(False)
        num_results = len(self.find_results)
        self.current_find_index = (
            self.current_find_index + direction + num_results
        ) % num_results
        new_item = self.find_results[self.current_find_index]
        self.tree_widget.scrollToItem(
            new_item, QAbstractItemView.ScrollHint.PositionAtCenter
        )
        self.tree_widget.setCurrentItem(new_item)

    def open_html_viewer(self):
        if self.results_df.empty:
            QMessageBox.information(self, "정보", "표시할 데이터가 없습니다.")
            return
        show_in_html_viewer(
            app_instance=self.app_instance,
            dataframe=self.results_df,
            title=f"{self.tab_name} 검색 결과",
            columns_to_display=self.column_headers,
            display_names=self.column_headers,
            link_column_name="상세 링크",
        )

    def open_pandas_viewer(self):
        if self.results_df.empty:
            QMessageBox.information(self, "정보", "표시할 데이터가 없습니다.")
            return
        show_in_dropdown_html_viewer(
            app_instance=self.app_instance,
            dataframe=self.results_df,
            title=f"{self.tab_name} 검색 결과 - 상세 분석",
            columns_to_display=self.column_headers,
            display_names=self.column_headers,
            link_column_name="상세 링크",
        )


# -----------------------------------------------------------------------------
# 🚀 스크립트 실행을 위한 메인 코드
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # main_app.py의 IntegratedSearchApp을 모방한 Mock 클래스
    class MockAppInstance:
        def __init__(self):
            self.stop_search_flag = threading.Event()

        def log_message(self, message, level="INFO"):
            # 간단한 콘솔 로그
            print(f"[{level}] {message.strip()}")

    app = QApplication(sys.argv)
    window = QMainWindow()
    mock_app = MockAppInstance()

    # 템플릿 위젯을 메인 윈도우의 중앙 위젯으로 설정
    main_widget = QtStandardTab(mock_app, tab_name="LC_Test")
    window.setCentralWidget(main_widget)
    window.setWindowTitle("PySide6 표준 탭 템플릿 실행 테스트")
    window.resize(1200, 800)
    window.show()

    sys.exit(app.exec())
