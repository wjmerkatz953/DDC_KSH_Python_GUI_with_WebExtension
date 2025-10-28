## 8. 최근 변경 사항 (2025년 10월 기준)

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