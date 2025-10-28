# SOTP – Status of the Project (자동 생성)
> **생성 시각**: {AUTO_GEN_TIMESTAMP}  
> **상태**: {AUTO_GEN_STATUS} **All Green**  
> **AI 전용 초고속 컨텍스트 문서** | 30초 파악 완료

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

## 2. 탭 요약 (총 {AUTO_GEN_TAB_COUNT}개)

| 그룹 | 탭 | 파일 | 아이콘 |
|------|----|------|-------|
| **검색** | ├─ `MARC 추출` | `qt_TabView_MARC_Extractor.py` | |
| | ├─ `NLK 검색` | `qt_TabView_NLK.py` | |
| | ├─ `NDL + CiNii 검색` | `qt_TabView_NDL.py` | |
| | ├─ `Western 검색` | `qt_TabView_Western.py` | |
| | ├─ `Global 통합검색` | `qt_TabView_Global.py` | |
| | └─ `납본 ID 검색` | `qt_TabView_LegalDeposit.py` | |
| **저작물/저자** | ├─ `저자전거 검색` | `qt_TabView_KACAuthorities.py` | |
| | ├─ `상세 저작물 정보` | `qt_TabView_ISNI_Detailed.py` | |
| | └─ `간략 저작물 정보` | `qt_TabView_BriefWorks.py` | |
| **주제어** | ├─ `KSH Hybrid` | `qt_TabView_KSH_Lite.py` | |
| | └─ `KSH Local` | `qt_TabView_KSH_Local.py` | |
| **분류/AI** | ├─ `Dewey 분류 검색` | `qt_TabView_Dewey.py` | |
| | ├─ `Gemini DDC 분류` | `qt_TabView_Gemini.py` | 🤖 |
| | └─ `AI 피드` | `qt_TabView_AIFeed.py` | |
| **편집** | └─ `MARC 로직 편집` | `qt_TabView_MARC_Editor.py` | |
| **도구** | └─ `Python` | `qt_TabView_Python.py` | 🐍 |
| **설정** | └─ `설정` | `qt_TabView_Settings.py` | ⚙️ |

---

## 3. DB 상태

| DB | 테이블 | 인덱스 | 비고 |
|----|--------|--------|------|
| `nlk_concepts.sqlite` | {AUTO_NLK_TABLES} | {AUTO_NLK_INDEXES} | KSH 개념, FTS5 |
| `kdc_ddc_mapping.db` | {AUTO_KDC_TABLES} | {AUTO_KDC_INDEXES} | KDC↔DDC 매핑 |
| `dewey_cache.db` | {AUTO_DEWEY_TABLES} | {AUTO_DEWEY_INDEXES} | DDC API 캐시 |
| `glossary.db` | {AUTO_GLOSSARY_TABLES} | {AUTO_GLOSSARY_INDEXES} | UI 레이아웃 저장 |

---

## 4. 최근 변경 (최신 5)

{AUTO_GEN_CHANGELOG}

---

> **자동 생성 완료** | `generate_sotp.py` 실행  
> **수정 금지** – 자동 갱신 전용