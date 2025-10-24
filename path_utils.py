# -*- coding: utf-8 -*-
# Version: v1.0.1
# 수정일시: 2025-08-07 17:00 KST (get_main_app_dir 함수 추가)

import os
import sys

def resource_path(relative_path):
    """
    프로그램이 PyInstaller로 묶였을 때와 아닐 때의 리소스 파일 경로를 반환합니다.
    (내부 번들된 파일용)
    """
    try:
        # PyInstaller로 묶인 경우, 임시 폴더 경로를 사용합니다.
        base_path = sys._MEIPASS
    except Exception:
        # 일반 파이썬으로 실행하는 경우, 현재 스크립트 경로를 사용합니다.
        base_path = os.path.abspath(".")
    
    # 기본 경로와 파일 이름을 조합하여 최종 경로를 만듭니다.
    return os.path.join(base_path, relative_path)

def get_main_app_dir():
    """
    프로그램이 PyInstaller로 묶였을 때 .exe 파일의 실제 디렉토리 경로를 반환하고,
    그렇지 않을 경우 현재 스크립트의 디렉토리 경로를 반환합니다.
    (외부에 배포된 파일용)
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller로 묶인 경우, sys.executable은 .exe 파일의 경로를 가리킵니다.
        return os.path.dirname(sys.executable)
    # 일반 파이썬으로 실행하는 경우, 현재 스크립트의 디렉토리를 반환합니다.
    return os.path.dirname(os.path.abspath(__file__))
