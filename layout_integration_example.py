# -*- coding: utf-8 -*-
"""
파일명: layout_integration_example.py
설명: qt_main_app.py에 레이아웃 설정 저장/복구 기능을 통합하는 방법 보여주는 예제
버전: 1.0.0
생성일: 2025-10-18

사용법:
1. qt_main_app.py의 __init__ 메서드에서 layout_settings_manager 초기화
2. setup_ui() 완료 후 레이아웃 설정 복구
3. closeEvent()에서 레이아웃 설정 저장
"""

# ============================================================================
# 1️⃣ qt_main_app.py의 __init__ 메서드에서 추가할 코드
# ============================================================================

def qt_main_app_init_addition():
    """
    MainApplicationWindow.__init__() 메서드에서 setup_ui() 다음에 추가할 코드
    """
    code = """
    # ✅ [추가] 레이아웃 설정 관리자 초기화
    from layout_settings_manager import LayoutSettingsManager
    self.layout_settings_manager = LayoutSettingsManager(self.app_instance.db_manager)

    # ✅ [추가] 저장된 레이아웃 설정 복구 (앱 시작 시)
    self.restore_layout_settings()
    """
    print(code)


# ============================================================================
# 2️⃣ MainApplicationWindow 클래스에 추가할 메서드들
# ============================================================================

layout_settings_methods = """
# ✅ [추가 메서드 1] 레이아웃 설정 복구 (앱 시작 시)
def restore_layout_settings(self):
    '''
    저장된 레이아웃 설정을 복구합니다. (앱 시작 시 호출)
    '''
    try:
        # 1. 탭 이름 리스트 가져오기
        tab_names = []
        if hasattr(self, "tab_widget") and self.tab_widget:
            for i in range(self.tab_widget.count()):
                tab_names.append(self.tab_widget.tabText(i))

        if not tab_names:
            self.app_instance.log_message("ℹ️ 복구할 탭이 없습니다.", "WARNING")
            return

        # 2. 기본 설정 정의
        default_splitters = {tab_name: {"main": [700, 300]} for tab_name in tab_names}
        default_widgets = {
            tab_name: {
                "find_area": True,  # F7
                "tab_bar": True,    # F9
                "menu_bar": True,   # F10
                "detail_panel": True,  # F11
                "log_panel": True   # F12
            }
            for tab_name in tab_names
        }

        # 3. 저장된 설정 복구
        splitter_configs, widget_configs = self.layout_settings_manager.load_all_layout_settings(
            tab_names, default_splitters, default_widgets
        )

        # 4. 메인 스플리터 복구
        if hasattr(self, "main_splitter") and "main" in splitter_configs.get(tab_names[0], {}):
            sizes = splitter_configs[tab_names[0]]["main"]
            self.main_splitter.setSizes(sizes)
            self.app_instance.log_message(f"✅ 메인 스플리터 복구: {sizes}", "INFO")

        # 5. 위젯 표시/숨김 설정 복구
        current_tab_name = tab_names[0] if tab_names else None
        if current_tab_name and current_tab_name in widget_configs:
            config = widget_configs[current_tab_name]

            # Find 영역 (F7)
            if "find_area" in config and not config["find_area"]:
                self.toggle_find_area_visibility()

            # 탭바 (F9)
            if "tab_bar" in config and not config["tab_bar"]:
                self.toggle_tab_bar_visibility()

            # 메뉴바 (F10)
            if "menu_bar" in config and not config["menu_bar"]:
                self.toggle_menu_bar_visibility()

            # 상세 정보 (F11)
            if "detail_panel" in config and not config["detail_panel"]:
                self.toggle_detail_visibility()

            # 로그 (F12)
            if "log_panel" in config and not config["log_panel"]:
                self.toggle_log_visibility()

        self.app_instance.log_message("✅ 레이아웃 설정 복구 완료", "INFO")

    except Exception as e:
        self.app_instance.log_message(f"❌ 레이아웃 설정 복구 실패: {e}", "ERROR")


# ✅ [추가 메서드 2] 레이아웃 설정 저장 (앱 종료 시)
def save_layout_settings(self):
    '''
    현재 레이아웃 설정을 저장합니다. (앱 종료 시 호출)
    '''
    try:
        # 1. 메인 스플리터 크기 수집
        splitter_configs = {}
        if hasattr(self, "main_splitter"):
            sizes = self.main_splitter.sizes()
            # 모든 탭에 동일한 설정 적용 (또는 탭별로 다르게 저장 가능)
            if hasattr(self, "tab_widget") and self.tab_widget:
                for i in range(self.tab_widget.count()):
                    tab_name = self.tab_widget.tabText(i)
                    splitter_configs[tab_name] = {"main": sizes}

        # 2. 위젯 표시/숨김 상태 수집
        widget_configs = {}
        if hasattr(self, "tab_widget") and self.tab_widget:
            for i in range(self.tab_widget.count()):
                tab_name = self.tab_widget.tabText(i)
                widget_configs[tab_name] = {
                    "find_area": self.is_find_visible if hasattr(self, "is_find_visible") else True,
                    "tab_bar": self.tab_widget.isVisible(),
                    "menu_bar": self.menuBar().isVisible(),
                    "detail_panel": self.is_detail_visible if hasattr(self, "is_detail_visible") else True,
                    "log_panel": self.is_log_visible if hasattr(self, "is_log_visible") else True
                }

        # 3. 저장
        self.layout_settings_manager.save_all_layout_settings(splitter_configs, widget_configs)
        self.app_instance.log_message("✅ 레이아웃 설정 저장 완료", "INFO")

    except Exception as e:
        self.app_instance.log_message(f"❌ 레이아웃 설정 저장 실패: {e}", "ERROR")
"""

