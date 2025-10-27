# -*- coding: utf-8 -*-
"""
qt_api_settings.py - Qt/PySide6용 API 설정 관련 UI 통합 모듈
Version: v1.1.2 - X 버튼 닫기 기능 수정
생성일: 2025-09-29
수정일: 2025-10-27
- 하드코딩된 색상을 UI 상수로 변경, 테마 전환 대응
- X 버튼 클릭 시 다이얼로그가 닫히도록 윈도우 플래그 수정

api_settings_ui.py의 Qt 버전 - PySide6로 완전 포팅
모든 API 설정 모달창과 상태 관리 UI를 중앙에서 관리합니다.
- 네이버 책 API (클라이언트 ID + 시크릿)
- NLK OpenAPI
- Google Books API
- Gemini API
- Dewey Linked Data API(DDC)
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QMessageBox,
)
from PySide6.QtCore import Qt
from ui_constants import U
import requests
import base64
from qt_utils import apply_dark_title_bar
from qt_utils import enable_modal_close_on_outside_click


def show_api_settings_modal(tab_name, db_manager, app_instance, parent_window=None):
    """
    탭별 API 설정 모달 창을 표시합니다. (Qt 버전)

    Args:
        tab_name (str): 탭 이름 ('네이버', 'NLK', 'Google', 'Gemini', 'Web Dewey')
        db_manager (DatabaseManager): 데이터베이스 매니저 인스턴스
        app_instance: GUI 애플리케이션 인스턴스
        parent_window: 부모 창 (None이면 app_instance.main_window 사용)
    """

    # ✅ 탭 이름 정규화
    def _normalize_tab_name(name: str) -> str:
        n = (name or "").strip().lower()
        if n in {"ddc", "dewey", "dewey 분류 검색", "web dewey", "webdewey"}:
            return "Web Dewey"
        elif n in {"gemini"}:
            return "Gemini"
        elif n in {"google", "google books"}:
            return "Google"
        elif n in {"nlk", "납본 ID 검색"}:
            return "NLK"
        elif n in {"네이버", "naver"}:
            return "네이버"
        return name

    normalized_tab = _normalize_tab_name(tab_name)

    # ✅ API 설정 정의
    api_settings = {
        "네이버": {
            "desc_text": "네이버 개발자 센터에서 발급받은 API 인증 정보를 입력해주세요.",
            "keys_info": [
                {
                    "label": "클라이언트 ID",
                    "placeholder": "네이버 클라이언트 ID",
                    "is_secret": False,
                },
                {
                    "label": "클라이언트 시크릿",
                    "placeholder": "네이버 클라이언트 시크릿",
                    "is_secret": True,
                },
            ],
            "get_func": db_manager.get_naver_api_credentials,
            "set_func": db_manager.set_naver_api_credentials,
            "delete_func": db_manager.delete_naver_api_credentials,
            "test_url": "https://openapi.naver.com/v1/search/book.xml?query=test&display=1",
            "test_headers": lambda keys: {
                "X-Naver-Client-Id": keys[0],
                "X-Naver-Client-Secret": keys[1],
            },
        },
        "NLK": {
            "desc_text": "국립중앙도서관 OpenAPI에서 발급받은 API 키를 입력해주세요.",
            "keys_info": [
                {"label": "API 키", "placeholder": "NLK OpenAPI 키", "is_secret": True},
            ],
            "get_func": db_manager.get_nlk_api_key,
            "set_func": db_manager.set_nlk_api_key,
            "delete_func": db_manager.delete_nlk_api_key,
            "test_url": "https://www.nl.go.kr/NL/search/openApi/search.do?key={key}&pageSize=1",
            "test_headers": None,
        },
        "Google": {
            "desc_text": "Google Cloud Console에서 발급받은 API 키를 입력해주세요.",
            "keys_info": [
                {
                    "label": "API 키",
                    "placeholder": "Google Books API 키",
                    "is_secret": True,
                },
            ],
            "get_func": db_manager.get_google_api_key,
            "set_func": db_manager.set_google_api_key,
            "delete_func": db_manager.delete_google_api_key,
            "test_url": "https://www.googleapis.com/books/v1/volumes?q=test&key={key}&maxResults=1",
            "test_headers": None,
        },
        "Gemini": {
            "desc_text": "Google AI Studio에서 발급받은 Gemini API 키를 입력해주세요.",
            "keys_info": [
                {"label": "API 키", "placeholder": "Gemini API 키", "is_secret": True},
            ],
            "get_func": db_manager.get_gemini_api_key,
            "set_func": db_manager.set_gemini_api_key,
            "delete_func": db_manager.delete_gemini_api_key,
            "test_url": "https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            "test_headers": None,
        },
        "Web Dewey": {
            "desc_text": "OCLC API Console에서 발급받은 DLD API 자격증명을 입력해주세요.",
            "keys_info": [
                {
                    "label": "클라이언트 ID",
                    "placeholder": "Dewey Client ID",
                    "is_secret": False,
                },
                {
                    "label": "클라이언트 시크릿",
                    "placeholder": "Dewey Client Secret",
                    "is_secret": True,
                },
            ],
            "get_func": db_manager.get_dewey_api_credentials,
            "set_func": db_manager.set_dewey_api_credentials,
            "delete_func": db_manager.delete_dewey_api_credentials,
            "test_url": "https://oauth.oclc.org/token",
            "test_headers": {},
        },
    }

    if normalized_tab in api_settings:
        settings = api_settings[normalized_tab]
        # ✅ [수정] 다이얼로그 참조를 저장하여 가비지 컬렉션 방지
        dialog = _create_qt_api_settings_dialog(
            parent_window
            or (
                app_instance.main_window
                if hasattr(app_instance, "main_window")
                else None
            ),
            db_manager,
            app_instance,
            tab_name=normalized_tab,
            desc_text=settings["desc_text"],
            keys_info=settings["keys_info"],
            get_func=settings["get_func"],
            set_func=settings["set_func"],
            delete_func=settings["delete_func"],
            test_url=settings["test_url"],
            test_headers=settings["test_headers"],
        )
        # 앱 인스턴스의 open_dialogs 리스트에 저장
        if not hasattr(app_instance, '_open_dialogs'):
            app_instance._open_dialogs = []
        app_instance._open_dialogs.append(dialog)
        # 다이얼로그 닫혔을 때 리스트에서 제거
        dialog.finished.connect(lambda: app_instance._open_dialogs.remove(dialog) if dialog in app_instance._open_dialogs else None)
    else:
        QMessageBox.warning(
            parent_window, "지원하지 않음", f"'{tab_name}' 탭은 아직 지원되지 않습니다."
        )


def _create_qt_api_settings_dialog(
    parent,
    db_manager,
    app_instance,
    tab_name,
    desc_text,
    keys_info,
    get_func,
    set_func,
    delete_func,
    test_url,
    test_headers=None,
):
    """Qt API 설정 다이얼로그를 생성합니다."""

    dialog = QDialog(parent)
    dialog.setWindowTitle(f"{tab_name} API 설정")
    dialog.setFixedSize(600, 400)
    # ✅ [수정] 모달이 아닌 모드리스 창으로 변경하여 Alt+Tab 시에도 유지
    dialog.setModal(False)
    # ✅ [수정] 윈도우 플래그 설정: 닫기 버튼 포함
    # Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint로 닫기 버튼 활성화
    dialog.setWindowFlags(
        Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint
    )

    # ✅ 닫기 이벤트 처리: X 버튼 클릭 시 다이얼로그 닫기
    dialog.setAttribute(Qt.WA_DeleteOnClose, False)  # 닫아도 객체 유지

    # 메인 레이아웃
    main_layout = QVBoxLayout(dialog)
    main_layout.setContentsMargins(20, 20, 20, 20)
    main_layout.setSpacing(15)

    # 제목
    title_label = QLabel(f"{tab_name} API 설정")
    title_label.setStyleSheet(
        f"font-size: {U.FONT_SIZE_LARGE}pt; font-weight: bold;"
    )
    # ✅ 색상은 전역 스타일시트에서 상속받도록 함 (테마 대응)
    title_label.setAlignment(Qt.AlignCenter)
    main_layout.addWidget(title_label)

    # 구분선
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    main_layout.addWidget(line)

    # 설명 텍스트
    desc_label = QLabel(desc_text)
    # ✅ TEXT_SUBDUED 색상을 인라인 스타일로 직접 적용 (속성 선택자 사용)
    desc_label.setProperty("label_type", "subdued")
    desc_label.setWordWrap(True)
    desc_label.setAlignment(Qt.AlignCenter)
    main_layout.addWidget(desc_label)

    # 현재 키 가져오기
    current_keys = get_func()
    key_entries = []

    # ✅ API 키 입력 필드 동적 생성 (중앙 정렬 + 마스킹 표시)
    for idx, key_info in enumerate(keys_info):
        key_layout = QHBoxLayout()
        key_layout.addStretch()  # 좌측 여백

        # 라벨
        label = QLabel(f"{key_info['label']}:")
        label.setFixedWidth(120)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # ✅ 테마 대응: 색상은 전역 스타일시트에서 상속
        key_layout.addWidget(label)

        # 입력창
        entry = QLineEdit()
        entry.setPlaceholderText(key_info["placeholder"])
        entry.setFixedWidth(300)
        if key_info["is_secret"]:
            entry.setEchoMode(QLineEdit.Password)

        # ✅ 현재 값 표시 (마스킹 처리)
        if current_keys:
            if isinstance(current_keys, tuple):
                if idx < len(current_keys) and current_keys[idx]:
                    current_value = current_keys[idx]
                    # 마스킹 표시
                    if key_info["is_secret"] and len(current_value) > 4:
                        entry.setText("****" + current_value[-4:])
                    elif len(current_value) > 8:
                        entry.setText(current_value[:8] + "...")
                    else:
                        entry.setText(current_value)
            else:
                if current_keys:
                    # 마스킹 표시
                    if key_info["is_secret"] and len(current_keys) > 4:
                        entry.setText("****" + current_keys[-4:])
                    elif len(current_keys) > 8:
                        entry.setText(current_keys[:8] + "...")
                    else:
                        entry.setText(current_keys)

        key_layout.addWidget(entry)
        key_layout.addStretch()  # 우측 여백
        key_entries.append(entry)

        main_layout.addLayout(key_layout)

    main_layout.addStretch()

    # 현재 상태 라벨
    status_label = QLabel("")
    status_label.setAlignment(Qt.AlignCenter)
    main_layout.addWidget(status_label)

    # 초기 상태 업데이트
    _update_qt_status_label(status_label, bool(current_keys))

    # ✅ 버튼 영역 (중앙 정렬)
    button_layout = QHBoxLayout()
    button_layout.setSpacing(10)
    button_layout.addStretch()  # 좌측 여백

    # 테스트 버튼
    test_btn = QPushButton("테스트")
    test_btn.setFixedWidth(80)
    test_btn.setStyleSheet(
        f"background-color: {U.ACCENT_YELLOW}; color: {U.TEXT_BUTTON};"
    )
    test_btn.clicked.connect(
        lambda: _test_api_qt(
            dialog,  # ✅ 다이얼로그 추가
            key_entries,
            tab_name,
            test_url,
            test_headers,
            status_label,
            current_keys,
            set_func,
            app_instance,
        )
    )
    button_layout.addWidget(test_btn)

    # 저장 버튼
    save_btn = QPushButton("저장")
    save_btn.setFixedWidth(80)
    save_btn.setStyleSheet(
        f"background-color: {U.ACCENT_BLUE}; color: {U.TEXT_BUTTON};"
    )
    save_btn.clicked.connect(
        lambda: _save_api_qt(
            dialog,  # ✅ 다이얼로그 추가
            key_entries, set_func, tab_name, status_label, current_keys, app_instance
        )
    )
    button_layout.addWidget(save_btn)

    # 삭제 버튼
    delete_btn = QPushButton("삭제")
    delete_btn.setFixedWidth(80)
    delete_btn.setStyleSheet(
        f"background-color: {U.ACCENT_RED}; color: {U.TEXT_BUTTON};"
    )
    delete_btn.clicked.connect(
        lambda: _delete_api_qt(
            dialog,  # ✅ 다이얼로그 추가
            key_entries, delete_func, tab_name, status_label, app_instance
        )
    )
    button_layout.addWidget(delete_btn)

    # 취소 버튼
    cancel_btn = QPushButton("취소")
    cancel_btn.setFixedWidth(80)
    cancel_btn.setStyleSheet(
        f"background-color: {U.ACCENT_ORANGE}; color: {U.TEXT_BUTTON};"
    )
    cancel_btn.clicked.connect(dialog.reject)
    button_layout.addWidget(cancel_btn)

    button_layout.addStretch()  # 우측 여백
    main_layout.addLayout(button_layout)

    # ✅ [수정] API 설정 모달에는 외부 클릭 닫기 비활성화
    # enable_modal_close_on_outside_click(dialog)은 Qt.Popup 플래그를 설정하여
    # 외부 클릭 시 자동으로 창이 닫혀버리므로 API 설정 모달에는 부적합
    # 따라서 이 호출 제거

    apply_dark_title_bar(dialog)

    # ✅ [수정] exec() 대신 show()를 사용하여 모드리스 윈도우로 표시
    # exec()는 blocking call이어서 모달 동작을 하게 됨
    # show()는 non-blocking이므로 다른 창과 함께 사용 가능
    dialog.show()

    # 다이얼로그 참조 반환 (가비지 컬렉션 방지)
    return dialog


def _test_api_qt(
    dialog,  # ✅ 다이얼로그 추가
    key_entries,
    tab_name,
    test_url,
    test_headers,
    status_label,
    current_keys,
    set_func,
    app_instance,
):
    """API 키 테스트 (Qt 버전) - NLK는 10초 간격 제한"""
    api_keys = [entry.text().strip() for entry in key_entries]

    if not all(api_keys):
        QMessageBox.warning(dialog, "테스트 오류", "모든 API 키를 입력해주세요.")
        return

    # ✅ 마스킹된 값 처리 (실제 값으로 변환)
    if isinstance(current_keys, tuple):
        test_keys = []
        for i, key in enumerate(api_keys):
            current_value = current_keys[i] if i < len(current_keys) else ""
            if (key.endswith("...") and len(key) > 3) or (
                key.startswith("****") and len(key) > 4
            ):
                test_keys.append(current_value)
            else:
                test_keys.append(key)
    else:
        final_key = api_keys[0]
        if (final_key.endswith("...") and len(final_key) > 3) or (
            final_key.startswith("****") and len(final_key) > 4
        ):
            test_keys = [current_keys]
        else:
            test_keys = [final_key]

    # ✅ NLK는 10초 간격 제한
    if tab_name == "NLK":
        import time

        current_time = time.time()

        if hasattr(_test_api_qt, "last_nlk_test_time"):
            elapsed = current_time - _test_api_qt.last_nlk_test_time
            if elapsed < 10:
                remaining = int(10 - elapsed)
                QMessageBox.warning(
                    dialog,  # ✅ 다이얼로그를 부모로 설정
                    "테스트 제한",
                    f"NLK API 테스트는 10초 간격으로만 가능합니다.\n\n"
                    f"남은 대기 시간: {remaining}초",
                )
                return

        _test_api_qt.last_nlk_test_time = current_time

    try:
        # ✅ 네이버 API 특수 처리
        if tab_name == "네이버":
            headers = {
                "X-Naver-Client-Id": test_keys[0],
                "X-Naver-Client-Secret": test_keys[1],
            }
            url = test_url
        # ✅ NLK API 특수 처리
        elif tab_name == "NLK":
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            url = test_url.format(key=test_keys[0]) if "{key}" in test_url else test_url
        # ✅ Web Dewey API 특수 처리 (POST 요청)
        elif tab_name == "Web Dewey":
            auth_header = base64.b64encode(
                f"{test_keys[0]}:{test_keys[1]}".encode()
            ).decode()
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            payload = {
                "grant_type": "client_credentials",
                "scope": "deweyLinkedData",
            }
            resp = requests.post(test_url, headers=headers, data=payload, timeout=10)
            resp.raise_for_status()
            data = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {}
            )

            if data.get("access_token"):
                # ✅ 테스트 성공 시 자동 저장 (모달은 닫지 않음)
                success_save = _save_api_keys_after_test_qt(
                    dialog,  # ✅ 다이얼로그 추가
                    key_entries,
                    set_func,
                    tab_name,
                    status_label,
                    current_keys,
                    app_instance,
                )
                if success_save:
                    QMessageBox.information(
                        dialog,  # ✅ 다이얼로그를 부모로 설정
                        "테스트 및 저장 성공",
                        "Dewey Linked Data API 인증 토큰을 성공적으로 발급받았습니다.\n"
                        "API 키가 자동으로 저장되었습니다.\n\n"
                        "모달창은 계속 열려있으니 필요시 수정하거나 취소 버튼을 눌러 닫아주세요.",
                    )
            else:
                QMessageBox.warning(
                    dialog,  # ✅ 다이얼로그를 부모로 설정
                    "테스트 경고",
                    "응답은 성공이지만 access_token을 확인하지 못했습니다.\n자격증명을 다시 확인하세요.",
                )
            return
        else:
            # 일반 GET 요청
            url = test_url.format(key=test_keys[0]) if "{key}" in test_url else test_url
            headers = (
                test_headers(test_keys)
                if callable(test_headers)
                else (test_headers or {})
            )

        # ✅ 타임아웃 설정
        timeout_value = 15 if tab_name in ["NLK", "Web Dewey"] else 10

        # API 호출
        response = requests.get(url, headers=headers, timeout=timeout_value)
        response.raise_for_status()

        # ✅ Gemini API 특수 검증
        if tab_name == "Gemini":
            response_json = response.json()
            if response_json.get("models") and len(response_json["models"]) > 0:
                # 테스트 성공 → 자동 저장 (모달은 닫지 않음)
                success_save = _save_api_keys_after_test_qt(
                    dialog,  # ✅ 다이얼로그 추가
                    key_entries,
                    set_func,
                    tab_name,
                    status_label,
                    current_keys,
                    app_instance,
                )
                if success_save:
                    QMessageBox.information(
                        dialog,  # ✅ 다이얼로그를 부모로 설정
                        "테스트 및 저장 성공",
                        f"{tab_name} API 키 테스트가 성공하여 자동으로 저장되었습니다.\n\n"
                        "모달창은 계속 열려있으니 필요시 수정하거나 취소 버튼을 눌러 닫아주세요.",
                    )
                else:
                    QMessageBox.warning(
                        dialog,  # ✅ 다이얼로그를 부모로 설정
                        "테스트 성공, 저장 실패",
                        f"{tab_name} API 키는 유효하지만 저장에 실패했습니다.",
                    )
            else:
                QMessageBox.warning(
                    dialog,  # ✅ 다이얼로그를 부모로 설정
                    "테스트 실패",
                    f"{tab_name} API 응답이 예상과 다릅니다. (모델 목록 없음 또는 빈 목록)",
                )
        # ✅ 일반 API (네이버, Google, NLK 등)
        elif response.status_code == 200:
            # 테스트 성공 → 자동 저장 (모달은 닫지 않음)
            success_save = _save_api_keys_after_test_qt(
                dialog,  # ✅ 다이얼로그 추가
                key_entries,
                set_func,
                tab_name,
                status_label,
                current_keys,
                app_instance,
            )
            if success_save:
                QMessageBox.information(
                    dialog,  # ✅ 다이얼로그를 부모로 설정
                    "테스트 및 저장 성공",
                    f"{tab_name} API 키 테스트가 성공하여 자동으로 저장되었습니다.\n\n"
                    "모달창은 계속 열려있으니 필요시 수정하거나 취소 버튼을 눌러 닫아주세요.",
                )
            else:
                QMessageBox.warning(
                    dialog,  # ✅ 다이얼로그를 부모로 설정
                    "테스트 성공, 저장 실패",
                    f"{tab_name} API 키는 유효하지만 저장에 실패했습니다.",
                )
        else:
            QMessageBox.warning(
                dialog,  # ✅ 다이얼로그를 부모로 설정
                "테스트 실패",
                f"API 응답 오류: {response.status_code}\n{response.text[:200]}",
            )
    except requests.exceptions.RequestException as e:
        QMessageBox.critical(
            dialog,  # ✅ 다이얼로그를 부모로 설정
            "테스트 오류",
            f"API 연결 또는 응답 오류: {str(e)}\n\n"
            "네트워크 연결 상태와 API 키가 유효한지 확인해주세요.",
        )
    except Exception as e:
        QMessageBox.critical(dialog, "테스트 실패", f"API 테스트 중 오류:\n{e}")


def _save_api_keys_after_test_qt(
    dialog,  # ✅ 다이얼로그 추가
    key_entries, set_func, tab_name, status_label, current_keys, app_instance
):
    """테스트 성공 후 API 키를 자동으로 저장하는 헬퍼 함수"""
    api_keys = [entry.text().strip() for entry in key_entries]

    # ✅ 마스킹된 값 처리
    if isinstance(current_keys, tuple):
        final_keys = []
        for i, key in enumerate(api_keys):
            current_value = current_keys[i] if i < len(current_keys) else ""
            if (key.endswith("...") and len(key) > 3) or (
                key.startswith("****") and len(key) > 4
            ):
                final_keys.append(current_value)
            else:
                final_keys.append(key)
        success = set_func(*final_keys)
    else:
        final_key = api_keys[0]
        if (final_key.endswith("...") and len(final_key) > 3) or (
            final_key.startswith("****") and len(final_key) > 4
        ):
            final_key = current_keys
        success = set_func(final_key)

    if success:
        _update_qt_status_label(status_label, True)
        if hasattr(app_instance, "log_message"):
            app_instance.log_message(f"✅ {tab_name} API 키 자동 저장 완료", "INFO")

    return success


def _save_api_qt(
    dialog,  # ✅ 다이얼로그 추가
    key_entries, set_func, tab_name, status_label, current_keys, app_instance
):
    """API 키 저장 (Qt 버전) - 모달은 닫지 않음"""
    api_keys = [entry.text().strip() for entry in key_entries]

    if not all(api_keys):
        QMessageBox.warning(dialog, "저장 오류", "모든 API 키를 입력해주세요.")
        return

    try:
        # ✅ 마스킹된 값 처리
        if isinstance(current_keys, tuple):
            final_keys = []
            for i, key in enumerate(api_keys):
                current_value = current_keys[i] if i < len(current_keys) else ""
                if (key.endswith("...") and len(key) > 3) or (
                    key.startswith("****") and len(key) > 4
                ):
                    final_keys.append(current_value)
                else:
                    final_keys.append(key)
            success = set_func(*final_keys)
        else:
            final_key = api_keys[0]
            if (final_key.endswith("...") and len(final_key) > 3) or (
                final_key.startswith("****") and len(final_key) > 4
            ):
                final_key = current_keys
            success = set_func(final_key)

        if success:
            QMessageBox.information(
                dialog, "저장 완료", f"{tab_name} API 키가 저장되었습니다."
            )
            _update_qt_status_label(status_label, True)
            if hasattr(app_instance, "log_message"):
                app_instance.log_message(f"✅ {tab_name} API 키 저장 완료", "INFO")
            # ✅ 모달은 닫지 않음 (계속 열린 상태)
        else:
            QMessageBox.warning(
                dialog, "저장 실패", f"{tab_name} API 키 저장에 실패했습니다."
            )
    except Exception as e:
        QMessageBox.critical(dialog, "저장 실패", f"API 키 저장 중 오류:\n{e}")


def _delete_api_qt(dialog, key_entries, delete_func, tab_name, status_label, app_instance):
    """API 키 삭제 (Qt 버전)"""
    reply = QMessageBox.question(
        dialog,  # ✅ 다이얼로그를 부모로 설정
        "삭제 확인",
        f"{tab_name} API 키를 정말 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.",
        QMessageBox.Yes | QMessageBox.No,
    )

    if reply == QMessageBox.Yes:
        try:
            success = delete_func()
            if success:
                QMessageBox.information(
                    dialog, "삭제 완료", f"{tab_name} API 키가 삭제되었습니다."
                )
                for entry in key_entries:
                    entry.clear()
                _update_qt_status_label(status_label, False)
                if hasattr(app_instance, "log_message"):
                    app_instance.log_message(f"✅ {tab_name} API 키 삭제 완료", "INFO")
            else:
                QMessageBox.warning(
                    dialog, "삭제 실패", f"{tab_name} API 키 삭제에 실패했습니다."
                )
        except Exception as e:
            QMessageBox.critical(dialog, "삭제 실패", f"API 키 삭제 중 오류:\n{e}")


def _update_qt_status_label(status_label, is_configured):
    """Qt 상태 라벨 업데이트 - 테마 대응 (속성 선택자 사용)"""
    if is_configured:
        status_label.setText("현재 상태: ✅ 설정됨")
        status_label.setProperty("api_status", "success")
    else:
        status_label.setText("현재 상태: ❌ 미설정")
        status_label.setProperty("api_status", "error")

    # ✅ 스타일 재적용 (테마 변경 시 즉시 반영)
    status_label.style().unpolish(status_label)
    status_label.style().polish(status_label)


def check_api_configured(tab_name, db_manager):
    """
    해당 탭의 API가 설정되어 있는지 확인합니다. (CTk 버전과 동일)

    Args:
        tab_name (str): 탭 이름
        db_manager: 데이터베이스 매니저

    Returns:
        bool: API 설정 여부
    """
    try:
        n = (tab_name or "").strip().lower()
        if n in {"네이버", "naver"}:
            cid, cs = db_manager.get_naver_api_credentials()
            return bool(cid and cs)
        if n == "nlk":
            k = db_manager.get_nlk_api_key()
            return bool(k)
        if n in {"google", "google books"}:
            k = db_manager.get_google_api_key()
            return bool(k)
        if n == "gemini":
            k = db_manager.get_gemini_api_key()
            return bool(k)
        if n in {"ddc", "dewey", "dewey 분류 검색", "web dewey", "webdewey"}:
            cid, cs = db_manager.get_dewey_api_credentials()
            return bool(cid and cs)
        return False
    except Exception:
        return False
