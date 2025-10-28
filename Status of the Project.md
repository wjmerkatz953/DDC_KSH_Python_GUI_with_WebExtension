# 통합 검색 데스크톱 프로젝트 상세 분석 (Integrated Search Desktop Project Detailed Analysis)

**📋 문서 목적**: AI 어시스턴트가 작업 전에 읽고 프로젝트의 전체 현황을 빠르게 파악하기 위한 컨텍스트 문서

이 문서는 PySide6 기반의 통합 검색 데스크톱 애플리케이션의 아키텍처, 핵심 구성 요소, 데이터 흐름 및 최근 개발 현황을 상세히 기술합니다. 프로젝트의 전체적인 구조와 각 모듈의 역할을 명확히 하여 향후 유지보수 및 기능 확장을 용이하게 하는 것을 목표로 합니다.

## 🚀 빠른 참조 (Quick Reference)

### 핵심 진입점 및 기반 클래스
- **메인 애플리케이션**: [qt_main_app.py](qt_main_app.py) - `MainApplicationWindow`, `IntegratedSearchApp`
- **탭 기반 클래스**: [qt_base_tab.py](qt_base_tab.py) - `BaseSearchTab` v3.0.1 (모든 검색 탭의 추상 부모)
- **탭 설정**: [qt_Tab_configs.py](qt_Tab_configs.py) - 각 탭의 컬럼, 검색 함수, 필드 매핑 정의

### 데이터 계층
- **DB 관리자**: [database_manager.py](database_manager.py) v2.2.0 - SQLite 연결, FTS5, FAISS 인덱스
- **검색 파사드**: [search_query_manager.py](search_query_manager.py) v3.0.0 - `SearchManager` 클래스
- **주요 데이터베이스**:
  - `nlk_concepts.sqlite` - KSH 개념 및 DDC 매핑 (FTS5 인덱스)
  - `kdc_ddc_mapping.db` - KDC↔DDC 매핑 테이블
  - `glossary.db` - UI 레이아웃 설정 저장
  - `dewey_cache.db` - WorldCat DDC API 응답 캐시

### 실행 환경
- **가상환경**: `venv/` - PySide6, transformers, faiss-cpu, BeautifulSoup4 등
- **실행 명령**: `python qt_main_app.py`
- **빌드 도구**: PyInstaller (`build/` 디렉토리에 출력)

---

## 1. 디렉토리 구조 (Directory Layout)

- **`./` (루트 디렉토리)**: `qt_main_app.py`와 같은 핵심 애플리케이션 소스 코드와 각종 유틸리티 및 빌드 스크립트가 위치합니다. 현재 활성화된 주력 개발 공간입니다.
- **`assets/`**: UI에 사용되는 리소스 파일 (`favicon.ico`, `loading.jpg` 등)을 포함합니다. 스플래시 스크린이나 탭 아이콘 등에서 사용됩니다.
- **`build/`**: PyInstaller를 통해 생성된 배포용 실행 파일 및 관련 데이터가 저장되는 공간입니다 (`MetaTextus/`, `Qt_TabView_Example/`).
- **`Gradio/`**: 레거시 Gradio 프로토타입과 관련 도우미 스크립트가 보관되어 있습니다. 현재의 Qt 애플리케이션에서는 참조되지 않는 과거 버전입니다.
- **`PEU/`, `QRPrint/`, `Regular/`, `backpup/`**: 독립적인 스크립트와 가상 환경을 포함하는 아카이브 또는 대체 프로젝트들입니다. 참조용으로 보관되어 있습니다.
- **`venv/`**: 프로젝트의 로컬 가상 환경으로, `PySide6`, `transformers`, `faiss-cpu` 등 서드파티 패키지가 설치되어 있습니다.
- **날짜가 찍힌 폴더 및 `.zip` 파일**: 특정 시점의 코드베이스 스냅샷 및 실험 결과물입니다. 프로젝트의 이력을 추적하는 데 사용되며, 현재 애플리케이션의 런타임에는 영향을 주지 않습니다.

---

## 2. 핵심 애플리케이션 및 UI 셸 (Core Application & UI Shell)

- **`qt_main_app.py`**: **애플리케이션의 진입점(Entry Point)이자 총괄 지휘자**입니다.
    - `IntegratedSearchApp` (QApplication)과 `MainApplicationWindow` (QMainWindow)를 정의합니다.
    - `database_manager.py`를 통해 데이터베이스 계층을 초기화하고 성능을 튜닝합니다.
    - `qt_Tab_configs.py`에 정의된 모든 탭(`qt_TabView_*.py`)을 동적으로 로드하고 UI에 배치합니다.
    - `qt_layout_settings_manager.py`를 이용해 창 크기 및 스플리터 위치 같은 레이아웃 상태를 `glossary.db`에 저장하고 복원합니다.
    - `qt_shortcuts.py`를 통해 전역 단축키를 등록하고, `qt_context_menus.py`를 통해 커스텀 컨텍스트 메뉴를 설정합니다.
    - 브라우저 확장 기능과의 연동을 위해 `extension_api_server.py` (Flask 서버)를 백그라운드 스레드로 실행하는 옵션을 제공합니다.

