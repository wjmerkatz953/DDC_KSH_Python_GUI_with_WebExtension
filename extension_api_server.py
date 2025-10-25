# -*- coding: utf-8 -*-
"""
파일명: extension_api_server.py
설명: 브라우저 확장 프로그램을 위한 Flask API 서버
버전: 1.0.0 (PySide6)
생성일: 2025-10-11
"""

import threading
import re
from typing import Any


class ExtensionAPIServer:
    """브라우저 확장 프로그램용 Flask API 서버"""

    def __init__(self, app_instance, db_manager, query_manager=None):
        """
        Args:
            app_instance: 메인 애플리케이션 인스턴스 (로그 기록용)
            db_manager: 데이터베이스 매니저 인스턴스
            query_manager: 검색 쿼리 매니저 인스턴스 (옵션, 없으면 자동 생성)
        """
        self.app_instance = app_instance
        self.db_manager = db_manager

        # query_manager가 없으면 생성
        if query_manager is None:
            from search_query_manager import SearchQueryManager

            self.query_manager = SearchQueryManager(db_manager)
        else:
            self.query_manager = query_manager

        self.api_app = None
        self.server_thread = None
        self.is_running = False

    def start_server(self, host: str = "127.0.0.1", port: int = 5000) -> bool:
        """
        Flask API 서버를 시작합니다.

        Args:
            host: 서버 호스트 주소 (기본값: 127.0.0.1)
            port: 서버 포트 번호 (기본값: 5000)

        Returns:
            bool: 서버 시작 성공 여부
        """
        try:
            from flask import Flask, jsonify, request
            from flask_cors import CORS
            import pandas as pd

            # Flask 앱 생성
            self.api_app = Flask(__name__)
            CORS(self.api_app)  # 익스텐션에서 접근 허용

            # ==================== API 엔드포인트 정의 ====================

            # 🎯 KSH 검색 API
            @self.api_app.route("/api/ksh/search", methods=["GET"])
            def search_ksh():
                """KSH 주제명 검색 API"""
                query = request.args.get("q", "").strip()
                if not query:
                    return jsonify([])

                try:
                    # [핵심 수정] 앱의 중앙 검색 관리자를 사용하여 통합 검색 실행
                    result = self.query_manager.search_integrated_ksh(query)

                    # search_integrated_ksh는 3개 요소를 포함한 튜플을 반환
                    if isinstance(result, tuple) and len(result) >= 3:
                        df_concepts, df_biblio, _ = result
                    else:
                        # 예외 처리: 예상치 못한 형식일 경우 빈 데이터프레임으로 초기화
                        self._log(
                            f"경고: search_integrated_ksh가 예상치 못한 결과를 반환했습니다: {type(result)}",
                            level="WARNING",
                        )
                        df_concepts = pd.DataFrame()
                        df_biblio = pd.DataFrame()

                    # 익스텐션용 간단한 형태로 변환
                    ksh_results = []

                    # 컨셉 DB 결과 처리 (필터링 없이 모든 결과 포함)
                    for _, row in df_concepts.iterrows():
                        subject = row.get(
                            "주제명", ""
                        )  # [수정] 컬럼명을 '주제명'으로 변경
                        if subject:
                            ksh_results.append(
                                {
                                    "subject": subject,
                                    "display": self._extract_display_text(subject),
                                    "category": row.get(
                                        "주제모음", ""
                                    ),  # [수정] 컬럼명을 '주제모음'으로 변경
                                    "type": "concept",
                                }
                            )

                    # 서지 DB 결과 처리
                    for _, row in df_biblio.iterrows():
                        ksh_labeled = row.get("ksh_labeled", "")
                        if ksh_labeled:
                            ksh_results.append(
                                {
                                    "subject": ksh_labeled,
                                    "display": self._extract_display_text(ksh_labeled),
                                    "ddc": row.get("ddc", ""),
                                    "title": row.get("title", ""),
                                    "type": "biblio",
                                }
                            )

                    # 전체 결과를 파일에 저장 (디버깅용)
                    import json
                    with open("extension_data.json", "w", encoding="utf-8") as f:
                        json.dump(ksh_results, f, ensure_ascii=False, indent=4)

                    return jsonify(ksh_results[:5000])

                except Exception as e:
                    import traceback

                    self._log(f"❌ KSH API 검색 실패: {e}", "ERROR")
                    self._log(traceback.format_exc(), "ERROR")
                    return jsonify({"error": str(e)}), 500

            # 🎯 DDC 검색 API
            @self.api_app.route("/api/dewey/search", methods=["GET"])
            def search_dewey():
                """DDC(듀이십진분류법) 검색 API"""
                ddc_code = request.args.get("ddc", "").strip()
                if not ddc_code:
                    return jsonify({"error": "DDC code required"}), 400

                try:
                    from Search_Dewey import DeweyClient

                    # DeweyClient 인스턴스 생성 및 검색
                    dewey_client = DeweyClient(self.db_manager)
                    context = dewey_client.get_dewey_context(ddc_code)

                    # 익스텐션용 간단한 형태로 변환
                    main_info = context.get("main", {})
                    result = {
                        "main": {
                            "notation": main_info.get("notation", ""),
                            "label": self._extract_dewey_label(main_info),
                            "definition": main_info.get("definition", ""),
                        },
                        "broader": [
                            {
                                "notation": item.get("notation", ""),
                                "label": self._extract_dewey_label(item),
                            }
                            for item in context.get("broader", [])[:5]
                        ],
                        "narrower": [
                            {
                                "notation": item.get("notation", ""),
                                "label": self._extract_dewey_label(item),
                            }
                            for item in context.get("narrower", [])[:10]
                        ],
                        "related": [
                            {
                                "notation": item.get("notation", ""),
                                "label": self._extract_dewey_label(item),
                            }
                            for item in context.get("related", [])[:5]
                        ],
                    }

                    return jsonify(result)

                except Exception as e:
                    self._log(f"❌ DDC API 검색 실패: {e}", "ERROR")
                    return jsonify({"error": str(e)}), 500

            # 🎯 서버 헬스 체크 API
            @self.api_app.route("/api/health", methods=["GET"])
            def health_check():
                """서버 상태 확인 API"""
                return jsonify(
                    {
                        "status": "healthy",
                        "app": "MetaTetus Extension API",
                        "version": "1.0.0",
                    }
                )

            # ==================== 서버 시작 ====================

            def run_server():
                """별도 스레드에서 Flask 서버 실행"""
                try:
                    self.api_app.run(
                        host=host,
                        port=port,
                        debug=False,
                        use_reloader=False,
                        threaded=True,
                    )
                except Exception as e:
                    self._log(f"❌ API 서버 실행 실패: {e}", "ERROR")
                finally:
                    self.is_running = False

            # 데몬 스레드로 서버 시작
            self.server_thread = threading.Thread(target=run_server, daemon=True)
            self.server_thread.start()
            self.is_running = True

            msg = (
                f"✅ 익스텐션용 API 서버가 " f"http://{host}:{port}에서 시작되었습니다."
            )
            self._log(msg, "INFO")
            return True

        except ImportError:
            msg = (
                "⚠️ Flask가 설치되지 않았습니다. "
                "익스텐션 기능을 사용하려면 "
                "'pip install flask flask-cors'를 실행하세요."
            )
            self._log(msg, "WARNING")
            return False

        except Exception as e:
            self._log(f"⚠️ 익스텐션 API 서버 시작 실패: {e}", "WARNING")
            return False

    def stop_server(self):
        """서버를 중지합니다 (현재는 데몬 스레드로 구동되므로 자동 종료됨)"""
        self.is_running = False
        self._log("ℹ️ API 서버가 종료되었습니다.", "INFO")

    # ==================== 헬퍼 메서드 ====================

    def _extract_display_text(self, marc_text: str) -> str:
        """
        MARC 형식에서 표시용 텍스트를 추출합니다.

        Args:
            marc_text: MARC 형식 텍스트 (예: ▼a한국 문학▼0KSH123▲)

        Returns:
            str: 추출된 표시용 텍스트
        """
        if not marc_text:
            return ""

        # ▼a텍스트▼0코드▲ 형태에서 텍스트 부분만 추출
        match = re.search(r"▼a([^▼]+)", marc_text)
        if match:
            return match.group(1).strip()

        return marc_text

    def _extract_dewey_label(self, item: Any) -> str:
        """
        Dewey 아이템에서 레이블을 추출합니다.

        Args:
            item: Dewey 아이템 (딕셔너리 또는 기타 타입)

        Returns:
            str: 추출된 레이블
        """
        if isinstance(item, dict):
            pref_label = item.get("prefLabel", {})
            if isinstance(pref_label, dict):
                return (
                    pref_label.get("ko")
                    or pref_label.get("en")
                    or pref_label.get("label", "")
                )
            return str(pref_label) if pref_label else ""
        return str(item) if item else ""

    def _get_ddc_label(self, ddc_code: str) -> str:
        """
        DDC 코드로 레이블을 조회합니다.

        Args:
            ddc_code: DDC 코드 (예: "810", "813.54")

        Returns:
            str: DDC 레이블 (없으면 빈 문자열)
        """
        if not ddc_code or not ddc_code.strip():
            return ""

        try:
            # SearchQueryManager를 통해 DDC 정보 조회
            ddc_info = self.query_manager.get_dewey_cache_entry(ddc_code.strip())

            if ddc_info and isinstance(ddc_info, dict):
                # 캐시에서 레이블 추출
                return ddc_info.get("label_ko", "") or ddc_info.get("label_en", "")

            # 캐시에 없으면 DeweyClient로 조회
            from Search_Dewey import DeweyClient

            dewey_client = DeweyClient(self.db_manager)
            context = dewey_client.get_dewey_context(ddc_code.strip())

            if context and context.get("main"):
                return self._extract_dewey_label(context.get("main", {}))

            return ""

        except Exception:
            # 오류 발생 시 빈 문자열 반환 (로그는 생략)
            return ""

    def _log(self, message: str, level: str = "INFO"):
        """
        로그 메시지를 기록합니다.

        Args:
            message: 로그 메시지
            level: 로그 레벨 (INFO, WARNING, ERROR 등)
        """
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message(message, level)
        else:
            print(f"[{level}] {message}")
