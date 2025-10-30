## 8. 최근 변경 사항 (2025년 10월 기준)

- **2025-10-31: `QItemSelectionModel.ClearAndSelect` 사용법 수정** (`qt_base_tab.py` v3.0.7)
  - **문제**: `qt_base_tab.py` (line 1320)에서 `self.table_view.selectionModel().ClearAndSelect`를 사용했으나, `selectionModel()`이 반환하는 `QItemSelectionModel` 인스턴스에는 `ClearAndSelect` 속성이 없음. `ClearAndSelect`는 선택 플래그(enum)이므로 클래스 레벨에서 접근해야 함.
  - **해결**: `QItemSelectionModel.ClearAndSelect` (또는 `QItemSelectionModel.SelectionFlag.ClearAndSelect`)로 수정하여 올바른 선택 플래그를 사용하도록 변경.
  - **효과**: `AttributeError` 발생 방지 및 선택 모델의 `clearAndSelect` 기능 정상 작동.


### 2025-10-30 (세션 2): 델리게이트 색상 및 Find 매치 하이라이트 구현

- **델리게이트 색상 문제 해결** (`qt_styles.py` v3.0.5)
  - **문제**: Western/Global/NDL 탭의 출처별 색상(LC, Harvard, MIT 등)이 10월 28일 이후 작동 중단
    - **근본 원인**: `qt_styles.py`의 `QTableView::item { color: {U.TEXT_DEFAULT}; }` 속성이 델리게이트의 `option.palette.setColor()` 설정을 무시
    - **증상**: 모든 텍스트가 기본 색상으로 표시되어 출처별 구분 불가
  - **해결**: `QTableView::item`에서 `color` 속성 제거
    - stylesheet의 `color` 속성이 델리게이트의 palette 설정보다 우선순위가 높아서 발생한 문제
    - 델리게이트가 텍스트 색상을 제어할 수 있도록 stylesheet에서 색상 강제 지정 제거
  - **효과**: 출처별 색상이 정상적으로 표시됨 (10월 27일 버전으로 복원)

- **10월 27일 델리게이트 패턴 복원** (`qt_TabView_Western.py` v1.0.2, `qt_TabView_Global.py` v1.0.2, `qt_TabView_NDL.py` v2.0.2)
  - **전략**: 작동하던 10월 27일 버전의 단순한 패턴 사용
    - `option.palette.setColor()` + `super().paint()` 조합
    - 복잡한 custom painting 방식 제거
  - **Western 탭**: 10개 출처 색상 (LC, Harvard, MIT, Princeton, UPenn, Cornell, DNB, BNF, BNE, Google)
  - **Global 탭**: 13개 출처 색상 (Western + NDL, CiNii, NLK)
  - **NDL 탭**: 2개 출처 색상 (NDL, CiNii)
  - **테마 대응**: `UI_CONSTANTS` 동적 로딩으로 Dark/Light 테마 자동 전환

- **Find 매치 하이라이트 기능 구현** (모든 탭)
  - **문제**: Find 기능으로 검색할 때 매치되는 셀들을 시각적으로 구분하기 어려움
    - 이전 세션에서 빨간색 하이라이트 시도했으나 stylesheet 문제로 실패
  - **해결**: 델리게이트 기반 매치 하이라이트 구현
    - **Western/Global/NDL 탭**: 기존 출처 색상 델리게이트에 매치 하이라이트 추가
    - **다른 모든 탭**: `BaseMatchHighlightDelegate` 생성 및 자동 적용
  - **구현 방식**:
    - `paint()` 메서드에서 검색어 매치 확인
    - 매치되는 셀: `painter.fillRect()`로 빨간색 배경 직접 그리기 (ACCENT_RED)
    - 선택된 매치 셀: 파란색 배경 (HIGHLIGHT_SELECTED) - F3 네비게이션 시 구분 가능
    - 선택되지 않은 매치 셀: 빨간색 배경 + 흰색 텍스트
    - `super().paint()` 호출하지 않아 stylesheet 영향 회피
  - **실시간 업데이트**: `_on_find_text_changed()` 메서드 수정
    - Find 입력창 변경 시 델리게이트에 검색어 전달
    - `viewport().update()` 호출로 테이블 다시 그리기
  - **효과**:
    - 검색어와 매치되는 모든 셀이 빨간색으로 강조됨
    - F3으로 이동하면 현재 선택된 셀은 파란색으로 구분됨
    - 검색어 입력과 동시에 하이라이트 실시간 업데이트

- **BaseMatchHighlightDelegate 구현** (`qt_base_tab.py` v3.0.6)
  - **목적**: 델리게이트가 없는 탭(KSH Local, NLK 등)에 매치 하이라이트 제공
  - **통합 기능**:
    - ✅ 매치 하이라이트 (빨간색 배경)
    - ✅ 선택 셀 구분 (파란색 배경)
    - ✅ URL 파란색 표시 (ACCENT_BLUE)
    - ✅ URL 클릭 시 브라우저 열기
    - ✅ KSH 마크업 태그 제거 및 순수 URL 추출
  - **자동 적용**: `BaseSearchTab.__init__`에서 `color_delegate` 속성이 없으면 자동 설정
  - **UrlLinkDelegate 대체**: 기존 UrlLinkDelegate 기능을 모두 포함하여 통합
- **Hotfix: Find navigation crash** (qt_base_tab.py v3.0.6)
  - Replaced selectionModel().ClearAndSelect with the class-level QItemSelectionModel.ClearAndSelect flag to eliminate the AttributeError during find navigation
  - Prevents F3/Shift+F3 lookups from crashing when selecting the next or previous match


- **브랜치 전략**:
  - `feature-match-highlight` 브랜치에서 안전하게 실험
  - 성공 후 `main` 브랜치에 머지 및 GitHub 푸시

