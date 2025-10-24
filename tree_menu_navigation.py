# -*- coding: utf-8 -*-
# 파일명: tree_menu_navigation.py
# Version: v1.0.0
# 설명: 트리메뉴 스타일 네비게이션 구현

import tkinter as tk
import customtkinter as ctk
from tkinter import ttk
from ui_constants import UI_CONSTANTS


class TreeMenuNavigation:
    """트리메뉴 스타일 네비게이션 클래스"""

    def __init__(self, parent, app_instance, tab_registry):
        self.parent = parent
        self.app_instance = app_instance
        self.tab_registry = tab_registry
        self.current_tab_frame = None
        self.tab_frames = {}

        # 탭 그룹 정의
        self.tab_groups = {
            "검색": [
                "MARC 추출",
                "NLK 검색",
                "LC 검색",
                "NDL + CiNii 검색",
                "Western 검색",
                "Global 통합검색",
                "납본 ID 검색",
                "Google Books",
            ],
            "저작물/저자": [
                "저자전거",
                "상세 저작물 정보",
                "간략 저작물 정보",
            ],
            "주제어": [
                "KSH Hybrid 검색",
                "KSH Local DB 검색",
            ],
            "분류/AI": ["Dewey 분류 검색", "네이버 책 검색", "Gemini AI DDC 분류"],
            "도구": ["Python Test"],
            "설정": ["설정"],
        }
        self.setup_ui()
        # -------------------
        # 🎯 개선 2: 마지막 선택된 탭 복원
        self._restore_last_selected_tab()
        # -------------------

    def _restore_last_selected_tab(self):
        """마지막으로 선택된 탭을 복원합니다."""
        try:
            if hasattr(self.app_instance, "get_last_selected_tab"):
                last_tab = self.app_instance.get_last_selected_tab()
                if last_tab and last_tab in self.tab_frames:
                    # 약간의 지연 후 탭 복원 (UI 초기화 완료 후)
                    self.app_instance.root.after(100, lambda: self.show_tab(last_tab))
                    return
        except Exception as e:
            print(f"마지막 탭 복원 실패: {e}")

        # 실패하면 기본적으로 첫 번째 탭 표시
        self.show_first_tab()

    def save_last_selected_tab(self, tab_name):
        """마지막 선택된 탭을 설정에 저장합니다."""
        try:
            # 간단한 파일 저장 방식
            import os
            import json

            config_file = os.path.join(os.path.dirname(__file__), "last_tab.json")
            config = {"last_tab": tab_name}

            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"마지막 탭 저장 실패: {e}")

    def get_last_selected_tab(self):
        """저장된 마지막 선택 탭을 가져옵니다."""
        try:
            import os
            import json

            config_file = os.path.join(os.path.dirname(__file__), "last_tab.json")
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("last_tab")
        except Exception as e:
            print(f"마지막 탭 로드 실패: {e}")

        return None

    def setup_ui(self):
        """트리메뉴 UI를 구성합니다."""
        # 메인 컨테이너를 2분할로 설정
        self.parent.grid_columnconfigure(0, weight=0)  # 트리메뉴 (고정 너비)
        self.parent.grid_columnconfigure(1, weight=1)  # 콘텐츠 영역 (확장)
        self.parent.grid_rowconfigure(0, weight=1)

        # 트리메뉴 프레임
        self.tree_menu_frame = ctk.CTkFrame(
            self.parent,
            fg_color=UI_CONSTANTS.BACKGROUND_SECONDARY,
            corner_radius=0,
            width=280,
        )
        self.tree_menu_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        self.tree_menu_frame.grid_propagate(False)  # 크기 고정

        # 트리뷰 생성
        self.create_treeview()

        # -------------------
        # 🎯 개선 3: 콘텐츠 프레임 초기 배경색을 미리 설정하여 깜빡임 방지
        self.content_frame = ctk.CTkFrame(
            self.parent,
            fg_color=UI_CONSTANTS.BACKGROUND_PRIMARY,  # 초기부터 올바른 배경색
            corner_radius=0,
        )
        self.content_frame.grid(row=0, column=1, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # 추가 깜빡임 방지: 프레임을 미리 그리드에 배치하고 업데이트
        self.content_frame.update_idletasks()
        # -------------------

        # 탭 프레임들 생성
        self.create_tab_frames()

        # 마지막 선택된 탭 복원 (첫 번째 탭 표시 대신)
        self._restore_last_selected_tab()

    # ===== tree_menu_navigation.py 호버 효과 최종 버전 =====
    # 다이아몬드(◆) 효과 + 색상 변화 조합

    def create_treeview(self):
        """트리뷰를 생성하고 설정합니다."""
        # 트리뷰 컨테이너
        tree_container = ctk.CTkFrame(self.tree_menu_frame, fg_color="transparent")
        tree_container.pack(fill="both", expand=True, padx=5, pady=5)

        # -------------------
        # 🎯 개선 1: 제목과 토글 버튼을 포함하는 헤더 프레임
        header_frame = ctk.CTkFrame(tree_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.grid_columnconfigure(0, weight=1)  # 제목 영역 확장
        header_frame.grid_columnconfigure(1, weight=0)  # 버튼 영역 고정

        # 제목 레이블 (왼쪽 여백 10px 추가)
        title_label = ctk.CTkLabel(
            header_frame,
            text="📋 메뉴",
            font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL, "bold"),
            text_color=UI_CONSTANTS.TEXT_DEFAULT,
        )
        title_label.grid(row=0, column=0, sticky="w", padx=(10, 0))  # 왼쪽 여백 10px

        # 전체 펼치기/접기 토글 버튼
        self.expand_all_button = ctk.CTkButton(
            header_frame,
            text="📂",
            width=30,
            height=24,
            font=(UI_CONSTANTS.FONT_FAMILY, 12),
            fg_color=UI_CONSTANTS.BACKGROUND_SECONDARY,
            hover_color=UI_CONSTANTS.BACKGROUND_FOURTH,
            text_color=UI_CONSTANTS.TEXT_DEFAULT,
            corner_radius=4,
            command=self.toggle_expand_all,
        )
        self.expand_all_button.grid(row=0, column=1, sticky="e", padx=(5, 0))

        # 상태 추적 변수
        self.all_expanded = True  # 시작할 때는 첫 번째 그룹이 열려있으므로 True
        # -------------------

        # Tkinter 트리뷰 (CustomTkinter에는 트리뷰가 없어서 Tkinter 사용)
        style = ttk.Style()
        style.theme_use("default")

        # 기본 트리뷰 스타일 설정
        style.configure(
            "TreeMenu.Treeview",
            background=UI_CONSTANTS.BACKGROUND_TERTIARY,
            foreground=UI_CONSTANTS.TEXT_DEFAULT,
            fieldbackground=UI_CONSTANTS.BACKGROUND_TERTIARY,
            font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL),
            rowheight=28,
            borderwidth=0,
            relief="flat",
        )

        style.map(
            "TreeMenu.Treeview",
            background=[("selected", UI_CONSTANTS.ACCENT_BLUE)],
            foreground=[("selected", UI_CONSTANTS.TEXT_BUTTON)],
        )

        style.configure(
            "TreeMenu.Treeview.Heading",
            background=UI_CONSTANTS.BACKGROUND_SECONDARY,
            foreground=UI_CONSTANTS.TEXT_DEFAULT,
            font=(UI_CONSTANTS.FONT_FAMILY, UI_CONSTANTS.FONT_SIZE_NORMAL, "bold"),
            borderwidth=0,
            relief="flat",
        )

        # 트리뷰 프레임
        tree_frame = tk.Frame(tree_container, bg=UI_CONSTANTS.BACKGROUND_TERTIARY)
        tree_frame.pack(fill="both", expand=True)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # 트리뷰 생성
        self.tree = ttk.Treeview(
            tree_frame, style="TreeMenu.Treeview", show="tree", selectmode="browse"
        )

        # ✅ LC 탭 스타일의 수직 스크롤바 (ctk.CTkScrollbar 사용)
        vsb = ctk.CTkScrollbar(
            tree_frame,
            command=self.tree.yview,
            fg_color=UI_CONSTANTS.BACKGROUND_TERTIARY,
            button_color=UI_CONSTANTS.ACCENT_BLUE,
            button_hover_color=UI_CONSTANTS.SCROLLBAR_ACTIVE_THUMB,
        )

        # ✅ LC 탭 스타일의 수평 스크롤바 (ctk.CTkScrollbar 사용)
        hsb = ctk.CTkScrollbar(
            tree_frame,
            orientation="horizontal",
            command=self.tree.xview,
            fg_color=UI_CONSTANTS.BACKGROUND_TERTIARY,
            button_color=UI_CONSTANTS.ACCENT_BLUE,
            button_hover_color=UI_CONSTANTS.SCROLLBAR_ACTIVE_THUMB,
        )

        # 트리뷰에 스크롤바 연결
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # grid를 사용하여 위젯 배치
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # 트리 항목 추가
        self.populate_tree()

        # 호버 관련 상태 변수
        self.hover_timer = None
        self.last_hovered_item = None
        self.hover_delay = 200
        self.is_hovering = False
        self.current_hover_item = None
        self._original_texts = {}  # 다이아몬드 효과용 원본 텍스트 저장
        self.hover_tags_created = False

        # 호버 효과를 위한 태그 생성
        self._create_hover_tags()

        # 이벤트 바인딩
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Enter>", self.on_tree_enter)
        self.tree.bind("<Motion>", self.on_tree_motion)
        self.tree.bind("<Leave>", self.on_tree_leave)

        # 첫 번째 그룹 펼치기
        if self.tree.get_children():
            first_group = self.tree.get_children()[0]
            self.tree.item(first_group, open=True)

    def _create_hover_tags(self):
        """호버 효과를 위한 태그 생성"""
        try:
            if not self.hover_tags_created:
                # 호버 태그 설정 (색상 변화)
                self.tree.tag_configure(
                    "hover",
                    background=UI_CONSTANTS.BACKGROUND_FOURTH,
                    foreground=UI_CONSTANTS.TEXT_HIGHLIGHT,
                )

                # 일반 태그 설정
                self.tree.tag_configure(
                    "normal",
                    background=UI_CONSTANTS.BACKGROUND_TERTIARY,
                    foreground=UI_CONSTANTS.TEXT_DEFAULT,
                )

                self.hover_tags_created = True
        except Exception as e:
            print(f"태그 생성 실패: {e}")

    def on_tree_enter(self, event):
        """트리뷰에 마우스가 진입했을 때"""
        self.is_hovering = True

        # 태그가 생성되지 않았으면 생성
        if not self.hover_tags_created:
            self._create_hover_tags()

    def on_tree_motion(self, event):
        """트리뷰 내에서 마우스가 움직일 때"""
        try:
            # 현재 마우스 위치의 아이템 찾기
            item_id = self.tree.identify_row(event.y)

            # 빈 공간이나 무효한 아이템은 무시
            if not item_id:
                self._clear_hover_effect()
                return

            # 스크롤바 영역 체크
            tree_width = self.tree.winfo_width() - 20
            if event.x > tree_width:
                self._clear_hover_effect()
                return

            # -------------------
            # 🎯 새로운 아이템에 호버할 때만 효과 적용
            if item_id != self.current_hover_item:
                self._clear_hover_effect()

                # 새 아이템에 호버 효과 적용
                if item_id and self.tree.exists(item_id):
                    self.current_hover_item = item_id

                    # 선택된 아이템이 아닌 경우에만 호버 효과
                    if item_id not in self.tree.selection():
                        # 1. 색상 변화 효과
                        self._apply_color_hover_effect(item_id)

                        # 2. 다이아몬드 효과 (그룹 아이템만)
                        if self.tree.get_children(item_id):  # 그룹인 경우
                            self._apply_diamond_hover_effect(item_id)

                    # 마우스 커서 변경
                    self.tree.configure(cursor="hand2")
            # -------------------

            # 기존 펼치기 타이머 로직
            if item_id != self.last_hovered_item:
                if self.hover_timer:
                    self.app_instance.root.after_cancel(self.hover_timer)
                    self.hover_timer = None

                self.last_hovered_item = item_id

                # 유효한 그룹 아이템인 경우에만 호버 타이머 시작
                if item_id and self.tree.get_children(item_id):
                    if not self.tree.item(item_id, "open"):
                        self.hover_timer = self.app_instance.root.after(
                            self.hover_delay, lambda: self.on_hover_expand(item_id)
                        )
        except Exception:
            pass

    def _apply_color_hover_effect(self, item_id):
        """색상 변화 호버 효과 적용"""
        try:
            if item_id and self.tree.exists(item_id):
                # 태그를 사용해서 배경색 변경
                current_tags = list(self.tree.item(item_id, "tags"))
                if "hover" not in current_tags:
                    # 기존 태그 제거하고 hover 태그 추가
                    new_tags = [
                        tag for tag in current_tags if tag not in ["normal", "selected"]
                    ]
                    new_tags.append("hover")
                    self.tree.item(item_id, tags=new_tags)
        except Exception as e:
            print(f"색상 호버 효과 적용 실패: {e}")

    def _apply_diamond_hover_effect(self, item_id):
        """다이아몬드(◆) 호버 효과 적용 - 그룹 아이템만"""
        try:
            if item_id and self.tree.exists(item_id):
                # 원본 텍스트 저장
                original_text = self.tree.item(item_id, "text")
                self._original_texts[item_id] = original_text

                # 텍스트에 다이아몬드 추가
                if "◆" not in original_text:
                    # 각 그룹 아이콘 뒤에 다이아몬드 추가
                    diamond_text = (
                        original_text.replace("📁", "📁◆")
                        .replace("🔍", "🔍◆")
                        .replace("📋", "📋◆")
                        .replace("🏷️", "🏷️◆")
                        .replace("📊", "📊◆")
                        .replace("🔧", "🔧◆")
                        .replace("⚙️", "⚙️◆")
                    )
                    self.tree.item(item_id, text=diamond_text)
        except Exception:
            pass

    def _clear_hover_effect(self):
        """호버 효과 제거 (색상 + 다이아몬드)"""
        try:
            # 마우스 커서 원래대로
            self.tree.configure(cursor="")

            if self.current_hover_item and self.tree.exists(self.current_hover_item):
                # 1. 색상 효과 제거
                current_tags = list(self.tree.item(self.current_hover_item, "tags"))
                if "hover" in current_tags:
                    # hover 태그 제거하고 normal 태그 추가
                    new_tags = [tag for tag in current_tags if tag != "hover"]
                    if (
                        "normal" not in new_tags
                        and self.current_hover_item not in self.tree.selection()
                    ):
                        new_tags.append("normal")
                    self.tree.item(self.current_hover_item, tags=new_tags)

                # 2. 다이아몬드 효과 제거
                if self.current_hover_item in self._original_texts:
                    original_text = self._original_texts[self.current_hover_item]
                    self.tree.item(self.current_hover_item, text=original_text)
                    del self._original_texts[self.current_hover_item]

            self.current_hover_item = None
        except Exception as e:
            print(f"호버 효과 제거 실패: {e}")

    def on_tree_leave(self, event):
        """트리뷰에서 마우스가 나갔을 때"""
        self.is_hovering = False

        # 호버 효과 즉시 제거
        self._clear_hover_effect()

        # 약간의 지연 후 정리
        self.app_instance.root.after(100, self._cleanup_hover_if_not_hovering)

    def _cleanup_hover_if_not_hovering(self):
        """호버 상태가 아닐 때만 정리"""
        if not self.is_hovering:
            if self.hover_timer:
                self.app_instance.root.after_cancel(self.hover_timer)
                self.hover_timer = None
            self.last_hovered_item = None
            self._clear_hover_effect()

    def on_hover_expand(self, item_id):
        """호버 지연 후 그룹 펼치기 (아코디언 방식 제거)"""
        try:
            if not item_id or not self.tree.exists(item_id):
                return

            # 그룹 아이템인지 확인 (자식이 있는 경우)
            if self.tree.get_children(item_id):
                # 현재 닫혀있으면 펼치기
                if not self.tree.item(item_id, "open"):
                    self.tree.item(item_id, open=True)
                    # 아코디언 방식 철폐 - 다른 그룹들 그대로 유지

        except Exception:
            pass
        finally:
            # 타이머 정리
            self.hover_timer = None

    def toggle_expand_all(self):
        """전체 펼치기/접기 토글"""
        try:
            if self.all_expanded:
                # 모든 그룹 접기
                for group_item in self.tree.get_children():
                    if self.tree.get_children(group_item):  # 그룹인 경우만
                        self.tree.item(group_item, open=False)

                self.expand_all_button.configure(text="📁")  # 접힌 폴더 아이콘
                self.all_expanded = False
                self.app_instance.log_message(
                    "정보: 모든 메뉴 그룹을 접었습니다.", level="INFO"
                )
            else:
                # 모든 그룹 펼치기
                for group_item in self.tree.get_children():
                    if self.tree.get_children(group_item):  # 그룹인 경우만
                        self.tree.item(group_item, open=True)

                self.expand_all_button.configure(text="📂")  # 열린 폴더 아이콘
                self.all_expanded = True
                self.app_instance.log_message(
                    "정보: 모든 메뉴 그룹을 펼쳤습니다.", level="INFO"
                )

        except Exception as e:
            self.app_instance.log_message(f"오류: 메뉴 토글 실패: {e}", level="ERROR")

    def populate_tree(self):
        """트리에 항목들을 추가합니다 (기본 태그 설정)"""
        self.tree_item_map = {}

        for group_name, tab_names in self.tab_groups.items():
            # 그룹 아이템 추가 (기본 normal 태그)
            group_icons = {
                "검색": "🔍",
                "저작물/저자": "📋",
                "주제어": "🔤",
                "분류/AI": "📊",
                "도구": "🔧",
                "설정": "⚙️",
            }
            icon = group_icons.get(group_name, "📁")
            group_item = self.tree.insert(
                "", "end", text=f"{icon} {group_name}", open=False, tags=("normal",)
            )

            # 각 그룹에 속한 탭들 추가 (기본 normal 태그)
            for tab_name in tab_names:
                tab_info = None
                for tab_data in self.tab_registry:
                    if tab_data["display_name"] == tab_name:
                        tab_info = tab_data
                        break

                if tab_info:
                    tab_icon = self.get_tab_icon(tab_name)
                    child_item = self.tree.insert(
                        group_item,
                        "end",
                        text=f"{tab_icon} {tab_name}",
                        tags=("normal",),
                    )
                    self.tree_item_map[child_item] = tab_info

    def _create_hover_tags(self):
        """호버 효과를 위한 태그 생성"""
        try:
            if not self.hover_tags_created:
                # 호버 태그 설정 (색상 변화)
                self.tree.tag_configure(
                    "hover",
                    background=UI_CONSTANTS.BACKGROUND_FOURTH,
                    foreground=UI_CONSTANTS.TEXT_HIGHLIGHT,
                )

                # 일반 태그 설정
                self.tree.tag_configure(
                    "normal",
                    background=UI_CONSTANTS.BACKGROUND_TERTIARY,
                    foreground=UI_CONSTANTS.TEXT_DEFAULT,
                )

                self.hover_tags_created = True
        except Exception as e:
            print(f"태그 생성 실패: {e}")

    def on_tree_enter(self, event):
        """트리뷰에 마우스가 진입했을 때"""
        self.is_hovering = True

        # 태그가 생성되지 않았으면 생성
        if not self.hover_tags_created:
            self._create_hover_tags()

    def on_tree_motion(self, event):
        """트리뷰 내에서 마우스가 움직일 때"""
        try:
            # 현재 마우스 위치의 아이템 찾기
            item_id = self.tree.identify_row(event.y)

            # 빈 공간이나 무효한 아이템은 무시
            if not item_id:
                self._clear_hover_effect()
                return

            # 스크롤바 영역 체크
            tree_width = self.tree.winfo_width() - 20
            if event.x > tree_width:
                self._clear_hover_effect()
                return

            # -------------------
            # 🎯 새로운 아이템에 호버할 때만 효과 적용
            if item_id != self.current_hover_item:
                self._clear_hover_effect()

                # 새 아이템에 호버 효과 적용
                if item_id and self.tree.exists(item_id):
                    self.current_hover_item = item_id

                    # 선택된 아이템이 아닌 경우에만 호버 효과
                    if item_id not in self.tree.selection():
                        # 1. 색상 변화 효과
                        self._apply_color_hover_effect(item_id)

                        # 2. 다이아몬드 효과 (그룹 아이템만)
                        if self.tree.get_children(item_id):  # 그룹인 경우
                            self._apply_diamond_hover_effect(item_id)

                    # 마우스 커서 변경
                    self.tree.configure(cursor="hand2")
            # -------------------

            # 기존 펼치기 타이머 로직
            if item_id != self.last_hovered_item:
                if self.hover_timer:
                    self.app_instance.root.after_cancel(self.hover_timer)
                    self.hover_timer = None

                self.last_hovered_item = item_id

                # 유효한 그룹 아이템인 경우에만 호버 타이머 시작
                if item_id and self.tree.get_children(item_id):
                    if not self.tree.item(item_id, "open"):
                        self.hover_timer = self.app_instance.root.after(
                            self.hover_delay, lambda: self.on_hover_expand(item_id)
                        )
        except Exception:
            pass

    def _apply_color_hover_effect(self, item_id):
        """색상 변화 호버 효과 적용"""
        try:
            if item_id and self.tree.exists(item_id):
                # 태그를 사용해서 배경색 변경
                current_tags = list(self.tree.item(item_id, "tags"))
                if "hover" not in current_tags:
                    # 기존 태그 제거하고 hover 태그 추가
                    new_tags = [
                        tag for tag in current_tags if tag not in ["normal", "selected"]
                    ]
                    new_tags.append("hover")
                    self.tree.item(item_id, tags=new_tags)
        except Exception as e:
            print(f"색상 호버 효과 적용 실패: {e}")

    def _apply_diamond_hover_effect(self, item_id):
        """다이아몬드(◆) 호버 효과 적용 - 그룹 아이템만"""
        try:
            if item_id and self.tree.exists(item_id):
                # 원본 텍스트 저장
                original_text = self.tree.item(item_id, "text")
                self._original_texts[item_id] = original_text

                # 텍스트에 다이아몬드 추가
                if "◆" not in original_text:
                    # 각 그룹 아이콘 뒤에 다이아몬드 추가
                    diamond_text = (
                        original_text.replace("📁", "📁◆")
                        .replace("🔍", "🔍◆")
                        .replace("📋", "📋◆")
                        .replace("🏷️", "🏷️◆")
                        .replace("📊", "📊◆")
                        .replace("🔧", "🔧◆")
                        .replace("⚙️", "⚙️◆")
                    )
                    self.tree.item(item_id, text=diamond_text)
        except Exception:
            pass

    def _clear_hover_effect(self):
        """호버 효과 제거 (색상 + 다이아몬드)"""
        try:
            # 마우스 커서 원래대로
            self.tree.configure(cursor="")

            if self.current_hover_item and self.tree.exists(self.current_hover_item):
                # 1. 색상 효과 제거
                current_tags = list(self.tree.item(self.current_hover_item, "tags"))
                if "hover" in current_tags:
                    # hover 태그 제거하고 normal 태그 추가
                    new_tags = [tag for tag in current_tags if tag != "hover"]
                    if (
                        "normal" not in new_tags
                        and self.current_hover_item not in self.tree.selection()
                    ):
                        new_tags.append("normal")
                    self.tree.item(self.current_hover_item, tags=new_tags)

                # 2. 다이아몬드 효과 제거
                if self.current_hover_item in self._original_texts:
                    original_text = self._original_texts[self.current_hover_item]
                    self.tree.item(self.current_hover_item, text=original_text)
                    del self._original_texts[self.current_hover_item]

            self.current_hover_item = None
        except Exception as e:
            print(f"호버 효과 제거 실패: {e}")

    def on_tree_leave(self, event):
        """트리뷰에서 마우스가 나갔을 때"""
        self.is_hovering = False

        # 호버 효과 즉시 제거
        self._clear_hover_effect()

        # 약간의 지연 후 정리
        self.app_instance.root.after(100, self._cleanup_hover_if_not_hovering)

    def _cleanup_hover_if_not_hovering(self):
        """호버 상태가 아닐 때만 정리"""
        if not self.is_hovering:
            if self.hover_timer:
                self.app_instance.root.after_cancel(self.hover_timer)
                self.hover_timer = None
            self.last_hovered_item = None
            self._clear_hover_effect()

    def on_hover_expand(self, item_id):
        """호버 지연 후 그룹 펼치기 (아코디언 방식 제거)"""
        try:
            if not item_id or not self.tree.exists(item_id):
                return

            # 그룹 아이템인지 확인 (자식이 있는 경우)
            if self.tree.get_children(item_id):
                # 현재 닫혀있으면 펼치기
                if not self.tree.item(item_id, "open"):
                    self.tree.item(item_id, open=True)
                    # 아코디언 방식 철폐 - 다른 그룹들 그대로 유지

        except Exception:
            pass
        finally:
            # 타이머 정리
            self.hover_timer = None

    def populate_tree(self):
        """트리에 항목들을 추가합니다 (기본 태그 설정)"""
        self.tree_item_map = {}

        for group_name, tab_names in self.tab_groups.items():
            # 그룹 아이템 추가 (기본 normal 태그)
            group_icons = {
                "검색": "🔍",
                "저작물/저자": "📋",
                "주제어": "🔤",
                "분류/AI": "📊",
                "도구": "🔧",
                "설정": "⚙️",
            }
            icon = group_icons.get(group_name, "📁")
            group_item = self.tree.insert(
                "", "end", text=f"{icon} {group_name}", open=False, tags=("normal",)
            )

            # 각 그룹에 속한 탭들 추가 (기본 normal 태그)
            for tab_name in tab_names:
                tab_info = None
                for tab_data in self.tab_registry:
                    if tab_data["display_name"] == tab_name:
                        tab_info = tab_data
                        break

                if tab_info:
                    tab_icon = self.get_tab_icon(tab_name)
                    child_item = self.tree.insert(
                        group_item,
                        "end",
                        text=f"{tab_icon} {tab_name}",
                        tags=("normal",),
                    )
                    self.tree_item_map[child_item] = tab_info

    def get_tab_icon(self, tab_name):
        """탭 이름에 따른 아이콘을 반환합니다."""
        icon_map = {
            # 검색 관련
            "KSH Local DB 검색": "💾",
            "KSH Hybrid 검색": "🔄",
            "LC 검색": "🇺🇸",
            "NDL + CiNii 검색": "🗾",
            "Western 검색": "🇩🇪",
            "Global 통합검색": "🇫🇷",
            "납본 ID 검색": "🇪🇸",
            "Google Books": "📚",
            "네이버 책 검색": "🔎",
            "NLK 검색": "🇰🇷",
            "저자전거": "👤",
            "상세 저작물 정보": "📋",
            "간략 저작물 정보": "🔢",
            "Dewey 분류 검색": "📊",
            # AI/분석
            "Gemini AI DDC 분류": "✨",
            # 도구
            "MARC 추출": "⚡",
            "Python Test": "🐍",
            # 설정
            "⚙️ 설정": "⚙️",
        }
        return icon_map.get(tab_name, "📄")

    def create_tab_frames(self):
        """각 탭의 프레임을 생성합니다."""
        for tab_info in self.tab_registry:
            try:
                # 탭 프레임 생성
                tab_frame = ctk.CTkFrame(
                    self.content_frame,
                    fg_color=UI_CONSTANTS.BACKGROUND_PRIMARY,
                    corner_radius=0,
                )

                # 탭 UI 설정 함수 호출
                tab_info["setup_func"](self.app_instance, tab_frame)

                # 프레임을 딕셔너리에 저장
                self.tab_frames[tab_info["display_name"]] = tab_frame

                # app_instance에 탭 변수 설정 (기존 코드 호환성)
                setattr(self.app_instance, tab_info["var_name"], tab_frame)

            except Exception as e:
                self.app_instance.log_message(
                    f"오류: '{tab_info['display_name']}' 탭 프레임 생성 중 오류: {e}",
                    level="ERROR",
                )

    def on_tree_select(self, event):
        """트리 선택 이벤트 처리"""
        selection = self.tree.selection()
        if not selection:
            return

        item_id = selection[0]

        # 선택된 항목이 탭인지 확인
        if item_id in self.tree_item_map:
            tab_info = self.tree_item_map[item_id]
            self.show_tab(tab_info["display_name"])

    def on_tree_double_click(self, event):
        """트리 더블클릭 이벤트 처리 (그룹 펼치기/접기)"""
        item_id = self.tree.selection()[0] if self.tree.selection() else None
        if item_id and not self.tree.get_children(item_id):
            # 리프 노드(탭)인 경우 선택 이벤트만 처리
            return

        # 그룹 노드인 경우 펼치기/접기
        if item_id:
            if self.tree.item(item_id, "open"):
                self.tree.item(item_id, open=False)
            else:
                self.tree.item(item_id, open=True)

    def show_tab(self, tab_name):
        """지정된 탭을 표시합니다."""
        if tab_name not in self.tab_frames:
            return

        # 현재 탭 숨기기
        if self.current_tab_frame:
            self.current_tab_frame.grid_forget()

        # 새 탭 표시
        self.current_tab_frame = self.tab_frames[tab_name]
        self.current_tab_frame.grid(row=0, column=0, sticky="nsew")

        # 현재 탭 이름 저장 (자체 객체에 저장)
        self._current_name = tab_name

        # -------------------
        # 🎯 개선 2: 마지막 탭 설정에 저장하여 재시작 시에도 기억
        try:
            # 설정 파일에 마지막 탭 저장
            if hasattr(self.app_instance, "save_last_selected_tab"):
                self.app_instance.save_last_selected_tab(tab_name)
        except Exception as e:
            print(f"마지막 탭 저장 실패: {e}")
        # -------------------

        # 탭 변경 이벤트 발생 (기존 코드 호환성)
        if hasattr(self.app_instance, "_on_tab_change"):
            self.app_instance._on_tab_change()

        # 로그 메시지
        self.app_instance.log_message(
            f"정보: '{tab_name}' 탭으로 전환되었습니다.", level="INFO"
        )

    def show_first_tab(self):
        """첫 번째 탭을 표시합니다."""
        if self.tab_registry:
            first_tab = self.tab_registry[0]["display_name"]
            self.show_tab(first_tab)

            # 트리에서 첫 번째 탭 선택
            for item_id, tab_info in self.tree_item_map.items():
                if tab_info["display_name"] == first_tab:
                    self.tree.selection_set(item_id)
                    self.tree.focus(item_id)
                    # 해당 그룹 펼치기
                    parent = self.tree.parent(item_id)
                    if parent:
                        self.tree.item(parent, open=True)
                    break

    def select_tab_by_name(self, tab_name):
        """프로그램적으로 탭을 선택합니다."""
        for item_id, tab_info in self.tree_item_map.items():
            if tab_info["display_name"] == tab_name:
                self.tree.selection_set(item_id)
                self.tree.focus(item_id)
                self.show_tab(tab_name)

                # 해당 그룹 펼치기
                parent = self.tree.parent(item_id)
                if parent:
                    self.tree.item(parent, open=True)
                break

    def get_current_tab(self):
        """현재 선택된 탭 이름을 반환합니다."""
        if hasattr(self, "_current_name"):
            return self._current_name

        selection = self.tree.selection()
        if selection and selection[0] in self.tree_item_map:
            return self.tree_item_map[selection[0]]["display_name"]
        return None

    def get(self):
        """현재 선택된 탭 이름을 반환합니다 (CTkTabview 호환성을 위해)"""
        return self.get_current_tab()

    def set(self, tab_name):
        """지정된 탭으로 전환합니다 (CTkTabview 호환성을 위해)"""
        self.select_tab_by_name(tab_name)

    def toggle_expand_all(self):
        """전체 펼치기/접기 토글"""
        try:
            if self.all_expanded:
                # 모든 그룹 접기
                for group_item in self.tree.get_children():
                    if self.tree.get_children(group_item):  # 그룹인 경우만
                        self.tree.item(group_item, open=False)

                self.expand_all_button.configure(text="📁")  # 접힌 폴더 아이콘
                self.all_expanded = False
                self.app_instance.log_message(
                    "정보: 모든 메뉴 그룹을 접었습니다.", level="INFO"
                )
            else:
                # 모든 그룹 펼치기
                for group_item in self.tree.get_children():
                    if self.tree.get_children(group_item):  # 그룹인 경우만
                        self.tree.item(group_item, open=True)

                self.expand_all_button.configure(text="📂")  # 열린 폴더 아이콘
                self.all_expanded = True
                self.app_instance.log_message(
                    "정보: 모든 메뉴 그룹을 펼쳤습니다.", level="INFO"
                )

        except Exception as e:
            self.app_instance.log_message(f"오류: 메뉴 토글 실패: {e}", level="ERROR")


def create_tree_menu_navigation(parent, app_instance, tab_registry):
    """트리메뉴 네비게이션을 생성하는 팩토리 함수"""
    return TreeMenuNavigation(parent, app_instance, tab_registry)