- **`qt_tab_template_standalone.py`, `layout_integration_example.py`, `run_template.py`**: `BaseSearchTab`을 상속받은 개별 탭이나 레이아웃 관리자 같은 특정 컴포넌트를 전체 애플리케이션 없이 독립적으로 실행하고 테스트하기 위한 최소한의 실행 환경(Harness)입니다.

---

## 3. UI 인프라 및 유틸리티 (UI Infrastructure & Utilities)

이 컴포넌트들은 모든 탭에서 일관된 UI/UX와 동작을 보장하는 기반 역할을 합니다.

- **`qt_base_tab.py` (v3.0.1)**: **모든 검색 탭의 추상 기반 클래스(Abstract Base Class)**입니다.
    - UI가 멈추는 것을 방지하기 위해 `qt_utils.py`의 `SearchThread`를 사용하여 모든 검색 작업을 백그라운드 스레드에서 처리합니다.
    - 정렬 및 필터링 기능이 내장된 테이블 뷰(`qt_proxy_models.py`)를 기본으로 제공합니다.
    - 컬럼 순서 및 너비 저장/복원(`qt_widget_events.py`), 데이터 내보내기, 상세 정보 패널(`view_displays.py`) 렌더링 등 탭의 공통 기능을 표준화합니다.
    - `ui_constants.py`, `qt_shortcuts.py`, `qt_context_menus.py` 등 다양한 UI 유틸리티와 직접적으로 연관됩니다.

- **`qt_Tab_configs.py`**: **탭의 명세서(Manifest)** 역할을 하는 설정 파일입니다.
    - 각 탭의 UI 컬럼 이름, 데이터베이스 필드 매핑, 호출할 검색 함수, 편집 가능 여부 등을 선언적으로 정의합니다.
    - 이를 통해 `qt_main_app.py`는 각 탭의 구체적인 구현을 알지 못해도 동적으로 탭을 생성하고 설정할 수 있어, 코드의 결합도를 낮춥니다.

- **`qt_utils.py`**: 대부분의 Qt 모듈에서 공통으로 사용하는 헬퍼 함수 모음입니다. (예: 스레드 래퍼, CSV/Excel 내보내기, URL 처리, 텍스트 링크 변환 등)

- **`qt_custom_widgets.py`**: `TripleClickLimitedTextBrowser` (트리플 클릭으로 내용 복사), 하이퍼링크 델리게이트 등 애플리케이션 전반에서 사용되는 커스텀 위젯을 정의합니다.

- **`qt_styles.py`**: 다크 테마를 포함한 애플리케이션의 전반적인 스타일시트(QSS)와 색상, 폰트 등 디자인 토큰을 중앙에서 관리합니다.

- **`ui_constants.py`**: UI 색상, 폰트, 패딩 등의 상수를 정의합니다. Light/Dark 테마별 색상 클래스를 제공하며, `set_theme()` 함수로 테마 전환이 가능합니다.

- **`qt_api_settings.py`**: API 설정 다이얼로그를 중앙에서 관리하는 모듈입니다. 네이버, NLK, Google Books, Gemini, Dewey API의 키 설정, 테스트, 저장, 삭제 기능을 제공합니다. 테마 전환에 대응하는 속성 선택자 기반 스타일링을 사용합니다.

- **`view_displays.py`**: 검색 결과의 상세 정보를 보여주는 리치 텍스트 뷰어입니다. `qt_base_tab.py`의 상세 정보 패널에서 사용되어 HTML 형식의 데이터를 시각적으로 렌더링합니다.

- **`qt_layout_settings_manager.py`**: Qt 위젯(스플리터, 창 상태)의 지오메트리를 `glossary.db`에 저장하고 복원하는 로직을 담당합니다.

- **`qt_data_transfer_manager.py`**: 탭 간 데이터 전송을 담당하는 브리지입니다. 예를 들어, `qt_TabView_MARC_Extractor.py`에서 추출한 저자/표제 데이터를 KSH 관련 탭으로 전달하는 역할을 합니다.

- **`qt_dewey_logic.py` / `qt_dewey_workers.py`**: Dewey 탭의 UI 로직과 백그라운드 작업을 분리하여 처리합니다. `qt_dewey_logic`은 메뉴 명령, 트리 확장 등 UI 이벤트를 처리하고, `qt_dewey_workers`는 실제 검색, KSH 연계 등 시간이 오래 걸리는 작업을 스레드에서 수행합니다.