- **수정 파일**:
  - `qt_styles.py` v3.0.5 (QTableView::item color 속성 제거)
  - `qt_TabView_Western.py` v1.0.2 (출처 색상 복원 + 매치 하이라이트)
  - `qt_TabView_Global.py` v1.0.2 (출처 색상 복원 + 매치 하이라이트)
  - `qt_TabView_NDL.py` v2.0.2 (출처 색상 복원 + 매치 하이라이트)
  - `qt_base_tab.py` v3.0.6 (BaseMatchHighlightDelegate 추가)

- **기술적 인사이트**:
  - Qt stylesheet의 `color` 속성은 델리게이트의 `option.palette.setColor()`보다 우선순위가 높음
  - stylesheet가 배경색을 덮어쓰는 경우 `super().paint()` 대신 직접 `painter.fillRect()` + `painter.drawText()` 사용
  - 델리게이트 기반 UI 렌더링 시 stylesheet의 전역 설정이 예상치 못한 문제를 일으킬 수 있음

### 2025-10-30 (세션 1): Find 기능 UX 개선

- **Find 입력창 자동 전체 선택 기능 추가** (`qt_base_tab.py` v3.0.4)
  - **문제**: Find 입력창에 기존 검색어가 있을 때 새 검색어를 입력하려면 수동으로 기존 텍스트를 지워야 함
  - **해결**: `QLineEdit` → `SelectAllLineEdit`로 변경
  - **효과**:
    - Ctrl+F 단축키로 Find 입력창 포커스 시 기존 검색어 자동 전체 선택
    - 입력창 클릭 시에도 텍스트 자동 전체 선택
    - 새 검색어 입력 시 기존 검색어가 자동으로 대체됨
  - 중복된 `QLineEdit` import 제거 (코드 정리)

- **Find 하이라이트 색상 시각화 개선** (`qt_base_tab.py` v3.0.4)
  - **문제 1**: Find 기능 사용 시 검색된 셀에 하이라이트가 표시되지 않음
    - **원인**: `setCurrentIndex()`와 `scrollTo()`만 호출하여 포커스만 이동하고 선택 표시는 없음
    - **해결**: `selectionModel().select()`를 추가하여 시각적 하이라이트 적용
  - **문제 2**: 일반 선택과 Find 검색 결과를 구분하기 어려움
    - **원인**: 모든 선택이 동일한 `HIGHLIGHT_SELECTED` 색상 사용
    - **해결**: Find 검색 시 `ACCENT_GREEN`(녹색) 색상으로 하이라이트
  - **구현 방식**:
    - `_find_in_table_view()` 메서드에서 동적 스타일시트 적용
    - `_reset_table_selection_color()` 메서드로 원래 색상 복구
    - 테이블 클릭 시 자동으로 기본 하이라이트 색상으로 복원
  - **효과**:
    - Find 검색 결과: 녹색(ACCENT_GREEN) 하이라이트
    - 일반 선택: 파란색(HIGHLIGHT_SELECTED) 하이라이트
    - 명확한 시각적 구분으로 사용성 향상

- **수정 파일**:
  - `qt_base_tab.py` v3.0.4 (Find 기능 UX 개선)

### 2025-10-29 (세션 5): HTML 뷰어 다중 테이블 지원 개선

- **문제**: Gemini DDC 분류 탭에서 HTML 뷰어 버튼 클릭 시 항상 중간 결과만 표시되는 버그
  - **원인**: 두 개의 테이블(상단 "계층적 검색 결과", 하단 "DDC 추천 결과")이 있을 때, 포커스/선택 우선순위만으로는 사용자 의도 파악 불가
  - **증상**: 사용자가 하단 테이블을 클릭해도 상단 테이블에 선택된 행이 남아있으면 계속 상단 데이터 표시

- **해결책**: 최근 클릭된 테이블 추적(Last Clicked Table Tracking) 패턴 도입
  - **핵심 개념**: 사용자가 마지막으로 클릭한 테이블을 `last_clicked_table` 속성에 기록
  - **우선순위 재설계** (`qt_base_tab.py`의 `_get_active_table_data()` 메서드):
    1. `last_clicked_table` 속성 (최우선) ✅ **신규 추가**
    2. 포커스된 테이블
    3. 선택된 행이 있는 테이블
    4. 기본 테이블 (`current_dataframe`)

- **Gemini DDC 분류 탭 개선** (`qt_TabView_Gemini.py` v2.2.8)
  - `last_clicked_table` 속성 추가: `None` | `"inter_table"` | `"table_view"`
  - 중간 결과 테이블(`inter_table`) 클릭 시 `_on_inter_table_clicked()` 호출
  - 최종 결과 테이블(`table_view`) 클릭 시 `_on_table_view_clicked()` 호출
  - HTML 뷰어가 정확히 마지막 클릭한 테이블 데이터 표시

- **KSH Local 탭 개선** (`qt_TabView_KSH_Local.py` v4.4.1)
  - 동일한 패턴 적용: `last_clicked_table` = `"table_view"` | `"biblio_table"`
  - 상단 개념 DB 테이블 클릭 시 `_on_table_view_clicked()` 호출
  - 하단 서지 DB 테이블 클릭 시 `_on_biblio_table_clicked()` 호출
  - 기존 기능 유지하면서 HTML 뷰어 정확도 향상

- **BaseSearchTab 핵심 로직 업데이트** (`qt_base_tab.py` v3.0.2)
  - `_get_active_table_data()` 메서드 완전 재설계
  - `last_clicked_table` 속성 최우선 체크 로직 추가
  - Gemini 탭과 KSH Local 탭 모두 지원
  - 단일 테이블 탭은 기존 로직 유지 (하위 호환성 보장)

- **테스트 결과** ✅
  - **Gemini DDC 분류 탭**:
    - 상단 "계층적 검색 결과" 클릭 → HTML 뷰어 → 중간 결과 표시 ✅
    - 하단 "DDC 추천 결과" 클릭 → HTML 뷰어 → 최종 결과 표시 ✅
  - **KSH Local 탭**:
    - 상단 "개념 DB" 클릭 → HTML 뷰어 → 개념 DB 표시 ✅
    - 하단 "서지 DB" 클릭 → HTML 뷰어 → 서지 DB 표시 ✅

