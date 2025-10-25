# -*- coding: utf-8 -*-
# 파일명: ssl_cert_utils.py
# 설명: PyInstaller 환경에서 SSL 인증서 경로를 올바르게 설정하는 유틸리티
# 생성일: 2025-10-24

import os
import sys


def configure_ssl_certificates():
    """
    PyInstaller로 패키징된 환경에서 SSL 인증서 경로를 올바르게 설정합니다.

    문제:
    - PyInstaller로 exe를 만들 때 certifi의 cacert.pem 파일이 올바르게 번들링되지 않음
    - requests 라이브러리가 HTTPS 통신 시 CA 인증서를 찾지 못해 오류 발생

    해결:
    - PyInstaller 환경(frozen) 감지 시 certifi.where()로 인증서 경로를 가져와
      환경 변수에 설정하여 requests가 올바른 경로를 사용하도록 함

    사용법:
    - 각 검색 모듈(Search_*.py)의 상단에서 import 후 호출
    """
    # PyInstaller로 패키징된 환경인지 확인
    if not getattr(sys, 'frozen', False):
        # 일반 Python 환경에서는 설정 불필요
        return

    try:
        import certifi

        # certifi가 제공하는 CA 인증서 번들 경로 가져오기
        ca_bundle_path = certifi.where()

        # requests 라이브러리가 참조하는 환경 변수 설정
        os.environ['REQUESTS_CA_BUNDLE'] = ca_bundle_path
        os.environ['SSL_CERT_FILE'] = ca_bundle_path

        print(f"[SSL] ✅ CA 인증서 경로 설정 완료: {ca_bundle_path}")

    except ImportError:
        # certifi가 설치되지 않은 경우 (거의 없지만 방어 코드)
        print("[SSL] ⚠️ certifi 패키지가 설치되지 않았습니다. SSL 검증이 실패할 수 있습니다.")
    except Exception as e:
        print(f"[SSL] ⚠️ CA 인증서 경로 설정 실패: {e}")


# 모듈 import 시 자동 실행 (선택적)
# configure_ssl_certificates()