- **`qt_widget_events.py`**: 컬럼 헤더 사이의 경계선이 보이지 않는 이유: qt_widget_events.py:202-212의 ExcelStyleTableHeaderView.paintSection() 메서드에서 커스텀 페인팅을 하고 있기 때문입니다. 이 클래스는 Excel 스타일의 헤더뷰로, 자체적으로 배경색, 테두리, 정렬 아이콘, 필터 표시 등을 모두 커스텀 페인팅합니다. 따라서 qt_styles.py에서 QHeaderView::section의 border-left와 border-right를 설정해도 무시됩니다. 이 프로젝트는 ExcelStyleTableHeaderView라는 커스텀 헤더뷰를 사용하여 Excel 스타일의 5구역 클릭(크기 조절, 정렬, 드래그, 필터), 정렬 인디케이터, 필터 아이콘 등을 구현하고 있습니다. 따라서 일반적인 스타일시트가 아닌 paintSection() 메서드 내부에서 직접 그리기 작업을 해야 합니다.

---

## 4. 탭 구현 (Tab Implementations)

각 `qt_TabView_*.py` 파일은 `qt_base_tab.py`를 상속받아 특정 도메인의 검색 기능을 구현한 구체적인 UI 컴포넌트입니다. 모든 탭은 비동기 검색, 테이블 뷰, 공통 컨텍스트 메뉴 등 `qt_base_tab`이 제공하는 표준화된 기능을 공유합니다.

### 📌 전체 탭 이름 목록 (qt_Tab_configs.py 기준)

**⚠️ 중요**: 트리메뉴나 탭 관련 코드를 수정할 때는 반드시 `qt_Tab_configs.py`에 정의된 정확한 `tab_name`을 사용해야 합니다.

| 탭 이름 (tab_name) | 파일명 | 그룹 | 설명 |
|-------------------|--------|------|------|
| **MARC 추출** | `qt_TabView_MARC_Extractor.py` | 검색 | MARC 데이터 추출 |
| **NLK 검색** | `qt_TabView_NLK.py` | 검색 | 국립중앙도서관 LOD 검색 |
| **NDL + CiNii 검색** | `qt_TabView_NDL.py` | 검색 | 일본 국립국회도서관 |
| **Western 검색** | `qt_TabView_Western.py` | 검색 | 서양권 통합 검색 |
| **Global 통합검색** | `qt_TabView_Global.py` | 검색 | 글로벌 통합 검색 |
| **납본 ID 검색** | `qt_TabView_LegalDeposit.py` | 검색 | 납본자료 검색 |
| **저자전거 검색** | `qt_TabView_KACAuthorities.py` | 저작물/저자 | KAC 저자전거 |
| **상세 저작물 정보** | `qt_TabView_ISNI_Detailed.py` | 저작물/저자 | ISNI 상세 정보 |
| **간략 저작물 정보** | `qt_TabView_BriefWorks.py` | 저작물/저자 | 간략 서지 정보 |
| **KSH Hybrid** | `qt_TabView_KSH_Lite.py` | 주제어 | KSH 하이브리드 검색 |
| **KSH Local** | `qt_TabView_KSH_Local.py` | 주제어 | KSH 로컬 DB 검색 |
| **Dewey 분류 검색** | `qt_TabView_Dewey.py` | 분류/AI | DDC 분류 검색 |
| **Gemini DDC 분류** | `qt_TabView_Gemini.py` | 분류/AI | Gemini AI 기반 분류 |
| **AI 피드** | `qt_TabView_AIFeed.py` | 분류/AI | AI 메타데이터 피드 |
| **MARC 로직 편집** | `qt_TabView_MARC_Editor.py` | 편집 | MARC 편집기 |
| **🐍 Python** | `qt_TabView_Python.py` | 도구 | 내장 Python 콘솔 |
| **설정** | `qt_TabView_Settings.py` | 설정 | 앱 설정 관리 |

### 4.1. 핵심 검색 탭

- **`qt_TabView_KSH_Local.py` (KSH 로컬 검색)**
  - 로컬에 구축된 `nlk_concepts.sqlite` 데이터베이스를 사용하여 KSH(국립중앙도서관 주제명표목) 데이터를 검색합니다.
  - 웹 접근 없이 빠른 속도로 주제명, 연관어, 계층 구조 등을 조회할 수 있습니다.

- **`qt_TabView_KSH_Lite.py` (KSH Lite 검색)**
  - 국립중앙도서관 KSH 웹 포털을 실시간으로 스크레이핑하여 주제명 정보를 검색합니다.
  - 로컬 DB에 없는 최신 데이터를 조회할 수 있지만, 네트워크 속도와 웹사이트 구조 변경에 영향을 받습니다.