- **효과**:
  - 다중 테이블 탭에서 HTML 뷰어가 사용자 의도를 정확히 파악
  - 엑셀 추출, HTML 뷰어 등 모든 데이터 내보내기 기능에 적용
  - 향후 다중 테이블 탭 추가 시 패턴 재사용 가능

- **수정 파일**:
  - `qt_base_tab.py` v3.0.2 (우선순위 로직 재설계)
  - `qt_TabView_Gemini.py` v2.2.8 (클릭 추적 기능 추가)
  - `qt_TabView_KSH_Local.py` v4.4.1 (클릭 추적 기능 추가)

### 2025-10-29 (세션 4): PyInstaller SSL 인증서 번들링 개선

- **SSL 인증서 경로 문제 해결** (`.spec`, `ssl_cert_utils.py`)
  - **문제**: PyInstaller로 빌드된 exe에서 HTTPS 요청 시 `Could not find a suitable TLS CA certificate bundle` 오류 발생
  - **원인**: certifi 패키지의 `cacert.pem` 파일이 exe에 포함되지 않음
  - **해결책 1**: `qt_main_app.spec` 파일에 certifi 인증서 명시적 포함
    - `datas`에 `cacert.pem` 추가: `(cacert_file, 'certifi')`
    - `hiddenimports`에 `certifi` 추가
  - **해결책 2**: `ssl_cert_utils.py` 강화
    - PyInstaller 번들링 경로(`sys._MEIPASS/certifi/cacert.pem`) 확인 로직 추가
    - 인증서를 찾을 수 없는 경우 폴백으로 SSL 검증 비활성화 (개발 환경용)
    - 더 많은 환경 변수 설정 (`CURL_CA_BUNDLE` 추가)
  - **테스트 스크립트 추가**: `test_ssl.py` - SSL 설정이 제대로 되었는지 확인
  - **빌드 방법**: `pyinstaller qt_main_app.spec --clean`

- **수정 파일**:
  - `qt_main_app.spec` (certifi 인증서 포함)
  - `ssl_cert_utils.py` v1.0.1 (폴백 로직 및 대체 경로 추가)
  - `test_ssl.py` (신규 생성)

### 2025-10-29 (세션 3): Search_Naver.py v1.2.0 - 네트워크 안정성 및 성능 최적화

- **네트워크 탄력성 강화** (`Search_Naver.py` v1.2.0)
  - **재시도 로직 + 지수 백오프 구현**
    - `_retry_request()` 함수 추가: 단일 재시도 + 0.6~1.2초 랜덤 대기
    - 429 (Too Many Requests), 503 (Service Unavailable) 자동 재시도
    - 타임아웃 및 ConnectionError 시 자동 재시도
    - 효과: 일시적 네트워크 오류나 서버 과부하 시 성공률 대폭 향상

- **HTTP 세션 재사용 및 공통 헤더 관리**
  - `get_http_session(site)` 함수 추가: 사이트별 세션 캐싱
  - 네이버, Yes24, 교보문고 각각의 최적화된 헤더 설정
  - 모듈 전역 세션 딕셔너리 + 스레드 락으로 동시성 보장
  - 효과: 커넥션 재수립 오버헤드 감소, 속도 향상

- **ISBN 정규화 유틸리티 추가**
  - `normalize_isbn_digits(isbn_str)`: 숫자만 추출 (공백, 하이픈 제거)
  - `split_isbn_tokens(isbn_str)`: ISBN13+ISBN10 조합 분리 및 정규화
  - 모든 ISBN 비교 및 로깅에 정규화 적용
  - 효과: ISBN10·13 혼재, 하이픈/공백 포함 등 다양한 형식 대응, 매칭 정확도 향상

- **스크레이핑 결과 캐시 시스템 (2시간 TTL)**
  - `_get_cached_scraping_result()`, `_set_cached_scraping_result()` 함수 추가
  - 메모리 기반 LRU 캐시 (최대 100개, 2시간 TTL)
  - Yes24, 교보문고 스크레이핑 결과 자동 캐싱
  - 캐시 히트 시 로그 출력으로 디버깅 가능
  - 효과: 동일 ISBN 반복 조회 시 즉시 응답, 외부 사이트 부하 감소

- **버그 수정**
  - `_call_naver_api()` 반환값 불일치 수정
    - 문제: 성공 시 1개 값 반환, 실패 시 2개 값 반환 → 언패킹 오류
    - 해결: 항상 `(response, error_msg)` 2개 값 반환하도록 통일

- **코드 품질 개선**
  - 타입 힌트 추가: `Literal`, `Optional`, `Tuple` 사용
  - 로깅 개선: ISBN은 정규화하여 로깅 (가독성 향상)
  - 코드 모듈화: 각 기능별로 명확한 함수 분리

- **변경 통계**: +355줄, -57줄 (총 412줄 변경)

- **수정 파일**:
  - `Search_Naver.py` v1.2.0 (대규모 리팩토링 및 기능 개선)

### 2025-10-29 (세션 2): 레코드 스키마 상수화 및 팩토리 패턴 도입

- **레코드 생성 로직 리팩토링** (`Search_Naver.py`, 기타 검색 모듈)
  - **스키마 상수 정의**: 모든 검색 모듈에서 사용하는 레코드 필드를 상수로 정의
  - **팩토리 함수 패턴**: `_create_error_record()` 같은 팩토리 함수로 레코드 생성 통일
  - **효과**: 코드 유지보수성 향상, 오타 방지, 필드 추가/제거 시 일관성 보장

- **어플리케이션 버전 업데이트** (`qt_main_app.py`)
  - 윈도우 타이틀에 표시되는 버전을 v5.1.0으로 업데이트
  - 버전 관리 체계 확립

- **.gitignore 업데이트**
  - JavaScript 파일(`*.js`) 예외 추가
  - 웹 확장 기능 개발 파일 포함

