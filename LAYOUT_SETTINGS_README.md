# 레이아웃 설정 자동 저장/복구 기능

## 📌 개요

앱의 QSplitter 크기와 F7~F12 단축키 위젯의 on/off 상태를 **자동으로 저장**하고, 앱 **재시작 시 이전 설정을 자동으로 복구**하는 기능입니다.

## ✨ 기능

### 저장되는 정보
- **QSplitter 크기**: 각 탭별 패널 크기 (메인 스플리터, 하단 스플리터 등)
- **F7**: Find/검색 영역 표시/숨김
- **F8**: 전체 화면 모드 (동시 on/off)
- **F9**: 탭바 표시/숨김
- **F10**: 메뉴바 표시/숨김
- **F11**: 상세 정보 패널 표시/숨김
- **F12**: 로그 패널 표시/숨김

### 저장 위치
- **데이터베이스**: `glossary.db` → `settings` 테이블
- **설정 키**:
  - `splitter_{tab_name}_{splitter_name}` (예: `splitter_NLK_검색_main`)
  - `widget_visibility_{tab_name}` (예: `widget_visibility_NLK_검색`)

## 🚀 사용 방법

### 1. 모듈 임포트

```python
from layout_settings_manager import LayoutSettingsManager

# qt_main_app.py의 __init__에서
self.layout_settings_manager = LayoutSettingsManager(self.app_instance.db_manager)
```

### 2. 앱 시작 시 설정 복구

```python
def restore_layout_settings(self):
    """저장된 레이아웃 설정을 복구합니다."""
    # 탭 이름 리스트
    tab_names = []
    for i in range(self.tab_widget.count()):
        tab_names.append(self.tab_widget.tabText(i))

    # 기본 설정
    default_splitters = {tab_name: {"main": [700, 300]} for tab_name in tab_names}
    default_widgets = {
        tab_name: {
            "find_area": True,
            "detail_panel": True,
            "log_panel": True
        }
        for tab_name in tab_names
    }

    # 설정 복구
    splitter_configs, widget_configs = self.layout_settings_manager.load_all_layout_settings(
        tab_names, default_splitters, default_widgets
    )

    # Splitter 크기 적용
    if hasattr(self, "main_splitter"):
        sizes = splitter_configs.get(tab_names[0], {}).get("main", [700, 300])
        self.main_splitter.setSizes(sizes)
```

### 3. 앱 종료 시 설정 저장

```python
def save_layout_settings(self):
    """현재 레이아웃 설정을 저장합니다."""
    # Splitter 크기 수집
    splitter_configs = {}
    if hasattr(self, "main_splitter"):
        sizes = self.main_splitter.sizes()
        for i in range(self.tab_widget.count()):
            tab_name = self.tab_widget.tabText(i)
            splitter_configs[tab_name] = {"main": sizes}

    # 위젯 표시/숨김 상태 수집
    widget_configs = {}
    for i in range(self.tab_widget.count()):
        tab_name = self.tab_widget.tabText(i)
        widget_configs[tab_name] = {
            "find_area": self.is_find_visible,
            "detail_panel": self.is_detail_visible,
            "log_panel": self.is_log_visible
        }

    # 저장
    self.layout_settings_manager.save_all_layout_settings(splitter_configs, widget_configs)

def closeEvent(self, event):
    """앱 종료 시"""
    self.save_layout_settings()
    event.accept()
```

## 📖 API 상세 설명

### LayoutSettingsManager 클래스

#### QSplitter 관련 메서드

```python
# 단일 splitter 저장
save_splitter_sizes(tab_name, splitter_name, sizes)
# 예: save_splitter_sizes("NLK 검색", "main", [700, 300])

# 단일 splitter 복구
sizes = load_splitter_sizes(tab_name, splitter_name, default_sizes)
# 예: sizes = load_splitter_sizes("NLK 검색", "main", [700, 300])

# 모든 splitter 한 번에 저장
save_all_splitter_sizes(splitter_configs)
# 예: save_all_splitter_sizes({
#     "NLK 검색": {"main": [700, 300], "detail": [500, 200]},
#     "Dewey 분류": {"main": [600, 400]}
# })
```

#### 위젯 표시/숨김 관련 메서드

```python
# 단일 탭의 위젯 설정 저장
save_widget_visibility(tab_name, widget_configs)
# 예: save_widget_visibility("NLK 검색", {
#     "find_area": True,
#     "detail_panel": False,
#     "log_panel": True
# })

# 단일 탭의 위젯 설정 복구
config = load_widget_visibility(tab_name, default_config)

# 모든 탭의 위젯 설정 한 번에 저장
save_all_widget_visibility(all_configs)
# 예: save_all_widget_visibility({
#     "NLK 검색": {"find_area": True, ...},
#     "Dewey 분류": {"find_area": False, ...}
# })
```

