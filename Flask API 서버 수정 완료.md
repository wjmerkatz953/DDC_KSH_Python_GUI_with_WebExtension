    def _start_extension_api_server(self):
        """익스텐션용 API 서버를 자동으로 시작합니다."""
        try:
            from flask import Flask, jsonify, request
            from flask_cors import CORS
            import threading

            # Flask 앱 생성
            self.api_app = Flask(__name__)
            CORS(self.api_app)  # 익스텐션에서 접근 허용

            # 🎯 KSH 검색 API 엔드포인트
            @self.api_app.route("/api/ksh/search", methods=["GET"])
            def search_ksh():
                query = request.args.get("q", "").strip()
                if not query:
                    return jsonify([])

                try:
                    # 기존 DB 검색 로직 그대로 활용!
                    result = self.db_manager.search_integrated_ksh(query)

                    # 결과 형태 확인 후 처리
                    if isinstance(result, tuple) and len(result) >= 2:
                        df_concepts, df_biblio = result[0], result[1]
                    else:
                        df_concepts = (
                            result if hasattr(result, "iterrows") else pd.DataFrame()
                        )
                        df_biblio = pd.DataFrame()

                    # 익스텐션용 간단한 형태로 변환
                    ksh_results = []

                    # 컨셉 DB 결과 처리
                    for _, row in df_concepts.iterrows():
                        subject = row.get("subject", "")
                        if subject and "▼a" in subject and "▲" in subject:
                            # 이미 MARC 형태인 경우
                            ksh_results.append(
                                {
                                    "subject": subject,
                                    "display": self._extract_display_text(subject),
                                    "category": row.get("main_category", ""),
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

                    return jsonify(ksh_results[:20])  # 상위 20개만 반환

                except Exception as e:
                    self.log_message(f"오류: KSH API 검색 실패: {e}", level="ERROR")
                    return jsonify({"error": str(e)}), 500

            # 🎯 DDC 검색 API 엔드포인트
            @self.api_app.route("/api/dewey/search", methods=["GET"])
            def search_dewey():
                ddc_code = request.args.get("ddc", "").strip()
                if not ddc_code:
                    return jsonify({"error": "DDC code required"}), 400

                try:
                    from Search_Dewey import DeweyClient

                    # -------------------
                    # 🔧 DeweyClient API 호출 방식 수정
                    dewey_client = DeweyClient(self.db_manager)

                    # get_dewey_context_by_iri 대신 올바른 메서드 사용
                    context = dewey_client.get_dewey_context(ddc_code)
                    # -------------------

                    # 익스텐션용 간단한 형태로 변환
                    result = {
                        "main": {
                            "notation": context.get("main", {}).get("notation", ""),
                            "label": self._extract_dewey_label(context.get("main", {})),
                            "definition": context.get("main", {}).get("definition", ""),
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
                    self.log_message(f"오류: DDC API 검색 실패: {e}", level="ERROR")
                    return jsonify({"error": str(e)}), 500

            # 🎯 서버 헬스 체크 엔드포인트
            @self.api_app.route("/api/health", methods=["GET"])
            def health_check():
                return jsonify(
                    {
                        "status": "healthy",
                        "app": "MetaTetus Extension API",
                        "version": "1.0.0",
                    }
                )

            # 별도 스레드에서 서버 실행
            def run_server():
                try:
                    self.api_app.run(
                        host="127.0.0.1",
                        port=5000,
                        debug=False,
                        use_reloader=False,
                        threaded=True,
                    )
                except Exception as e:
                    self.log_message(f"오류: API 서버 실행 실패: {e}", level="ERROR")

            # 데몬 스레드로 서버 시작
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()

            self.log_message(
                "정보: 익스텐션용 API 서버가 http://localhost:5000에서 시작되었습니다.",
                level="INFO",
            )

        except ImportError as e:
            self.log_message(
                f"경고: Flask가 설치되지 않았습니다. 익스텐션 기능을 사용하려면 'pip install flask flask-cors'를 실행하세요.",
                level="WARNING",
            )
        except Exception as e:
            self.log_message(f"경고: 익스텐션 API 서버 시작 실패: {e}", level="WARNING")

    def _extract_display_text(self, marc_text):
        """MARC 형식에서 표시용 텍스트 추출"""
        import re

        if not marc_text:
            return ""

        # ▼a텍스트▼0코드▲ 형태에서 텍스트 부분만 추출
        match = re.search(r"▼a([^▼]+)", marc_text)
        if match:
            return match.group(1).strip()

        return marc_text

    def _extract_dewey_label(self, item):
        """Dewey 아이템에서 레이블 추출"""
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

    def register_search_target(self, tab_key: str, entry_widget, trigger=None):
        """
        entry_widget: 해당 탭의 '주 검색' Entry (Return 바인딩이 있으면 trigger 생략 가능)
        trigger: 버튼 콜백 등 직접 실행 함수가 필요할 때만 지정.
        """
        self.search_registry[tab_key] = {"entry": entry_widget, "trigger": trigger}

    # ✅ 공용 트리거: 컨텍스트 메뉴에서 호출
    def trigger_search(self, text: str, tab_key: str | None = None):
        """
        1) 등록된 trigger가 있으면 그걸 '최우선'으로 호출
        2) 없으면 Entry에 값 세팅 후, Return 이벤트와 버튼 invoke까지 폴백
        """
        try:
            target_key = tab_key or getattr(self, "active_tab_key", None)

            entry_widget = None
            trigger = None

            # 우선: 레지스트리 → 위젯맵
            if target_key:
                reg = self.search_registry.get(target_key)
                if reg:
                    entry_widget = reg.get("entry")
                    trigger = reg.get("trigger")

                if entry_widget is None and target_key in WIDGET_CONFIGS:
                    for name in WIDGET_CONFIGS[target_key].get("entry_widgets", []):
                        if "find" in name:
                            continue
                        w = getattr(self, name, None)
                        if w is not None:
                            entry_widget = w
                            break

            # 전수 폴백(레지스트리)
            if entry_widget is None and self.search_registry:
                for _key, reg in self.search_registry.items():
                    if reg and reg.get("entry") is not None:
                        entry_widget = reg.get("entry")
                        trigger = reg.get("trigger")
                        target_key = _key
                        break

            # 전수 폴백(WIDGET_CONFIGS)
            if entry_widget is None:
                for _key, cfg in WIDGET_CONFIGS.items():
                    for name in cfg.get("entry_widgets", []):
                        if "find" in name:
                            continue
                        w = getattr(self, name, None)
                        if w is not None:
                            entry_widget = w
                            trigger = None
                            target_key = _key
                            break
                    if entry_widget is not None:
                        break

            # 값 주입
            if entry_widget:
                import tkinter as tk

                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, text or "")

            # -------------------
            # ✅ 트리거 우선 호출 (CTkEntry의 event_generate 이슈 회피)
            if callable(trigger):
                # Tk 이벤트 루프에 안전하게 던져줌
                try:
                    self.after(1, trigger)
                except Exception:
                    trigger()
            elif entry_widget:
                # 1차: Return 이벤트
                try:
                    entry_widget.focus_set()
                    entry_widget.event_generate("<Return>")
                    entry_widget.event_generate("<Key-Return>")
                except Exception:
                    pass
                # 2차: 버튼 invoke 폴백 (탭별 버튼 속성명이 다를 수 있어 안전하게 시도)
                try:
                    # 가장 흔한 네이밍들 시도
                    btn_candidates = [
                        f"{target_key}_search_button",
                        "ksh_search_button",
                        "search_button",
                    ]
                    for btn_name in btn_candidates:
                        btn = getattr(self, btn_name, None)
                        if btn and hasattr(btn, "invoke"):
                            self.after(1, btn.invoke)
                            break
                except Exception:
                    pass
            else:
                if hasattr(self, "log_message"):
                    self.log_message(
                        "경고: 검색 Entry/트리거를 찾지 못했습니다. (tab_key=None 포함)",
                        level="WARNING",
                    )
            # -------------------

        except Exception as e:
            if hasattr(self, "log_message"):
                self.log_message(f"오류: 범용 검색 트리거 실패: {e}", level="ERROR")




# Flask API 서버 수정 완료 (SearchQueryManager 통합)

## 수정 날짜: 2025-10-11

## 문제점
```
ERROR: 'DatabaseManager' object has no attribute 'search_integrated_ksh'
```

`search_integrated_ksh` 메서드가 `DatabaseManager`에서 `SearchQueryManager`로 이동되었습니다.

## 해결 방법

### 1. extension_api_server.py 수정

#### 변경 전:
```python
def __init__(self, app_instance, db_manager):
    self.app_instance = app_instance
    self.db_manager = db_manager
    ...

result = self.db_manager.search_integrated_ksh(query)
```

#### 변경 후:
```python
def __init__(self, app_instance, db_manager, query_manager=None):
    self.app_instance = app_instance
    self.db_manager = db_manager

    # query_manager가 없으면 자동 생성
    if query_manager is None:
        from search_query_manager import SearchQueryManager
        self.query_manager = SearchQueryManager(db_manager)
    else:
        self.query_manager = query_manager
    ...

# ✅ query_manager 사용
result = self.query_manager.search_integrated_ksh(query)
```

### 2. 코드 품질 개선

#### Linting 오류 수정:
- ✅ 사용하지 않는 import 제거 (`Optional`)
- ✅ 라인 길이 제한 준수 (79자)
- ✅ 사용하지 않는 변수 제거

## 테스트 방법

### 1. 애플리케이션 실행
```bash
python qt_main_app.py
```

### 2. API 테스트 (별도 터미널)
```bash
# 헬스 체크
curl http://localhost:5000/api/health

# KSH 검색 (한글 검색어)
curl "http://localhost:5000/api/ksh/search?q=한국"

# DDC 검색
curl "http://localhost:5000/api/dewey/search?ddc=810"
```

### 3. Python 테스트 스크립트
```bash
python test_api_server.py
```

## 예상 결과

### KSH 검색 응답:
```json
[
  {
    "subject": "▼a한국 문학 평론[韓國文學評論]▼0KSH1998019437▲",
    "display": "한국 문학 평론[韓國文學評論]",
    "category": "문학",
    "type": "concept"
  },
  ...
]
```

### DDC 검색 응답:
```json
{
  "main": {
    "notation": "810",
    "label": "미국 문학",
    "definition": "..."
  },
  "broader": [...],
  "narrower": [...],
  "related": [...]
}
```

## 주요 변경 파일

- ✅ `extension_api_server.py` - SearchQueryManager 통합
- ✅ `test_api_server.py` - API 테스트 스크립트 (신규)

## 참고사항

### SearchQueryManager vs DatabaseManager

| 메서드 | 이전 위치 | 현재 위치 |
|--------|----------|----------|
| `search_integrated_ksh()` | DatabaseManager | SearchQueryManager |
| `get_dewey_context()` | DeweyClient | DeweyClient (변경 없음) |

### 자동 생성
`query_manager` 파라미터를 생략하면 `ExtensionAPIServer`가 자동으로 `SearchQueryManager` 인스턴스를 생성합니다:

```python
# 이렇게 사용해도 됨:
api_server = ExtensionAPIServer(app_instance, db_manager)

# 또는 명시적으로:
query_manager = SearchQueryManager(db_manager)
api_server = ExtensionAPIServer(app_instance, db_manager, query_manager)
```

## 다음 단계

1. ✅ Flask 및 flask-cors 설치 완료
2. ✅ SearchQueryManager 통합 완료
3. ✅ Linting 오류 수정 완료
4. ⏳ 브라우저 확장 프로그램 테스트
5. ⏳ 실제 검색 결과 검증

## 문제 해결

### 만약 여전히 오류가 발생한다면:

1. **SearchQueryManager 확인**:
   ```python
   from search_query_manager import SearchQueryManager
   from database_manager import DatabaseManager

   db_manager = DatabaseManager(concepts_db, kdc_ddc_db)
   query_manager = SearchQueryManager(db_manager)

   # 테스트
   result = query_manager.search_integrated_ksh("한국")
   print(result)
   ```

2. **로그 확인**:
   - 메인 앱 로그 창에서 `❌ KSH API 검색 실패` 메시지 확인
   - 상세한 오류 메시지 확인

3. **API 서버 재시작**:
   - 메인 앱 종료 후 재시작
   - 로그에서 `✅ 브라우저 확장 프로그램용 API 서버가 시작되었습니다.` 확인
