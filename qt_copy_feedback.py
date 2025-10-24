# -*- coding: utf-8 -*-
# 파일명: qt_copy_feedback.py
# 설명: PySide6 기반 복사 피드백 시스템 - 완전 개선 버전
# 버전: 2.0.0
# 생성일: 2025-09-24

from PySide6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QFont, QColor, QPalette
from ui_constants import U
from PySide6.QtWidgets import (
    QWidget,
    QLineEdit,
    QTextEdit,
    QTreeWidget,
    QLabel,
    QApplication,
)


class CopyFeedbackWindow(QWidget):
    """복사 피드백을 위한 독립적인 팝업 창"""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setup_window()
        self.setup_ui(text)
        self.setup_animation()

    def setup_window(self):
        """창 설정"""
        # 프레임리스 윈도우, 항상 위에 표시, 태스크바 숨김
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )

        # 반투명 배경 비활성화 (명확한 표시를 위해)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # 고정 크기 설정
        self.setFixedSize(300, 80)

    def setup_ui(self, text):
        """UI 설정"""
        # 텍스트 길이 제한
        display_text = text[:40] + "..." if len(text) > 40 else text

        # 라벨 생성
        self.label = QLabel(f"📋 복사됨: {display_text}", self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)

        # 세련된 토스트 스타일
        self.setStyleSheet(
            f"""
            /* 💡 QWidget: 배경을 불투명하고 단일한 검은색으로 설정 (컨테이너 역할) */
            QWidget {{
                background-color: #1e1e1e; /* 단일 색상으로 명확하게 */
                border-radius: 1px;
                border: 1px solid #1e1e1e; /* 어두운 테두리 추가 */
            }}
            /* 💡 QLabel: 창 전체를 덮도록 하고, QLabel의 배경에 그라데이션을 직접 적용 */
            QLabel {{
                color: #f5f5f5;
                font-family: '{U.FONT_FAMILY}';
                font-size: 13px;
                font-weight: 600;
                /* ✅ 그라데이션 적용: 중앙(0.3)은 매우 밝게, 바깥쪽(1.0)은 QWidget과 유사하게 */
                background-color: qradialgradient(
                    cx: 0.5, cy: 0.5, radius: 1.1,
                    fx: 0.5, fy: 0.5,
                    stop: 0.1 #AD2E00,    /* 중앙: 빨간색 */
                    stop: 1.0 #1e1e1e     /* 바깥쪽: QWidget과 동일한 어두운 색 */
                );
                padding: 0 16px; /* 상하 패딩 제거 */
            }}
        """
        )

        # 그림자 효과 추가
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        shadow = QGraphicsDropShadowEffect(self)
        # 흐림 효과를 줄이고 투명도를 높여 선명하고 진하게 만듭니다.
        shadow.setBlurRadius(10)  # 흐림 효과를 줄임
        shadow.setOffset(0, 5)  # 그림자를 약간 더 멀리
        shadow.setColor(QColor(0, 0, 0, 220))  # 투명도를 높여(불투명하게) 더 진하게
        self.setGraphicsEffect(shadow)

        # 라벨을 전체 크기로 확장
        self.label.resize(self.size())

    def setup_animation(self):
        """애니메이션 설정"""
        # 페이드 아웃 애니메이션
        self.opacity_animation = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_animation.setDuration(500)  # 더 천천히
        self.opacity_animation.setStartValue(1.0)
        self.opacity_animation.setEndValue(0.0)
        self.opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.opacity_animation.finished.connect(self.close)

        # 자동 사라짐 타이머
        self.auto_close_timer = QTimer()
        self.auto_close_timer.timeout.connect(self.start_fade_out)
        self.auto_close_timer.setSingleShot(True)

    def show_feedback(self, duration_ms=2000):
        """피드백 표시"""
        # 위치: 부모 중앙 우선, 실패 시 화면 중앙
        if not self.center_on_parent():
            self.center_on_screen()

        # 표시
        self.show()
        self.raise_()  # 맨 앞으로

        # 자동 사라짐 시작
        self.auto_close_timer.start(duration_ms)

    def center_on_parent(self) -> bool:
        """부모(최상위 창) 중앙에 위치시키기. 성공 시 True."""
        try:
            # 1단계 수정으로 전달된 부모 위젯을 가져옵니다.
            parent = self.parent()
            if parent:
                # parent.window()를 통해 항상 최상위 메인 윈도우를 찾습니다.
                top_level_window = parent.window()
                if top_level_window and top_level_window.isVisible():
                    # 1. 부모 창의 내부 좌표 기준 중앙 지점을 계산합니다.
                    parent_center_local = top_level_window.rect().center()

                    # 2. ✨핵심✨: 내부 좌표를 화면 전체의 '절대 좌표'로 변환합니다.
                    parent_center_global = top_level_window.mapToGlobal(
                        parent_center_local
                    )

                    # 3. 변환된 절대 좌표를 기준으로 피드백 창의 최종 위치를 계산합니다.
                    x = parent_center_global.x() - self.width() // 2
                    y = parent_center_global.y() - self.height() // 2

                    # 4. 절대 좌표로 피드백 창을 이동시킵니다.
                    self.move(x, y)
                    return True
        except Exception as e:
            print(f"부모 중앙 정렬 실패: {e}")  # 디버깅을 위해 오류 출력 추가
        return False

    def center_on_screen(self):
        """화면 중앙에 위치시키기"""
        try:
            # 현재 화면의 기하학적 정보 가져오기
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.geometry()

                # 창을 화면 중앙에 위치시키기
                x = (screen_geometry.width() - self.width()) // 2
                y = (screen_geometry.height() - self.height()) // 2 - 100  # 약간 위쪽

                self.move(x, y)
            else:
                # 기본 위치
                self.move(400, 300)
        except Exception:
            # 예외 발생 시 기본 위치
            self.move(400, 300)

    def start_fade_out(self):
        """페이드 아웃 시작"""
        self.opacity_animation.start()


