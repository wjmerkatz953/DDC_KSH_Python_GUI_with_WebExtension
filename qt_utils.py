# 파일명: qt_utils.py
# 설명: PySide6 애플리케이션 전체에서 사용될 공용 유틸리티 함수 및 클래스 모음

import pandas as pd
import sys
import re
import html
import ctypes as ct
import threading
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QLineEdit,
    QApplication,
    QStyledItemDelegate,
)
from PySide6.QtCore import QUrl, QThread, Signal, Qt
from PySide6.QtGui import QDesktopServices, QTextDocument, QPalette, QColor
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtCore import (
    QObject,
    QEvent,
    QTimer,
    Qt,
    QEvent,
)


# =================================================================
# 1. 범용 백그라운드 스레드
# =================================================================
class SearchThread(QThread):
    search_completed = Signal(object)
    search_failed = Signal(str)

    def __init__(self, search_function, search_params, app_instance):
        super().__init__()
        self.search_function = search_function
        self.search_params = search_params
        self.app_instance = app_instance

    def run(self):
        try:
            if self.app_instance and hasattr(self.app_instance, "stop_search_flag"):
                self.app_instance.stop_search_flag.clear()

            results = self.search_function(**self.search_params)

            # -------------------
            # ✅ [핵심 수정] 스레드 간 데이터 전달 안정성 확보
            import pandas as pd

            if isinstance(results, pd.DataFrame):
                # DataFrame을 안전한 '딕셔너리 리스트'로 변환 후 전달
                results_to_emit = results.to_dict("records")
            else:
                results_to_emit = results

            self.search_completed.emit(results_to_emit)
            # -------------------

        except Exception as e:
            import traceback

            tb_str = traceback.format_exc()
            if self.app_instance:
                self.app_instance.log_message(
                    f"SearchThread 오류: {e}\n{tb_str}", "ERROR"
                )
            self.search_failed.emit(f"{e}\n{tb_str}")

    def cancel_search(self):
        if self.app_instance and hasattr(self.app_instance, "stop_search_flag"):
            self.app_instance.stop_search_flag.set()


