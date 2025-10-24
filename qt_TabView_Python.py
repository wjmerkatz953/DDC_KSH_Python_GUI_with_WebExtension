# -*- coding: utf-8 -*-
# 파일명: qt_TabView_Python.py
# 버전: v1.0.0
# 설명: Qt 파이썬 코드 실행 탭
# 생성일: 2025-10-02
#
# 변경 이력:
# v1.0.0 (2025-10-02)
# - CustomTkinter Tab_Python.py를 Qt로 변환
# - 파이썬 코드 편집기 및 실행 기능
# - 결과 출력 콘솔

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QFrame,
    QGroupBox,
    QSplitter,  # 👈 [추가] QSplitter를 임포트합니다.
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor
from ui_constants import UI_CONSTANTS as U
import io
import contextlib
import sys

DEFAULT_PYTHON_CODE = """# -*- coding: utf-8 -*-
# 이 곳에 파이썬 코드를 작성하고 '코드 실행' 버튼을 클릭하세요.
# print() 함수를 사용하여 결과를 출력할 수 있습니다.

def greet(name):
    return f"안녕하세요, {name}님!"

if __name__ == "__main__":
    message = greet("사용자")
    print(message)
    print("코드 실행이 완료되었습니다.")
"""


class PythonExecutionThread(QThread):
    """파이썬 코드를 실행하는 스레드"""

    output_ready = Signal(str, str)  # (output_text, status_level)

    def __init__(self, code, app_instance):
        super().__init__()
        self.code = code
        self.app_instance = app_instance

    def run(self):
        """백그라운드에서 파이썬 코드 실행"""
        old_stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(old_stdout):
                exec_globals = {
                    "app_instance": self.app_instance,
                    "__builtins__": __builtins__,
                    "__name__": "__main__",
                }
                exec(self.code, exec_globals)

            output = old_stdout.getvalue()
            self.output_ready.emit(output, "COMPLETE")

        except Exception as e:
            output = old_stdout.getvalue()
            error_message = f"코드 실행 중 오류 발생:\n{output}\n{e}"
            self.output_ready.emit(error_message, "ERROR")


