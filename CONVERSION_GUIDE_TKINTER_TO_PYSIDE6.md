# tkinter/CustomTkinter → PySide6 컨버팅 가이드

**작성일**: 2025-10-02
**작성자**: Claude Code
**목적**: tkinter 기반 코드를 PySide6로 안전하게 컨버팅하기 위한 체크리스트

---

## 📋 목차

1. [오류 사례 분석](#1-오류-사례-분석)
2. [핵심 원칙](#2-핵심-원칙)
3. [단계별 체크리스트](#3-단계별-체크리스트)
4. [필수 검증 항목](#4-필수-검증-항목)
5. [프롬프트 템플릿](#5-프롬프트-템플릿)

---

## 1. 오류 사례 분석

### 🐛 **실제 발생한 오류**

```python
TypeError: 'PySide6.QtWidgets.QWidget.__init__' called with wrong argument types:
  PySide6.QtWidgets.QWidget.__init__(IntegratedSearchApp)
```

### 🔍 **근본 원인**

#### **문제 코드** (qt_TabView_Dewey.py)
```python
class QtDeweySearchTab(QWidget):
    def __init__(self, app_instance, parent=None):  # ❌ 잘못된 시그니처
        super().__init__(parent)
        self.app_instance = app_instance
```

#### **호출 코드** (qt_main_app.py)
```python
# 모든 탭을 동일한 방식으로 생성
tab_instance = TabClass(config, app_instance)  # config가 첫 번째 인자!
```

#### **다른 탭들의 올바른 패턴**
```python
# qt_TabView_KSH_Local.py
class QtKSHLocalSearchTab(BaseSearchTab):
    def __init__(self, config, app_instance):  # ✅ 올바른 시그니처
        super().__init__(config, app_instance)

# qt_TabView_NLK.py
class QtNLKSearchTab(BaseSearchTab):
    def __init__(self, config, app_instance):  # ✅ 올바른 시그니처
        super().__init__(config, app_instance)
```

### 💥 **왜 발생했는가?**

1. **일관성 부재**:
   - Agent가 Tab_Dewey.py를 독립적으로 컨버팅
   - 프로젝트의 기존 Qt 탭 구조를 참조하지 않음
   - 결과: 다른 탭들과 다른 `__init__` 시그니처

2. **호출 규칙 미확인**:
   - qt_main_app.py의 탭 생성 코드 패턴 미확인
   - 기존 프로젝트 아키텍처 무시

3. **검증 부재**:
   - 컨버팅 후 실제 실행 테스트 없음
   - import/instantiation 오류 미발견

---

## 2. 핵심 원칙

### ✅ **프로젝트 아키텍처 우선**

> **"기존 PySide6 코드의 패턴을 따라야 한다"**

tkinter에서 PySide6로 컨버팅할 때:

1. **먼저 유사한 기존 Qt 탭 파일을 찾아 패턴 분석**
2. **호출하는 코드(qt_main_app.py 등)의 규칙 확인**
3. **기존 패턴과 100% 일치하도록 컨버팅**

### 🔒 **필수 체크 항목**

#### **A. 클래스 시그니처**
```python
# ❌ 독자적 판단 금지
class NewTab(QWidget):
    def __init__(self, some_custom_args):
        pass

# ✅ 기존 탭과 동일한 시그니처 필수
class NewTab(BaseSearchTab):  # or QWidget
    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)
```

#### **B. 상속 구조**
```python
# 프로젝트에 BaseSearchTab이 있다면:
class NewTab(BaseSearchTab):  # ✅ 상속 활용
    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)
        # BaseSearchTab이 표준 UI/기능 제공

# BaseSearchTab이 불필요하다면:
class NewTab(QWidget):  # ✅ 직접 상속
    def __init__(self, config, app_instance, parent=None):
        super().__init__(parent)
        self.config = config
        self.app_instance = app_instance
```

#### **C. 생성 방식**
```python
# qt_main_app.py 확인 필수!

# 패턴 1: 딕셔너리 기반 동적 생성
for key, config in TAB_CONFIGURATIONS.items():
    TabClass = tab_class_map[key]
    tab_instance = TabClass(config, app_instance)  # ← 이 패턴!

# 패턴 2: 직접 생성
tab = QtDeweySearchTab(config, app_instance)  # ← 이 패턴!
```

---

## 3. 단계별 체크리스트

### 📝 **컨버팅 전 준비 (Pre-Conversion)**

- [ ] **1. 기존 Qt 탭 파일 3개 이상 확인**
  ```bash
  # 패턴 분석용 파일 찾기
  ls qt_TabView_*.py | head -5

  # 확인할 항목:
  # - __init__ 시그니처
  # - 상속 클래스 (BaseSearchTab vs QWidget)
  # - super().__init__() 호출 방식
  ```

- [ ] **2. qt_main_app.py의 탭 생성 코드 확인**
  ```python
  # setup_tabs() 메서드 찾기
  # TabClass(?, ?) ← 이 인자 순서 확인!
  ```

- [ ] **3. BaseSearchTab/BaseTab 존재 여부 확인**
  ```bash
  grep -n "class BaseSearchTab" qt_base_tab.py
  grep -n "class BaseTab" qt_base_tab.py
  ```

- [ ] **4. 프로젝트 표준 패턴 문서화**
  ```
  현재 프로젝트의 탭 클래스 표준:
  - 시그니처: __init__(self, config, app_instance)
  - 상속: BaseSearchTab or QWidget
  - 생성: TabClass(config, app_instance)
  ```

---

### 🔧 **컨버팅 중 (During Conversion)**

- [ ] **5. 클래스 정의 시 기존 패턴 복사**
  ```python
  # ✅ GOOD: 기존 탭에서 복사
  class QtDeweySearchTab(BaseSearchTab):  # ← 다른 탭과 동일
      def __init__(self, config, app_instance):  # ← 다른 탭과 동일
          super().__init__(config, app_instance)

  # ❌ BAD: 독자적 판단
  class QtDeweySearchTab(QWidget):
      def __init__(self, app_instance, parent=None):  # ← 다름!
          super().__init__(parent)
  ```

- [ ] **6. Public Entry Point 일관성 유지**
  ```python
  # 모든 탭이 동일한 패턴이어야 함
  def setup_xxx_tab_ui(config, app_instance, parent=None):
      return QtXXXTab(config, app_instance, parent)
  ```

- [ ] **7. 필수 속성 저장**
  ```python
  def __init__(self, config, app_instance):
      self.config = config  # ✅ 필수
      self.app_instance = app_instance  # ✅ 필수
  ```

---

### ✅ **컨버팅 후 검증 (Post-Conversion)**

- [ ] **8. Import 테스트**
  ```python
  # 터미널에서 실행
  python -c "from qt_TabView_Dewey import QtDeweySearchTab; print('OK')"
  ```

- [ ] **9. Instantiation 테스트**
  ```python
  # 실제 생성 테스트
  python -c "
  from qt_TabView_Dewey import QtDeweySearchTab
  from PySide6.QtWidgets import QApplication
  import sys

  app = QApplication(sys.argv)
  config = {'tab_name': 'Test'}

  class MockApp:
      def __init__(self):
          self.db_manager = None

  mock_app = MockApp()
  tab = QtDeweySearchTab(config, mock_app)
  print('✅ Instantiation OK')
  "
  ```

- [ ] **10. 전체 애플리케이션 실행**
  ```bash
  python qt_main_app.py
  # 오류 없이 탭이 로드되는지 확인
  ```

- [ ] **11. 타입 힌트 검증** (선택사항)
  ```python
  from typing import Dict, Any

  def __init__(self, config: Dict[str, Any], app_instance: Any) -> None:
      # 타입 힌트로 명확성 향상
  ```

---

## 4. 필수 검증 항목

### 🎯 **시그니처 일치 검증**

#### **체크 스크립트**
```bash
# 모든 Qt 탭의 __init__ 시그니처 추출
grep -A 1 "class Qt.*SearchTab" qt_TabView_*.py | grep "def __init__"

# 예상 출력 (모두 동일해야 함):
# qt_TabView_Dewey.py:    def __init__(self, config, app_instance):
# qt_TabView_KSH_Local.py:    def __init__(self, config, app_instance):
# qt_TabView_NLK.py:    def __init__(self, config, app_instance):
```

#### **불일치 발견 시**
```python
# ❌ 발견된 불일치
qt_TabView_Dewey.py:    def __init__(self, app_instance, parent=None):

# ✅ 즉시 수정
qt_TabView_Dewey.py:    def __init__(self, config, app_instance):
```

---

### 🧪 **실행 시뮬레이션**

```python
# test_tab_instantiation.py (검증용 스크립트)
"""
모든 탭 클래스의 instantiation을 테스트합니다.
"""
from PySide6.QtWidgets import QApplication
import sys

# 모든 탭 클래스 import
from qt_TabView_Dewey import QtDeweySearchTab
from qt_TabView_KSH_Local import QtKSHLocalSearchTab
# ... 기타 탭들

class MockApp:
    def __init__(self):
        self.db_manager = None
        # 필요한 다른 속성들...

def test_all_tabs():
    app = QApplication(sys.argv)
    mock_app = MockApp()
    config = {"tab_name": "Test"}

    # 모든 탭 클래스 테스트
    tabs_to_test = [
        ("Dewey", QtDeweySearchTab),
        ("KSH Local", QtKSHLocalSearchTab),
        # ... 기타 탭들
    ]

    for name, TabClass in tabs_to_test:
        try:
            tab = TabClass(config, mock_app)
            print(f"✅ {name}: OK")
        except Exception as e:
            print(f"❌ {name}: FAIL - {e}")

if __name__ == "__main__":
    test_all_tabs()
```

---

## 5. 프롬프트 템플릿

### 📋 **컨버팅 요청 시 사용할 프롬프트**

```markdown
**작업**: Tab_XXX.py 파일을 PySide6로 완전히 컨버팅하여 qt_TabView_XXX.py 파일로 작성

**필수 사항**:

1. **기존 Qt 탭 패턴 분석 먼저 수행**:
   - qt_TabView_KSH_Local.py, qt_TabView_NLK.py 등 최소 3개 파일 확인
   - 클래스 시그니처, 상속 구조, __init__ 패턴 파악
   - BaseSearchTab 사용 여부 확인

2. **qt_main_app.py의 탭 생성 방식 확인**:
   - setup_tabs() 메서드 분석
   - TabClass(?, ?) 인자 순서 확인
   - TAB_CONFIGURATIONS 구조 파악

3. **컨버팅 규칙**:
   - 클래스 시그니처: 기존 Qt 탭과 **100% 동일**하게
   - __init__ 메서드: `def __init__(self, config, app_instance)` 패턴 사용
   - 상속: BaseSearchTab 또는 QWidget (기존 패턴 따름)
   - 모든 기능 누락 없이 변환

4. **검증 필수**:
   - 컨버팅 완료 후 import 테스트 코드 제공
   - 실제 instantiation 가능 여부 확인
   - 다른 탭들과 시그니처 일치 여부 검증

5. **출력 형식**:
   - 완전히 동작하는 qt_TabView_XXX.py 파일
   - 파일 상단에 버전 및 수정 내역 주석
   - 각 주요 섹션에 원본 파일 라인 번호 참조

**참고 파일**:
- 원본: Tab_XXX.py
- 패턴 참조: qt_TabView_KSH_Local.py, qt_TabView_NLK.py
- 호출 코드: qt_main_app.py (setup_tabs 메서드)
```

---

### 🎯 **Agent에게 추가로 요청할 사항**

```markdown
**검증 요청**:

컨버팅 완료 후 다음을 확인해주세요:

1. **시그니처 일치 검증**:
   ```bash
   grep -A 1 "def __init__" qt_TabView_*.py | grep -v "^--$"
   ```
   모든 탭이 동일한 패턴인지 확인

2. **Import 테스트**:
   ```python
   python -c "from qt_TabView_XXX import QtXXXSearchTab; print('OK')"
   ```

3. **Mock Instantiation**:
   ```python
   # 실제 생성 가능한지 테스트
   config = {"tab_name": "Test"}
   mock_app = type('MockApp', (), {'db_manager': None})()
   tab = QtXXXSearchTab(config, mock_app)
   ```

4. **다른 탭과 비교**:
   - qt_TabView_KSH_Local.py의 __init__과 비교
   - 인자 순서, 타입, 개수 동일 여부 확인
```

---

## 6. 트러블슈팅

### ❓ **자주 발생하는 문제**

#### **문제 1**: TypeError - wrong argument types
```python
TypeError: 'QWidget.__init__' called with wrong argument types
```

**원인**: `__init__` 시그니처가 다른 탭들과 다름

**해결**:
```python
# 모든 Qt 탭의 __init__ 확인
grep -B 2 "def __init__" qt_TabView_*.py

# 동일한 패턴으로 수정
def __init__(self, config, app_instance):
    super().__init__()  # or super().__init__(config, app_instance)
```

---

#### **문제 2**: AttributeError - 'config' has no attribute
```python
AttributeError: 'IntegratedSearchApp' object has no attribute 'get'
```

**원인**: 인자 순서가 바뀌어서 `app_instance`가 `config` 위치로 전달됨

**해결**:
```python
# 잘못된 순서
def __init__(self, app_instance, config):  # ❌

# 올바른 순서 (qt_main_app.py와 일치)
def __init__(self, config, app_instance):  # ✅
```

---

#### **문제 3**: BaseSearchTab을 써야 하는데 QWidget 직접 상속
```python
class QtNewTab(QWidget):  # ❌ 표준 기능 누락
```

**해결**:
```python
# qt_base_tab.py 확인
grep -n "class BaseSearchTab" qt_base_tab.py

# BaseSearchTab 사용
class QtNewTab(BaseSearchTab):  # ✅ 표준 기능 자동 포함
    def __init__(self, config, app_instance):
        super().__init__(config, app_instance)
```

---

## 7. 베스트 프랙티스

### 🌟 **컨버팅 전 "3+3 규칙"**

#### **3개 파일 확인**
1. 기존 Qt 탭 3개 (패턴 분석)
2. qt_main_app.py (호출 방식)
3. qt_base_tab.py (상속 구조)

#### **3가지 검증**
1. Import 테스트
2. Instantiation 테스트
3. 실제 실행 테스트

---

### 📚 **참고 체크리스트 (요약)**

```
□ 기존 Qt 탭 3개 이상 분석 완료
□ qt_main_app.py의 탭 생성 패턴 확인
□ BaseSearchTab 사용 여부 확인
□ __init__ 시그니처 동일 (config, app_instance)
□ super().__init__() 올바른 인자 전달
□ Public entry point 함수 동일 패턴
□ Import 테스트 통과
□ Mock instantiation 테스트 통과
□ 전체 앱 실행 테스트 통과
□ 다른 탭들과 시그니처 비교 완료
```

---

## 8. 결론

### 💡 **핵심 교훈**

> **"독립적으로 컨버팅하지 말고, 프로젝트의 기존 패턴을 먼저 파악하라"**

1. **일관성 > 독창성**: 독자적 판단보다 기존 패턴 준수
2. **검증 필수**: 컨버팅 후 즉시 테스트
3. **문서화**: 프로젝트 표준 패턴을 문서로 유지

### 🎯 **이 가이드의 목적**

- ✅ 동일한 오류 재발 방지
- ✅ 컨버팅 품질 향상
- ✅ Agent/개발자 간 소통 명확화
- ✅ 유지보수 용이성 향상

---

**문서 버전**: 1.0.0
**최종 수정**: 2025-10-02
**작성자**: Claude Code
**라이선스**: 내부 사용 전용