- **수정 파일**:
  - `qt_main_app.py` (버전 5.1.0)
  - `.gitignore`
  - 다수의 검색 모듈 (레코드 스키마 상수화)

### 2025-10-29 (세션 1): Search_Naver.py 리팩토링 완료

- **search_naver_catalog 함수 대규모 리팩토링** (`Search_Naver.py` v1.1.1)
  - **문제점**: 500줄 넘는 거대한 단일 함수, 가독성 및 유지보수성 저하
  - **리팩토링 목표**: 함수 분해, 단일 책임 원칙 적용, 오류 처리 개선

- **신규 헬퍼 함수 추가**:
  - `_validate_search_input()`: 검색어 유효성 검사
  - `_prepare_naver_api_request()`: API 요청 URL 및 검색 타입 결정
  - `_call_naver_api()`: API 호출 및 네트워크 오류 처리
  - `_parse_naver_api_response()`: XML 응답 파싱 및 오류 처리
  - `_scrape_additional_info()`: Yes24/교보문고 병렬 스크레이핑
  - `_process_scraped_data()`: 스크레이핑 데이터 병합 및 레코드 생성
  - `_create_error_record()`: 표준화된 오류 레코드 생성

- **개선 사항**:
  - 명확한 단계별 흐름: 입력 검증 → API 호출 → 파싱 → 스크레이핑 → 병합
  - 오류 처리 강화: 네트워크 오류, XML 파싱 오류, 검색 결과 없음 등 세분화
  - 코드 재사용성 향상: 헬퍼 함수들을 다른 곳에서도 활용 가능
  - 테스트 용이성: 각 함수를 독립적으로 테스트 가능

- **교보문고 스크레이핑 개선**
  - **버그 수정**: 제2저자(번역자 등)의 "다른 작품" 정보가 누락되던 문제 해결
  - **원인**: `.find()`는 첫 번째 `writer_info_box`만 찾음 (지은이만 추출)
  - **해결**: `.find_all()`로 변경하여 저자, 번역자 등 모든 `writer_info_box` 순회
  - **효과**: 번역서의 경우 번역자의 다른 작품 목록도 정상 추출

- **수정 파일**:
  - `Search_Naver.py` v1.1.0 → v1.1.1 (대규모 리팩토링)

### 2025-10-29: 기타 버그 수정 및 개선

- **웹 확장 기능 데이터 업데이트** (`extension/data.json`)
  - 웹 확장 기능에서 사용하는 설정 및 데이터 파일 업데이트

- **수정 파일**:
  - `extension/data.json`

### 2025-10-28 (세션 3): HTML 뷰어 자동 테이블 감지 및 Dewey 탭 지원

- **HTML 보기 기능 개선: 포커스/선택된 테이블 자동 감지**
  - **배경**: Gemini DDC 분류 탭(2개 테이블), KSH Local 탭(2개 테이블)에서 "표시할 데이터가 없습니다" 오류 발생
  - **문제**: `current_dataframe`이 업데이트되지 않음

- **해결 방법**:
  1. **각 탭에서 `current_dataframe` 업데이트** (Option 1 선택)
     - Gemini 탭: 최종 결과를 `current_dataframe`에 저장, 중간 결과를 `intermediate_dataframe`에 저장
     - KSH Local 탭: 상단 개념 DB를 `current_dataframe`에, 하단 서지 DB를 `biblio_dataframe`에 저장

  2. **포커스/선택된 테이블 자동 감지 로직 구현** (`qt_base_tab.py`)
     - `_get_active_table_data()` 메서드 추가 - 현재 활성화된 테이블을 지능적으로 감지
     - **감지 우선순위**:
       1. 포커스된 테이블 (`QApplication.focusWidget()`)
       2. 선택된 행이 있는 테이블 (`selectionModel().hasSelection()`)
       3. 기본 테이블 (`table_view`)
     - `_get_dataframe_from_model()` 메서드 추가 - 모델에서 DataFrame 추출
     - **효과**: 사용자가 클릭한 테이블이 자동으로 HTML 뷰어에 표시됨

- **Gemini DDC 분류 탭** (`qt_TabView_Gemini.py` v2.2.7)
  - `on_search_completed()`에서 `current_dataframe` 업데이트 추가
  - `_on_intermediate_rows()`에서 `intermediate_dataframe` 업데이트 추가
  - `on_clear_results()`에서 두 DataFrame 모두 초기화
  - `__init__()`에서 `intermediate_dataframe` 초기화
  - LC Catalog 링크 URL 변경:
    - Before: `https://lccn.loc.gov/search/?q=813.6&format=web`
    - After: `https://search.catalog.loc.gov/search?option=advanced&pageNumber=1&query=keyword%20containsAll%20%22813.6%22&recordsPerPage=25`
  - 순위 개수 표시 수정: "전체 설명" 행을 제외한 실제 순위만 카운트

- **KSH Local 탭** (`qt_TabView_KSH_Local.py` v2.2.1)
  - `on_search_completed()`에서 `current_dataframe`/`biblio_dataframe` 업데이트
  - `_on_title_search_completed()`에서 `biblio_dataframe` 업데이트
  - `_on_biblio_search_completed()`에서 `biblio_dataframe` 업데이트

- **Dewey 탭 HTML 보기 기능 추가** (`qt_TabView_Dewey.py` v4.3.2)
  - "HTML로 보기" 버튼 추가 (연동검색 ON 버튼과 API 설정 버튼 사이)
  - `setup_connections()`에서 `column_keys` 설정 추가
  - `qt_dewey_logic.py` v4.3.2:
    - `_on_ksh_search_completed()`에서 `current_dataframe` 업데이트 추가
    - `import pandas as pd` 추가

- **BaseSearchTab** (`qt_base_tab.py` v3.0.2)
  - `_get_active_table_data()` 메서드 신규 추가
  - `_get_dataframe_from_model()` 메서드 신규 추가
  - `show_html_viewer()` 메서드 수정 - 포커스/선택된 테이블 자동 감지