class QtPythonTab(QWidget):
    """Qt 파이썬 코드 실행 탭"""

    def __init__(self, config, app_instance):
        super().__init__()
        self.config = config
        self.app_instance = app_instance
        self.execution_thread = None
        self.setup_ui()

    def setup_ui(self):
        """UI 구성"""
        # 메인 레이아웃: 탭 전체의 기본이 되는 수직 레이아웃입니다.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 3, 6, 3)
        main_layout.setSpacing(10)

        # [핵심] 코드 편집기와 결과 콘솔을 담을 수직 QSplitter를 생성합니다.
        splitter = QSplitter(Qt.Vertical)

        # -------------------
        # [변경 1] === 코드 입력 영역을 QGroupBox로 변경 ===
        # 기존 QFrame 대신 QGroupBox를 사용하여 MARC Editor와 동일한 테두리 스타일을 적용합니다.
        editor_group = QGroupBox()
        editor_layout = QVBoxLayout(editor_group)
        # 내부 여백을 설정하여 에디터가 그룹박스에 꽉 차도록 합니다.
        editor_layout.setContentsMargins(6, 6, 6, 6)

        # [변경 2] 안내용 QLabel 제거
        # code_label = QLabel("▼ 여기에 파이썬 코드를 작성하세요:")
        # code_layout.addWidget(code_label)

        # 코드 에디터
        self.code_editor = QTextEdit()
        self.code_editor.setPlainText(DEFAULT_PYTHON_CODE)
        code_font = QFont(U.FONT_FAMILY, U.FONT_SIZE_MEDIUM)
        self.code_editor.setFont(code_font)

        # [변경 3] 개별 스타일시트 제거
        # 전역 스타일(qt_styles.py)을 상속받아 다른 위젯과 통일성을 갖도록 합니다.
        # self.code_editor.setStyleSheet(...)

        editor_layout.addWidget(self.code_editor, 1)
        # -------------------

        # -------------------
        # [변경 4] === 결과 출력 영역을 QGroupBox로 변경 ===
        console_group = QGroupBox()
        console_layout = QVBoxLayout(console_group)
        console_layout.setContentsMargins(6, 6, 6, 6)

        # [변경 5] 안내용 QLabel 제거
        # output_label = QLabel("▼ 코드 실행 결과:")
        # console_layout.addWidget(output_label)

        # 결과 콘솔
        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        output_font = QFont(U.FONT_FAMILY, U.FONT_SIZE_MEDIUM)
        self.output_console.setFont(output_font)

        # [변경 6] 개별 스타일시트 제거
        # self.output_console.setStyleSheet(...)

        console_layout.addWidget(self.output_console, 1)
        # -------------------

        # [핵심] QSplitter에 편집기 그룹과 콘솔 그룹을 추가합니다.
        splitter.addWidget(editor_group)
        splitter.addWidget(console_group)

        # [핵심] 메인 레이아웃에 스플리터를 추가하여 공간을 최대한 차지하도록 합니다 (stretch=1).
        main_layout.addWidget(splitter, 1)

        # -------------------
        # [변경 7] === 버튼 영역을 스플리터 밖, 탭의 최하단으로 이동 ===
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 코드 실행 버튼
        self.run_button = QPushButton("코드 실행")
        self.run_button.clicked.connect(self.run_code)
        self.run_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {U.ACCENT_BLUE};
                color: {U.TEXT_BUTTON};
                font-weight: bold;
                padding: 8px 16px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {U.ACCENT_BLUE_HOVER};
            }}
            QPushButton:disabled {{
                background-color: #555555;
                color: #888888;
            }}
            """
        )
        button_layout.addWidget(self.run_button)

        # 코드 지우기 버튼
        self.clear_code_button = QPushButton("코드 지우기")
        self.clear_code_button.clicked.connect(self.clear_code)
        self.clear_code_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {U.BACKGROUND_TERTIARY};
                color: {U.TEXT_SUBDUED};
                font-weight: bold;
                padding: 8px 16px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {U.SCROLLBAR_ACTIVE_THUMB};
            }}
            """
        )
        button_layout.addWidget(self.clear_code_button)

        # 결과 지우기 버튼
        self.clear_output_button = QPushButton("결과 지우기")
        self.clear_output_button.clicked.connect(self.clear_output)
        self.clear_output_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {U.BACKGROUND_TERTIARY};
                color: {U.TEXT_SUBDUED};
                font-weight: bold;
                padding: 8px 16px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {U.SCROLLBAR_ACTIVE_THUMB};
            }}
            """
        )
        button_layout.addWidget(self.clear_output_button)

        button_layout.addStretch()
        # 버튼 레이아웃을 메인 레이아웃의 최하단에 추가합니다.
        main_layout.addLayout(button_layout)
        # -------------------

        # 스플리터의 초기 크기를 설정합니다 (상단:하단 비율).
        splitter.setSizes([600, 400])

    def run_code(self):
        """코드 실행"""
        code = self.code_editor.toPlainText().strip()

        if not code:
            self.app_instance.show_messagebox(
                "입력 오류", "실행할 파이썬 코드를 입력해주세요.", "warning"
            )
            self.app_instance.log_message(
                "경고: 실행할 파이썬 코드가 비어있습니다.", level="WARNING"
            )
            return

        # 버튼 비활성화
        self.run_button.setEnabled(False)
        self.clear_code_button.setEnabled(False)
        self.clear_output_button.setEnabled(False)

        # 기존 결과 지우기
        self.output_console.clear()

        # 상태 업데이트
        self.app_instance.log_message("정보: 파이썬 코드 실행 시작...")

        # 스레드 실행
        self.execution_thread = PythonExecutionThread(code, self.app_instance)
        self.execution_thread.output_ready.connect(self.on_execution_complete)
        self.execution_thread.finished.connect(self.on_thread_finished)
        self.execution_thread.start()

    def on_execution_complete(self, output_text, status_level):
        """실행 완료 시 결과 표시"""
        self.output_console.setPlainText(output_text)
        # 스크롤을 끝으로
        cursor = self.output_console.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.output_console.setTextCursor(cursor)

        if status_level == "ERROR":
            self.app_instance.log_message("오류: 파이썬 코드 실행 오류", level="ERROR")
        elif status_level == "COMPLETE":
            self.app_instance.log_message(
                "정보: 파이썬 코드 실행 완료.", level="COMPLETE"
            )

    def on_thread_finished(self):
        """스레드 종료 시 버튼 다시 활성화"""
        self.run_button.setEnabled(True)
        self.clear_code_button.setEnabled(True)
        self.clear_output_button.setEnabled(True)

    def clear_code(self):
        """코드 에디터 내용 지우기"""
        self.code_editor.clear()
        self.app_instance.log_message("정보: 파이썬 코드 편집기 내용이 지워졌습니다.")

    def clear_output(self):
        """결과 콘솔 내용 지우기"""
        self.output_console.clear()
        self.app_instance.log_message("정보: 파이썬 코드 실행 결과가 지워졌습니다.")

    def cleanup_all_threads(self):
        """스레드 정리"""
        if self.execution_thread and self.execution_thread.isRunning():
            self.execution_thread.wait(2000)
            if self.execution_thread.isRunning():
                self.execution_thread.terminate()
                self.execution_thread.wait()