- **`qt_TabView_Dewey.py` (Dewey DDC 검색)**
  - DDC(듀이십진분류법) 분류 체계를 탐색하고 검색하는 기능을 제공합니다.
  - 트리 구조를 통해 분류 계층을 시각적으로 탐색하고, 키워드나 분류기호를 통해 관련 주제를 찾습니다.
  - `dewey_cache.db`를 통해 API 조회 결과를 캐싱하여 성능을 최적화합니다.

### 4.2. 통합 및 외부 검색 탭

- **`qt_TabView_Global.py` (글로벌 통합 검색)**
  - `search_orchestrator.py`를 통해 전 세계 주요 도서관(CiNii, NDL, 유럽 등)의 데이터를 한 번에 병렬로 검색하고 결과를 통합하여 보여줍니다.

- **`qt_TabView_Western.py` (서양권 통합 검색)**
  - `search_orchestrator.py`를 통해 서양 주요 대학 및 기관 도서관(LC, Harvard, MIT, Princeton 등)의 데이터를 통합 검색합니다.

- **`qt_TabView_NDL.py` (일본 국립국회도서관 검색)**
  - 일본 국립국회도서관(NDL)의 서지 데이터를 검색하는 전용 탭입니다.

- **`qt_TabView_NLK.py` (국립중앙도서관 검색)**
  - LOD(Linked Open Data) 등 국립중앙도서관이 제공하는 API를 통해 자료를 검색합니다.

- **`qt_TabView_LegalDeposit.py` (납본자료 검색)**
  - 국립중앙도서관의 납본자료 데이터베이스를 조회하는 기능을 제공합니다.

### 4.3. 저자 및 서지 정보 탭

- **`qt_TabView_KACAuthorities.py` (KAC 저자전거)**
  - 예술자료원(KAC)의 저자전거 데이터베이스를 검색하여 저자 정보를 조회합니다.

- **`qt_TabView_BriefWorks.py` (간략 서지)**
  - ISNI, KAC 등의 데이터를 활용하여 저작(Work)에 대한 간략한 서지 정보를 조회합니다.

- **`qt_TabView_ISNI_Detailed.py` (ISNI 상세 정보)**
  - ISNI(국제 표준 이름 식별자)를 기반으로 특정 개인이나 단체에 대한 상세 정보를 조회하는 전용 탭입니다.

### 4.4. AI 및 도구 탭

- **`qt_TabView_Gemini.py` (Gemini AI 검색)**
  - Google Gemini API를 활용하여 키워드에 대한 개념적 설명이나 연관 정보를 생성하고, 이를 로컬 데이터베이스와 연계하여 보여줍니다. 복합적인 질의를 통해 풍부한 메타데이터를 생성하는 것을 목표로 합니다.

- **`qt_TabView_AIFeed.py` (AI 피드)**
  - `Search_Gemini.py`와 카탈로그 데이터를 결합하여 AI가 생성하거나 보강한 메타데이터 피드를 제공합니다.

- **`qt_TabView_MARC_Extractor.py` (MARC 추출기)**
  - 원시 MARC 데이터를 입력받아 특정 필드(예: 저자, 표제, DDC)를 추출하고, `qt_data_transfer_manager`를 통해 다른 탭으로 데이터를 전송하는 유틸리티 탭입니다.

- **`qt_TabView_MARC_Editor.py` (MARC 편집기)**
  - MARC 데이터를 편집하고 생성하는 기능을 제공하는 도구 탭입니다.

### 4.5. 시스템 및 개발 탭

- **`qt_TabView_Settings.py` (설정)**
  - API 키 관리, 자동 검색 활성화/비활성화, UI 테마 변경 등 애플리케이션의 전반적인 설정을 관리하는 인터페이스를 제공합니다.

- **`qt_TabView_Python.py` (내장 파이썬 콘솔)**
  - 애플리케이션 내에서 파이썬 코드를 실행하고 디버깅할 수 있는 대화형 콘솔을 제공합니다. 개발 및 테스트 목적으로 사용됩니다.

- **`qt_TabView_Example.py` (예제 탭)**
  - 새로운 탭을 개발할 때 참조할 수 있는 최소한의 기능과 구조를 갖춘 템플릿입니다.

---

## 5. 검색 관리자 및 데이터 접근 (Search Managers & Data Access)

이 계층은 UI와 데이터베이스/외부 API 사이의 비즈니스 로직을 담당합니다.