- **Gemini 검색 로직 버그 수정** (`Search_Gemini.py`)
  - `_fallback_hierarchy_from_text()` 반환 구조 수정
  - Before: `{"broad": ["키워드"], ...}` (리스트)
  - After: `{"broad": {"korean": ["키워드"], "english": []}, ...}` (딕셔너리)
  - `AttributeError: 'list' object has no attribute 'get'` 오류 해결

- **교훈**:
  - 여러 테이블을 가진 탭에서는 포커스/선택 상태를 추적하여 사용자 의도를 파악해야 함
  - DataFrame을 별도 변수에 저장해두면 HTML 뷰어/CSV 추출 등 다양한 기능에 재사용 가능
  - CSV 저장 기능은 HTML 뷰어에 이미 구현되어 있으므로 중복 구현 불필요

- **수정 파일**:
  - `qt_TabView_Gemini.py` v2.2.7
  - `qt_TabView_KSH_Local.py` v2.2.1
  - `qt_TabView_Dewey.py` v4.3.2
  - `qt_dewey_logic.py` v4.3.2
  - `qt_base_tab.py` v3.0.2
  - `Search_Gemini.py`

### 2025-10-28 (세션 2): 트리메뉴 모드 스타일 적용 및 테마 전환 문제 해결

- **⚠️ 중요 패턴: 인라인 스타일과 테마 전환 문제**
  - **문제 1**: 트리메뉴 모드에서 `QTextEdit#MARC_Gemini_Input` 같은 objectName 기반 전역 스타일시트가 적용되지 않음
    - **원인**: Qt는 숨겨진 위젯(`hide()` 상태)에 objectName 기반 ID 선택자를 완전히 적용하지 않음
    - **1차 시도 (실패)**: `style().polish(tab_widget)` 호출 - 효과 없음
    - **2차 시도 (실패)**: `show()` → `polish()` → `hide()` 트릭 - 여전히 효과 없음
    - **최종 해결**: **인라인 스타일(`setStyleSheet()`)을 명시적으로 설정**

  - **문제 2**: 인라인 스타일이 **탭 생성 시점의 색상으로 고정**됨
    - **현상**: Dark Theme일 때 모듈 로드 → Light Theme 설정 → 탭 생성 → 여전히 Dark 색상 표시
    - **원인**: 모듈 최상단에서 `from ui_constants import U`로 import하면 **모듈 로드 시점의 값으로 고정**
      ```python
      # 모듈 최상단 (잘못된 방법)
      from ui_constants import UI_CONSTANTS as U

      def create_input_section(self):
          self.input_edit.setStyleSheet(f"background: {U.INPUT_WIDGET_BG}")
          # ❌ U는 모듈 로드 시점(Dark)의 값으로 고정됨!
      ```
    - **해결 1**: 함수 내에서 **지역 import**로 최신 값 가져오기
      ```python
      def create_input_section(self):
          from ui_constants import UI_CONSTANTS as U_CURRENT
          self.input_edit.setStyleSheet(f"background: {U_CURRENT.INPUT_WIDGET_BG}")
          # ✅ 함수 호출 시점의 최신 테마 값 적용!
      ```
    - **해결 2**: `refresh_theme()` 메서드로 테마 전환 시 스타일 재설정
      ```python
      def refresh_theme(self):
          from ui_constants import UI_CONSTANTS as U
          self.input_edit.setStyleSheet(f"background: {U.INPUT_WIDGET_BG}")
      ```

  - **교훈**:
    1. 전역 스타일시트만으로는 트리메뉴 모드(숨겨진 위젯)에서 불충분
    2. **인라인 스타일 사용 시 반드시 함수 내에서 UI_CONSTANTS를 import**
    3. 테마 전환을 지원하려면 `refresh_theme()` 메서드 필수 구현
    4. 설정 탭에서 모든 탭의 `refresh_theme()` 호출 필수

- **트리메뉴 모드 테마 전환 에러 수정** (`qt_TabView_Settings.py` v1.0.4)
  - Light/Dark 테마 전환 시 `'NoneType' object has no attribute 'count'` 에러 수정
  - **원인**: `main_window.tab_widget.count()` 호출 시 트리메뉴 모드에서 `tab_widget`이 `None`
  - **해결**: 탭 모드와 트리메뉴 모드 구분 처리
    - 탭 모드: `main_window.tab_widget` 순회
    - 트리메뉴 모드: `main_window.tree_menu_navigation.tab_widgets` 딕셔너리 순회
  - 모든 탭의 `refresh_theme()` 메서드 호출하여 인라인 스타일 업데이트

- **MARC 추출 및 Gemini 탭 테마 적용 완전 수정** (`qt_TabView_MARC_Extractor.py` v2.1.6, `qt_TabView_Gemini.py` v2.2.6)
  - **v2.1.5/v2.2.5**: `refresh_theme()` 메서드 추가 (테마 전환 지원)
  - **v2.1.6/v2.2.6**: 탭 생성 시점에도 올바른 테마 적용되도록 수정
    - 문제: 모듈 최상단 import로 인해 Dark 테마 값으로 고정
    - 해결: 함수 내에서 `from ui_constants import UI_CONSTANTS as U_CURRENT` 지역 import
  - **효과**:
    - 앱 시작 시 Light 테마로 설정되어 있어도 정확한 색상 적용
    - Dark/Light 테마 전환 시에도 즉시 업데이트

- **트리메뉴 네비게이션 스타일 강제 적용** (`qt_tree_menu_navigation.py` v1.2.2)
  - 사전 로딩 시 `show()` → `polish()` → `hide()` 트릭 시도 (효과 제한적)
  - 최종적으로는 각 탭의 인라인 스타일 + `refresh_theme()`으로 해결

- **수정 파일**:
  - `qt_TabView_Settings.py` v1.0.4 (트리메뉴 모드 테마 전환 에러 수정)
  - `qt_tree_menu_navigation.py` v1.2.2 (스타일 강제 적용 시도)
  - `qt_TabView_Gemini.py` v2.2.6 (지역 import + refresh_theme)
  - `qt_TabView_MARC_Extractor.py` v2.1.6 (지역 import + refresh_theme)

