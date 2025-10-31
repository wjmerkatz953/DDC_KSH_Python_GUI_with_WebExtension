# -*- coding: utf-8 -*-
# 파일명: ssl_cert_utils.py v1.1.0
# 설명: PyInstaller 환경에서 SSL 인증서 경로를 올바르게 설정하는 유틸리티
# ✅ [개선] 런타임마다 경로 재확인하여 잘못된 캐시 방지
# 생성일: 2025-10-24
# 수정일: 2025-10-31

import os
import sys


def configure_ssl_certificates():
    """
    SSL 인증서 경로를 올바르게 설정합니다.

    ✅ [v1.1.0 개선]
    - 모든 환경에서 certifi 경로를 명시적으로 환경 변수에 설정
    - PyInstaller 환경에서 매 실행마다 달라지는 _MEI 경로 문제 해결
    - 이전 실행의 invalid _MEI 경로가 캐시되는 것 방지

    문제:
    - PyInstaller로 exe를 만들 때 매 실행마다 다른 _MEIXXXXXX 임시 폴더 생성
    - 이전 실행의 _MEI 경로가 환경 변수나 모듈 캐시에 남아 invalid path 오류 발생
    - requests 라이브러리가 HTTPS 통신 시 CA 인증서를 찾지 못함

    해결:
    - 모든 환경에서 certifi.where()로 올바른 인증서 경로를 가져와 환경 변수에 설정
    - PyInstaller 환경에서는 sys._MEIPASS 경로를 우선 확인
    - 런타임마다 경로를 재설정하여 캐시 문제 방지

    사용법:
    - 각 검색 모듈(Search_*.py)의 상단에서 import 후 호출
    """
    is_frozen = getattr(sys, 'frozen', False)

    try:
        import certifi

        # ✅ [핵심 개선] 올바른 CA 인증서 경로 결정 로직
        ca_bundle_path = None

        if is_frozen and hasattr(sys, '_MEIPASS'):
            # PyInstaller 환경: 현재 실행의 _MEIPASS 경로 사용
            meipass_cert = os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
            if os.path.exists(meipass_cert):
                ca_bundle_path = meipass_cert
                print(f"[SSL] ✅ PyInstaller 번들 인증서 사용: {ca_bundle_path}")
            else:
                print(f"[SSL] ⚠️ PyInstaller 번들 인증서 없음: {meipass_cert}")

        # certifi.where() 폴백 (일반 환경 또는 번들 실패 시)
        if not ca_bundle_path:
            ca_bundle_path = certifi.where()
            if os.path.exists(ca_bundle_path):
                print(f"[SSL] ✅ certifi 기본 경로 사용: {ca_bundle_path}")
            else:
                print(f"[SSL] ⚠️ certifi 경로 invalid: {ca_bundle_path}")
                ca_bundle_path = None

        # ✅ [핵심] 환경 변수 설정으로 모든 requests 호출에 적용
        if ca_bundle_path:
            os.environ['REQUESTS_CA_BUNDLE'] = ca_bundle_path
            os.environ['SSL_CERT_FILE'] = ca_bundle_path
            os.environ['CURL_CA_BUNDLE'] = ca_bundle_path
            print(f"[SSL] ✅ 환경 변수 설정 완료")
            return

        # 모든 경로가 실패한 경우: SSL 검증 비활성화 (보안 주의!)
        print(f"[SSL] ⚠️ 인증서를 찾을 수 없어 SSL 검증을 비활성화합니다.")
        os.environ['REQUESTS_CA_BUNDLE'] = ''
        os.environ['CURL_CA_BUNDLE'] = ''

        # urllib3 경고 비활성화
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            pass

        print(f"[SSL] ⚠️ SSL 검증 비활성화됨 (보안 위험 - 인증서 설치 필요)")

    except ImportError:
        # certifi가 설치되지 않은 경우
        print("[SSL] ⚠️ certifi 패키지가 설치되지 않았습니다. SSL 검증이 실패할 수 있습니다.")
    except Exception as e:
        print(f"[SSL] ⚠️ CA 인증서 경로 설정 실패: {e}")


# 모듈 import 시 자동 실행 (선택적)
# configure_ssl_certificates()