- **`search_query_manager.py` (v3.0.0)**: **검색 로직의 퍼사드(Facade)**입니다. `SearchDeweyManager`와 `SearchKshManager`의 기능을 통합하여 다른 모듈에게 단순화된 인터페이스(`SearchManager` 클래스)를 제공합니다.
- **`search_common_manager.py`**: 여러 검색 관리자에서 공유하는 공통 루틴(쿼리 정규화, KSH 마크업 포맷팅, 스레드 풀 관리 등)을 포함하는 기반 클래스입니다.
- **`search_dewey_manager.py` / `search_ksh_manager.py`**: 각각 DDC와 KSH 검색에 특화된 비즈니스 로직(캐싱, 순위 결정, 결과 데이터 가공)을 담당합니다.
- **`search_orchestrator.py`**: **통합 검색의 지휘자**입니다. ISBN, ISNI, 서양/글로벌 카탈로그 등 여러 데이터 소스에 대한 검색 요청을 `ThreadPoolExecutor`를 사용해 병렬로 실행하고 결과를 취합합니다.
- **`Search_*.py` 모듈들**:
    - `Search_KSH_Lite.py`: 국립중앙도서관 KSH 포털을 웹 스크레이핑하여 결과를 DataFrame으로 반환합니다.
    - `Search_Gemini.py`: Gemini API를 호출하고 그 결과를 로컬 데이터베이스 정보와 결합하여 메타데이터를 풍부하게 만듭니다.
    - `Search_Dewey.py`: WorldCat Dewey API 연동(OAuth, Negative Caching)을 담당합니다.
    - 이 외 다수의 `Search_*.py` 파일들은 각 외부 카탈로그(BNE, BNF, DNB, Naver 등)와의 통신을 개별적으로 캡슐화한 모듈입니다.

---

## 6. 데이터베이스, 파이프라인 및 도구 (Database, Data Pipelines & Tooling)

- **`database_manager.py` (v2.2.0)**: **데이터베이스 접근의 중앙 관문**입니다.
    - `nlk_concepts.sqlite`, `kdc_ddc_mapping.db`, `glossary.db`, `dewey_cache.db` 등 여러 SQLite 데이터베이스 연결을 관리합니다.
    - PRAGMA 최적화, FTS5 인덱스 유지보수, 캐시 관리, 벡터 검색(FAISS) 연동 등 데이터베이스 관련 모든 저수준 작업을 처리합니다.

- **빌드 및 유지보수 스크립트**:
    - `build_kac_authority_and_biblio_db.py`: 원시 데이터로부터 KAC/서지 통합 데이터베이스를 구축합니다.
    - `build_vector_db.py`: DDC 임베딩을 위한 FAISS 벡터 인덱스를 생성합니다.
    - `manage_ddc_index.py`, `migrate_ddc_schema.py`: DDC 스키마 변경 및 인덱스 관리를 위한 스크립트입니다.

- **`marc_parser.py` / `mark_generator.py`**: MARC 데이터를 파싱하고 생성하는 유틸리티로, MARC 관련 탭에서 사용됩니다.

---

6.1. dewey_cache.db (DDC API 캐시 및 통계)

이 데이터베이스는 WorldCat DDC API 응답을 캐싱하고 관련 통계를 수집하는 데 특화되어 있습니다. 총 10개의 테이블 과 3개의 인덱스 , 3개의 트리거 로 구성됩니다.

주요 테이블:

    dewey_cache

    목적: DDC API의 raw_json 응답을 캐싱하는 핵심 테이블입니다.

스키마: iri (PRIMARY KEY), ddc_code, raw_json (NOT NULL), last_updated, hit_count, file_size

인덱스: ddc_code 와 last_updated 컬럼에 별도 인덱스가 생성되어 조회 성능을 향상시킵니다.

ddc_keyword 및 ddc_keyword_fts

    목적: DDC 관련 키워드를 저장하고 FTS5(Full-Text Search)를 통해 빠른 검색을 지원합니다.

ddc_keyword: iri, ddc, keyword, term_type 등을 저장합니다.

ddc_keyword_fts: ddc_keyword 테이블을 기반으로 fts5 가상 테이블이 생성됩니다.

트리거: ddc_keyword_ad (AFTER DELETE), ddc_keyword_ai (AFTER INSERT), ddc_keyword_au (AFTER UPDATE) 트리거가 ddc_keyword 테이블의 데이터 변경 시 ddc_keyword_fts를 자동으로 동기화합니다.

dewey_stats

    목적: 캐시 및 API 사용에 대한 일별 통계를 저장합니다.

스키마: stat_date (PRIMARY KEY), total_entries, cache_hits, api_calls, db_size_mb

search_history

    목적: 사용자의 DDC 검색 이력을 기록합니다.

스키마: id (INTEGER PRIMARY KEY AUTOINCREMENT), ddc_code (NOT NULL), searched_at

인덱스: searched_at (DESC)에 인덱스가 있어 최근 검색 내역을 빠르게 조회할 수 있습니다.

6.2. nlk_concepts.sqlite (국립중앙도서관 KSH 개념 DB)

