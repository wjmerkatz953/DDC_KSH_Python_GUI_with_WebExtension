# SOTP – Status of the Project (자동 생성)
> **생성 시각**: 2025-10-31 21:42:07
> **상태**: All Green **All Green** > **AI 전용 초고속 컨텍스트 문서** | 30초 파악 완료

---

## 1. 핵심 파일 5개 (AI 필수)

| 파일 | 역할 |
|------|------|
| `qt_main_app.py` | 진입점, 탭 로딩, 레이아웃 관리 |
| `qt_Tab_configs.py` | 탭 선언, 컬럼/검색함수 매핑 |
| `qt_base_tab.py` | 모든 탭의 부모 클래스 (v3.0.1) |
| `search_query_manager.py` | 검색 파사드 (v3.0.0) |
| `database_manager.py` | DB 중앙 관리자 (v2.2.0) |

---

## 2. 탭 요약 (총 13개)

| 그룹 | 탭 | 파일 | 아이콘 |
|------|----|------|-------|
| **AI** | └─ `AI Feed` | `qt_TabView_AIFeed.py` | 🤖 |
| **Classification** | ├─ `Dewey` | `qt_TabView_Dewey.py` | 📚 |
| **Classification** | └─ `Gemini` | `qt_TabView_Gemini.py` | 🔮 |
| **Configuration** | └─ `Settings` | `qt_TabView_Settings.py` | ⚙️ |
| **Editing** | └─ `MARC Editor` | `qt_TabView_MARC_Editor.py` | ✏️ |
| **Extraction** | └─ `MARC Extractor` | `qt_TabView_MARC_Extractor.py` | 📄 |
| **Integration** | ├─ `Global` | `qt_TabView_Global.py` | 🌐 |
| **Integration** | ├─ `NDL` | `qt_TabView_NDL.py` | 📘 |
| **Integration** | ├─ `Western` | `qt_TabView_Western.py` | 🌍 |
| **Integration** | ├─ `NLK 검색` | `qt_TabView_NLK.py` | 📖 |
| **Integration** | └─ `저자 확인` | `qt_TabView_Author_Check.py` | 👤 |
| **Legal** | └─ `Legal Deposit` | `qt_TabView_LegalDeposit.py` | ⚖️ |
| **Local** | └─ `KSH Local` | `qt_TabView_KSH_Local.py` | 📂 |


---

## 3. DB 상태 (✅ [개선] 핵심 테이블 확인)

| DB | 핵심 테이블 상태 |
|----|------------------|
| `nlk_concepts.sqlite` | ✅ `concepts`<br>✅ `literal_props`<br>✅ `literal_props_fts`<br>✅ `uri_props` |
| `kdc_ddc_mapping.db` | ✅ `mapping_data` ✅ `mapping_data_fts` |
| `dewey_cache.db` | ✅ `dewey_cache` ✅ `ddc_keyword_fts` |
| `glossary.db` | ✅ `settings` ✅ `glossary` |

---

## 4. 최근 변경 (✅ [개선] 파일 변경 내역 포함)

### 2025-10-30 (세션 2): 델리게이트 색상 및 Find 매치 하이라이트 구현
- **델리게이트 색상 문제 해결** (`qt_styles.py` v3.0.5)
- **10월 27일 델리게이트 패턴 복원** (`qt_TabView_Western.py` v1.0.2, `qt_TabView_Global.py` v1.0.2, `qt_TabView_NDL.py` v2.0.2)
- **Find 매치 하이라이트 기능 구현** (모든 탭)
- **BaseMatchHighlightDelegate 구현** (`qt_base_tab.py` v3.0.6)
- **Hotfix: Find navigation crash** (qt_base_tab.py v3.0.6)
- **브랜치 전략**:
- **수정 파일**:
- **기술적 인사이트**:

### 2025-10-30 (세션 1): Find 기능 UX 개선
- **Find 입력창 자동 전체 선택 기능 추가** (`qt_base_tab.py` v3.0.4)
- **Find 하이라이트 색상 시각화 개선** (`qt_base_tab.py` v3.0.4)
- **수정 파일**:

### 2025-10-29 (세션 5): HTML 뷰어 다중 테이블 지원 개선
- **문제**: Gemini DDC 분류 탭에서 HTML 뷰어 버튼 클릭 시 항상 중간 결과만 표시되는 버그
- **해결책**: 최근 클릭된 테이블 추적(Last Clicked Table Tracking) 패턴 도입
- **Gemini DDC 분류 탭 개선** (`qt_TabView_Gemini.py` v2.2.8)
- **KSH Local 탭 개선** (`qt_TabView_KSH_Local.py` v4.4.1)
- **BaseSearchTab 핵심 로직 업데이트** (`qt_base_tab.py` v3.0.2)
- **테스트 결과** ✅
- **효과**:
- **수정 파일**:

### 2025-10-29 (세션 4): PyInstaller SSL 인증서 번들링 개선
- **SSL 인증서 경로 문제 해결** (`.spec`, `ssl_cert_utils.py`)
- **수정 파일**:

### 2025-10-29 (세션 3): Search_Naver.py v1.2.0 - 네트워크 안정성 및 성능 최적화
- **네트워크 탄력성 강화** (`Search_Naver.py` v1.2.0)
- **HTTP 세션 재사용 및 공통 헤더 관리**
- **ISBN 정규화 유틸리티 추가**
- **스크레이핑 결과 캐시 시스템 (2시간 TTL)**
- **버그 수정**
- **코드 품질 개선**
- **변경 통계**: +355줄, -57줄 (총 412줄 변경)
- **수정 파일**:

---

## 5. 키 의존성 맵 (Key Dependencies Map)

### UI 계층 의존성
```
qt_main_app.py
├── qt_Tab_configs.py (탭 메타데이터)
├── qt_TabView_*.py (개별 탭 구현)
│   └── qt_base_tab.py (BaseSearchTab)
│       ├── qt_utils.py (SearchThread, 유틸리티)
│       ├── qt_proxy_models.py (정렬/필터)
│       ├── qt_widget_events.py (컬럼 저장)
│       ├── view_displays.py (상세 뷰)
│       ├── qt_custom_widgets.py (커스텀 위젯)
│       └── qt_TabView_Gemini.py (Gemini 탭)
│       └── qt_TabView_Settings.py (설정 탭)
│       └── qt_TabView_MARC_Extractor.py (MARC 추출 탭)
│       └── qt_TabView_NDL.py (NDL 탭)
│       └── qt_TabView_Western.py (Western 탭)
│       └── qt_TabView_AIFeed.py (AI 피드 탭)
├── qt_layout_settings_manager.py (레이아웃 저장)
├── qt_shortcuts.py (단축키)
├── qt_context_menus.py (컨텍스트 메뉴)
├── qt_styles.py (스타일시트)
└── extension_api_server.py (Flask API, 선택적)
```

### 검색 계층 의존성
```
search_query_manager.py (SearchManager 파사드)
├── search_common_manager.py (공통 기능)
├── search_dewey_manager.py (DDC 특화)
│   └── Search_Dewey.py (WorldCat API)
├── search_ksh_manager.py (KSH 특화)
│   ├── Search_KSH_Lite.py (웹 스크레이핑)
│   └── Search_KSH_Local.py (로컬 DB)
└── search_orchestrator.py (통합 검색)
    ├── Search_BNE.py, Search_BNF.py, ...
    ├── Search_CiNii.py, Search_NDL.py
    └── Search_Harvard.py, Search_MIT.py, ...
```

### 데이터 계층 의존성
```
database_manager.py (DatabaseManager v2.2.0)
├── nlk_concepts.sqlite (KSH 개념, FTS5)
├── kdc_ddc_mapping.db (KDC↔DDC)
├── dewey_cache.db (API 캐시)
├── glossary.db (UI 설정)
└── FAISS 벡터 인덱스 (임베딩 검색)
```

---

## 6. 브라우저 확장 프로그램 (Browser Extension)

### 구성 파일
| 파일 | 역할 |
|------|------|
| `manifest.json` | 확장 프로그램 메타데이터 (v6.5.6) |
| `background.js` | 백그라운드 서비스 워커, 메시지 중계 |
| `content.js` | KSH 패널 UI 및 MARC 650 필드 삽입 |
| `search-addon.js` | DDC/KSH 검색 패널, ISBN 조회 |
| `article-processor.js` | 정관사 처리, 090 청구기호 검색 |

### 주요 기능
- **KSH 패널**: MARC 650 필드 자동 삽입, 프리셋 관리, 082 필드 연동
- **검색 패널**: DDC/KSH 검색 (Flask API 연동), ISBN 서지정보 조회
- **정관사 처리**: 246 필드 정관사 제거 및 자동 변환
- **단축키**: `Ctrl+Shift+Q` (KSH 패널), `Ctrl+Shift+S` (검색 패널)

### Flask API 연동
```
extension_api_server.py (Flask, 포트 5000)
├── GET /api/dewey/search?ddc={코드}
└── GET /api/ksh/search?q={쿼리}
```

---

> **자동 생성 완료** | `generate_sotp.py` 실행
> **수정 금지** – 자동 갱신 전용