### 2025-10-28 (세션 1): 트리메뉴와 탭뷰 완전 통일

- **트리메뉴 네비게이션 아키텍처 개선** (`qt_tree_menu_navigation.py` v1.2.0)
  - 지연 로딩(lazy loading) 제거 - 모든 탭을 초기화 시점에 미리 생성
  - `preload_tabs_and_show_first()` 메서드 추가 - 17개 모든 탭 사전 로딩
  - **탭뷰와 완전 동일한 동작**:
    - 탭 전환 시 레이아웃에서 제거하지 않고 `hide()`/`show()`만 사용
    - MARC Extractor/Editor 탭을 `app_instance`에 등록 (탭 간 데이터 전송 지원)
    - 탭 전환 시 자동 포커스 설정 (`set_initial_focus()` 호출)
  - **효과**: 레이아웃 복원, 데이터 전송, 예외 처리 등 지연 로딩으로 인한 문제 해결
  - **성능**: 탭 생성 속도가 빠르고 메모리 사용량이 적어 사전 로딩 부담 없음
  - **일관성**: 탭 모드와 트리메뉴 모드의 동작 방식 완전히 통일

- **스타일시트 적용 문제 해결** (`qt_TabView_MARC_Extractor.py` v2.1.3, `qt_TabView_Gemini.py` v2.2.3, `qt_styles.py` v3.0.4)
  - 트리메뉴 모드에서 `BACKGROUND_SECONDARY` 색상이 적용되지 않던 문제 해결
  - **원인**: 인라인 스타일(`setStyleSheet()`)이 탭 생성 시점의 색상으로 고정되어 테마 전환 불가
  - **해결**: 인라인 스타일 제거, `objectName` 설정만으로 전역 스타일시트 자동 적용
  - 탭을 레이아웃에 추가한 후 숨김 처리하여 부모의 스타일시트 상속 보장
  - `:focus` 스타일을 전역 스타일시트에 추가
  - **효과**: 테마 전환 시 자동으로 색상 업데이트, 코드 간결화

- **배경**:
  - 이전 트리메뉴 모드는 탭을 클릭할 때마다 생성 (지연 로딩)
  - 탭 모드는 시작 시 모든 탭 생성 (사전 로딩)
  - 지연 로딩으로 인한 문제:
    - 레이아웃 복원 시점에 탭이 존재하지 않아 스플리터 크기 복원 불가
    - 탭 간 데이터 전송 시 대상 탭이 아직 생성되지 않아 에러 발생
    - 예외 처리가 복잡해지고 코드 일관성 저하
  - 사전 로딩 도입 시 이점:
    - 레이아웃 복원이 즉시 작동 (모든 탭이 이미 존재)
    - 데이터 전송 로직 단순화 (항상 탭이 존재한다고 가정 가능)
    - 탭 모드와 동일한 코드 경로 사용으로 버그 감소

- **데이터 전송 로직 간소화** (`qt_main_app.py`)
  - `get_tab_by_name()` 메서드에서 트리메뉴용 자동 생성 로직 제거
  - **이전**: 탭이 없으면 `create_tab_widget()`으로 자동 생성
  - **현재**: 사전 로딩으로 모든 탭이 이미 존재, 단순히 `tab_widgets.get(name)` 호출
  - **효과**: 코드 간소화, 예외 처리 불필요, 더 빠른 데이터 전송

- **MARC 파서 버그 수정** (`marc_parser.py`, `qt_TabView_Dewey.py`)
  - 듀이 탭으로 082 필드(DDC 번호) 데이터가 전송되지 않던 버그 수정
  - **버그 1**: `f_fields` 초기화 딕셔너리에 `F11_DDC` 키가 누락
    - 해결: 초기화 딕셔너리에 `"F11_DDC": ""` 추가
  - **버그 2**: `receive_data()` 호출 시 `ddc` 인자 중복 전달 에러
    - 원인: `kwargs.get("ddc")` 후 `**kwargs`에 여전히 `ddc` 포함
    - 해결: `kwargs.pop("ddc")` 사용하여 추출과 동시에 제거
  - **효과**: MARC 추출 시 082 필드가 정상적으로 파싱되어 듀이 탭으로 전송됨

- **수정 파일**:
  - `qt_tree_menu_navigation.py` v1.2.0
  - `qt_TabView_MARC_Extractor.py` v2.1.3
  - `qt_TabView_Gemini.py` v2.2.3
  - `qt_TabView_Dewey.py` (receive_data 인자 중복 버그 수정)
  - `qt_styles.py` v3.0.4
  - `qt_main_app.py` (get_tab_by_name 메서드 간소화)
  - `marc_parser.py` (F11_DDC 필드 초기화 추가)

### 2025-10-27: 테마 대응 개선 및 기능 추가

- **API 설정 다이얼로그 테마 대응 및 버그 수정** (`qt_api_settings.py` v1.1.2, `qt_styles.py` v3.0.3)
  - Light Theme에서 흐릿하게 보이던 레이블 텍스트 색상 문제 해결
  - 하드코딩된 인라인 스타일을 속성 선택자 기반으로 변경
  - 제목 레이블: `TEXT_DEFAULT` 색상을 전역 스타일시트에서 상속
  - 설명 레이블: `QLabel[label_type="subdued"]` 속성 선택자 사용으로 `TEXT_SUBDUED` 색상 적용
  - 입력 필드 레이블: 전역 스타일시트에서 색상 상속
  - 상태 레이블: `setProperty("api_status", "success/error")`와 `style().unpolish()/polish()` 패턴 사용
  - X 버튼 클릭 시 다이얼로그가 닫히지 않던 버그 수정
  - 윈도우 플래그를 `Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint`로 명시적 설정

