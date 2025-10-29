# -*- coding: utf-8 -*-
"""SSL 인증서 설정 테스트 스크립트"""

import sys
import os

# PyInstaller 환경 시뮬레이션
print(f"Python 실행 환경: {sys.executable}")
print(f"Frozen (PyInstaller): {getattr(sys, 'frozen', False)}")

# SSL 설정 적용
from ssl_cert_utils import configure_ssl_certificates
configure_ssl_certificates()

# HTTPS 요청 테스트
import requests

try:
    print("\n[테스트 1] HTTPS 요청 (네이버)")
    response = requests.get("https://www.naver.com", timeout=5)
    print(f"✅ 성공: 상태 코드 {response.status_code}")
except Exception as e:
    print(f"❌ 실패: {e}")

try:
    print("\n[테스트 2] HTTPS 요청 (Yes24)")
    response = requests.get("https://www.yes24.com", timeout=5)
    print(f"✅ 성공: 상태 코드 {response.status_code}")
except Exception as e:
    print(f"❌ 실패: {e}")

try:
    print("\n[테스트 3] HTTPS 요청 (교보문고)")
    response = requests.get("https://www.kyobobook.co.kr", timeout=5)
    print(f"✅ 성공: 상태 코드 {response.status_code}")
except Exception as e:
    print(f"❌ 실패: {e}")

print("\n모든 테스트 완료!")
input("엔터를 눌러 종료...")