이 데이터베이스는 국립중앙도서관(NLK)의 KSH 개념, 속성, 관계 및 분류 매핑(DDC, KDC) 정보를 저장하는 핵심 지식 베이스입니다. 총 11개의 테이블 , 24개의 인덱스 , 3개의 트리거 로 구성되어 있으며, 매우 정교한 읽기/검색 최적화가 이루어져 있습니다.

주요 테이블:

    concepts

    목적: 모든 개념(Concept)의 유일한 식별자(concept_id)와 타입(type)을 저장하는 중앙 엔티티 테이블입니다.

스키마: concept_id (PRIMARY KEY), type

literal_props 및 literal_props_fts

    목적: 개념의 문자열 속성(예: 표제어, 정의)을 저장하고 FTS5를 통해 검색합니다.

    literal_props: concept_id (FOREIGN KEY), prop (속성명), value (원본 값), value_normalized (검색용 정규화 값)를 저장합니다.

literal_props_fts: value_normalized 컬럼을 대상으로 하는 fts5 가상 테이블입니다.

트리거: literal_props_ad, literal_props_ai, literal_props_au 트리거가 literal_props 변경 시 literal_props_fts를 자동으로 동기화합니다.

uri_props

    목적: 개념과 다른 개념(URI) 간의 관계(예: 상위어, 하위어, 연관어)를 저장합니다.

    스키마: concept_id (FOREIGN KEY), prop (관계명), target (대상 URI)

매핑 테이블 (Classification & Category)

    ddc_mapping: concept_id와 ddc_classification (DDC 분류)을 매핑합니다.

kdc_mapping: concept_id와 kdc_like_classification (KDC 분류)을 매핑합니다.

category_mapping: concept_id와 main_category (메인 카테고리)를 매핑합니다.

인덱스 최적화:

총 24개의 인덱스 가 존재하며, 이는 매우 특정한 조회 패턴에 대해 고도로 최적화되어 있음을 시사합니다.

    FTS 최적화: idx_literal_props_covering 인덱스 는 FTS 검색 후 원본 테이블(literal_props)을 다시 조회할 필요 없이 value_normalized, concept_id, prop, value를 모두 가져올 수 있게 설계된 **커버링 인덱스(Covering Index)**로, 검색 성능을 극대화합니다.

주요 조회 경로: literal_props 테이블의 (concept_id, prop) , (prop, value_normalized) , value_normalized 등 핵심 조회 컬럼 조합에 대해 복합 인덱스가 촘촘하게 생성되어 있습니다.

관계 조회: uri_props 테이블 역시 (concept_id, prop) , (prop, target) , target 등 다양한 관계 탐색 경로에 최적화된 인덱스를 갖추고 있습니다.

실제 DB 테이블 내의 데이터 예시
(value_normalized는 공백이 제거되어 있음)
concept_id	        prop     value	              value_normalized
nlk:KSH1997000001	  label	   대립 개념[對立槪念]    대립개념[對立槪念]


6.3. kdc_ddc_mapping.db (KDC-DDC 매핑 및 검색)

이 데이터베이스는 KDC(한국십진분류법)와 DDC(듀이십진분류법) 간의 매핑 데이터를 저장하며, KSH(주제명)와 연계하여 매우 강력한 검색 기능을 제공하도록 고도로 최적화되어 있습니다. 총 9개의 테이블, 28개의 인덱스, 3개의 트리거로 구성됩니다.

주요 테이블:

    mapping_data

        목적: KDC, DDC, KSH, 서지 정보(표제, 출판연도) 등 모든 핵심 매핑 데이터를 저장하는 메인 테이블입니다.

스키마: id, identifier, kdc, ddc, ksh, kdc_edition, ddc_edition, publication_year, title, data_type, source_file, ksh_labeled, ksh_korean.

mapping_data_fts

    목적: mapping_data 테이블의 데이터를 FTS5(Full-Text Search)로 빠르게 검색하기 위한 가상 테이블입니다.

특징: ksh_korean (KSH 한글 용어) 필드를 중심으로 색인하며, identifier는 색인에서 제외(UNINDEXED)됩니다.

settings 및 translations

    목적: 각각 데이터베이스 관련 설정(Key-Value) 및 용어 번역 정보 를 저장하는 유틸리티 테이블입니다.

인덱스 최적화 (28개):

이 데이터베이스는 28개의 인덱스를 통해 특정 검색 경로에 대해 극단적으로 최적화되어 있습니다.

    기본 인덱스: idx_kdc, idx_ddc, idx_ksh, idx_ksh_korean 등 단일 컬럼 인덱스를 통해 각 분류 체계 및 주제명으로의 빠른 조회를 지원합니다.

