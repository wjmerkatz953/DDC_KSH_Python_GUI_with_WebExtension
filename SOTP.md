# SOTP – Status of the Project (자동 생성)
> **생성 시각**: 2025-10-29 23:16:12
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

### 2025-10-29 (세션 2): 레코드 스키마 상수화 및 팩토리 패턴 도입
- **레코드 생성 로직 리팩토링** (`Search_Naver.py`, 기타 검색 모듈)
- **어플리케이션 버전 업데이트** (`qt_main_app.py`)
- **.gitignore 업데이트**
- **수정 파일**:

### 2025-10-29 (세션 1): Search_Naver.py 리팩토링 완료
- **search_naver_catalog 함수 대규모 리팩토링** (`Search_Naver.py` v1.1.1)
- **신규 헬퍼 함수 추가**:
- **개선 사항**:
- **교보문고 스크레이핑 개선**
- **수정 파일**:

### 2025-10-29: 기타 버그 수정 및 개선
- **웹 확장 기능 데이터 업데이트** (`extension/data.json`)
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
