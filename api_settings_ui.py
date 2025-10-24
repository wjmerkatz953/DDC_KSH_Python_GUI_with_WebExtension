# -*- coding: utf-8 -*-
"""
api_settings_ui.py - API 설정 관련 UI 통합 모듈
Version: v1.0.1
생성일: 2025-08-14 KST

모든 API 설정 모달창과 상태 관리 UI를 중앙에서 관리합니다.
- 네이버 책 API (클라이언트 ID + 시크릿)
- NLK OpenAPI
- Google Books API
- Gemini API
- Dewey Linked Data API(DDC)
"""
import base64  # ✅ Dewey Basic Auth 인코딩용
from tkinter.messagebox import askyesno
import customtkinter as ctk
from ui_constants import UI_CONSTANTS
import requests
from widget_events import setup_modal_keybindings

print(f"🔍 setup_modal_keybindings 함수 위치: {setup_modal_keybindings.__module__}")
print(f"🔍 함수 파일 경로: {setup_modal_keybindings.__code__.co_filename}")


def show_api_settings_modal(tab_name, db_manager, app_instance, parent_window=None):
    """
    탭별 API 설정 모달 창을 표시합니다.

    Args:
        tab_name (str): 탭 이름 ('네이버','납본 ID 검색', 'NLK', 'Google', 'Gemini', 'Web Dewey'/'DDC'/'Dewey 분류 검색')
        db_manager (DatabaseManager): 데이터베이스 매니저 인스턴스
        app_instance: GUI 애플리케이션 인스턴스
        parent_window: 부모 창 (None이면 app_instance.root 사용)
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
        elif n in {"nlk"}:
            return "NLK"
        elif n in {"bne", "납본 id 검색"}:
            return "NLK"  # BNE는 NLK API 키를 사용
        elif n in {"네이버", "naver"}:
            return "네이버"
        return name

    normalized_tab = _normalize_tab_name(tab_name)
    parent = parent_window or app_instance.root

    # [수정 1] - 중복 창 생성을 방지하는 로직 추가
    # 이미 같은 제목의 모달 창이 열려 있는지 확인
    for widget in parent.winfo_children():
        if (
            isinstance(widget, ctk.CTkToplevel)
            and widget.title() == f"{tab_name} API 설정"
        ):
            widget.lift()
            widget.focus_force()
            return

    # 모달 창 생성
    modal = ctk.CTkToplevel(parent)
    modal.configure(fg_color=UI_CONSTANTS.BACKGROUND_PRIMARY)  # 어두운 배경
    modal.title(f"{tab_name} API 설정")
    # [수정 2] - 중복된 geometry 설정 줄 제거
    modal.resizable(False, False)

    # 모달을 부모 창 중앙에 배치
    modal.transient(parent)
    modal.grab_set()

    # [수정 3] - 모달 창이 부모 뒤에 숨는 것을 방지
    modal.lift()
    modal.focus_force()

    # 모달을 부모 창 중앙에 배치
    parent.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 300
    y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 225
    modal.geometry(f"600x450+{x}+{y}")

    # 메인 프레임
    main_frame = ctk.CTkFrame(modal, fg_color=UI_CONSTANTS.BACKGROUND_TERTIARY)
    main_frame.pack(fill="both", expand=True, padx=20, pady=20)

    # 제목
    title_label = ctk.CTkLabel(
        main_frame,
        text=f"{tab_name} API 설정",
        font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_LARGE, "bold"),
        text_color=UI_CONSTANTS.TEXT_DEFAULT,
    )
    title_label.pack(pady=(10, 20))

    # 🔥 여기에 추가!
    setup_modal_keybindings(modal)

    # API별 매개변수 정의
    api_settings = {
        "네이버": {
            "desc_text": "네이버 개발자 센터에서 발급받은 API 키를 입력해주세요.",
            "keys_info": [
                {
                    "label": "클라이언트 ID",
                    "placeholder": "클라이언트 ID를 입력하세요",
                    "is_secret": False,
                },
                {
                    "label": "클라이언트 시크릿",
                    "placeholder": "클라이언트 시크릿을 입력하세요",
                    "is_secret": True,
                },
            ],
            "get_func": db_manager.get_naver_api_credentials,
            "set_func": db_manager.set_naver_api_credentials,
            "delete_func": db_manager.delete_naver_api_credentials,
            "test_url": "https://openapi.naver.com/v1/search/book.xml?query=test&display=1",
            "test_headers": {},
        },
        "NLK": {
            "desc_text": "국립중앙도서관 OpenAPI 키를 입력해주세요.\n(https://www.nl.go.kr/NL/search/openApi/search.do)",
            "keys_info": [
                {
                    "label": "API 키",
                    "placeholder": "NLK OpenAPI 키를 입력하세요",
                    "is_secret": True,
                }
            ],
            "get_func": db_manager.get_nlk_api_key,
            "set_func": db_manager.set_nlk_api_key,
            "delete_func": db_manager.delete_nlk_api_key,
            "test_url": "https://www.nl.go.kr/NL/search/openApi/search.do?key={key}&pageSize=1",
            "test_headers": None,
        },
        "Google": {
            "desc_text": "Google Cloud Platform에서 발급받은 API 키를 입력해주세요.",
            "keys_info": [
                {
                    "label": "API 키",
                    "placeholder": "Google Books API 키를 입력하세요",
                    "is_secret": True,
                }
            ],
            "get_func": db_manager.get_google_api_key,
            "set_func": db_manager.set_google_api_key,
            "delete_func": db_manager.delete_google_api_key,
            "test_url": "https://www.googleapis.com/books/v1/volumes?q=test&key={key}&maxResults=1",
            "test_headers": None,
        },
        # Gemini API 부분 수정 시작
        "Gemini": {
            "desc_text": "Google AI Studio 또는 Google Cloud Platform에서\n발급받은 Gemini API 키를 입력해주세요.",
            "keys_info": [
                {
                    "label": "API 키",
                    "placeholder": "Gemini API 키를 입력하세요",
                    "is_secret": True,
                }
            ],
            "get_func": db_manager.get_gemini_api_key,
            "set_func": db_manager.set_gemini_api_key,
            "delete_func": db_manager.delete_gemini_api_key,
            # 이 URL은 유효한 모델 목록을 반환하는지 확인하는 데 사용됩니다.
            # ⭐ 수정: 모델 목록을 반환하는 정확한 URL로 변경 ⭐
            "test_url": "https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            "test_headers": None,
        },
        # ✅ Web Dewey (DLD) - ‘DDC’, ‘Dewey 분류 검색’ 등도 정규화되어 이 항목 사용
        "Web Dewey": {
            "desc_text": "OCLC API Console에서 발급받은 DLD API 자격증명을 입력해주세요.",
            "keys_info": [
                {
                    "label": "클라이언트 ID",
                    "placeholder": "Dewey Client ID를 입력하세요",
                    "is_secret": False,
                },
                {
                    "label": "클라이언트 시크릿",
                    "placeholder": "Dewey Client Secret을 입력하세요",
                    "is_secret": True,
                },
            ],
            "get_func": db_manager.get_dewey_api_credentials,
            "set_func": db_manager.set_dewey_api_credentials,
            "delete_func": db_manager.delete_dewey_api_credentials,
            "test_url": "https://oauth.oclc.org/token",  # 토큰 발급 엔드포인트
            "test_headers": {},
        },
    }

    if normalized_tab in api_settings:
        settings = api_settings[normalized_tab]
        _create_generic_api_settings(
            main_frame,
            modal,
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
    else:
        # 지원하지 않는 탭
        error_label = ctk.CTkLabel(
            main_frame,
            text=f"'{tab_name}' 탭은 아직 지원되지 않습니다.",
            text_color="red",
        )
        error_label.pack(pady=20)

        close_button = ctk.CTkButton(
            main_frame,
            text="닫기",
            command=modal.destroy,
            fg_color=UI_CONSTANTS.ACCENT_BLUE,
        )
        close_button.pack(pady=10)


def _create_generic_api_settings(
    parent_frame,
    modal,
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
    """
    API 설정 모달 창의 UI를 동적으로 생성하는 범용 함수.

    Args:
        parent_frame: 부모 프레임
        modal: 모달 창 인스턴스
        db_manager: 데이터베이스 매니저 인스턴스
        app_instance: GUI 애플리케이션 인스턴스
        tab_name (str): 탭 이름
        desc_text (str): UI에 표시할 설명 텍스트
        keys_info (list): 키 정보를 담은 리스트 (label, placeholder, is_secret)
        get_func (callable): db_manager의 키 조회 메서드
        set_func (callable): db_manager의 키 저장 메서드
        delete_func (callable): db_manager의 키 삭제 메서드
        test_url (str): API 테스트에 사용할 URL
        test_headers (dict, optional): API 테스트에 사용할 헤더. Defaults to None.
    """

    # 설명 텍스트
    desc_label = ctk.CTkLabel(
        parent_frame,
        text=desc_text,
        font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL),
        text_color=UI_CONSTANTS.TEXT_SUBDUED,
        justify="center",
    )
    desc_label.pack(pady=(0, 20))

    current_keys = get_func()
    key_entries = []

    # API 키 입력 필드 동적 생성
    for key_info in keys_info:
        key_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        key_frame.pack(pady=1)

        ctk.CTkLabel(
            key_frame,
            text=f"{key_info['label']}:",
            font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL),
            width=80,
            anchor="e",
        ).pack(side="left", padx=(60, 5))

        entry = ctk.CTkEntry(
            key_frame,
            placeholder_text=key_info["placeholder"],
            font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL),
            # ✅ WIDGET_BG_DEFAULT → BACKGROUND_FOURTH로 변경
            fg_color=UI_CONSTANTS.BACKGROUND_FOURTH,
            text_color=UI_CONSTANTS.TEXT_DEFAULT,
            border_color=UI_CONSTANTS.ACCENT_BLUE,
            border_width=0.3,
            show="*" if key_info["is_secret"] else None,
            width=300,
        )
        entry.pack(side="left", padx=(0, 80))
        key_entries.append(entry)

        # 현재 값이 있으면 표시 (보안상 일부만)
        if current_keys:
            # 단일 키와 여러 키를 처리하기 위한 로직 개선
            if isinstance(current_keys, tuple):
                # keys_info 리스트에서 현재 key_info의 인덱스를 찾습니다.
                try:
                    current_value = current_keys[keys_info.index(key_info)]
                except ValueError:
                    current_value = ""  # 찾지 못하면 빈 값
            else:  # 단일 키인 경우
                current_value = current_keys

            if current_value:  # 값이 존재하는 경우에만 삽입 시도
                if key_info["is_secret"] and len(current_value) > 4:
                    entry.insert(0, "****" + current_value[-4:])
                elif len(current_value) > 8:
                    entry.insert(0, current_value[:8] + "...")
                else:
                    entry.insert(0, current_value)

    # 상태 라벨
    status_label = ctk.CTkLabel(
        parent_frame,
        text="API 상태: ✅ 설정됨" if current_keys else "API 상태: ❌ 미설정",
        font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_SMALL),
        text_color=(
            UI_CONSTANTS.ACCENT_GREEN if current_keys else UI_CONSTANTS.ACCENT_RED
        ),
    )
    status_label.pack(pady=20)

    # 버튼 프레임 (중앙 정렬)
    button_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
    button_frame.pack(pady=20)

    def save_api():
        """API 키 저장"""
        api_keys = [entry.get().strip() for entry in key_entries]

        # 입력값 유효성 검사
        if not all(api_keys):
            app_instance.show_messagebox(
                "입력 오류", "모든 API 키를 입력해주세요.", "warning"
            )
            return

        # 기존 값과 동일한 경우 처리 (마스킹된 경우)
        if isinstance(current_keys, tuple):
            final_keys = []
            for i, key in enumerate(api_keys):
                current_value = current_keys[i] if len(current_keys) > i else ""
                if (key.endswith("...") and len(key) > 3) or (
                    key.startswith("****") and len(key) > 4
                ):
                    final_keys.append(current_value)
                else:
                    final_keys.append(key)
            success = set_func(*final_keys)
        else:  # 단일 키
            final_key = api_keys[0]
            if (final_key.endswith("...") and len(final_key) > 3) or (
                final_key.startswith("****") and len(final_key) > 4
            ):
                final_key = current_keys
            success = set_func(final_key)

        if success:
            app_instance.show_messagebox(
                "저장 완료", f"{tab_name} API 키가 성공적으로 저장되었습니다.", "info"
            )
            _update_local_status_label(status_label, True)
            if hasattr(
                app_instance, f"{tab_name.lower().replace(' ', '_')}_api_status_label"
            ):
                update_api_status_label(...)
            try:
                modal.grab_release()  # ⬅️ 추가: 그랩 해제
            except Exception:
                pass

            # 1) 외부(메인 앱) 상태 라벨 먼저 갱신
            try:
                ext_name = f"{tab_name.lower().replace(' ', '_')}_api_status_label"
                if hasattr(app_instance, ext_name):
                    update_api_status_label(
                        tab_name, getattr(app_instance, ext_name), db_manager
                    )
            except Exception:
                pass

            # 2) 모달 안 라벨은 "살아있을 때만" 갱신
            try:
                if status_label.winfo_exists():
                    _update_local_status_label(status_label, True)
            except Exception:
                pass

            # 3) 안전 파괴 (지연 포커스 충돌 방지 - 개선)
            if modal.winfo_exists():
                try:
                    # 포커스를 메인 윈도우로 먼저 이동
                    app_instance.root.focus_set()
                    modal.grab_release()
                except Exception:
                    pass
                # 충분한 지연 시간을 두고 파괴 (포커스 이벤트 완료 대기)
                modal.after(100, lambda: _safe_modal_destroy(modal))
        else:
            app_instance.show_messagebox(
                "저장 실패",
                f"{tab_name} API 키 저장에 실패했습니다.",
                "error",
                parent=modal,
            )

    def _safe_modal_destroy(modal):
        """모달 창을 안전하게 파괴하는 헬퍼 함수"""
        try:
            if modal.winfo_exists():
                modal.destroy()
        except Exception:
            pass  # 이미 파괴된 경우 무시

    def test_api():
        """API 키 테스트"""
        # NLK만 테스트 간격 제한
        if tab_name == "NLK":
            import time

            current_time = time.time()
            if hasattr(test_api, "last_nlk_test_time"):
                if current_time - test_api.last_nlk_test_time < 10:  # 10초 제한
                    app_instance.show_messagebox(
                        "테스트 제한",
                        "NLK API 테스트는 10초 간격으로만 가능합니다.",
                        "warning",
                    )
                    return
            test_api.last_nlk_test_time = current_time

        api_keys = [entry.get().strip() for entry in key_entries]

        # 입력값 유효성 검사
        if not all(api_keys):
            app_instance.show_messagebox(
                "테스트 오류", "모든 API 키를 입력해주세요.", "warning"
            )
            return

        # 입력값 유효성 검사
        if not all(api_keys):
            app_instance.show_messagebox(
                "테스트 오류", "모든 API 키를 입력해주세요.", "warning"
            )
            return

        # 마스킹된 기존 값 처리
        if isinstance(current_keys, tuple):
            test_keys = []
            for i, key in enumerate(api_keys):
                current_value = current_keys[i] if len(current_keys) > i else ""
                if (key.endswith("...") and len(key) > 3) or (
                    key.startswith("****") and len(key) > 4
                ):
                    test_keys.append(current_value)
                else:
                    test_keys.append(key)
        else:  # 단일 키
            final_key = api_keys[0]
            test_keys = [final_key]
            if (final_key.endswith("...") and len(final_key) > 3) or (
                final_key.startswith("****") and len(final_key) > 4
            ):
                test_keys[0] = current_keys

        try:
            # 네이버 API는 헤더에 클라이언트 ID와 시크릿을 따로 넣어야 함
            headers = test_headers
            if tab_name == "네이버":
                headers = {
                    "X-Naver-Client-Id": test_keys[0],
                    "X-Naver-Client-Secret": test_keys[1],
                }

            elif tab_name == "NLK":
                headers = headers or {}
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )

            elif tab_name == "Web Dewey":
                # ✅ Dewey: Client Credentials로 토큰 발급 (POST) 테스트, 성공 시 조기 반환
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
                resp = requests.post(
                    test_url, headers=headers, data=payload, timeout=10
                )
                resp.raise_for_status()
                data = (
                    resp.json()
                    if resp.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                if data.get("access_token"):
                    app_instance.show_messagebox(
                        "테스트 성공",
                        "Dewey Linked Data API 인증 토큰을 성공적으로 발급받았습니다.",
                        "info",
                    )
                else:
                    app_instance.show_messagebox(
                        "테스트 경고",
                        "응답은 성공이지만 access_token을 확인하지 못했습니다. 자격증명을 다시 확인하세요.",
                        "warning",
                    )
                return  # ✅ POST 성공 후 불필요한 GET 시도 방지

            elif tab_name == "Gemini":
                headers = headers or {}
                # 이후 공통 GET 로직에서 models 엔드포인트 호출됨

            # ✅ 공통 GET 테스트 (네이버/Google/Gemini 등)
            formatted_test_url = test_url
            if "{key}" in test_url:
                if test_keys and test_keys[0]:
                    formatted_test_url = test_url.format(key=test_keys[0])
                else:
                    app_instance.show_messagebox(
                        "테스트 오류",
                        "API 키가 비어있어 테스트 URL을 완성할 수 없습니다.",
                        "warning",
                    )
                    return
            elif (
                tab_name == "Gemini"
            ):  # Gemini API는 일반적으로 API 키를 URL 파라미터로 포함
                # 추가적인 헤더가 필요할 경우 여기에 추가
                if not headers:
                    headers = {}
                # headers.update({"Content-Type": "application/json"}) # Gemini는 일반적으로 JSON 요청

            # 테스트 URL에 API 키를 삽입
            # 공통 GET 테스트 준비
            formatted_test_url = test_url
            if "{key}" in test_url:
                if test_keys and test_keys[0]:
                    formatted_test_url = test_url.format(key=test_keys[0])
                else:
                    app_instance.show_messagebox(
                        "테스트 오류",
                        "API 키가 비어있어 테스트 URL을 완성할 수 없습니다.",
                        "warning",
                    )
                    return

            # 다음과 같이 수정:
            timeout_value = 15 if tab_name in ["NLK", "Web Dewey"] else 10
            response = requests.get(
                formatted_test_url, headers=headers, timeout=timeout_value
            )
            response.raise_for_status()  # HTTP 오류 발생 시 예외 발생

            # Gemini API 테스트 성공 여부 판단 로직 추가
            if tab_name == "Gemini":
                response_json = response.json()
                # Gemini API의 /models 엔드포인트는 'models' 리스트를 반환합니다.
                # 이 리스트가 존재하고 비어있지 않으면 성공으로 간주합니다.
                if response_json.get("models") and len(response_json["models"]) > 0:
                    # ✅ 테스트 성공 시 자동 저장 추가
                    success_save = _save_api_keys_after_test()
                    if success_save:
                        app_instance.show_messagebox(
                            "테스트 및 저장 성공",
                            f"{tab_name} API 키 테스트가 성공하여 자동으로 저장되었습니다.",
                            "info",
                        )
                    else:
                        app_instance.show_messagebox(
                            "테스트 성공, 저장 실패",
                            f"{tab_name} API 키는 유효하지만 저장에 실패했습니다.",
                            "warning",
                        )
                else:
                    app_instance.show_messagebox(
                        "테스트 실패",
                        f"{tab_name} API 응답이 예상과 다릅니다. (모델 목록 없음 또는 빈 목록)",
                        "warning",
                    )
            # 다른 API들의 기존 테스트 로직 유지
            elif response.status_code == 200:
                # ✅ 테스트 성공 시 자동 저장 추가
                success_save = _save_api_keys_after_test()
                if success_save:
                    app_instance.show_messagebox(
                        "테스트 및 저장 성공",
                        f"{tab_name} API 키 테스트가 성공하여 자동으로 저장되었습니다.",
                        "info",
                    )
                else:
                    app_instance.show_messagebox(
                        "테스트 성공, 저장 실패",
                        f"{tab_name} API 키는 유효하지만 저장에 실패했습니다.",
                        "warning",
                    )
            else:
                app_instance.show_messagebox(
                    "테스트 실패",
                    f"API 키가 유효하지 않습니다. (응답 코드: {response.status_code})",
                    "error",
                )

        except requests.exceptions.RequestException as e:
            app_instance.show_messagebox(
                "테스트 오류",
                f"API 연결 또는 응답 오류: {str(e)}\n\n네트워크 연결 상태와 API 키가 유효한지 확인해주세요.",
                "error",
            )
        except Exception as e:
            app_instance.show_messagebox(
                "테스트 오류", f"알 수 없는 오류 발생: {str(e)}", "error"
            )

    def _save_api_keys_after_test():
        """테스트 성공 후 API 키를 저장하는 헬퍼 함수"""
        api_keys = [entry.get().strip() for entry in key_entries]

        # 기존 값과 동일한 경우 처리 (마스킹된 경우)
        if isinstance(current_keys, tuple):
            final_keys = []
            for i, key in enumerate(api_keys):
                current_value = current_keys[i] if len(current_keys) > i else ""
                if (key.endswith("...") and len(key) > 3) or (
                    key.startswith("****") and len(key) > 4
                ):
                    final_keys.append(current_value)
                else:
                    final_keys.append(key)
            return set_func(*final_keys)
        else:  # 단일 키
            final_key = api_keys[0]
            if (final_key.endswith("...") and len(final_key) > 3) or (
                final_key.startswith("****") and len(final_key) > 4
            ):
                final_key = current_keys
            return set_func(final_key)

    def delete_api():
        """API 키 삭제"""
        confirmed = askyesno(
            title="삭제 확인",
            message=f"정말로 저장된 {tab_name} API 키를 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
            parent=modal,
        )
        if not confirmed:
            return

        success = delete_func()
        if success:
            app_instance.show_messagebox(
                "삭제 완료", f"{tab_name} API 키가 성공적으로 삭제되었습니다.", "info"
            )
            app_instance.log_message(f"정보: {tab_name} API 키가 삭제되었습니다.")

            for entry in key_entries:
                entry.delete(0, "end")

            _update_local_status_label(status_label, False)
            if hasattr(
                app_instance, f"{tab_name.lower().replace(' ', '_')}_api_status_label"
            ):
                update_api_status_label(
                    tab_name,
                    getattr(
                        app_instance,
                        f"{tab_name.lower().replace(' ', '_')}_api_status_label",
                    ),
                    db_manager,
                )

        else:
            app_instance.show_messagebox(
                "삭제 실패", f"{tab_name} API 키 삭제에 실패했습니다.", "error"
            )

    # 버튼들
    ctk.CTkButton(
        button_frame,
        text="테스트",
        command=test_api,
        fg_color=UI_CONSTANTS.ACCENT_YELLOW,
        hover_color=UI_CONSTANTS.BACKGROUND_FOURTH,
        text_color=UI_CONSTANTS.TEXT_BUTTON,
        width=80,
    ).pack(side="left", padx=5)
    ctk.CTkButton(
        button_frame,
        text="저장",
        command=save_api,
        fg_color=UI_CONSTANTS.ACCENT_BLUE,
        hover_color=UI_CONSTANTS.BACKGROUND_FOURTH,
        text_color=UI_CONSTANTS.TEXT_BUTTON,
        width=80,
    ).pack(side="left", padx=5)
    ctk.CTkButton(
        button_frame,
        text="삭제",
        command=delete_api,
        fg_color=UI_CONSTANTS.ACCENT_RED,
        hover_color=UI_CONSTANTS.BACKGROUND_FOURTH,
        text_color=UI_CONSTANTS.TEXT_BUTTON,
        width=80,
    ).pack(side="left", padx=5)
    ctk.CTkButton(
        button_frame,
        text="취소",
        command=modal.destroy,
        fg_color=UI_CONSTANTS.ACCENT_ORANGE,
        hover_color=UI_CONSTANTS.BACKGROUND_FOURTH,
        text_color=UI_CONSTANTS.TEXT_BUTTON,
        width=80,
    ).pack(side="left", padx=5)


def _update_local_status_label(status_label, is_configured):
    """모달 창 내부의 상태 라벨을 업데이트하는 헬퍼 함수"""
    if is_configured:
        status_label.configure(
            text="현재 상태: ✅ 설정됨", text_color=UI_CONSTANTS.ACCENT_GREEN
        )
    else:
        status_label.configure(text="현재 상태: ❌ 미설정", text_color="red")


def create_api_status_widget(parent_frame, tab_name, db_manager, app_instance):
    """
    API 상태 표시 위젯을 생성합니다.

    Args:
        parent_frame: 부모 프레임
        tab_name (str): 탭 이름
        db_manager: 데이터베이스 매니저
        app_instance: 앱 인스턴스

    Returns:
        tuple: (api_button, status_label) - 업데이트용
    """
    # API 설정 버튼
    api_button = ctk.CTkButton(
        parent_frame,
        text="⚙️ API 설정",
        command=lambda: show_api_settings_modal(tab_name, db_manager, app_instance),
        fg_color=UI_CONSTANTS.BACKGROUND_TERTIARY,
        hover_color=UI_CONSTANTS.ACCENT_BLUE,
        text_color=UI_CONSTANTS.TEXT_DEFAULT,
        width=100,
        height=30,
    )

    # API 상태 라벨
    status_label = ctk.CTkLabel(
        parent_frame,
        text="",
        font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_SMALL),
        width=120,
    )

    # 초기 상태 업데이트
    update_api_status_label(tab_name, status_label, db_manager)

    return api_button, status_label


def update_api_status_label(tab_name, status_label, db_manager):
    """
    API 설정 상태에 따라 상태 라벨을 업데이트합니다.

    Args:
        tab_name (str): 탭 이름
        status_label: 상태 라벨 위젯
        db_manager: 데이터베이스 매니저
    """
    is_configured = check_api_configured(tab_name, db_manager)

    if is_configured:
        status_label.configure(
            text="현재 상태: ✅ 설정됨", text_color=UI_CONSTANTS.ACCENT_GREEN
        )
    else:
        status_label.configure(
            text="API 상태: ❌ 미설정", text_color=UI_CONSTANTS.ACCENT_RED
        )


def check_api_configured(tab_name, db_manager):
    """
    해당 탭의 API가 설정되어 있는지 확인합니다.

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
        if n in {"nlk", "bne", "납본 id 검색"}:
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


# 테스트용 메인 함수
if __name__ == "__main__":
    print("api_settings_ui.py - API 설정 UI 모듈")
    print("사용법: show_api_settings_modal('네이버', db_manager, app_instance)")