복합 인덱스: idx_kdc_ksh_korean , idx_ddc_ksh_korean_year , idx_ksh_korean_ddc_year 등 사용자의 주된 검색 시나리오(예: KSH 한글 용어와 DDC, 출판연도를 함께 조회)에 최적화된 다중 컬럼 인덱스가 다수 존재합니다.

커버링 인덱스 (Covering Index):

    idx_mapping_data_korean_search_cover 인덱스는 ksh_korean, ddc, publication_year (DESC), identifier, title, ksh, ksh_labeled 필드를 모두 포함합니다.

        이는 ksh_korean으로 검색 시, 원본 mapping_data 테이블을 다시 읽지 않고도 필요한 대부분의 정보를 인덱스만으로 반환할 수 있게 하여 검색 성능을 극대화합니다.

트리거 (3개):

    mapping_data_fts_delete, mapping_data_fts_insert, mapping_data_fts_update 트리거가 존재합니다.

이 트리거들은 mapping_data 테이블에 데이터가 추가, 수정, 삭제될 때마다 mapping_data_fts 가상 테이블의 내용을 자동으로 동기화하는 역할을 합니다.

6.4. glossary.db (UI 설정 및 용어집)

이 데이터베이스는 프로젝트 문서의 qt_layout_settings_manager.py (이전 문서 내용 참조) 및 qt_main_app.py (이전 문서 내용 참조)와 연관되어, 애플리케이션의 설정과 UI 상태(창 크기, 스플리터 위치 등)를 저장하는 데 사용됩니다. 총 4개의 테이블, 0개의 인덱스, 0개의 뷰, 0개의 트리거로 구성된 비교적 단순한 구조입니다.

주요 테이블:

    settings

        목적: 애플리케이션의 주요 설정을 저장하는 핵심 Key-Value 테이블입니다. qt_layout_settings_manager가 이 테이블을 사용하여 UI 레이아웃 상태를 저장할 가능성이 높습니다.

        스키마: key (PRIMARY KEY), value (NOT NULL), description, created_at, updated_at.

glossary

    목적: 용어집 또는 번역 데이터를 저장합니다.

    스키마: id (PK AUTOINCREMENT), original_term (UNIQUE NOT NULL), translated_term (NOT NULL), created_at.

translations

    목적: glossary 테이블과 유사하게 용어 번역을 저장하는 또 다른 테이블입니다.

    스키마: original_term (PRIMARY KEY), translated_term (NOT NULL).

인덱스 및 트리거:

    사용자가 생성한 별도의 인덱스나 트리거는 존재하지 않습니다. 테이블의 PRIMARY KEY 및 UNIQUE 제약 조건에 의해 생성되는 기본 인덱스만 사용됩니다.

## 7. 주요 관계 및 데이터 흐름 (Key Relationships & Data Flow)

**일반적인 검색 흐름 (예: Dewey 탭)**
1.  **사용자 입력**: 사용자가 `qt_TabView_Dewey`의 검색창에 키워드를 입력하고 Enter를 누릅니다.
2.  **UI 이벤트 처리**: `qt_TabView_Dewey`가 입력을 받아 `SearchThread`를 생성하여 백그라운드 검색을 시작합니다. (UI 프리징 방지)
3.  **검색 함수 호출**: 스레드는 `qt_Tab_configs.py`에 정의된 Dewey 탭의 검색 함수를 호출합니다. 이 함수는 `qt_dewey_logic.py`를 거쳐 `Search_Dewey.py`의 로직을 실행합니다.
4.  **캐시 확인 및 API 호출**: `Search_Dewey.py`는 먼저 `database_manager.py`를 통해 `dewey_cache.db`에 결과가 있는지 확인합니다. 캐시가 없으면 WorldCat API를 호출하고, 동시에 `search_dewey_manager.py`를 통해 로컬 `nlk_concepts.sqlite`에서 연관 개념을 조회합니다.
5.  **결과 처리 및 반환**: API 결과와 로컬 DB 조회 결과를 조합하고 순위를 매겨 최종 결과셋을 생성한 후, `SearchThread`로 반환합니다.
6.  **UI 업데이트**: `SearchThread`는 완료 신호(Signal)를 UI 스레드로 보냅니다. `qt_TabView_Dewey`는 신호와 함께 전달된 데이터를 받아 테이블 뷰 모델을 업데이트하고, 사용자는 화면에서 결과를 확인합니다.

---

## 8. 최근 변경 사항
CHANGELOG.md
파일에 별도 기록
---

## 9. 주요 의존성 맵 (Key Dependencies Map)

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
│       └── qt_custom_widgets.py (커스텀 위젯)
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

## 10. 문제 해결 가이드 (Troubleshooting Guide)

### 자주 발생하는 이슈