# =================================================================
# 2. 데이터 처리 및 내보내기
# =================================================================
def export_dataframe_to_excel(parent, dataframe, default_filename, app_instance=None):
    """데이터프레임을 Excel 파일로 내보냅니다."""
    if dataframe.empty:
        QMessageBox.information(parent, "알림", "내보낼 데이터가 없습니다.")
        return

    try:
        file_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Excel 파일로 저장",
            f"{default_filename}.xlsx",
            "Excel Files (*.xlsx)",
        )

        if file_path:
            dataframe.to_excel(file_path, index=False, engine="openpyxl")

            if app_instance and hasattr(app_instance, "log_message"):
                app_instance.log_message(
                    f"📊 Excel 내보내기 완료: {file_path}", "COMPLETE"
                )

            reply = QMessageBox.question(
                parent,
                "내보내기 완료",
                f"파일이 저장되었습니다.\n열어보시겠습니까?\n\n{file_path}",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    except ImportError:
        QMessageBox.warning(
            parent,
            "라이브러리 오류",
            "Excel 내보내기를 위해 openpyxl 라이브러리가 필요합니다.\n\npip install openpyxl",
        )
    except Exception as e:
        if app_instance and hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ Excel 내보내기 실패: {e}", "ERROR")
        QMessageBox.critical(
            parent, "오류", f"Excel 내보내기 중 오류가 발생했습니다:\n{e}"
        )


def _generate_html_from_model(model, title, column_headers):
    """데이터 모델을 기반으로 인쇄용 HTML 테이블을 생성합니다."""
    html_lines = [
        "<html><head><style>",
        "table { border-collapse: collapse; width: 100%; font-family: sans-serif; }",
        "th, td { border: 1px solid black; padding: 8px; text-align: left; }",
        "th { background-color: #f2f2f2; font-weight: bold; }",
        "</style></head><body>",
        f"<h2>{title} - 검색 결과</h2>",
        "<table>",
    ]

    # 헤더 행
    html_lines.append("<tr>")
    for header in column_headers:
        html_lines.append(f"<th>{header}</th>")
    html_lines.append("</tr>")

    # 데이터 행들
    for row in range(model.rowCount()):
        html_lines.append("<tr>")
        for col in range(len(column_headers)):
            index = model.index(row, col)
            cell_text = model.data(index, Qt.DisplayRole) or ""
            # 간단한 HTML 이스케이프
            cell_text = (
                str(cell_text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            html_lines.append(f"<td>{cell_text}</td>")
        html_lines.append("</tr>")

    html_lines.extend(["</table>", "</body></html>"])
    return "\n".join(html_lines)


def print_table_data(parent, model, title, column_headers, app_instance=None):
    """테이블 모델의 데이터를 인쇄합니다."""
    if model.rowCount() == 0:
        QMessageBox.information(parent, "알림", "인쇄할 데이터가 없습니다.")
        return
    try:
        printer = QPrinter()
        dialog = QPrintDialog(printer, parent)

        if dialog.exec() == QPrintDialog.Accepted:
            html_content = _generate_html_from_model(model, title, column_headers)
            document = QTextDocument()
            document.setHtml(html_content)
            document.print_(printer)  # print는 Python 예약어이므로 print_ 사용

            if app_instance and hasattr(app_instance, "log_message"):
                app_instance.log_message("🖨️ 테이블 인쇄 완료", "INFO")
    except Exception as e:
        if app_instance and hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 인쇄 실패: {e}", "ERROR")
        QMessageBox.critical(parent, "오류", f"인쇄 중 오류가 발생했습니다:\n{e}")


def show_dataframe_statistics(parent, dataframe, title, app_instance=None):
    """데이터프레임의 통계 정보를 다이얼로그로 표시합니다."""
    if dataframe.empty:
        QMessageBox.information(parent, "알림", "분석할 데이터가 없습니다.")
        return
    try:
        total_rows = len(dataframe)
        total_cols = len(dataframe.columns)

        stats_info = [
            f"📊 {title} 데이터 통계",
            f"=" * 50,
            f"총 행 수: {total_rows:,}",
            f"총 열 수: {total_cols}",
            f"",
            "📈 컬럼별 상위 빈도 데이터 (상위 3개):",
            f"-" * 30,
        ]

        for col_name in dataframe.columns:
            if any(keyword in col_name.lower() for keyword in ["link", "url", "상세"]):
                continue

            value_counts = dataframe[col_name].value_counts().head(3)
            if not value_counts.empty:
                stats_info.append(f"\n[{col_name}]")
                for value, count in value_counts.items():
                    if str(value).strip() and str(value) != "nan":
                        stats_info.append(f"  • {str(value)[:40]}: {count}회")

        dialog = QDialog(parent)
        dialog.setWindowTitle(f"{title} - 데이터 통계")
        dialog.setMinimumSize(600, 500)

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText("\n".join(stats_info))
        layout.addWidget(text_edit)

        close_button = QPushButton("닫기")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    except Exception as e:
        if app_instance and hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 통계 분석 실패: {e}", "ERROR")
        QMessageBox.critical(parent, "오류", f"통계 분석 중 오류가 발생했습니다:\n{e}")


# =================================================================
# 3. 외부 연동
# =================================================================
def open_url_safely(url, app_instance=None):
    """
    URL을 메인 스레드 이벤트 루프에 전달하여 안전하게 엽니다.
    (QDesktopServices.openUrl이 메인 스레드에서 호출되도록 강제)
    """
    try:
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url

        # -------------------
        # ✅ [핵심 수정] 스레드를 사용하지 않고, QTimer.singleShot(0, ...)을 사용하여
        # Qt의 이벤트 루프가 다음 사이클에 메인 스레드에서 작업을 실행하도록 만듭니다.

        final_url = url

        def _open_on_main_thread():
            try:
                QDesktopServices.openUrl(QUrl(final_url))
                if app_instance and hasattr(app_instance, "log_message"):
                    app_instance.log_message(f"🌐 링크 열림: {final_url}", "INFO")
            except Exception as e:
                if app_instance and hasattr(app_instance, "log_message"):
                    app_instance.log_message(f"❌ 브라우저 열기 실패: {e}", "ERROR")

        # 0ms 지연으로 메인 이벤트 루프의 다음 처리 주기에 실행되도록 예약
        QTimer.singleShot(0, _open_on_main_thread)
        # -------------------

    except Exception as e:
        if app_instance and hasattr(app_instance, "log_message"):
            app_instance.log_message(f"❌ 링크 열기 실패: {e}", "ERROR")


# ✅ [추가] 모든 창에 다크 타이틀바를 적용하는 헬퍼 함수
def apply_dark_title_bar(window):
    """주어진 PySide6 윈도우에 다크 테마 타이틀바를 적용 (Windows OS 전용)"""
    if sys.platform != "win32":
        return

    # 윈도우 핸들을 가져옵니다.
    window.winId()
    hwnd = int(window.winId())

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    try:
        ct.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ct.byref(ct.c_int(2)), 4
        )
    except Exception:
        ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ct.byref(ct.c_int(1)), 4)


def enable_modal_close_on_outside_click(modal_widget, close_callback=None):
    """
    Qt.Popup 플래그만 사용하여 외부 클릭 시 닫기 기능을 활성화합니다.
    (장점: 가장 간단하고 안정적 / 단점: 타이틀바가 사라짐)

    Note: QDialog의 경우 exec()이 show()를 포함하므로,
    setWindowFlags만 설정하고 show()는 호출하지 않습니다.
    """
    from PySide6.QtWidgets import QDialog

    modal_widget.setWindowFlags(Qt.Popup)

    # QDialog가 아닌 경우에만 show() 호출 (QDialog는 exec()이 show()를 포함)
    if not isinstance(modal_widget, QDialog):
        modal_widget.show()

    # 콜백이 있는 경우, 창이 닫힐 때(finished) 신호에 연결
    if close_callback and hasattr(modal_widget, "finished"):
        modal_widget.finished.connect(close_callback)


class SelectAllLineEdit(QLineEdit):
    """포커스를 받으면 자동으로 전체 텍스트를 선택하는 QLineEdit"""

    def focusInEvent(self, event):
        # 먼저 부모 클래스의 이벤트를 호출하여 기본 동작을 보장합니다.
        super().focusInEvent(event)

        # 타이머를 사용해 이벤트 처리가 끝난 후 선택을 실행 (안정성 향상)
        def _select_all_if_needed():
            # 사용자가 이미 일부 텍스트를 선택한 경우는 제외하여
            # 의도적인 선택을 방해하지 않도록 합니다.
            if self.text() and not self.hasSelectedText():
                self.selectAll()

        QTimer.singleShot(0, _select_all_if_needed)


class KshHyperlinkDelegate(QStyledItemDelegate):
    """
    KSH 탭 전용 하이퍼링크 델리게이트.
    보이는 컬럼과 숨겨진 URL 컬럼을 매핑하여 링크를 엽니다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # 보이는 컬럼 이름 -> 숨겨진 URL 컬럼 이름 매핑
        self.link_column_map = {
            "전체 목록 검색 결과": "_url_data",
            "동의어/유사어(UF)": "_url_uf",
            "상위어": "_url_bt",
            "하위어": "_url_nt",
            "관련어": "_url_rt",
            "외국어": "_url_foreign",
        }

    def paint(self, painter, option, index):
        # 현재 컬럼이 링크를 가질 수 있는 컬럼인지 확인
        column_headers = index.model().sourceModel().column_headers
        current_col_name = column_headers[index.column()]
        from ui_constants import UI_CONSTANTS as U_CURRENT

        if current_col_name in self.link_column_map:
            # 숨겨진 URL 컬럼에서 실제 URL 데이터가 있는지 확인
            hidden_col_name = self.link_column_map[current_col_name]
            hidden_col_index = column_headers.index(hidden_col_name)
            url_index = index.siblingAtColumn(hidden_col_index)
            url_data = index.model().data(url_index)

            if url_data:  # URL이 존재할 때만 파란색으로 표시
                option.palette.setColor(QPalette.Text, QColor(U_CURRENT.SOURCE_UPENN),)

        super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if (
            event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            column_headers = model.sourceModel().column_headers
            current_col_name = column_headers[index.column()]

            if current_col_name in self.link_column_map:
                hidden_col_name = self.link_column_map[current_col_name]
                hidden_col_index = column_headers.index(hidden_col_name)

                url_index = index.siblingAtColumn(hidden_col_index)
                url_str = model.data(url_index)

                if url_str:
                    open_url_safely(url_str)  # 기존에 만든 공용 함수 사용
                    return True
        return False


def linkify_text(plain_text, preserve_html=False):
    """텍스트 내의 URL을 찾아 HTML <a> 태그로 변환합니다.

    Args:
        plain_text: 변환할 텍스트
        preserve_html: True이면 기존 HTML 태그를 보존, False이면 이스케이프
    """
    if not plain_text:
        return ""

    # preserve_html=True인 경우 기존 HTML 태그를 보존
    if preserve_html:
        # URL을 찾는 정규식
        url_pattern = re.compile(r'(https?://[^\s<>"]+|www\.[^\s<>"]+)')
        # 찾은 URL을 <a> 태그로 교체
        html_text = url_pattern.sub(r'<a href="\1">\1</a>', plain_text)
    else:
        # 1. 기존 HTML 특수 문자를 이스케이프 처리
        escaped_text = html.escape(plain_text)
        # 2. URL을 찾는 정규식
        url_pattern = re.compile(r'(https?://[^\s<>"]+|www\.[^\s<>"]+)')
        # 3. 찾은 URL을 <a> 태그로 교체
        html_text = url_pattern.sub(r'<a href="\1">\1</a>', escaped_text)

    # 4. 줄바꿈을 <br> 태그로 변환
    return html_text.replace("\n", "<br>")


# [기존 UrlLinkDelegate를 대신할 범용 Delegate 추가]
class UrlLinkDelegate(QStyledItemDelegate):
    """
    셀 내용이 URL일 경우 (색상 변경 없이) 싱글 왼쪽 클릭 시 해당 URL을 엽니다.
    """

    def __init__(self, parent=None, app_instance=None):
        # -------------------
        super().__init__(parent)
        self.app_instance = app_instance
        # -------------------
        # UI 상수에서 ACCENT_BLUE 색상 가져오기
        from ui_constants import UI_CONSTANTS

        # ✅ [수정] link_color는 더 이상 paint에서 사용되지 않지만, 제거하지 않고 유지합니다.
        self.link_color = QColor(UI_CONSTANTS.ACCENT_BLUE)

    def paint(self, painter, option, index):
        data = str(index.data(Qt.DisplayRole) or "").strip()

        # URL로 인식되면 파란색 링크 스타일 적용
        if self.is_url_text(data):
            # 텍스트 색상을 링크 색상으로 강제 변경
            option.palette.setColor(QPalette.Text, self.link_color)

            # 밑줄을 그어서 링크임을 표시할 수도 있습니다.
            # 하지만 Qt 스타일시트가 이를 잘 처리하므로 여기선 생략합니다.

        super().paint(painter, option, index)
        # 중요: 텍스트 색상을 원래 색상으로 되돌릴 필요는 없습니다.
        # Qt가 다음 항목을 그릴 때 기본 팔레트를 다시 사용합니다.

    def _extract_pure_url(self, data, column_name):
        """데이터와 컬럼 이름을 기반으로 URL을 추출합니다."""
        # 1. KSH 마크업/HTML 태그 제거
        clean_data = re.sub(r"▼[a-zA-Z0-9].*?▲", "", data)
        clean_data = re.sub(r"<[^>]+>", "", clean_data).strip().rstrip(".")

        # 2. URL 패턴 추출 시도
        # -------------------
        # ✅ [핵심 수정] 명시적인 링크 컬럼일지라도, URL 패턴을 찾아서 순수한 URL만 추출
        # 이는 링크 외의 추가 텍스트가 셀에 포함되어 있을 경우를 대비합니다.
        match = re.search(r'(https?://[^\s<>"]+|www\.[^\s<>"]+)', clean_data)

        if "링크" in column_name or "URL" in column_name:
            # a) 명시적인 링크 컬럼
            if match:
                return match.group(0).strip()
            return ""  # URL이 없으면 빈 값 반환
        else:
            # b) 일반 컬럼: URL 패턴 추출 시도
            if match:
                return match.group(0).strip()  # 발견된 URL만 반환

            # c) 일반 컬럼인데 URL이 없으면 빈 값 반환
            return ""

    def editorEvent(self, event, model, option, index):
        if (
            event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            data = str(index.data(Qt.DisplayRole) or "").strip()

            # 컬럼 이름 가져오기 (추출 로직에 사용)
            column_name = (
                model.headerData(index.column(), Qt.Horizontal, Qt.DisplayRole) or ""
            )

            # 1. 순수한 URL을 추출합니다.
            pure_url = self._extract_pure_url(data, column_name)

            if self.is_url_text(pure_url):
                # 2. 싱글 클릭 시 URL 열기
                open_url_safely(pure_url, self.app_instance)
                return True
        return False

    def is_url_text(self, text):
        """URL 패턴을 확인하는 로직 (순수한 텍스트에 대해 검사)"""
        if not text or len(text) < 4:
            return False

        text_lower = text.lower()

        url_patterns = [
            r"^https?://",
            r"^www\.",
            r"\.com\b",
            r"\.org\b",
            r"\.net\b",
            r"\.edu\b",
            r"\.gov\b",
            r"\.co\.kr\b",
            r"\.kr\b",
            r"ncid/[A-Za-z0-9]+$",
        ]

        # -------------------
        # ✅ [핵심 수정] URL 시작 패턴이 있으면 바로 True 반환 (가장 확실한 방법)
        if text_lower.startswith(("http://", "https://", "www.", "ftp://")):
            return True
        # -------------------

        # 나머지 패턴은 보조적으로 사용
        return any(re.search(pattern, text_lower) for pattern in url_patterns)


# -------------------
