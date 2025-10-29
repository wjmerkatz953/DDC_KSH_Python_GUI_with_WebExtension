# SOTP – Status of the Project (자동 생성)
> **생성 시각**: 2025-10-29 00:07:12
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

## 2. 탭 요약 (총 11개)

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
| **Integration** | └─ `Western` | `qt_TabView_Western.py` | 🌍 |
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

### 2025-10-28 (세션 3): HTML 뷰어 자동 테이블 감지 및 Dewey 탭 지원
- **HTML 보기 기능 개선: 포커스/선택된 테이블 자동 감지**
- **해결 방법**:
- **Gemini DDC 분류 탭** (`qt_TabView_Gemini.py` v2.2.7)
- **KSH Local 탭** (`qt_TabView_KSH_Local.py` v2.2.1)
- **Dewey 탭 HTML 보기 기능 추가** (`qt_TabView_Dewey.py` v4.3.2)
- **BaseSearchTab** (`qt_base_tab.py` v3.0.2)
- **Gemini 검색 로직 버그 수정** (`Search_Gemini.py`)
- **교훈**:
- **수정 파일**:

### 2025-10-28 (세션 2): 트리메뉴 모드 스타일 적용 및 테마 전환 문제 해결
- **⚠️ 중요 패턴: 인라인 스타일과 테마 전환 문제**
- **트리메뉴 모드 테마 전환 에러 수정** (`qt_TabView_Settings.py` v1.0.4)
- **MARC 추출 및 Gemini 탭 테마 적용 완전 수정** (`qt_TabView_MARC_Extractor.py` v2.1.6, `qt_TabView_Gemini.py` v2.2.6)
- **트리메뉴 네비게이션 스타일 강제 적용** (`qt_tree_menu_navigation.py` v1.2.2)
- **수정 파일**:

### 2025-10-28 (세션 1): 트리메뉴와 탭뷰 완전 통일
- **트리메뉴 네비게이션 아키텍처 개선** (`qt_tree_menu_navigation.py` v1.2.0)
- **스타일시트 적용 문제 해결** (`qt_TabView_MARC_Extractor.py` v2.1.3, `qt_TabView_Gemini.py` v2.2.3, `qt_styles.py` v3.0.4)
- **배경**:
- **데이터 전송 로직 간소화** (`qt_main_app.py`)
- **MARC 파서 버그 수정** (`marc_parser.py`, `qt_TabView_Dewey.py`)
- **수정 파일**:

### 2025-10-27: 테마 대응 개선 및 기능 추가
- **API 설정 다이얼로그 테마 대응 및 버그 수정** (`qt_api_settings.py` v1.1.2, `qt_styles.py` v3.0.3)
- **세로 헤더(행 번호) 스타일 추가** (`qt_styles.py`, `qt_TabView_MARC_Extractor.py`, `qt_TabView_Dewey.py`)
- **API 상태 표시 테마 대응** (`qt_styles.py`, `qt_TabView_NLK.py`, `qt_TabView_Gemini.py`, `qt_TabView_AIFeed.py`, `qt_dewey_logic.py`)
- **NDL 및 Western 탭 델리게이트 테마 대응** (`qt_TabView_NDL.py`, `qt_TabView_Western.py`, `ui_constants.py`, `qt_TabView_Settings.py`)
- **Western 탭 출처별 색상 상수 추가** (`ui_constants.py`)
- **Western 탭 Google Books API 설정 기능 추가** (`qt_TabView_Western.py`)
- **Cornell 상세 링크에 librarian_view 추가** (`Search_Cornell.py`)
- **Global 탭 델리게이트 테마 대응** (`qt_TabView_Global.py`, `ui_constants.py`)
- **테이블 헤더뷰 테마 대응** (`qt_widget_events.py` v2.1.1, `qt_base_tab.py`)
- **레이아웃 설정 저장/복구 트리메뉴 모드 지원** (`qt_main_app.py`)
- **수정 파일**:

### 2025-10-25 (세션 2): UI 일관성 개선 및 테마 호환성 강화
- **MARC_Gemini 입력 위젯 그룹 스타일 추가** (`qt_styles.py`, `qt_TabView_MARC_Extractor.py`, `qt_TabView_Gemini.py`)
- **라디오 버튼 스타일 개선** (`qt_styles.py`)
- **설정 탭 "적용" 버튼 텍스트 색상 수정** (`qt_TabView_Settings.py`)
- **트리메뉴 테두리 색상 수정** (`qt_tree_menu_navigation.py`)
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

> **자동 생성 완료** | `generate_sotp.py` 실행
> **수정 금지** – 자동 갱신 전용