**1. 검색 결과가 표시되지 않음**
- **확인사항**: `database_manager.py`의 데이터베이스 연결 상태 확인
- **로그 위치**: `SearchThread` 실행 시 콘솔 출력 확인
- **해결**: `nlk_concepts.sqlite` 파일 존재 여부 및 FTS5 인덱스 무결성 점검

**2. UI가 멈춤 (Freezing)**
- **원인**: 검색 작업이 메인 스레드에서 실행됨
- **확인**: `qt_base_tab.py`의 `SearchThread` 사용 여부 점검
- **해결**: 모든 검색 함수는 반드시 `SearchThread`를 통해 백그라운드 실행

**3. 탭 레이아웃이 저장되지 않음**
- **확인**: `glossary.db` 쓰기 권한 및 경로
- **관련 파일**: `qt_layout_settings_manager.py`
- **해결**: `qt_main_app.py`의 `closeEvent`에서 저장 함수 호출 확인

**4. API 호출 실패 (Dewey, Gemini)**
- **확인**: `qt_TabView_Settings.py`에서 API 키 설정 여부
- **캐시**: `dewey_cache.db`에 음수 캐시(Negative Cache) 저장됨
- **해결**: API 키 갱신 및 네트워크 연결 확인

**5. 빌드 후 실행 시 모듈 누락**
- **원인**: PyInstaller가 동적 임포트를 감지하지 못함
- **해결**: `.spec` 파일에 `hiddenimports` 추가
- **예**: `hiddenimports=['transformers', 'faiss']`

---

## 11. 개발 시 주의사항 (Development Guidelines)

### 새 탭 추가 시
1. `qt_TabView_Example.py`를 템플릿으로 복사
2. `BaseSearchTab`을 상속하여 클래스 작성
3. `qt_Tab_configs.py`에 탭 메타데이터 등록
4. 검색 함수는 `SearchThread` 호환 시그니처 준수 (`query` → `results`)
5. `qt_main_app.py`에서 탭 동적 로딩 확인

### 데이터베이스 스키마 변경 시
1. `migrate_ddc_schema.py` 또는 유사 마이그레이션 스크립트 작성
2. FTS5 인덱스 재구축 필요 여부 판단
3. `database_manager.py`의 PRAGMA 설정 검토
4. 테스트 스크립트로 성능 검증 (`test_final_performance.py`)

### 검색 로직 수정 시
1. `search_common_manager.py`에 공통 기능 우선 배치
2. DDC/KSH 특화 로직은 각각 `search_dewey_manager.py`, `search_ksh_manager.py`에 분리
3. 캐싱 전략 고려 (DB 캐시 vs 메모리 캐시)
4. 스레드 안전성 확보 (ThreadPoolExecutor 사용)

### UI 컴포넌트 수정 시
1. `ui_constants.py`의 색상/폰트 상수 우선 사용
2. 다크 테마 호환성 확인 (`qt_styles.py`)
3. 커스텀 위젯은 `qt_custom_widgets.py`에 중앙화
4. 레이아웃 상태 저장 필요 시 `qt_layout_settings_manager.py` 활용
---

## 12. 성능 최적화 포인트 (Performance Optimization)

- **데이터베이스**: FTS5 커버링 인덱스 활용 (`database_manager.py` v2.2.0)
- **API 캐싱**: `dewey_cache.db`로 중복 요청 방지
- **스레드 풀**: `search_orchestrator.py`의 `ThreadPoolExecutor`로 병렬 검색
- **UI 반응성**: 모든 검색은 `SearchThread`로 백그라운드 처리
- **벡터 검색**: FAISS 인덱스로 DDC 임베딩 검색 가속
- **쿼리 정규화**: `search_common_manager.py`의 쿼리 전처리로 캐시 적중률 향상

---

## 13. 외부 연동 요약 (External Integrations)

| 연동 대상 | 모듈 | 용도 |
|---------|------|------|
| WorldCat DDC API | `Search_Dewey.py` | DDC 분류 조회 |
| Google Gemini API | `Search_Gemini.py` | AI 메타데이터 생성 |
| 국립중앙도서관 KSH | `Search_KSH_Lite.py` | 웹 스크레이핑 |
| 일본 NDL | `Search_NDL.py` | 서지 검색 |
| CiNii | `Search_CiNii.py` | 학술 논문 검색 |
| BNF, BNE, DNB 등 | `Search_BNF.py` 등 | 유럽 도서관 카탈로그 |
| Harvard, MIT 등 | `Search_Harvard.py` 등 | 미국 대학 도서관 |
| 브라우저 확장 | `extension_api_server.py` | Flask API 서버 |

---

**📌 중요**: 이 문서는 프로젝트의 전체 구조를 이해하기 위한 출발점입니다. 세부 구현은 각 모듈의 docstring과 주석을 참조하십시오.
