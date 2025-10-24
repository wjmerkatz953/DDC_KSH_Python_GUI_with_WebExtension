# -*- coding: utf-8 -*-
# Version: v1.0.3
# 수정일시: 2025-08-07 17:05 KST (PRESETS_FILE 경로 get_main_app_dir() 사용으로 수정)

"""
preset_manager.py - MARC 추출 로직 프리셋을 관리하는 함수들을 포함합니다.
프리셋 로드, 저장, 삭제 기능을 담당합니다.
"""

import json
import os
from path_utils import get_main_app_dir  # get_main_app_dir 함수 임포트

# 프리셋 파일 경로 설정
# .exe 파일이 있는 실제 디렉토리를 기준으로 파일을 찾도록 수정
PRESETS_FILE = os.path.join(get_main_app_dir(), "marc_extraction_presets.json")

# 프리셋 파일이 없으면 기본값으로 생성하는 함수


def create_presets_if_not_exists(file_path=None):
    """
    프리셋 파일이 없으면 기본값으로 생성하는 함수
    Args:
        file_path (str, optional): 파일 경로. None이면 기본 PRESETS_FILE 사용
    """
    target_file = file_path if file_path else PRESETS_FILE
    if not os.path.exists(target_file):
        default_presets = {
            "default_preset": {
                "field_010": ["$a"],
                "field_020": ["$a", "$b"],
                "field_245": ["$a", "$b", "$c"]
            }
        }
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(default_presets, f, indent=4, ensure_ascii=False)
        print(f"'{target_file}' 파일이 생성되었습니다.")


def load_presets():
    """
    프리셋 파일을 로드하여 딕셔너리 형태로 반환합니다.
    파일이 없거나 파싱 오류 발생 시 빈 딕셔너리를 반환합니다.
    """
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"오류: 프리셋 파일 파싱 오류: {e}")
            return {}
        except IOError as e:
            print(f"오류: 프리셋 파일 로드 중 입출력 오류: {e}")
            return {}
    return {}


def save_presets(presets):
    """
    주어진 프리셋 딕셔너리를 파일에 저장합니다.
    """
    try:
        with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=4, ensure_ascii=False)
        return True
    except IOError as e:
        print(f"오류: 프리셋 파일 저장 오류: {e}")
        return False


def add_or_update_preset(preset_name, code_content):
    """
    새로운 프리셋을 추가하거나 기존 프리셋을 업데이트합니다.
    Args:
        preset_name (str): 저장할 프리셋의 이름.
        code_content (str): 저장할 코드 내용.
    Returns:
        bool: 저장 성공 여부.
    """
    if not preset_name or not code_content:
        return False
    presets = load_presets()
    presets[preset_name] = code_content
    return save_presets(presets)


def delete_preset(preset_name):
    """
    지정된 이름의 프리셋을 삭제합니다.
    Args:
        preset_name (str): 삭제할 프리셋의 이름.
    Returns:
        bool: 삭제 성공 여부.
    """
    if not preset_name:
        return False
    presets = load_presets()
    if preset_name in presets:
        del presets[preset_name]
        return save_presets(presets)
    return False


def rename_preset(old_name, new_name):
    """
    프리셋의 이름을 변경합니다.
    Args:
        old_name (str): 기존 프리셋 이름.
        new_name (str): 새로운 프리셋 이름.
    Returns:
        bool: 이름 변경 성공 여부.
    """
    if not old_name or not new_name or old_name == new_name:
        return False
    presets = load_presets()
    if old_name in presets:
        code_content = presets[old_name]
        del presets[old_name]
        presets[new_name] = code_content
        return save_presets(presets)
    return False


def get_preset_content(preset_name):
    """
    지정된 이름의 프리셋 코드 내용을 반환합니다.
    Args:
        preset_name (str): 가져올 프리셋의 이름.
    Returns:
        str or None: 프리셋 코드 내용 또는 찾을 수 없으면 None.
    """
    presets = load_presets()
    return presets.get(preset_name)


def get_preset_names():
    """
    저장된 모든 프리셋의 이름을 리스트로 반환합니다.
    """
    presets = load_presets()
    return list(presets.keys())


def save_last_used_preset(preset_name):
    """마지막 사용한 프리셋 이름을 저장합니다."""
    try:
        # 이 파일은 동적 파일이므로, get_main_app_dir()로 경로 설정
        last_preset_file = os.path.join(get_main_app_dir(), "last_preset.txt")
        with open(last_preset_file, "w", encoding='utf-8') as f:
            f.write(preset_name)
        return True
    except IOError as e:
        print(f"오류: 마지막 사용 프리셋 저장 오류: {e}")
        return False


def load_last_used_preset():
    """마지막 사용한 프리셋 이름을 로드합니다."""
    try:
        # 이 파일은 동적 파일이므로, get_main_app_dir()로 경로 설정
        last_preset_file = os.path.join(get_main_app_dir(), "last_preset.txt")
        with open(last_preset_file, "r", encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
    except IOError as e:
        print(f"오류: 마지막 사용 프리셋 로드 오류: {e}")
        return None