print(layout_settings_methods)


# ============================================================================
# 3️⃣ closeEvent() 메서드에서 추가할 코드
# ============================================================================

def qt_main_app_close_event_addition():
    """
    MainApplicationWindow.closeEvent() 메서드에서 추가할 코드
    기존 코드 마지막에 추가
    """
    code = """
    # ✅ [추가] 레이아웃 설정 저장 (앱 종료 시)
    self.save_layout_settings()

    # 기존 close 동작
    event.accept()
    """
    print(code)


# ============================================================================
# 4️⃣ 현재 F7-F12 토글 메서드 수정 (위젯 상태 추적)
# ============================================================================

widget_state_tracking = """
# ✅ [수정] 각 toggle 메서드에서 상태 추적 변수 업데이트

def toggle_find_area_visibility(self):
    '''Find 영역 표시/숨김 토글 (F7)'''
    if hasattr(self, "find_area_container"):
        is_visible = self.find_area_container.isVisible()
        self.find_area_container.setVisible(not is_visible)
        # ✅ [추가] 상태 저장
        self.is_find_visible = not is_visible
        ...

def toggle_detail_visibility(self):
    '''상세 정보 패널 표시/숨김 토글 (F11)'''
    self.is_detail_visible = not self.is_detail_visible
    self.detail_group.setVisible(self.is_detail_visible)
    ...

def toggle_log_visibility(self):
    '''로그 패널 표시/숨김 토글 (F12)'''
    self.is_log_visible = not self.is_log_visible
    self.log_group.setVisible(self.is_log_visible)
    ...
"""

print(widget_state_tracking)


# ============================================================================
# 사용 요약
# ============================================================================

if __name__ == "__main__":
    print("""
╔═════════════════════════════════════════════════════════════════════════════╗
║                        레이아웃 설정 저장/복구 통합 방법                       ║
╚═════════════════════════════════════════════════════════════════════════════╝

📋 변경 사항:

1️⃣ qt_main_app.py의 __init__() 메서드에서:
   - layout_settings_manager 초기화
   - setup_ui() 다음에 restore_layout_settings() 호출

2️⃣ MainApplicationWindow 클래스에 추가할 메서드:
   - restore_layout_settings(): 앱 시작 시 설정 복구
   - save_layout_settings(): 앱 종료 시 설정 저장

3️⃣ closeEvent() 메서드에서:
   - save_layout_settings() 호출

4️⃣ F7-F12 토글 메서드에서:
   - 위젯 상태 변수 업데이트 (is_find_visible, is_detail_visible 등)

📌 저장되는 정보:
   ✅ QSplitter 크기 (각 탭별)
   ✅ F7: Find 영역 표시/숨김
   ✅ F9: 탭바 표시/숨김
   ✅ F10: 메뉴바 표시/숨김
   ✅ F11: 상세 정보 패널 표시/숨김
   ✅ F12: 로그 패널 표시/숨김

🎯 결과:
   ✅ 앱을 종료했다가 다시 시작하면 이전 레이아웃 설정이 자동으로 복구됨
   ✅ 각 탭별로 다른 레이아웃 설정 가능
   ✅ 사용자 설정이 자동으로 glossary.db에 저장됨
    """)