- **세로 헤더(행 번호) 스타일 추가** (`qt_styles.py`, `qt_TabView_MARC_Extractor.py`, `qt_TabView_Dewey.py`)
  - QHeaderView::section:vertical 스타일로 행 번호 중앙 정렬 및 테마별 색상 적용
  - MARC 추출 탭과 Dewey 탭에 세로 헤더 표시 활성화
  - `setDefaultAlignment(Qt.AlignCenter)`로 행 번호 중앙 정렬 구현

- **API 상태 표시 테마 대응** (`qt_styles.py`, `qt_TabView_NLK.py`, `qt_TabView_Gemini.py`, `qt_TabView_AIFeed.py`, `qt_dewey_logic.py`)
  - 하드코딩된 API 상태 색상을 QLabel[api_status] 속성 선택자로 변경
  - `api_status="success"` → ACCENT_GREEN, `api_status="error"` → ACCENT_RED
  - 테마 전환 시 자동으로 색상 업데이트되도록 개선
  - Dewey 탭에 API 상태 라벨 추가

- **NDL 및 Western 탭 델리게이트 테마 대응** (`qt_TabView_NDL.py`, `qt_TabView_Western.py`, `ui_constants.py`, `qt_TabView_Settings.py`)
  - SourceColorDelegate와 WesternSourceColorDelegate에서 매번 최신 UI_CONSTANTS 가져오기
  - Western 탭 출처별 색상을 UI 상수로 정의 (Dark/Light 테마별)
  - `refresh_theme()` 메서드 추가로 테마 전환 시 viewport 강제 업데이트
  - 설정 탭의 `_apply_theme()`에서 모든 탭의 `refresh_theme()` 호출

