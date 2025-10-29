#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파일명: qt_main_app.py
설명: Qt/PySide6 기반 통합 서지검색 시스템 메인 애플리케이션
버전: 2.1.0
생성일: 2025-09-23
수정일: 2025-10-18

변경 이력:
v2.1.0 (2025-10-18)
- [기능 추가] 모든 탭의 QSplitter 자동 저장/복구 기능 통합
  : save_layout_settings()에 모든 탭 스플리터 저장 로직 추가
    · Gemini 탭: main_splitter
    · KSH_Local 탭: results_splitter
    · MARC_Extractor 탭: v_splitter, h_splitter
    · MARC_Editor 탭: main_splitter
    · Dewey 탭: master_splitter, left_content_splitter, right_content_splitter
  : restore_layout_settings()에 모든 탭 스플리터 복구 로직 추가
  : 각 탭별 스플리터 설정이 glossary.db에 자동 저장되고 앱 재시작 시 복구됨

v2.0.2 (2025-10-02)
- [수정] closeEvent()에서 트리메뉴 모드와 탭 모드 구분 처리
  : 트리메뉴 모드일 때 tree_navigation.tab_widgets 사용
  : 탭 모드일 때 tab_widget.count() 사용
  : NoneType 오류 수정

v2.0.1 (2025-10-02)
- [개선] MainApplicationWindow.closeEvent() 메서드 강화
  : 앱 종료 시 모든 탭을 순회하며 실행 중인 스레드를 안전하게 종료
  : cleanup_all_threads() 메서드가 있는 탭 우선 처리
  : BaseSearchTab 기반 탭의 search_thread도 안전하게 종료
