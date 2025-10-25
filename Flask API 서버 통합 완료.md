# Flask API 서버 통합 완료

## 개요
브라우저 확장 프로그램(Extension)에 검색 기능을 제공하기 위해 Flask API 서버를 PySide6 애플리케이션에 통합했습니다.

## 생성된 파일

### 1. extension_api_server.py
Flask API 서버를 관리하는 독립 모듈

#### 주요 클래스: ExtensionAPIServer

**초기화**
```python
api_server = ExtensionAPIServer(app_instance, db_manager)
api_server.start_server(host="127.0.0.1", port=5000)
```

**제공 API 엔드포인트**

1. **KSH 검색 API**
   - URL: `GET /api/ksh/search?q={검색어}`
   - 설명: KSH 주제명을 통합 검색
   - 응답: JSON 배열 (최대 20개 결과)
   ```json
   [
     {
       "subject": "▼a한국 문학▼0KSH123▲",
       "display": "한국 문학",
       "category": "문학",
       "type": "concept"
     }
   ]
   ```

2. **DDC 검색 API**
   - URL: `GET /api/dewey/search?ddc={DDC코드}`
   - 설명: 듀이십진분류법 정보 조회
   - 응답: JSON 객체 (계층구조 포함)
   ```json
   {
     "main": {
       "notation": "810",
       "label": "미국 문학",
       "definition": "..."
     },
     "broader": [...],
     "narrower": [...],
     "related": [...]
   }
   ```

3. **헬스 체크 API**
   - URL: `GET /api/health`
   - 설명: 서버 상태 확인
   - 응답:
   ```json
   {
     "status": "healthy",
     "app": "MetaTetus Extension API",
     "version": "1.0.0"
   }
   ```

#### 헬퍼 메서드

- `_extract_display_text(marc_text)`: MARC 형식에서 표시용 텍스트 추출
- `_extract_dewey_label(item)`: Dewey 아이템에서 레이블 추출
- `_log(message, level)`: 로그 메시지 기록

## 수정된 파일

### qt_main_app.py

#### 1. IntegratedSearchApp.__init__()
```python
def __init__(self):
    self.db_manager = None
    self.main_window = None
    self.api_server = None  # ✅ Flask API 서버 인스턴스 추가
    ...
```

#### 2. start_extension_api_server() 메서드 추가
```python
def start_extension_api_server(self):
    """브라우저 확장 프로그램용 Flask API 서버를 시작합니다."""
    try:
        from extension_api_server import ExtensionAPIServer

        # API 서버 인스턴스 생성 및 시작
        self.api_server = ExtensionAPIServer(self, self.db_manager)
        success = self.api_server.start_server(host="127.0.0.1", port=5000)
        ...
```

#### 3. initialize_database() 수정
데이터베이스 초기화 후 자동으로 API 서버 시작:
```python
self.logger.info("데이터베이스 초기화 완료")
self.start_extension_api_server()  # ✅ 자동 시작
```

#### 4. MainApplicationWindow.closeEvent() 수정
앱 종료 시 API 서버도 정리:
```python
# 3. Flask API 서버 종료
if hasattr(self.app_instance, "api_server") and self.app_instance.api_server:
    self.app_instance.log_message("🛑 API 서버 종료 중...", "INFO")
    self.app_instance.api_server.stop_server()
```

## CTk vs PySide6 차이점

### CTk 버전의 특징
- `self.after()` 메서드로 Tkinter 이벤트 루프 제어
- `trigger()` 콜백 직접 호출
- `event_generate()` 메서드로 이벤트 생성

### PySide6 버전의 특징
- **완전히 독립된 모듈**: `extension_api_server.py`로 분리
- **데몬 스레드**: Flask 서버가 백그라운드에서 자동 실행
- **자동 시작/종료**: 앱 시작 시 자동 시작, 종료 시 자동 정리
- **로그 통합**: 메인 앱의 로그 시스템과 통합

## 사용 방법

### 1. 필수 패키지 설치
```bash
pip install flask flask-cors
```

### 2. 애플리케이션 실행
```bash
python qt_main_app.py
```

### 3. API 테스트
```bash
# KSH 검색
curl "http://localhost:5000/api/ksh/search?q=한국"

# DDC 검색
curl "http://localhost:5000/api/dewey/search?ddc=810"

# 헬스 체크
curl "http://localhost:5000/api/health"
```

### 4. 브라우저 확장 프로그램 연동
확장 프로그램의 JavaScript에서 다음과 같이 호출:
```javascript
// KSH 검색
fetch('http://localhost:5000/api/ksh/search?q=한국')
  .then(response => response.json())
  .then(data => console.log(data));

// DDC 검색
fetch('http://localhost:5000/api/dewey/search?ddc=810')
  .then(response => response.json())
  .then(data => console.log(data));
```

## 장점

1. **모듈화**: API 서버가 독립된 파일로 분리되어 유지보수 용이
2. **자동화**: 수동으로 서버를 시작/종료할 필요 없음
3. **안정성**: 데몬 스레드로 실행되어 메인 앱과 독립적
4. **로깅**: 모든 API 요청/응답이 메인 앱의 로그에 기록됨
5. **CORS 지원**: 브라우저 확장 프로그램에서 자유롭게 접근 가능

## 주의사항

1. **포트 충돌**: 5000번 포트가 이미 사용 중이면 시작 실패
2. **Flask 미설치**: Flask가 없으면 경고 메시지만 표시하고 계속 실행
3. **데이터베이스 필수**: db_manager가 None이면 API 서버 시작 안 됨
4. **보안**: 현재는 localhost만 허용 (외부 접근 불가)

## 다음 단계

1. Extension 파일들(background.js, content.js, manifest.json) 업데이트
2. API 응답 형식에 맞춰 확장 프로그램 로직 수정
3. 필요시 추가 엔드포인트 구현 (예: 검색 히스토리, 즐겨찾기 등)

## 파일 위치

- 신규: `e:\Python\extension_api_server.py`
- 수정: `e:\Python\qt_main_app.py`
- 문서: `e:\Python\Flask API 서버 통합 완료.md`