def show_copy_feedback(text, parent_widget=None, app_instance=None):
    """
    복사 피드백 표시 (tkinter 버전과 유사한 중앙 모달)

    Args:
        text: 복사된 텍스트
        parent_widget: 부모 위젯 (사용되지 않지만 호환성 유지)
        app_instance: 앱 인스턴스 (로그 메시지용)
    """
    try:
        # 피드백 창 생성 및 표시 (부모 중앙 정렬)
        feedback_window = CopyFeedbackWindow(str(text), parent=parent_widget)
        feedback_window.show_feedback(2000)  # 2초간 표시

        # 전역 참조 유지 (가비지 컬렉션 방지)
        if not hasattr(QApplication.instance(), "_copy_feedback_windows"):
            QApplication.instance()._copy_feedback_windows = []
        QApplication.instance()._copy_feedback_windows.append(feedback_window)

        # 창이 닫힐 때 참조 제거
        feedback_window.destroyed.connect(
            lambda: (
                QApplication.instance()._copy_feedback_windows.remove(feedback_window)
                if hasattr(QApplication.instance(), "_copy_feedback_windows")
                and feedback_window in QApplication.instance()._copy_feedback_windows
                else None
            )
        )

        # 로그 메시지
        if app_instance and hasattr(app_instance, "log_message"):
            app_instance.log_message(
                f"📋 클립보드 복사 완료: {str(text)[:50]}{'...' if len(str(text)) > 50 else ''}",
                "INFO",
            )

    except Exception as e:
        print(f"복사 피드백 표시 실패: {e}")

        # 로그 메시지만 표시
        if app_instance and hasattr(app_instance, "log_message"):
            app_instance.log_message(
                f"📋 클립보드 복사 완료 (피드백 없음): {str(text)[:30]}...", "WARNING"
            )


def show_toast_message(message, message_type="info", parent=None, duration_ms=2000):
    """
    범용 토스트 메시지

    Args:
        message: 표시할 메시지
        message_type: 메시지 타입 ("info", "success", "warning", "error")
        parent: 부모 위젯
        duration_ms: 표시 시간 (밀리초)
    """
    try:
        # 타입별 아이콘과 색상
        type_config = {
            "info": {"icon": "ℹ️", "color": "#0984e3"},
            "success": {"icon": "✅", "color": "#00b894"},
            "warning": {"icon": "⚠️", "color": "#fdcb6e"},
            "error": {"icon": "❌", "color": "#e17055"},
        }

        config = type_config.get(message_type, type_config["info"])
        formatted_message = f"{config['icon']} {message}"

        # 토스트 창 생성 (부모 중앙 정렬)
        toast_window = CopyFeedbackWindow(formatted_message, parent=parent)

        # 타입별 색상 적용
        toast_window.setStyleSheet(
            f"""
            QWidget {{
                background-color: #2d3436;
                border: 3px solid {config['color']};
                border-radius: 12px;
            }}
            QLabel {{
                color: #ffffff;
                font-family: '{U.FONT_FAMILY}';
                font-size: 12px;
                font-weight: bold;
                background-color: transparent;
                padding: 10px;
            }}
        """
        )

        # 표시
        toast_window.show_feedback(duration_ms)

        # 전역 참조 유지
        if not hasattr(QApplication.instance(), "_toast_windows"):
            QApplication.instance()._toast_windows = []
        QApplication.instance()._toast_windows.append(toast_window)

        # 창이 닫힐 때 참조 제거
        toast_window.destroyed.connect(
            lambda: (
                QApplication.instance()._toast_windows.remove(toast_window)
                if hasattr(QApplication.instance(), "_toast_windows")
                and toast_window in QApplication.instance()._toast_windows
                else None
            )
        )

    except Exception as e:
        print(f"토스트 메시지 표시 실패: {e}")


def copy_to_clipboard_with_feedback(text, app_instance, parent_widget=None):
    """클립보드 복사 + 피드백 표시 - 완전 개선 버전"""
    try:
        # -------------------
        # ✅ [핵심 추가] U+2029 문자 제거
        cleaned_text = str(text).replace("\u2029", "")
        # -------------------

        # 클립보드에 복사
        clipboard = QApplication.clipboard()
        clipboard.setText(cleaned_text)

        # 피드백 표시
        show_copy_feedback(cleaned_text, parent_widget, app_instance)

        return True

    except Exception as e:
        # 피드백 표시 실패해도 기본 복사는 시도
        try:
            # -------------------
            # ✅ [핵심 추가] U+2029 문자 제거
            cleaned_text = str(text).replace("\u2029", "")
            # -------------------

            clipboard = QApplication.clipboard()
            clipboard.setText(cleaned_text)

            if app_instance and hasattr(app_instance, "log_message"):
                app_instance.log_message(
                    f"📋 클립보드 복사 완료 (피드백 없음): {cleaned_text[:30]}...",
                    "WARNING",
                )
            return True
        except Exception as e2:
            if app_instance and hasattr(app_instance, "log_message"):
                app_instance.log_message(f"❌ 클립보드 복사 실패: {e2}", "ERROR")
            return False