- [효과] 앱 종료 시 "QThread: Destroyed while thread is still running" 경고 제거
"""
import sys
import re
import os
import sqlite3
import logging
import threading
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,  # ✅ 추가
    QHBoxLayout,
    QGroupBox,
    QMessageBox,
    QTabWidget,
    QSplitter,  # <-- 이 부분을 추가해야 합니다.
    QTextBrowser,
    QSplashScreen,  # ✅ 스플래시 스크린 추가
)
from qt_custom_widgets import TripleClickLimitedTextBrowser
from PySide6.QtCore import (
    Signal,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QAction,  # ✅ QAction은 QtGui에 속하므로 QtWidgets에서 제거
    QFont,
    QTextCursor,
    QShortcut,  # 👈 QShortcut 추가
    QKeySequence,  # 👈 QKeySequence 추가
    QPixmap,  # ✅ 스플래시 이미지용 추가
)
from qt_styles import apply_button_shadows

# UI 상수
from ui_constants import U

# 프로젝트 모듈 import
from database_manager import DatabaseManager
from db_perf_tweaks import warm_up_queries, wait_for_warmup  # ✅ WAL 워밍업 유틸
from qt_shortcuts import show_shortcuts_help
from qt_utils import (
    apply_dark_title_bar,
    enable_modal_close_on_outside_click,
    linkify_text,
)
from qt_TabView_NDL import QtNDLSearchTab
from qt_TabView_Global import QtGlobalSearchTab
from qt_TabView_Western import QtWesternSearchTab
from qt_TabView_LegalDeposit import QtLegalDepositSearchTab
from qt_TabView_AIFeed import QtAIFeedSearchTab
from qt_TabView_KACAuthorities import QtKACAuthoritiesSearchTab
from qt_TabView_BriefWorks import QtBriefWorksSearchTab
from qt_TabView_KSH_Lite import QtKshHyridSearchTab
from qt_TabView_ISNI_Detailed import QtISNIDetailedSearchTab
from qt_TabView_NLK import QtNLKSearchTab
from qt_TabView_KSH_Local import QtKSHLocalSearchTab
from qt_TabView_MARC_Extractor import QtMARCExtractorTab
from qt_TabView_MARC_Editor import QtMARCEditorTab
from qt_TabView_Dewey import QtDeweySearchTab
from qt_TabView_Settings import QtSettingsTab
from qt_TabView_Python import QtPythonTab
from qt_context_menus import setup_widget_context_menu
from qt_TabView_Gemini import QtGeminiTab


def ensure_sqlite_db(db_path: str, schema_sql: str | None = None) -> None:
    """
    db_path가 없으면 상위 폴더를 만들고, 빈 SQLite 파일을 생성한다.
    schema_sql이 주어지면 CREATE TABLE IF NOT EXISTS 형태의 스키마를 적용한다.
    """
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # 파일이 없으면 생성 (연결 후 바로 닫기)
    need_schema = False
    if not p.exists():
        with sqlite3.connect(str(p)) as _conn:
            pass
        need_schema = True  # 새로 만들었으면 스키마 적용 기회로 간주

    # 스키마가 제공되면 적용 (이미 있어도 IF NOT EXISTS로 안전)
    if schema_sql:
        with sqlite3.connect(str(p)) as conn:
            cur = conn.cursor()
            cur.executescript(schema_sql)
            conn.commit()


class IntegratedSearchApp:
    """통합 서지검색 애플리케이션 - Qt 전용"""

    def __init__(self):
        self.db_manager = None
        self.main_window = None
        self.api_server = None  # ✅ [추가] Flask API 서버 인스턴스
        self.setup_logging()
        self.initialize_database()
        # ✅ [추가] 검색 스레드 중지를 위한 플래그 추가
        self.stop_search_flag = threading.Event()

    def setup_logging(self):
        """로깅 설정"""

        # 커스텀 핸들러: UI 로그 위젯에도 출력
        class UILogHandler(logging.Handler):
            def __init__(self, app_instance):
                super().__init__()
                self.app_instance = app_instance

            def emit(self, record):
                msg = self.format(record)
                level = record.levelname
                if self.app_instance and self.app_instance.main_window:
                    # UI 스레드 안전하게 로그 출력
                    self.app_instance.main_window.log_signal.emit(msg, level)

        # ✅ [수정] exe 환경에서 이모지 출력을 위한 UTF-8 StreamHandler 설정
        import sys

        # Windows exe 환경에서 UTF-8 인코딩을 강제하는 SafeStreamHandler
        class SafeStreamHandler(logging.StreamHandler):
            def emit(self, record):
                try:
                    super().emit(record)
                except UnicodeEncodeError:
                    # 이모지 등 인코딩 불가능한 문자는 무시
                    pass

        # UTF-8 스트림 핸들러 생성
        stream_handler = SafeStreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)

        # sys.stdout.reconfigure(encoding='utf-8')는 TextIOBase 객체에만 적용 가능하며,
        # PyInstaller 환경 등에서는 sys.stdout이 다른 타입일 수 있어 오류 발생 가능.
        # SafeStreamHandler가 이미 인코딩 문제를 처리하므로 여기서 추가적인 reconfigure는 불필요.
        # 필요한 경우, SafeStreamHandler 내부에서 sys.stdout.buffer를 사용하여 바이너리 쓰기를 고려할 수 있음.

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("search_app.log", encoding="utf-8"),
                stream_handler,
            ],
            force=True,  # 기존 설정 강제 재설정
        )
        self.logger = logging.getLogger(__name__)

        # database_manager 로거도 INFO 레벨로 설정하고 UI 핸들러 추가
        db_logger = logging.getLogger("qt_main_app.database_manager")
        db_logger.setLevel(logging.INFO)

        # UI 핸들러 추가 (나중에 main_window 생성 후)
        self.ui_handler = UILogHandler(self)
        self.ui_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )

    def initialize_database(self):
        """데이터베이스 초기화"""
        try:
            # [핵심] 경로 정의
            concepts_db_path = "nlk_concepts.sqlite"
            kdc_ddc_mapping_db_path = "kdc_ddc_mapping.db"

            # [안전망] 파일이 없으면 생성 + 최소 스키마 적용
            # 개념 DB: KSH 상세보기에서 참조하는 테이블(최소)
            concepts_min_schema = """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS literal_props (
                concept_id TEXT NOT NULL,
                prop       TEXT NOT NULL,
                value      TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_literal_props_cpv
                ON literal_props (concept_id, prop, value);

            CREATE TABLE IF NOT EXISTS uri_props (
                concept_id TEXT NOT NULL,
                prop       TEXT NOT NULL,
                target     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_uri_props_cpt
                ON uri_props (concept_id, prop, target);
            """

            # 매핑 DB: 최소한의 settings 테이블만 (탐색 스타일을 읽을 때 사용될 수 있음)
            mapping_min_schema = """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """

            ensure_sqlite_db(concepts_db_path, concepts_min_schema)
            ensure_sqlite_db(kdc_ddc_mapping_db_path, mapping_min_schema)

            # [본 처리] DatabaseManager가 있다면 내부 initialize_databases()가
            # 필요한 추가 스키마/마이그레이션을 수행
            self.db_manager = DatabaseManager(concepts_db_path, kdc_ddc_mapping_db_path)
            self.db_manager.initialize_databases()

            self.logger.info("데이터베이스 초기화 완료")

            # ✅ [성능 개선] WAL 모드 즉시 워밍업 - 첫 쿼리 블로킹(10-15초) 방지
            self._warm_up_databases()

            # ✅ [추가] Flask API 서버 자동 시작
            self.start_extension_api_server()

        except Exception as e:
            self.logger.error(f"데이터베이스 초기화 실패: {e}")
            # 데이터베이스 없어도 앱 실행은 가능하도록
            self.db_manager = None

    def _warm_up_databases(self):
        """
        ✅ [성능 개선] 앱 시작 직후 백그라운드에서 DB 워밍업
        - WAL 모드 초기화를 미리 수행하여 첫 쿼리 시 메인 스레드 블로킹 방지
        - 3.5GB mapping_data 테이블의 첫 쿼리: 20초 → 2-3초로 단축
        """
        if self.db_manager is None:
            return

        try:
            db_manager = self.db_manager  # 타입 체커를 위한 로컬 변수

            # 🔥 mapping_data 테이블 워밍업 (가장 중요!)
            # ⚡ 실제 사용되는 쿼리 패턴으로 WAL 파일을 충분히 초기화
            # ✅ 백그라운드 실행으로 UI 블로킹 없음
            self.logger.info("🔄 데이터베이스 워밍업 시작 (백그라운드)...")

            mapping_warmup_queries = [
                "SELECT 1",
                # DDC 인덱스 워밍업 (여러 패턴으로 인덱스 전체 활성화)
                "SELECT identifier, ddc FROM mapping_data WHERE ddc LIKE '0%' LIMIT 1",
                "SELECT identifier, ddc FROM mapping_data WHERE ddc LIKE '3%' LIMIT 1",
                "SELECT identifier, ddc FROM mapping_data WHERE ddc LIKE '5%' LIMIT 1",
                "SELECT identifier, ddc FROM mapping_data WHERE ddc LIKE '9%' LIMIT 1",
                # ksh_korean 인덱스 워밍업 (FTS5 사용하므로 가벼운 쿼리만)
                "SELECT identifier, ksh_korean FROM mapping_data WHERE ksh_korean LIKE '태%' LIMIT 1",
            ]
            warm_up_queries(
                lambda: db_manager._get_mapping_connection(),
                extra_queries=mapping_warmup_queries,
                delay_sec=0.0,
                warmup_key="mapping_data",  # 첫 검색 시 대기할 키
            )

            # KSH Concept DB 워밍업
            ksh_warmup_queries = [
                "SELECT 1",
                "SELECT COUNT(*) FROM concepts LIMIT 1",
            ]
            warm_up_queries(
                lambda: db_manager._get_concepts_connection(),
                extra_queries=ksh_warmup_queries,
                delay_sec=0.0,
                warmup_key="concepts",
            )

        except Exception as e:
            self.logger.warning(f"⚠️ 데이터베이스 워밍업 실패 (무시 가능): {e}")

    def start_extension_api_server(self):
        """브라우저 확장 프로그램용 Flask API 서버를 시작합니다."""
        try:
            from extension_api_server import ExtensionAPIServer

            if self.db_manager is None:
                self.log_message(
                    "⚠️ 데이터베이스가 초기화되지 않아 API 서버를 시작할 수 없습니다.",
                    "WARNING",
                )
                return

            # API 서버 인스턴스 생성 및 시작
            self.api_server = ExtensionAPIServer(self, self.db_manager)
            success = self.api_server.start_server(host="127.0.0.1", port=5000)

            if success:
                self.log_message(
                    "✅ 브라우저 확장 프로그램용 API 서버가 시작되었습니다.", "INFO"
                )
            else:
                self.log_message("⚠️ API 서버 시작에 실패했습니다.", "WARNING")

        except ImportError:
            self.log_message(
                "⚠️ Flask가 설치되지 않았습니다. 확장 프로그램 기능을 사용하려면 'pip install flask flask-cors'를 실행하세요.",
                "WARNING",
            )
        except Exception as e:
            self.log_message(f"❌ API 서버 시작 실패: {e}", "ERROR")

    def log_message(self, message, level="INFO"):
        """로그 메시지 출력 (UI 연동용)"""
        if level == "ERROR":
            self.logger.error(message)
        elif level == "WARNING":
            self.logger.warning(message)
        else:
            self.logger.info(message)

        # 메인 윈도우의 로그 디스플레이에도 출력
        if self.main_window:
            # ✅ [핵심] UI 수정을 위한 '신호'를 보냅니다.
            self.main_window.log_signal.emit(message, level)

    # ✅ [추가] 백그라운드 스레드에서 프로그레스 바 업데이트를 요청하는 메서드
    def update_progress(self, value):
        """프로그레스 바 업데이트 (UI 연동용)"""
        if self.main_window:
            # UI 수정을 위한 '신호'를 보냅니다.
            self.main_window.update_progress_signal.emit(value)

    def run(self):
        """애플리케이션 실행"""
        app = QApplication(sys.argv)
        app.setApplicationName("통합 서지검색 시스템")
        app.setApplicationVersion("2.0.0")

        # 저장된 테마 불러오기 및 적용
        self.load_and_apply_theme(app)

        # ✅ 스플래시 스크린 생성 및 표시
        # PyInstaller exe 환경에서도 작동하도록 경로 처리
        if getattr(sys, "frozen", False):
            # PyInstaller로 패키징된 exe 환경
            base_path = sys._MEIPASS
        else:
            # 일반 Python 스크립트 실행 환경
            base_path = os.path.dirname(os.path.abspath(__file__))

        splash_image_path = os.path.join(base_path, "loading.jpg")
        splash_pixmap = QPixmap(splash_image_path)

        if splash_pixmap.isNull():
            # 이미지 로드 실패 시 기본 컬러 배경 사용
            self.logger.warning(
                f"스플래시 이미지를 찾을 수 없습니다: {splash_image_path}"
            )
            splash_pixmap = QPixmap(600, 400)
            splash_pixmap.fill(Qt.GlobalColor.darkBlue)

        splash = QSplashScreen(splash_pixmap, Qt.WindowType.WindowStaysOnTopHint)
        splash.show()
        splash.showMessage(
            "로딩 중...",
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
            Qt.GlobalColor.white,
        )
        app.processEvents()  # UI 업데이트

        # ✅ 스플래시가 충분히 보이도록 실제 대기
        import time

        time.sleep(0.5)  # 500ms 대기
        app.processEvents()

        # 메인 윈도우 생성
        splash.showMessage(
            "데이터베이스 초기화 중...",
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
            Qt.GlobalColor.white,
        )
        app.processEvents()

        self.main_window = MainApplicationWindow(self)

        splash.showMessage(
            "UI 구성 중...",
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
            Qt.GlobalColor.white,
        )
        app.processEvents()

        # UI 핸들러를 database_manager 로거에 추가
        db_logger = logging.getLogger("qt_main_app.database_manager")
        db_logger.addHandler(self.ui_handler)

        # 초기화 완료 메시지
        self.log_message("통합 서지검색 시스템이 시작되었습니다.", "INFO")

        # ✅ 스플래시 최소 표시 시간 보장 (총 1.5초)
        time.sleep(1.0)  # 추가 1초 대기
        app.processEvents()

        # 스플래시 스크린 종료 및 메인 윈도우 표시
        splash.finish(self.main_window)
        self.main_window.show()

        # 애플리케이션 실행
        sys.exit(app.exec())

    def load_and_apply_theme(self, app):
        """저장된 테마를 불러와서 적용합니다"""
        from ui_constants import set_theme
        from qt_styles import get_app_stylesheet

        # DB에서 저장된 테마 설정 불러오기
        saved_theme = "dark"  # 기본값
        if self.db_manager:
            theme_setting = self.db_manager.get_setting("ui_theme")
            if theme_setting and "light" in theme_setting.lower():
                saved_theme = "light"

        # ui_constants의 테마 설정
        set_theme(saved_theme)

        # 새 스타일시트 생성 및 적용
        app.setStyleSheet(get_app_stylesheet())

        self.logger.info(f"✅ {saved_theme.capitalize()} 테마 적용됨")

    # ✅ [추가] 각 탭에서 메인 창의 상태 표시줄을 제어하기 위한 중계 함수
    def set_status_message(self, message, level="INFO"):
        if self.main_window:
            # -------------------
            # ✅ [수정] 현재 활성화된 탭을 가져와서 해당 탭의 status_label을 직접 업데이트합니다.
            current_tab = self.main_window.get_current_tab()
            if hasattr(current_tab, "status_label"):
                current_tab.status_label.setText(message)
            # -------------------


class MainApplicationWindow(QMainWindow):
    """메인 애플리케이션 윈도우"""

    # ✅ [핵심] 스레드로부터 메시지를 받을 신호(Signal)를 정의합니다.
    log_signal = Signal(str, str)
    # -------------------
    # ✅ [추가] 스레드로부터 프로그레스 값을 받을 신호를 정의합니다.
    update_progress_signal = Signal(int)
    # -------------------

    def __init__(self, app_instance):
        super().__init__()
        self.app_instance = app_instance
        self.setup_ui()
        self.setup_menu_and_toolbar()
        # ✅ [핵심] 신호(log_signal)가 오면 append_log 함수를 실행하도록 연결합니다.
        self.log_signal.connect(self.append_log)
        # -------------------
        # ✅ [추가] 프로그레스 신호가 오면 update_current_tab_progress 함수를 실행하도록 연결합니다.
        self.update_progress_signal.connect(self.update_current_tab_progress)
        # -------------------
        apply_dark_title_bar(self)

        # [추가] 로그/상세 정보창의 초기 표시 상태를 저장할 변수
        self.is_detail_visible = True
        self.is_log_visible = True

        # ✅ [추가] F7 단축키로 찾기 영역을 숨기거나 보이게 하는 기능을 추가합니다.
        shortcut_toggle_find = QShortcut(QKeySequence("F7"), self)
        shortcut_toggle_find.activated.connect(self.toggle_find_area_visibility)

        # [핵심 추가] F8 단축키로 전체 화면 모드(F10, F11, F12 동시 작동)를 구현합니다.
        shortcut_toggle_all = QShortcut(QKeySequence("F8"), self)
        shortcut_toggle_all.activated.connect(self.toggle_all_visibility)

        # ✅ [추가] F9 단축키로 탭바를 숨기거나 보이게 하는 기능을 추가합니다.
        shortcut_toggle_tabbar = QShortcut(QKeySequence("F9"), self)
        shortcut_toggle_tabbar.activated.connect(self.toggle_tab_bar_visibility)

        # [핵심] F10 단축키로 메뉴바를 숨기거나 보이게 하는 기능을 추가합니다.
        shortcut_toggle_menubar = QShortcut(QKeySequence("F10"), self)
        shortcut_toggle_menubar.activated.connect(self.toggle_menu_bar_visibility)

        # [추가] F11 단축키로 상세 정보창을 숨기거나 보이게 하는 기능
        shortcut_toggle_detail = QShortcut(QKeySequence("F11"), self)
        shortcut_toggle_detail.activated.connect(self.toggle_detail_visibility)

        # [핵심] F12 단축키로 로그창을 숨기거나 보이게 하는 기능을 추가합니다.
        shortcut_toggle_log = QShortcut(QKeySequence("F12"), self)
        shortcut_toggle_log.activated.connect(self.toggle_log_visibility)

        # ✅ [추가] 레이아웃 설정 관리자 초기화 및 설정 복구
        from qt_layout_settings_manager import LayoutSettingsManager

        self.layout_settings_manager = LayoutSettingsManager(
            self.app_instance.db_manager
        )
        # UI가 완전히 준비된 후 설정 복구를 위해 QTimer 사용
        QTimer.singleShot(100, self.restore_layout_settings)

    def setup_ui(self):
        """UI 설정"""
        self.setWindowTitle(
            "통합 검색 시스템 - Qt Model/View Edition V. 5.0.9 Beta for PNU Library 자료조직팀 by InnovaNex"
        )
        self.setMinimumSize(1200, 850)
        self.resize(1850, 1000)

        # 중앙 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 메인 레이아웃 (수직 분할)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 0)

        # [핵심 수정] 메인 스플리터: 탭 영역과 하단 정보 영역으로 분할
        # ✅ [수정] 인스턴스 변수로 저장 (레이아웃 설정 저장/복구용)
        self.main_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(self.main_splitter)

        # 1. 탭 위젯(테이블 뷰)을 메인 스플리터 상단에 추가
        self.setup_tabs(self.main_splitter)

        # 2. 로그와 상세 정보를 담을 하단 스플리터 (좌우 분할)
        # ✅ [수정] 인스턴스 변수로 저장 (레이아웃 설정 저장/복구용)
        self.bottom_splitter = QSplitter(Qt.Horizontal)

        # 2-1. 왼쪽: 로그 섹션
        self.log_group = QGroupBox("시스템 로그")
        self.log_group.setObjectName("BottomPanelGroup")
        # self.log_group.setStyleSheet(groupbox_style)  # <--  스타일 적용 코드 추가
        log_layout = QVBoxLayout(self.log_group)
        log_layout.setContentsMargins(0, 20, 0, 0)  # ,좌,상,우,하
        self.log_display = QTextBrowser()
        self.log_display.setReadOnly(True)
        self.log_display.setOpenExternalLinks(True)
        self.log_display.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_display)
        # ✅ [추가] 로그 위젯에 커스텀 컨텍스트 메뉴를 연결합니다.
        setup_widget_context_menu(self.log_display, self.app_instance)
        self.bottom_splitter.addWidget(self.log_group)

        # 2-2. 오른쪽: 상세 정보 섹션
        self.detail_group = QGroupBox("선택 행 상세 정보")
        self.detail_group.setObjectName("BottomPanelGroup")
        # self.detail_group.setStyleSheet(groupbox_style)  # <-- 스타일 적용 코드 추가
        detail_layout = QVBoxLayout(self.detail_group)
        detail_layout.setContentsMargins(0, 20, 0, 0)
        self.detail_display = TripleClickLimitedTextBrowser()
        self.detail_display.setReadOnly(True)
        self.detail_display.setOpenExternalLinks(True)
        self.detail_display.setFont(QFont("Consolas", 9))
        detail_layout.addWidget(self.detail_display)
        # ✅ [추가] 상세 정보 위젯에 커스텀 컨텍스트 메뉴를 연결합니다.
        setup_widget_context_menu(self.detail_display, self.app_instance)
        self.bottom_splitter.addWidget(self.detail_group)

        # [핵심 수정 1] 좌우 여백을 위한 wrapper 위젯 추가
        self.bottom_container = QWidget()
        bottom_layout = QHBoxLayout(self.bottom_container)
        bottom_layout.setContentsMargins(6, 0, 6, 10)  # 하단패널 여백 조절(좌,상,우,하)
        bottom_layout.addWidget(self.bottom_splitter)

        # 3. 여백이 적용된 컨테이너를 메인 스플리터 하단에 추가
        self.main_splitter.addWidget(self.bottom_container)
        apply_button_shadows(self)  # 윈도우 전체 버튼에 섀도 적용

        # 스플리터 초기 크기 비율 설정
        self.main_splitter.setSizes([700, 300])  # 탭 영역 : 하단 정보 영역
        self.bottom_splitter.setSizes([500, 500])  # 로그 : 상세 정보

    def setup_tabs(self, parent):
        """탭 설정 - 네비게이션 스타일에 따라 조건부 실행"""
        # [핵심] 중앙 설정 파일 임포트
        from qt_Tab_configs import TAB_CONFIGURATIONS

        # 네비게이션 스타일 확인
        nav_style = "tab"  # 기본값
        if self.app_instance.db_manager:
            nav_style = (
                self.app_instance.db_manager.get_setting("navigation_style") or "tab"
            )

        if nav_style == "tree":
            # 트리메뉴 네비게이션
            self.app_instance.log_message(
                "ℹ️ 트리메뉴 네비게이션을 로드합니다...", "INFO"
            )
            from qt_tree_menu_navigation import create_tree_menu_navigation

            self.tree_navigation = create_tree_menu_navigation(
                parent, self.app_instance, TAB_CONFIGURATIONS
            )
            parent.addWidget(self.tree_navigation)
            self.tab_widget = None  # 탭 위젯 없음

        else:
            # 기본 탭 위젯 네비게이션
            self.app_instance.log_message(
                "ℹ️ 기본 탭 네비게이션을 로드합니다...", "INFO"
            )
            self.tab_widget = QTabWidget()
            parent.addWidget(self.tab_widget)
            self.tree_navigation = None  # 트리 네비게이션 없음

        # 일반 탭 위젯 모드일 때만 탭 생성
        if self.tab_widget is not None:
            # 각 탭 클래스를 쉽게 찾을 수 있도록 매핑
            tab_class_map = {
                "NLK_SEARCH": QtNLKSearchTab,
                "NDL_SEARCH": QtNDLSearchTab,
                "WESTERN_SEARCH": QtWesternSearchTab,
                "GLOBAL_SEARCH": QtGlobalSearchTab,
                "LEGAL_DEPOSIT_SEARCH": QtLegalDepositSearchTab,
                "AI_FEED_SEARCH": QtAIFeedSearchTab,
                "KAC_AUTHORITIES_SEARCH": QtKACAuthoritiesSearchTab,
                "BRIEF_WORKS_SEARCH": QtBriefWorksSearchTab,
                "ISNI_DETAILED_SEARCH": QtISNIDetailedSearchTab,
                "KSH_HYBRID_SEARCH": QtKshHyridSearchTab,
                "KSH_LOCAL_SEARCH": QtKSHLocalSearchTab,
                "MARC_EXTRACTOR": QtMARCExtractorTab,
                "MARC_EDITOR": QtMARCEditorTab,
                "DEWEY_SEARCH": QtDeweySearchTab,
                "PYTHON_TAB": QtPythonTab,
                "SETTINGS": QtSettingsTab,
                "GEMINI_DDC_SEARCH": QtGeminiTab,
            }
            # 중앙 설정(TAB_CONFIGURATIONS)을 순회하며 동적으로 탭 생성
            for key, config in TAB_CONFIGURATIONS.items():
                if key in tab_class_map:
                    TabClass = tab_class_map[key]
                    tab_instance = TabClass(config, self.app_instance)
                    self.tab_widget.addTab(
                        tab_instance, config.get("tab_name", "Untitled")
                    )

            # ✅ [추가] 탭 인스턴스 생성 후, 상호 참조를 위해 app_instance에 등록합니다.
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if isinstance(widget, QtMARCExtractorTab):
                    self.app_instance.marc_extractor_tab = widget
                elif isinstance(widget, QtMARCEditorTab):
                    self.app_instance.marc_editor_tab = widget

            # 탭 변경 이벤트 연결
            self.tab_widget.currentChanged.connect(self.on_tab_changed)

    def setup_menu_and_toolbar(self):
        """메뉴바와 툴바 설정"""
        menubar = self.menuBar()

        # 파일 메뉴 (기존 항목 보존)
        file_menu = menubar.addMenu("파일(&F)")
        file_menu.addAction("종료(&X)", self.close)

        # 검색 메뉴 (새로 추가)
        search_menu = menubar.addMenu("검색(&S)")
        search_menu.addAction("MARC 추출", self.marc_extract)
        search_menu.addSeparator()
        search_menu.addAction("NLK 검색", self.search_nlk)
        search_menu.addAction("LC 검색", self.search_lc)
        search_menu.addAction("NDL + CiNii 검색", self.search_ndl)
        search_menu.addAction("Western 검색", self.search_western)
        search_menu.addAction("Global 통합검색", self.search_global)
        search_menu.addSeparator()
        search_menu.addAction("납본 ID 검색", self.search_bne)
        # search_menu.addAction("Google Books", self.search_google)

        # 저작물/저자 메뉴 (새로 추가)
        author_menu = menubar.addMenu("저작물/저자(&W)")
        author_menu.addAction("저자전거", self.search_authorities)
        author_menu.addSeparator()
        author_menu.addAction("상세 저작물 정보", self.show_detailed_works)
        author_menu.addAction("간략 저작물 정보", self.show_brief_works)

        # 주제어 메뉴 (새로 추가)
        subject_menu = menubar.addMenu("주제어(&J)")
        subject_menu.addAction("KSH Hybrid 검색", self.search_ksh_hybrid)
        subject_menu.addSeparator()
        subject_menu.addAction("KSH Local DB 검색", self.search_ksh_local)

        # 분류/AI 메뉴 (새로 추가)
        classification_menu = menubar.addMenu("분류/AI(&C)")
        classification_menu.addAction("Dewey 분류 검색", self.search_dewey)
        classification_menu.addSeparator()
        classification_menu.addAction("AI 피드", self.search_naver)
        classification_menu.addAction("Gemini AI DDC 분류", self.search_gemini_ddc)

        # 도구 메뉴 (새로 추가)
        tools_menu = menubar.addMenu("도구(&T)")
        tools_menu.addAction("Python Test", self.python_test)

        # 설정 메뉴 (기존 파일 메뉴에서 분리)
        settings_menu = menubar.addMenu("설정(&X)")
        settings_action = QAction("설정", self)
        # [수정] QTimer로 감싸서 이벤트 충돌 방지
        settings_action.triggered.connect(
            lambda: QTimer.singleShot(0, self.open_settings)
        )
        settings_menu.addAction(settings_action)

        # -------------------
        settings_menu.addSeparator()
        db_status_action = QAction("데이터베이스 상태 확인", self)
        db_status_action.triggered.connect(
            lambda: QTimer.singleShot(0, self.check_db_status)
        )
        settings_menu.addAction(db_status_action)

        # -------------------
        # ✅ [신규 추가] 데이터베이스 현황 보기 메뉴
        db_stats_action = QAction("데이터베이스 현황 보기", self)
        db_stats_action.triggered.connect(
            lambda: QTimer.singleShot(0, self.show_db_statistics)
        )
        settings_menu.addAction(db_stats_action)
        # -------------------

        # 도움말 메뉴 (기존 항목 보존)
        help_menu = menubar.addMenu("도움말(&H)")
        about_action = QAction("정보(&A)", self)
        # [수정] QTimer로 감싸서 이벤트 충돌 방지
        about_action.triggered.connect(lambda: QTimer.singleShot(0, self.show_about))
        help_menu.addAction(about_action)
        help_menu.addSeparator()

        # [추가] 단축키 안내 메뉴 복원 및 QTimer 적용
        shortcuts_action = QAction("단축키 안내", self)
        shortcuts_action.triggered.connect(
            lambda: QTimer.singleShot(0, lambda: show_shortcuts_help(self))
        )
        help_menu.addAction(shortcuts_action)

    def switch_to_tab_by_name(self, tab_name):
        """지정된 이름의 탭으로 전환합니다."""
        if self.tab_widget is not None:
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == tab_name:
                    self.tab_widget.setCurrentIndex(i)
                    # on_tab_changed에서 이미 로그를 남기므로 중복을 피하기 위해 주석 처리
                    # self.app_instance.log_message(f"ℹ️ '{tab_name}' 탭으로 이동했습니다.", "INFO")
                    return
        elif self.tree_navigation is not None:
            if hasattr(self.tree_navigation, "select_tab_by_name"):
                self.tree_navigation.select_tab_by_name(tab_name)
                # self.app_instance.log_message(f"ℹ️ '{tab_name}' 탭으로 이동했습니다.", "INFO")
                return

        QMessageBox.warning(self, "경고", f"'{tab_name}' 탭을 찾을 수 없습니다.")
        self.app_instance.log_message(
            f"⚠️ '{tab_name}' 탭을 찾을 수 없습니다.", "WARNING"
        )

    # ✅ [수정] 메뉴 항목과 탭을 연결합니다.
    def marc_extract(self):
        self.switch_to_tab_by_name("MARC 추출")

    def search_nlk(self):
        self.switch_to_tab_by_name("NLK 검색")

    def search_lc(self):
        # "LC 검색" 메뉴는 "Western 검색" 탭을 열도록 잠정적으로 연결합니다.
        self.switch_to_tab_by_name("Western 검색")

    def search_ndl(self):
        self.switch_to_tab_by_name("NDL + CiNii 검색")

    def search_western(self):
        self.switch_to_tab_by_name("Western 검색")

    def search_global(self):
        self.switch_to_tab_by_name("Global 통합검색")

    def search_bne(self):
        self.switch_to_tab_by_name("납본 ID 검색")

    def search_google(self):
        # "Google Books"에 해당하는 탭이 없습니다. 필요시 추가해야 합니다.
        self.app_instance.log_message(
            "Google Books 탭은 아직 구현되지 않았습니다.", "WARNING"
        )

    def search_authorities(self):
        self.switch_to_tab_by_name("저자전거 검색")

    def show_detailed_works(self):
        self.switch_to_tab_by_name("상세 저작물 정보")

    def show_brief_works(self):
        self.switch_to_tab_by_name("간략 저작물 정보")

    def search_ksh_hybrid(self):
        self.switch_to_tab_by_name("KSH Hybrid")

    def search_ksh_local(self):
        self.switch_to_tab_by_name("KSH Local")

    def search_dewey(self):
        self.switch_to_tab_by_name("Dewey 분류 검색")

    def search_naver(self):
        # "네이버 책 검색" 메뉴는 "AI 피드" 탭을 열도록 연결합니다.
        self.switch_to_tab_by_name("AI 피드")

    def search_gemini_ddc(self):
        self.switch_to_tab_by_name("Gemini DDC 분류")

    def python_test(self):
        self.switch_to_tab_by_name("🐍 Python")

    def on_tab_changed(self, index):
        """✅ [모델/뷰 전환] 탭 변경 이벤트"""
        tab_name = self.tab_widget.tabText(index)
        clean_name = tab_name.replace("📚 ", "").replace("🇯🇵 ", "").replace("🇩🇪 ", "")
        self.app_instance.log_message(f"'{clean_name}' 탭으로 전환되었습니다.", "INFO")

        current_tab = self.get_current_tab()

        # [핵심 추가] 탭 변경 시 첫 번째 검색창에 자동 포커스
        if hasattr(current_tab, "set_initial_focus"):
            current_tab.set_initial_focus()

        if hasattr(current_tab, "table_view"):
            self.app_instance.log_message(
                f"✅ 모델/뷰 기반 탭 활성화: {clean_name}", "DEBUG"
            )
        elif hasattr(current_tab, "tree_widget"):
            self.app_instance.log_message(
                f"⚠️ 구버전 탭 감지: {clean_name} (향후 모델/뷰로 전환 예정)", "WARNING"
            )

        # [핵심 수정] 현재 활성화된 탭의 status_label을 직접 업데이트합니다.
        if hasattr(current_tab, "status_label"):
            current_tab.status_label.setText(f"현재 탭: {clean_name}")

    def append_log(self, message, level="INFO"):
        """로그 디스플레이에 메시지 추가"""
        from ui_constants import UI_CONSTANTS

        U = UI_CONSTANTS  # UI 상수 가져오기

        # ✅ 색상 설정 - 테마별로 다른 색상 사용
        if U.BACKGROUND_PRIMARY == "#0e111a":  # Dark theme
            color_map = {
                "ERROR": "#D84040",
                "WARNING": "#ff7300",
                "INFO": "#4EC9B0",
                "DEBUG": "#888888",
            }
            timestamp_color = "#888888"
        else:  # Light theme
            color_map = {
                "ERROR": "#C41E3A",
                "WARNING": "#D97706",
                "INFO": "#0369A1",
                "DEBUG": "#6B7280",
            }
            timestamp_color = "#6B7280"

        color = color_map.get(level, U.TEXT_SUBDUED)

        # ✅ [수정] 올바른 Qt DateTime 사용
        from PySide6.QtCore import QDateTime

        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")

        # ✅ [핵심 수정] 메시지 내용에 linkify_text를 적용하여 URL을 링크로 변환합니다.
        linked_message = linkify_text(message)

        # ✅ [최종 수정] linkify_text가 만든 <a> 태그에 인라인 스타일을 강제 삽입합니다.
        link_style = f'style="color: {U.ACCENT_BLUE}; text-decoration: none;"'
        linked_message = linked_message.replace("<a href=", f"<a {link_style} href=")

        # KSH/KAC 마크업을 HTML로 변환 (로그 가독성 향상)
        ksh_pattern = re.compile(r"▼a(.*?)▼0(KSH\d+?)▲")
        linked_message = ksh_pattern.sub(
            r'<span style="color: #6a9955; font-weight: bold;">\1</span> <span style="color: #569cd6;">[\2]</span>',
            linked_message,
        )

        html_message = f'<span style="color: {timestamp_color};">[{timestamp}]</span> <span style="color: {color};">[{level}]</span> {linked_message}'

        self.log_display.append(html_message)

        # 자동 스크롤
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_display.setTextCursor(cursor)

    def get_current_tab(self):
        """✅ [수정] 현재 활성 탭 반환 (탭 모드 + 트리뷰 모드 모두 지원)"""
        if self.tab_widget is not None:
            # 탭 모드
            current_index = self.tab_widget.currentIndex()
            return self.tab_widget.widget(current_index)
        elif self.tree_navigation is not None:
            # 트리뷰 모드
            return self.tree_navigation.current_tab_widget
        return None

    def get_tab_by_name(self, name):
        """✅ [수정] 이름으로 탭 위젯 인스턴스를 찾습니다. (탭 모드 + 트리메뉴 모드 모두 지원)"""
        if self.tab_widget is not None:
            # 탭 모드
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == name:
                    return self.tab_widget.widget(i)
        elif self.tree_navigation is not None:
            # 트리메뉴 모드: 사전 로딩된 탭 찾기
            # ✅ [수정] 사전 로딩 도입으로 모든 탭이 이미 생성되어 있음
            # 자동 생성 로직 제거 (불필요)
            if hasattr(self.tree_navigation, "tab_widgets"):
                return self.tree_navigation.tab_widgets.get(name)
        return None

    # 메뉴 액션들

    def open_settings(self):
        """설정 탭으로 이동"""
        if self.tab_widget is not None:
            # 일반 탭 모드: Settings 탭 찾기
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == "설정":
                    self.tab_widget.setCurrentIndex(i)
                    self.app_instance.log_message("ℹ️ 설정 탭으로 이동했습니다.", "INFO")
                    return
        elif self.tree_navigation is not None:
            # 트리메뉴 모드: 트리에서 Settings 탭 선택
            self.tree_navigation.select_tab_by_name("설정")
            self.app_instance.log_message("ℹ️ 설정 탭으로 이동했습니다.", "INFO")
            return

        # 찾지 못한 경우
        QMessageBox.warning(self, "경고", "설정 탭을 찾을 수 없습니다.")
        self.app_instance.log_message("⚠️ 설정 탭을 찾을 수 없습니다.", "WARNING")

    def clear_log(self):
        """로그 지우기"""
        self.log_display.clear()
        self.app_instance.log_message("로그가 지워졌습니다.", "INFO")

    def check_db_status(self):
        """데이터베이스 상태 확인"""
        if self.app_instance.db_manager:
            msg_box = QMessageBox(parent=None)
            msg_box.setWindowTitle("데이터베이스 상태")
            msg_box.setText("데이터베이스가 정상적으로 연결되어 있습니다.")
            msg_box.setIcon(QMessageBox.Icon.Information)
            apply_dark_title_bar(msg_box)
            enable_modal_close_on_outside_click(msg_box)
            msg_box.exec()
        else:
            msg_box = QMessageBox(parent=None)
            msg_box.setWindowTitle("데이터베이스 상태")
            msg_box.setText("데이터베이스 연결에 문제가 있습니다.")
            msg_box.setIcon(QMessageBox.Icon.Warning)
            apply_dark_title_bar(msg_box)
            enable_modal_close_on_outside_click(msg_box)
            msg_box.exec()

    def show_db_statistics(self):
        """데이터베이스 현황 통계를 메시지 박스로 표시합니다."""
        if not self.app_instance.db_manager:
            QMessageBox.warning(
                self, "오류", "데이터베이스 관리자가 초기화되지 않았습니다."
            )
            return

        stats = self.app_instance.db_manager.get_all_db_statistics()

        message = "<h3>🗄️ 데이터베이스 현황</h3>"

        # KSH 개념 DB
        concepts = stats.get("concepts_db", {})
        if "error" in concepts:
            message += f"<p><b>KSH 개념 DB:</b> <span style='color:red;'>오류</span><br><small>경로: {concepts.get('path')}</small></p>"
        else:
            count = concepts.get("ksh_concept_count", 0)
            message += f"<p><b>KSH 개념 DB:</b> {count:,} 개의 KSH 개념<br><small>경로: {concepts.get('path')}</small></p>"

        # 서지 매핑 DB
        mapping = stats.get("mapping_db", {})
        if "error" in mapping:
            message += f"<p><b>서지 매핑 DB:</b> <span style='color:red;'>오류</span><br><small>경로: {mapping.get('path')}</small></p>"
        else:
            count = mapping.get("biblio_count", 0)
            message += f"<p><b>서지 매핑 DB:</b> {count:,} 개의 서지 데이터<br><small>경로: {mapping.get('path')}</small></p>"

        # DDC 캐시 DB
        dewey = stats.get("dewey_cache_db", {})
        if "error" in dewey:
            message += f"<p><b>DDC 캐시 DB:</b> <span style='color:red;'>오류</span><br><small>경로: {dewey.get('path')}</small></p>"
        else:
            ds = dewey.get("stats", {})
            entries = ds.get("total_entries", 0)
            size_mb = ds.get("total_size_mb", 0)
            message += f"<p><b>DDC 캐시 DB:</b> {entries:,} 개 항목 ({size_mb} MB)<br><small>경로: {dewey.get('path')}</small></p>"

        # 용어/설정 DB
        glossary = stats.get("glossary_db", {})
        if "error" in glossary:
            message += f"<p><b>용어/설정 DB:</b> <span style='color:red;'>오류</span><br><small>경로: {glossary.get('path')}</small></p>"
        else:
            trans = glossary.get("translation_count", 0)
            settings = glossary.get("settings_count", 0)
            message += f"<p><b>용어/설정 DB:</b> 용어 {trans:,} 개, 설정 {settings:,} 개<br><small>경로: {glossary.get('path')}</small></p>"

        msg_box = QMessageBox(parent=self)
        msg_box.setWindowTitle("데이터베이스 현황")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Information)
        apply_dark_title_bar(msg_box)
        enable_modal_close_on_outside_click(msg_box)
        msg_box.exec()

    def show_about(self):
        """정보 창"""
        about_text = """
        <h3>통합 서지검색 시스템</h3>
        <p><b>버전:</b> 2.0.0 (Qt 전용)</p>
        <p><b>개발:</b> Claude & 메르카츠</p>
        <p><b>기술스택:</b> Python, PySide6, SQLite</p>
        <p><b>설명:</b> 다양한 도서관 시스템을 통합 검색하는 도구</p>
        """
        msg_box = QMessageBox(parent=None)
        msg_box.setWindowTitle("정보")
        msg_box.setText(about_text)
        msg_box.setIcon(QMessageBox.Icon.Information)

        # ✅ [추가] 외부 클릭 시 닫기 기능 적용
        enable_modal_close_on_outside_click(msg_box)
        # ✅ [추가] 메시지 박스에 다크 타이틀바 적용 함수를 호출합니다.
        apply_dark_title_bar(msg_box)

        msg_box.exec()

    def find_next(self):
        """✅ [모델/뷰 전환] 현재 활성 탭의 다음 찾기"""
        current_tab = self.get_current_tab()

        # ✅ [모델/뷰 우선] BaseSearchTab 기반 탭 처리
        if hasattr(current_tab, "find_in_results"):
            current_tab.find_in_results("forward")
            return

        # ✅ [디버그] 찾기 기능이 없는 탭
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(
                "현재 탭에서 찾기 기능을 지원하지 않습니다.", "WARNING"
            )

    def find_prev(self):
        """✅ [모델/뷰 전환] 현재 활성 탭의 이전 찾기"""
        current_tab = self.get_current_tab()

        # ✅ [모델/뷰 우선] BaseSearchTab 기반 탭 처리
        if hasattr(current_tab, "find_in_results"):
            current_tab.find_in_results("backward")
            return

        # ✅ [디버그] 찾기 기능이 없는 탭
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(
                "현재 탭에서 찾기 기능을 지원하지 않습니다.", "WARNING"
            )

    # [핵심] 메뉴바의 보이기/숨기기 상태를 전환하는 함수를 추가합니다.
    def toggle_menu_bar_visibility(self):
        """메뉴바를 보이거나 숨깁니다."""
        menu_bar = self.menuBar()
        menu_bar.setVisible(not menu_bar.isVisible())

    # [최종] 전체 하단 UI의 표시 상태를 업데이트하는 단일 함수
    def refresh_bottom_widgets(self):
        """
        self.is_detail_visible와 self.is_log_visible 상태 변수를 기반으로
        UI의 표시 여부를 한 번에 올바르게 업데이트합니다.
        """
        if not (hasattr(self, "detail_group") and hasattr(self, "log_group")):
            return

        # 1. 상태 변수에 따라 각 위젯의 가시성 설정
        self.detail_group.setVisible(self.is_detail_visible)
        self.log_group.setVisible(self.is_log_visible)

        # 2. 둘 중 하나라도 '보여야 할 상태'라면 부모 컨테이너를 표시
        should_parent_be_visible = self.is_detail_visible or self.is_log_visible
        if hasattr(self, "bottom_container"):
            self.bottom_container.setVisible(should_parent_be_visible)

    # ✅ [추가] F9 단축키가 호출할 새로운 메서드를 추가합니다.
    def toggle_tab_bar_visibility(self):
        """탭바를 보이거나 숨깁니다."""
        if hasattr(self, "tab_widget"):
            tab_bar = self.tab_widget.tabBar()
            is_visible = tab_bar.isVisible()
            tab_bar.setVisible(not is_visible)
            status = "숨김" if is_visible else "표시"
            self.app_instance.log_message(
                f"ℹ️ 탭바를 {status} 처리했습니다. (F9)", "INFO"
            )

    # [최종] 상세 정보창 상태를 전환하는 함수
    def toggle_detail_visibility(self):
        """상세 정보창의 '보임/숨김' 상태 변수만 변경하고 UI 업데이트를 요청합니다."""
        if not hasattr(self, "detail_group"):
            return

        # 실제 UI를 직접 제어하는 대신, 상태 변수의 값만 뒤집습니다.
        self.is_detail_visible = not self.is_detail_visible

        # 상태 변수를 기반으로 UI를 새로고침하는 함수를 호출합니다.
        self.refresh_bottom_widgets()

    # [최종] 로그창 상태를 전환하는 함수
    def toggle_log_visibility(self):
        """로그창의 '보임/숨김' 상태 변수만 변경하고 UI 업데이트를 요청합니다."""
        if not hasattr(self, "log_group"):
            return

        self.is_log_visible = not self.is_log_visible
        self.refresh_bottom_widgets()

    # ✅ [추가] F7 단축키가 호출할 메서드를 추가합니다.
    def toggle_find_area_visibility(self):
        """현재 활성화된 탭의 찾기(Find) 영역 표시/숨김을 토글합니다."""
        current_tab = self.get_current_tab()
        if hasattr(current_tab, "toggle_find_area_visibility"):
            current_tab.toggle_find_area_visibility()

    # [핵심 추가] F8 단축키를 위한 통합 토글 함수
    def toggle_all_visibility(self):
        """F10, F11, F12 기능을 동시에 실행하여 전체 화면 모드를 구현합니다."""

        # 1. 메뉴바 토글 (F10)
        self.toggle_menu_bar_visibility()

        # ✅ [추가] 찾기 영역 토글 (F7) 기능을 여기에 추가합니다.
        self.toggle_find_area_visibility()

        # 2. 상세 정보창 토글 (F11)
        self.toggle_detail_visibility()

        # 3. 로그창 토글 (F12)
        # (toggle_detail_visibility와 toggle_log_visibility 내부에서
        # refresh_bottom_widgets가 호출되므로 순서대로 호출해도 무방합니다.)
        self.toggle_log_visibility()

        # 로그 메시지 출력 (사용자 피드백)
        self.app_instance.log_message(
            "F8 전체 화면 모드 토글: 메뉴바/찾기/로그/상세 정보 표시 상태 변경", "INFO"
        )

    # ============================================================================
    # 레이아웃 설정 저장/복구 메서드
    # ============================================================================

    def restore_layout_settings(self):
        """
        저장된 레이아웃 설정을 복구합니다. (앱 시작 시 호출)
        탭 모드와 트리메뉴 모드 모두 지원합니다.
        """
        try:
            # ✅ 탭 이름 리스트 가져오기 (탭 모드 또는 트리메뉴 모드)
            tab_names = []
            tabs_dict = {}  # 탭 이름 -> 탭 위젯 매핑

            if hasattr(self, "tab_widget") and self.tab_widget:
                # 탭 모드
                for i in range(self.tab_widget.count()):
                    tab_name = self.tab_widget.tabText(i)
                    tab_names.append(tab_name)
                    tabs_dict[tab_name] = self.tab_widget.widget(i)
            elif hasattr(self, "tree_menu_navigation") and self.tree_menu_navigation:
                # 트리메뉴 모드
                tabs_dict = self.tree_menu_navigation.tab_widgets
                tab_names = list(tabs_dict.keys())

            # 메인 스플리터 설정 복구
            if hasattr(self, "main_splitter"):
                sizes = self.layout_settings_manager.load_splitter_sizes(
                    "MainWindow", "main", [700, 300]
                )
                if sizes:
                    self.main_splitter.setSizes(sizes)
                    self.app_instance.log_message(
                        f"✅ 메인 스플리터 복구: {sizes}", "INFO"
                    )

            # 하단 스플리터 설정 복구
            if hasattr(self, "bottom_splitter"):
                sizes = self.layout_settings_manager.load_splitter_sizes(
                    "MainWindow", "bottom", [1, 1]
                )
                if sizes:
                    # QSplitter는 상대 비율로 설정하기 위해 실제 크기를 계산
                    total_width = self.bottom_splitter.width()
                    if total_width > 0:
                        actual_sizes = [
                            int(total_width * s / sum(sizes)) for s in sizes
                        ]
                        self.bottom_splitter.setSizes(actual_sizes)

            # ✅ 각 탭의 QSplitter 설정 복구 (탭 모드/트리메뉴 모드 공통)
            if tab_names:
                for tab_name in tab_names:
                    tab = tabs_dict.get(tab_name)
                    if not tab:
                        continue

                    # Gemini 탭: main_splitter
                    if hasattr(tab, "main_splitter"):
                        sizes = self.layout_settings_manager.load_splitter_sizes(
                            tab_name, "main", [400, 200]
                        )
                        if sizes:
                            tab.main_splitter.setSizes(sizes)

                    # KSH_Local 탭: results_splitter
                    if hasattr(tab, "results_splitter"):
                        sizes = self.layout_settings_manager.load_splitter_sizes(
                            tab_name, "results", [500, 500]
                        )
                        if sizes:
                            tab.results_splitter.setSizes(sizes)

                    # MARC_Extractor 탭: v_splitter, h_splitter
                    if hasattr(tab, "v_splitter"):
                        sizes = self.layout_settings_manager.load_splitter_sizes(
                            tab_name, "vertical", [350, 450]
                        )
                        if sizes:
                            tab.v_splitter.setSizes(sizes)

                    if hasattr(tab, "h_splitter"):
                        sizes = self.layout_settings_manager.load_splitter_sizes(
                            tab_name, "horizontal", [500, 500]
                        )
                        if sizes:
                            tab.h_splitter.setSizes(sizes)

                    # Dewey 탭: master_splitter, left_content_splitter, right_content_splitter
                    if hasattr(tab, "master_splitter"):
                        sizes = self.layout_settings_manager.load_splitter_sizes(
                            tab_name, "master", [600, 800]
                        )
                        if sizes:
                            tab.master_splitter.setSizes(sizes)

                    if hasattr(tab, "left_content_splitter"):
                        sizes = self.layout_settings_manager.load_splitter_sizes(
                            tab_name, "left_content", [500, 300]
                        )
                        if sizes:
                            tab.left_content_splitter.setSizes(sizes)

                    if hasattr(tab, "right_content_splitter"):
                        sizes = self.layout_settings_manager.load_splitter_sizes(
                            tab_name, "right_content", [500, 300]
                        )
                        if sizes:
                            tab.right_content_splitter.setSizes(sizes)
            else:
                self.app_instance.log_message(
                    "ℹ️ 트리메뉴 모드: 탭 스플리터 설정은 탭 생성 시 개별 복구됩니다.",
                    "INFO",
                )

            # 위젯 표시/숨김 설정 복구
            widget_config = self.layout_settings_manager.load_widget_visibility(
                "MainWindow",
                {
                    "detail_panel": True,
                    "log_panel": True,
                    "menu_bar": True,
                    "tab_bar": True,
                },
            )

            if widget_config:
                # 상세 정보 (F11)
                if "detail_panel" in widget_config:
                    self.is_detail_visible = widget_config["detail_panel"]
                    if hasattr(self, "detail_group"):
                        self.detail_group.setVisible(self.is_detail_visible)

                # 로그 (F12)
                if "log_panel" in widget_config:
                    self.is_log_visible = widget_config["log_panel"]
                    if hasattr(self, "log_group"):
                        self.log_group.setVisible(self.is_log_visible)

                # 메뉴바 (F10)
                if "menu_bar" in widget_config and not widget_config["menu_bar"]:
                    self.menuBar().setVisible(False)

                # 탭바 (F9)
                if "tab_bar" in widget_config and not widget_config["tab_bar"]:
                    if hasattr(self, "tab_widget"):
                        self.tab_widget.tabBar().setVisible(False)

            self.app_instance.log_message("✅ 레이아웃 설정 복구 완료", "INFO")

        except Exception as e:
            self.app_instance.log_message(f"❌ 레이아웃 설정 복구 실패: {e}", "ERROR")

    def save_layout_settings(self):
        """
        현재 레이아웃 설정을 저장합니다. (앱 종료 시 호출)
        탭 모드와 트리메뉴 모드 모두 지원합니다.
        """
        try:
            # 메인 윈도우 스플리터 크기 저장
            if hasattr(self, "main_splitter"):
                sizes = self.main_splitter.sizes()
                self.layout_settings_manager.save_splitter_sizes(
                    "MainWindow", "main", sizes
                )

            # 하단 스플리터 비율 저장
            if hasattr(self, "bottom_splitter"):
                sizes = self.bottom_splitter.sizes()
                self.layout_settings_manager.save_splitter_sizes(
                    "MainWindow", "bottom", sizes
                )

            # ✅ 탭 정보 가져오기 (탭 모드 또는 트리메뉴 모드)
            tabs_dict = {}
            if hasattr(self, "tab_widget") and self.tab_widget:
                # 탭 모드
                for i in range(self.tab_widget.count()):
                    tab_name = self.tab_widget.tabText(i)
                    tabs_dict[tab_name] = self.tab_widget.widget(i)
            elif hasattr(self, "tree_menu_navigation") and self.tree_menu_navigation:
                # 트리메뉴 모드
                tabs_dict = self.tree_menu_navigation.tab_widgets

            # ✅ 각 탭의 QSplitter 설정 저장 (탭 모드/트리메뉴 모드 공통)
            for tab_name, tab in tabs_dict.items():
                # Gemini 탭: main_splitter
                if hasattr(tab, "main_splitter"):
                    sizes = tab.main_splitter.sizes()
                    self.layout_settings_manager.save_splitter_sizes(
                        tab_name, "main", sizes
                    )

                # KSH_Local 탭: results_splitter
                if hasattr(tab, "results_splitter"):
                    sizes = tab.results_splitter.sizes()
                    self.layout_settings_manager.save_splitter_sizes(
                        tab_name, "results", sizes
                    )

                # MARC_Extractor 탭: v_splitter, h_splitter
                if hasattr(tab, "v_splitter"):
                    sizes = tab.v_splitter.sizes()
                    self.layout_settings_manager.save_splitter_sizes(
                        tab_name, "vertical", sizes
                    )

                if hasattr(tab, "h_splitter"):
                    sizes = tab.h_splitter.sizes()
                    self.layout_settings_manager.save_splitter_sizes(
                        tab_name, "horizontal", sizes
                    )

                # Dewey 탭: master_splitter, left_content_splitter, right_content_splitter
                if hasattr(tab, "master_splitter"):
                    sizes = tab.master_splitter.sizes()
                    self.layout_settings_manager.save_splitter_sizes(
                        tab_name, "master", sizes
                    )

                if hasattr(tab, "left_content_splitter"):
                    sizes = tab.left_content_splitter.sizes()
                    self.layout_settings_manager.save_splitter_sizes(
                        tab_name, "left_content", sizes
                    )

                if hasattr(tab, "right_content_splitter"):
                    sizes = tab.right_content_splitter.sizes()
                    self.layout_settings_manager.save_splitter_sizes(
                        tab_name, "right_content", sizes
                    )

            # 위젯 표시/숨김 상태 저장
            widget_config = {
                "detail_panel": self.is_detail_visible,
                "log_panel": self.is_log_visible,
                "menu_bar": self.menuBar().isVisible(),
                "tab_bar": (
                    self.tab_widget.tabBar().isVisible()
                    if hasattr(self, "tab_widget") and self.tab_widget
                    else True
                ),
            }

            self.layout_settings_manager.save_widget_visibility(
                "MainWindow", widget_config
            )

            self.app_instance.log_message("✅ 레이아웃 설정 저장 완료", "INFO")

        except Exception as e:
            self.app_instance.log_message(f"❌ 레이아웃 설정 저장 실패: {e}", "ERROR")

    # ============================================================================
    # 기존 메서드들
    # ============================================================================

    # ✅ [추가] 현재 활성화된 탭의 프로그레스 바를 업데이트하는 슬롯 메서드
    def update_current_tab_progress(self, value):
        """현재 활성화된 탭의 프로그레스 바 값을 업데이트합니다."""
        current_tab = self.get_current_tab()
        if hasattr(current_tab, "progress_bar"):
            # 프로그레스 바가 숨겨져 있다면 보이도록 설정
            if not current_tab.progress_bar.isVisible():
                current_tab.progress_bar.setVisible(True)
            current_tab.progress_bar.setValue(value)

    # ✅ [추가] 저자전거 -> 간략 저작물 탭 연동을 위한 중계 메서드
    def handle_kac_to_brief_works_search(self, kac_code):
        """'저자전거' 탭에서 받은 KAC 코드로 '간략 저작물 정보' 탭에서 검색을 실행합니다."""
        target_tab_name = "간략 저작물 정보"  # qt_Tab_configs.py에 정의된 이름
        brief_works_tab = None

        # 1. '간략 저작물 정보' 탭 찾기
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == target_tab_name:
                brief_works_tab = self.tab_widget.widget(i)
                # 2. 해당 탭으로 화면 전환
                self.tab_widget.setCurrentWidget(brief_works_tab)
                break

        # 3. 해당 탭의 검색 실행 메서드 호출
        if brief_works_tab and hasattr(brief_works_tab, "search_by_kac_code"):
            brief_works_tab.search_by_kac_code(kac_code)
            self.app_instance.log_message(
                f"✅ KAC 연동: '{kac_code}'로 간략 저작물 검색을 시작합니다."
            )
        else:
            self.app_instance.log_message(
                f"❌ KAC 연동 실패: '{target_tab_name}' 탭을 찾을 수 없습니다.",
                level="ERROR",
            )

    def closeEvent(self, event):
        """✅ [신규 추가] 앱 종료 시 리소스 정리"""
        try:
            # 0. ✅ [추가] 레이아웃 설정 저장
            if hasattr(self, "layout_settings_manager"):
                self.save_layout_settings()

            # 1. 검색 스레드 중지
            if hasattr(self.app_instance, "stop_search_flag"):
                self.app_instance.stop_search_flag.set()

            # 2. ✅ [추가] 모든 탭의 스레드 정리
            # 탭 모드와 트리메뉴 모드 구분
            if hasattr(self, "tab_widget") and self.tab_widget:
                # 일반 탭 모드
                for i in range(self.tab_widget.count()):
                    self._cleanup_tab_thread(self.tab_widget.widget(i))

            elif hasattr(self, "tree_navigation") and self.tree_navigation:
                # 트리메뉴 모드
                for tab_name, tab_widget in self.tree_navigation.tab_widgets.items():
                    self._cleanup_tab_thread(tab_widget)

            # 3. ✅ [추가] Flask API 서버 종료
            if (
                hasattr(self.app_instance, "api_server")
                and self.app_instance.api_server
            ):
                self.app_instance.log_message("🛑 API 서버 종료 중...", "INFO")
                self.app_instance.api_server.stop_server()

            # 4. ✅ [추가] 워커 스레드 정리 (Dewey 캐시 쓰기, 키워드 추출 등)
            if (
                hasattr(self.app_instance, "db_manager")
                and self.app_instance.db_manager
            ):
                self.app_instance.log_message("🛑 워커 스레드 종료 중...", "INFO")
                self.app_instance.db_manager.close_connections()

            # 5. 로그 메시지
            self.app_instance.log_message(
                "✅ 앱 종료: 모든 리소스가 정리되었습니다.", "INFO"
            )

            # 5. 설정 저장 (필요시)
            # self.save_window_state()

        except Exception as e:
            print(f"❌ 종료 시 오류: {e}")
        finally:
            # 이벤트 수락 (앱 종료 계속 진행)
            event.accept()

    def _cleanup_tab_thread(self, tab_widget):
        """지정된 탭 위젯의 스레드를 안전하게 정리합니다."""
        # 1. cleanup_all_threads 메서드가 있는 탭 우선 처리 (가장 안전)
        if hasattr(tab_widget, "cleanup_all_threads") and callable(
            getattr(tab_widget, "cleanup_all_threads")
        ):
            tab_widget.cleanup_all_threads()
        # 2. BaseSearchTab 기반 탭의 search_thread 처리
        elif hasattr(tab_widget, "search_thread") and tab_widget.search_thread:
            if tab_widget.search_thread.isRunning():
                if hasattr(tab_widget.search_thread, "cancel_search"):
                    tab_widget.search_thread.cancel_search()
                tab_widget.search_thread.wait(2000)  # 최대 2초 대기


def main():
    """메인 실행 함수"""
    app = IntegratedSearchApp()
    app.run()


if __name__ == "__main__":
    main()
