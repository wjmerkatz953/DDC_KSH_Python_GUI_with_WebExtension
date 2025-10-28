# SOTP – Status of the Project (자동 생성)
> **생성 시각**: 2025-10-28 20:16:30  
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

## 2. 탭 요약 (총 0개)

| 그룹 | 탭 | 파일 | 아이콘 |
|------|----|------|-------|


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

### 2025-10-25 (세션 1): 트리메뉴 네비게이션 개선 및 Gemini 탭 추가
- **트리메뉴 호버 자동 펼치기 구현** (`qt_tree_menu_navigation.py`)
- **Gemini DDC 분류 탭 트리메뉴 추가**
- **수정 파일**: `qt_tree_menu_navigation.py` v1.0.3

---

> **자동 생성 완료** | `generate_sotp.py` 실행  
> **수정 금지** – 자동 갱신 전용
