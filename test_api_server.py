#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API 서버 테스트 스크립트
"""

import time
import requests
import sys

print("=" * 60)
print("Flask API 서버 테스트")
print("=" * 60)

# 1. 서버가 실행 중인지 확인
print("\n1. 서버 헬스 체크...")
try:
    response = requests.get("http://localhost:5000/api/health", timeout=2)
    if response.status_code == 200:
        print("✅ 서버가 정상적으로 실행 중입니다.")
        print(f"   응답: {response.json()}")
    else:
        print(f"❌ 서버 응답 오류: {response.status_code}")
        sys.exit(1)
except requests.exceptions.ConnectionError:
    print("❌ 서버에 연결할 수 없습니다.")
    print("   먼저 qt_main_app.py를 실행하세요.")
    sys.exit(1)
except Exception as e:
    print(f"❌ 오류 발생: {e}")
    sys.exit(1)

# 2. KSH 검색 테스트
print("\n2. KSH 검색 API 테스트...")
try:
    response = requests.get("http://localhost:5000/api/ksh/search?q=한국", timeout=5)
    if response.status_code == 200:
        results = response.json()
        print(f"✅ 검색 성공: {len(results)}개 결과")
        if results:
            print(f"   첫 번째 결과: {results[0].get('display', 'N/A')}")
    else:
        print(f"❌ 검색 실패: {response.status_code}")
except Exception as e:
    print(f"❌ 오류 발생: {e}")

# 3. DDC 검색 테스트
print("\n3. DDC 검색 API 테스트...")
try:
    response = requests.get("http://localhost:5000/api/dewey/search?ddc=810", timeout=5)
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 검색 성공")
        print(f"   DDC: {result.get('main', {}).get('notation', 'N/A')}")
        print(f"   레이블: {result.get('main', {}).get('label', 'N/A')}")
    else:
        print(f"❌ 검색 실패: {response.status_code}")
except Exception as e:
    print(f"❌ 오류 발생: {e}")

print("\n" + "=" * 60)
print("테스트 완료")
print("=" * 60)