#### 통합 메서드

```python
# 모든 설정 한 번에 저장 (앱 종료 시)
save_all_layout_settings(splitter_configs, widget_configs)

# 모든 설정 한 번에 복구 (앱 시작 시)
splitter_configs, widget_configs = load_all_layout_settings(
    tab_names,
    default_splitters,
    default_widgets
)

# 설정 초기화
clear_layout_settings(tab_name)  # 특정 탭만 초기화
clear_layout_settings()          # 모든 설정 초기화
```

## 🔧 통합 단계별 가이드

### 단계 1: qt_main_app.py 수정

```python
class MainApplicationWindow(QMainWindow):
    def __init__(self, app_instance):
        super().__init__()
        self.app_instance = app_instance
        self.setup_ui()

        # ✅ [추가] 레이아웃 설정 관리자 초기화
        from layout_settings_manager import LayoutSettingsManager
        self.layout_settings_manager = LayoutSettingsManager(self.app_instance.db_manager)

        # ✅ [추가] 저장된 레이아웃 설정 복구
        self.restore_layout_settings()
```

### 단계 2: 상태 추적 변수 추가

```python
def __init__(self, app_instance):
    ...
    # 위젯 표시/숨김 상태 추적 (기존 코드)
    self.is_detail_visible = True
    self.is_log_visible = True
    # ✅ [추가] Find 영역 상태 추적
    self.is_find_visible = True
```

### 단계 3: F7-F12 토글 메서드에서 상태 업데이트

```python
def toggle_find_area_visibility(self):
    if hasattr(self, "find_area_container"):
        is_visible = self.find_area_container.isVisible()
        self.find_area_container.setVisible(not is_visible)
        # ✅ [추가] 상태 저장
        self.is_find_visible = not is_visible
```

### 단계 4: closeEvent에 저장 로직 추가

```python
def closeEvent(self, event):
    """앱 종료 시"""
    try:
        # ✅ [추가] 레이아웃 설정 저장
        self.save_layout_settings()

        # 기존 종료 로직...
        ...

        event.accept()
    except Exception as e:
        self.app_instance.log_message(f"❌ 앱 종료 오류: {e}", "ERROR")
        event.accept()
```

## 📊 데이터베이스 저장 형식

### settings 테이블

| key | value | description |
|-----|-------|-------------|
| `splitter_NLK_검색_main` | `[700, 300]` | NLK 검색 탭의 메인 스플리터 크기 |
| `widget_visibility_NLK_검색` | `{"find_area": true, "detail_panel": false, ...}` | NLK 검색 탭의 위젯 표시/숨김 |

## 🎯 실행 흐름

```
앱 시작
  ↓
MainApplicationWindow.__init__()
  ↓
setup_ui() (기본 레이아웃 생성)
  ↓
restore_layout_settings() (✅ 저장된 설정 복구)
  ├─ load_all_layout_settings() 호출
  ├─ splitter 크기 적용
  └─ 위젯 표시/숨김 상태 적용
  ↓
사용자가 레이아웃 조정 (F7-F12, splitter 드래그 등)
  ↓
앱 종료 (closeEvent 발생)
  ↓
save_layout_settings() (✅ 현재 설정 저장)
  ├─ splitter 크기 수집
  ├─ 위젯 상태 수집
  └─ 데이터베이스에 저장
  ↓
앱 종료 완료
```

## ⚠️ 주의사항

1. **상태 변수 추적**: F7-F12 토글 메서드에서 상태 변수를 업데이트해야 함
2. **기본값 설정**: 첫 실행 시 저장된 설정이 없으면 기본값이 사용됨
3. **탭별 설정**: 각 탭마다 독립적인 설정이 저장됨
4. **대소문자 구분**: 탭 이름의 대소문자가 정확히 일치해야 함

## 🔍 디버깅

### 저장된 설정 확인

```python
# SQLite에서 직접 확인
sqlite3 glossary.db "SELECT * FROM settings WHERE key LIKE 'splitter_%' OR key LIKE 'widget_visibility_%';"
```

### 로그 메시지

```python
# 저장 시 로그
✅ Splitter 설정 저장: splitter_NLK_검색_main = [700, 300]
✅ 위젯 표시/숨김 설정 저장: widget_visibility_NLK_검색
✅ 모든 레이아웃 설정 저장 완료

# 복구 시 로그
✅ Splitter 설정 복구: splitter_NLK_검색_main = [700, 300]
✅ 위젯 표시/숨김 설정 복구: widget_visibility_NLK_검색
✅ 모든 레이아웃 설정 복구 완료
```

## 📝 예제 코드

자세한 통합 예제는 `layout_integration_example.py`를 참고하세요.

## 🤝 기여

이 모듈의 개선 사항이 있으면 알려주세요!
