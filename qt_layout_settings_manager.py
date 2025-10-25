# -*- coding: utf-8 -*-
"""
파일명: layout_settings_manager.py
설명: 앱의 레이아웃 설정(QSplitter 크기, F7-F12 위젯 on/off)을 자동 저장/복구하는 모듈
버전: 1.0.0
생성일: 2025-10-18

기능:
- 각 탭별 QSplitter 크기 저장/복구
- F7~F12 단축키 위젯의 on/off 상태 저장/복구
- 앱 시작 시 자동으로 이전 설정 복구
"""

import json
import logging

logger = logging.getLogger(__name__)


class LayoutSettingsManager:
    """
    레이아웃 설정을 데이터베이스에서 관리하는 클래스입니다.
    """

    def __init__(self, db_manager):
        """
        Args:
            db_manager: DatabaseManager 인스턴스
        """
        self.db_manager = db_manager

    # ============================================================================
    # QSplitter 설정 저장/복구
    # ============================================================================

    def save_splitter_sizes(self, tab_name, splitter_name, sizes):
        """
        특정 탭의 QSplitter 크기를 저장합니다.

        Args:
            tab_name (str): 탭 이름 (예: "NLK 검색", "Dewey 분류 검색")
            splitter_name (str): splitter 이름 (예: "main", "input", "detail")
            sizes (list): [int, int, ...] splitter의 각 패널 크기
        """
        try:
            key = f"splitter_{tab_name}_{splitter_name}"
            value = json.dumps(sizes)  # 리스트를 JSON 문자열로 변환
            description = f"{tab_name} 탭의 {splitter_name} splitter 크기"

            self.db_manager.set_setting(key, value, description)
            logger.info(f"✅ Splitter 설정 저장: {key} = {sizes}")
        except Exception as e:
            logger.error(f"❌ Splitter 설정 저장 실패: {e}")

    def load_splitter_sizes(self, tab_name, splitter_name, default_sizes=None):
        """
        특정 탭의 QSplitter 크기를 복구합니다.

        Args:
            tab_name (str): 탭 이름
            splitter_name (str): splitter 이름
            default_sizes (list): 저장된 설정이 없을 때 기본값

        Returns:
            list: splitter 크기 리스트 또는 None
        """
        try:
            key = f"splitter_{tab_name}_{splitter_name}"
            value = self.db_manager.get_setting(key)

            if value:
                sizes = json.loads(value)  # JSON 문자열을 리스트로 변환
                logger.info(f"✅ Splitter 설정 복구: {key} = {sizes}")
                return sizes
            else:
                logger.info(f"ℹ️ Splitter 설정 없음: {key} (기본값 사용)")
                return default_sizes
        except Exception as e:
            logger.error(f"❌ Splitter 설정 복구 실패: {e}")
            return default_sizes

    def save_all_splitter_sizes(self, splitter_configs):
        """
        여러 splitter의 크기를 한 번에 저장합니다.

        Args:
            splitter_configs (dict): 저장할 설정
                {
                    "tab_name_1": {
                        "main": [700, 300],
                        "detail": [500, 300]
                    },
                    "tab_name_2": {
                        "input": [400, 200]
                    }
                }
        """
        try:
            for tab_name, splitters in splitter_configs.items():
                for splitter_name, sizes in splitters.items():
                    self.save_splitter_sizes(tab_name, splitter_name, sizes)
            logger.info("✅ 모든 Splitter 설정 저장 완료")
        except Exception as e:
            logger.error(f"❌ 모든 Splitter 설정 저장 실패: {e}")

    # ============================================================================
    # F7~F12 위젯 on/off 설정 저장/복구
    # ============================================================================

    def save_widget_visibility(self, tab_name, widget_configs):
        """
        특정 탭의 위젯 표시/숨김 설정을 저장합니다.

        Args:
            tab_name (str): 탭 이름
            widget_configs (dict): 위젯 on/off 설정
                {
                    "detail_panel": True,  # F7
                    "filter_panel": True,  # F8
                    "search_panel": False  # F9
                }
        """
        try:
            key = f"widget_visibility_{tab_name}"
            value = json.dumps(widget_configs)
            description = f"{tab_name} 탭의 위젯 표시/숨김 설정 (F7-F12)"

            self.db_manager.set_setting(key, value, description)
            logger.info(f"✅ 위젯 표시/숨김 설정 저장: {key}")
        except Exception as e:
            logger.error(f"❌ 위젯 표시/숨김 설정 저장 실패: {e}")

    def load_widget_visibility(self, tab_name, default_config=None):
        """
        특정 탭의 위젯 표시/숨김 설정을 복구합니다.

        Args:
            tab_name (str): 탭 이름
            default_config (dict): 저장된 설정이 없을 때 기본값

        Returns:
            dict: 위젯 설정 또는 None
        """
        try:
            key = f"widget_visibility_{tab_name}"
            value = self.db_manager.get_setting(key)

            if value:
                config = json.loads(value)
                logger.info(f"✅ 위젯 표시/숨김 설정 복구: {key}")
                return config
            else:
                logger.info(f"ℹ️ 위젯 표시/숨김 설정 없음: {key} (기본값 사용)")
                return default_config
        except Exception as e:
            logger.error(f"❌ 위젯 표시/숨김 설정 복구 실패: {e}")
            return default_config

    def save_all_widget_visibility(self, all_configs):
        """
        모든 탭의 위젯 설정을 한 번에 저장합니다.

        Args:
            all_configs (dict): 모든 탭의 위젯 설정
                {
                    "NLK 검색": {"detail_panel": True, ...},
                    "Dewey 분류 검색": {"filter_panel": False, ...}
                }
        """
        try:
            for tab_name, config in all_configs.items():
                self.save_widget_visibility(tab_name, config)
            logger.info("✅ 모든 위젯 표시/숨김 설정 저장 완료")
        except Exception as e:
            logger.error(f"❌ 모든 위젯 표시/숨김 설정 저장 실패: {e}")

    # ============================================================================
    # 통합 저장/복구 (앱 종료/시작 시 호출)
    # ============================================================================

    def save_all_layout_settings(self, splitter_configs, widget_configs):
        """
        모든 레이아웃 설정을 한 번에 저장합니다. (앱 종료 시 호출)

        Args:
            splitter_configs (dict): QSplitter 설정
            widget_configs (dict): 위젯 표시/숨김 설정
        """
        try:
            self.save_all_splitter_sizes(splitter_configs)
            self.save_all_widget_visibility(widget_configs)
            logger.info("✅ 모든 레이아웃 설정 저장 완료")
        except Exception as e:
            logger.error(f"❌ 모든 레이아웃 설정 저장 실패: {e}")

    def load_all_layout_settings(self, tab_names, default_splitters=None, default_widgets=None):
        """
        모든 레이아웃 설정을 한 번에 복구합니다. (앱 시작 시 호출)

        Args:
            tab_names (list): 탭 이름 리스트
            default_splitters (dict): 기본 splitter 설정
            default_widgets (dict): 기본 위젯 설정

        Returns:
            tuple: (splitter_configs, widget_configs)
        """
        try:
            splitter_configs = {}
            widget_configs = {}

            for tab_name in tab_names:
                # Splitter 설정 복구
                loaded_splitters = self.load_splitter_sizes(
                    tab_name,
                    "main",  # 기본 splitter
                    default_splitters.get(tab_name, {}).get("main") if default_splitters else None
                )
                if loaded_splitters:
                    splitter_configs[tab_name] = {"main": loaded_splitters}

                # 위젯 설정 복구
                loaded_widgets = self.load_widget_visibility(
                    tab_name,
                    default_widgets.get(tab_name) if default_widgets else None
                )
                if loaded_widgets:
                    widget_configs[tab_name] = loaded_widgets

            logger.info("✅ 모든 레이아웃 설정 복구 완료")
            return splitter_configs, widget_configs
        except Exception as e:
            logger.error(f"❌ 모든 레이아웃 설정 복구 실패: {e}")
            return default_splitters or {}, default_widgets or {}

    # ============================================================================
    # 유틸리티 메서드
    # ============================================================================

    def clear_layout_settings(self, tab_name=None):
        """
        레이아웃 설정을 초기화합니다.

        Args:
            tab_name (str): 특정 탭만 초기화. None이면 모든 설정 초기화
        """
        try:
            if tab_name:
                # 특정 탭의 설정만 삭제
                keys_to_delete = [
                    f"splitter_{tab_name}_main",
                    f"widget_visibility_{tab_name}"
                ]
                for key in keys_to_delete:
                    self.db_manager.delete_setting(key)
                logger.info(f"✅ {tab_name} 탭의 레이아웃 설정 초기화 완료")
            else:
                # 모든 레이아웃 설정 삭제 (LIKE 쿼리 사용 필요 - DB 구조에 따라 구현)
                logger.info("⚠️ 모든 레이아웃 설정 초기화는 별도 구현 필요")
        except Exception as e:
            logger.error(f"❌ 레이아웃 설정 초기화 실패: {e}")