- **Western 탭 출처별 색상 상수 추가** (`ui_constants.py`)
  - Dark Theme: SOURCE_LC (#C7DA72), SOURCE_HARVARD (#99A1E6) 등 기존 색상 유지
  - Light Theme: 진한 색상으로 가독성 확보 (SOURCE_LC #6B8E23, SOURCE_HARVARD #4A5FC1 등)
  - SOURCE_DNB, SOURCE_BNF는 TEXT_DEFAULT, ACCENT_BLUE 상수 사용

- **Western 탭 Google Books API 설정 기능 추가** (`qt_TabView_Western.py`)
  - NLK 탭 구조를 참고하여 API 설정 버튼과 상태 라벨 추가
  - `create_find_section()` 오버라이드하여 HTML 버튼 옆에 API 관련 위젯 배치
  - `_show_api_settings()`, `_update_api_status()` 메서드 구현
  - Qt, QPushButton, QLabel import 추가

- **Cornell 상세 링크에 librarian_view 추가** (`Search_Cornell.py`)
  - 상세 링크 URL에 `/librarian_view` 경로 추가
  - 클릭 시 바로 MARC 레코드 뷰 표시되도록 개선

- **Global 탭 델리게이트 테마 대응** (`qt_TabView_Global.py`, `ui_constants.py`)
  - GlobalSourceColorDelegate에서 매번 최신 UI_CONSTANTS 가져오기
  - Global 탭 전용 출처별 색상 상수 추가 (Dark/Light 테마별)
  - Dark Theme: SOURCE_NDL (#FF6B9D), SOURCE_CINII (#87CEEB), SOURCE_NLK (#FFB347)
  - Light Theme: SOURCE_NDL (#C2185B), SOURCE_CINII (#1976D2), SOURCE_NLK (#F57C00)
  - `refresh_theme()` 메서드 추가로 테마 전환 시 viewport 강제 업데이트
  - Western 탭의 모든 출처 색상(LC, Harvard, MIT 등)도 Global에서 사용

- **테이블 헤더뷰 테마 대응** (`qt_widget_events.py` v2.1.1, `qt_base_tab.py`)
  - ExcelStyleTableHeaderView의 paintSection 메서드에서 모든 색상을 동적으로 로드하도록 수정
  - 배경색 (ACCENT_BLUE, WIDGET_BG_DEFAULT), 테두리색 (QHEADER_BORDER), 텍스트색 (TEXT_BUTTON), 정렬 아이콘색 (ACCENT_GREEN, ACCENT_BLUE), 필터 라인색 (ACCENT_RED) 모두 UI_CONSTANTS에서 동적으로 가져옴
  - `from ui_constants import UI_CONSTANTS` 패턴으로 매 렌더링마다 최신 테마 색상 적용
  - 모든 BaseSearchTab 상속 탭에서 수평 스크롤바 항상 표시 (`setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)`)

- **레이아웃 설정 저장/복구 트리메뉴 모드 지원** (`qt_main_app.py`)
  - `save_layout_settings()`, `restore_layout_settings()` 메서드가 트리메뉴 모드에서 작동하지 않던 버그 수정
  - 기존: `self.tab_widget`만 체크하여 탭 모드에서만 동작
  - 수정: `self.tree_menu_navigation.tab_widgets` 딕셔너리를 통해 트리메뉴 모드도 지원
  - 탭 접근 로직을 통일하여 탭/트리메뉴 모드 모두에서 스플리터 크기 저장/복구 정상 동작
  - 트리메뉴 모드에서 탭이 지연 로딩되어도 메뉴바/로그/상세정보 패널 표시 상태는 정상 복구됨
  - `tab_widget.tabBar()` 접근 시 None 체크 추가로 에러 방지

- **수정 파일**:
  - `qt_api_settings.py` v1.1.2 (테마 대응 + X 버튼 수정)
  - `qt_styles.py` v3.0.3 (label_type="subdued" 스타일 추가)
  - `qt_widget_events.py` v2.1.1 (paintSection 테마 대응)
  - `qt_base_tab.py` (수평 스크롤바 항상 표시)
  - `qt_main_app.py` (레이아웃 저장/복구 트리메뉴 모드 지원)
  - `qt_TabView_MARC_Extractor.py` v2.1.2
  - `qt_TabView_Dewey.py` v4.3.1
  - `qt_TabView_NLK.py` v1.0.5
  - `qt_TabView_Gemini.py` v2.2.2
  - `qt_TabView_AIFeed.py` v1.0.2
  - `qt_TabView_NDL.py` v2.0.1
  - `qt_TabView_Western.py` v1.0.1
  - `qt_TabView_Global.py` v1.0.1
  - `qt_TabView_Settings.py` v1.0.3
  - `qt_dewey_logic.py` v4.3.1
  - `ui_constants.py` v3.0.2
  - `Search_Cornell.py` v2.0.1

### 2025-10-25 (세션 2): UI 일관성 개선 및 테마 호환성 강화
- **MARC_Gemini 입력 위젯 그룹 스타일 추가** (`qt_styles.py`, `qt_TabView_MARC_Extractor.py`, `qt_TabView_Gemini.py`)
  - MARC 추출 탭과 Gemini 탭의 입력 위젯에 `MARC_Gemini_Input` objectName 지정
  - `QTextEdit#MARC_Gemini_Input` 전용 스타일 그룹 생성
  - 두 탭의 입력 위젯 배경색을 한 곳에서 조절 가능하도록 통합
  - 트리메뉴 모드에서도 정확한 배경색 적용을 위해 `get_color()` 함수 사용한 인라인 스타일 추가

- **라디오 버튼 스타일 개선** (`qt_styles.py`)
  - QRadioButton 커스텀 스타일 추가로 선택/미선택 상태 명확히 구분
  - radial gradient 사용하여 선택 시 중앙 점 효과 구현
  - Light Theme에서도 선명하게 보이도록 테두리 및 색상 조정
  - 호버 상태에서 파란색 테두리로 인터랙션 피드백 제공

- **설정 탭 "적용" 버튼 텍스트 색상 수정** (`qt_TabView_Settings.py`)
  - 하드코딩된 `color: white`를 `TEXT_BUTTON` UI 상수로 변경
  - 테마 전환 시에도 일관된 버튼 텍스트 색상 유지

- **트리메뉴 테두리 색상 수정** (`qt_tree_menu_navigation.py`)
  - 하드코딩된 `#3d3d3d`를 `BORDER_LIGHT` UI 상수로 변경
  - 트리메뉴 모드와 탭 모드 간 외관 일관성 확보
  - Light/Dark 테마 모두에서 적절한 테두리 색상 표시

- **수정 파일**:
  - `qt_styles.py` v3.0.1
  - `qt_TabView_MARC_Extractor.py` v2.1.1
  - `qt_TabView_Gemini.py` v2.2.1
  - `qt_TabView_Settings.py` v1.0.2
  - `qt_tree_menu_navigation.py` v1.0.4

### 2025-10-25 (세션 1): 트리메뉴 네비게이션 개선 및 Gemini 탭 추가
- **트리메뉴 호버 자동 펼치기 구현** (`qt_tree_menu_navigation.py`)
  - 마우스 호버 시 그룹 메뉴가 자동으로 펼쳐지도록 `itemEntered` 시그널 연결
  - `setMouseTracking(True)` 활성화로 호버 이벤트 감지
  - 싱글 클릭으로 그룹 펼치기/접기 동작 추가
- **Gemini DDC 분류 탭 트리메뉴 추가**
  - 분류/AI 그룹에 "Gemini DDC 분류" 탭 추가
  - 탭 이름 통일: `qt_Tab_configs.py`의 정확한 탭 이름과 일치시킴
  - 아이콘 매핑: 🤖 (로봇) 아이콘 할당
- **수정 파일**: `qt_tree_menu_navigation.py` v1.0.3

### 2025-10-24: Light/Dark 테마 시스템 완성
- **다크/라이트 테마 전환 시스템 구현** (`ui_constants.py`, `qt_styles.py`)
  - `UI_CONSTANTS_DARK` 및 `UI_CONSTANTS_LIGHT` 클래스 정의
  - 테마별 색상 상수: BACKGROUND, TEXT, ACCENT, BORDER 등
  - 설정 탭에서 테마 선택 및 저장 기능
- **테마 적용 개선**
  - 하드코딩된 색상을 UI 상수로 전환 (다수 파일)
  - Light 테마 가독성 향상: 로그 색상, 컬럼명 색상, 설명 텍스트 색상 조정
  - INPUT_WIDGET_BG 상수 추가로 입력 위젯 배경색 통일
- **트리메뉴 스타일 개선**
  - 호버 및 선택 항목 색상을 ACCENT_BLUE로 통일
  - 텍스트 색상을 TEXT_DEFAULT 및 TEXT_BUTTON으로 변경
- **수정 파일**:
  - `ui_constants.py` v1.0.2
  - `qt_styles.py` v1.0.2
  - `qt_TabView_Settings.py` v1.0.2
  - `qt_TabView_Gemini.py` v1.0.1
  - `qt_TabView_Dewey.py` v1.0.1
  - `qt_TabView_MARC_Extractor.py` v1.0.1
  - `qt_tree_menu_navigation.py` v1.0.2
  - `qt_main_app.py` v1.0.1

- **2025-10-24**: `Search_KSH_Lite.py`와 `search_ksh_manager.py`가 개선되었습니다. DDC 출현 빈도, 연관 관계 확장 등을 고려한 정교한 랭킹 로직이 추가되었습니다.
- **2025-10-20**: **대규모 리팩토링**: 기존의 거대했던 `SearchQueryManager`가 `search_common_manager.py`, `search_dewey_manager.py`, `search_ksh_manager.py`로 분리되어 역할과 책임이 명확해졌습니다. 관련 UI 코드들도 새 관리자 구조에 맞게 업데이트되었습니다.
- **2025-10-19**: `database_manager.py`가 v2.2.0으로 업데이트되면서 FTS5 기반의 가상 테이블과 백그라운드 쓰기 스레드가 도입되었습니다. 이를 통해 Dewey 검색 로직이 커버링 인덱스를 활용하게 되어 성능이 크게 향상되었습니다.
- **2025-10-18**: `qt_main_app.py`에 모든 탭의 스플리터 상태를 저장/복원하는 기능이 안정화되었고, 앱 종료 시 백그라운드 스레드와 서버가 확실히 종료되도록 코드가 강화되었습니다.

---