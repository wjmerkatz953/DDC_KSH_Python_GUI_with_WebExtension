# 📚 Python GUI DDC·KSH Search App  
**통합 분류검색 GUI 애플리케이션 (PySide6 기반)**

이 프로젝트는 KDC/DDC/KSH 등 주요 분류체계를 한 화면에서 비교·검증하기 위한  
**라이브러리 정보학 기반 연구용 GUI 도구**입니다.  
공공도서관, 대학도서관, 또는 분류/주제분석 교육을 위한 실습 환경을 목표로 설계되었습니다.

---

## 🚀 주요 기능

- **다중 SRU 기반 검색**
  - LC (Library of Congress), NDL, BNF, DNB 등 해외 도서관 API 연동  
  - KSH, KDC, DDC 통합 탐색 및 비교 조회
- **자동 필드 파싱**
  - MARC, MODS, DC 등 다양한 메타데이터 자동 정규화
- **Dewey 캐시 / 로컬 매핑 DB**
  - `dewey_cache.db`, `kdc_ddc_mapping.db`를 활용한 오프라인 검색 속도 향상
- **Gemini 기반 DDC 계층 검증 시스템**
  - AI 기반 계층적 주제어 추출 및 분류번호 의미 일치 검증
- **PySide6 기반 GUI**
  - QTabWidget으로 구성된 탭 구조 (NLK, NDL, LC, KAC 등)
  - TableView + Context Menu + TextBrowser 연동
  - 자연 정렬, 실시간 필터링, DB 결과 표시

---

## 🧩 프로젝트 구조

📦 python-gui-DDC-KSH-search-app
┣ 📂 Tabs/ # LC, NDL, KAC 등 각 검색 탭 모듈
┣ 📂 Database/ # SQLite DB 파일 (dewey_cache, glossary 등)
┣ 📂 Utils/ # 파서 및 텍스트 처리 유틸리티
┣ 📜 main_app.py # 앱 실행 진입점
┣ 📜 database_manager.py # DB 연결 및 캐시 관리
┣ 📜 context_menus.py # 테이블/텍스트 컨텍스트 메뉴 정의
┣ 📜 view_displays.py # View 출력 관련 모듈
┗ 📜 Status of the Project.md # 진행 현황 로그


---

## ⚙️ 실행 방법

### 1. 가상환경 생성 및 활성화
```bash
python -m venv venv
venv\Scripts\activate

2. 필수 라이브러리 설치

pip install -r requirements.txt

3. 실행

python main_app.py

💾 데이터베이스 구성
파일명	설명
dewey_cache.db	DDC 계층 구조 및 라벨 캐시
kdc_ddc_mapping.db	KDC ↔ DDC 매핑 테이블
glossary.db	용어집 및 다국어 번역 캐시
nlk_concepts.sqlite  KSH 개념 인덱싱 및 의미 유사도 계산
🔬 연구적 활용

이 앱은 다음과 같은 연구/교육 목적에 활용될 수 있습니다.

    공공도서관 분류정확도 분석

    AI 기반 주제 자동분류 연구 (Gemini API 연계)

    KDC-DDC-KSH 통합 매핑 검증

    도서관 연계형 분류정책 개발 실험 환경

📅 개발 기록

    진행 상황은 Status of the Project.md

    에서 확인 가능합니다.

🧠 기술 스택

    Python 3.11+

    PySide6

    SQLite3 (FTS5)

    requests / pandas / logging

    Gemini API (for semantic validation)

📜 라이선스

이 프로젝트는 개인 연구 및 교육 목적으로 공개된 것으로,
별도의 상업적 이용은 금지됩니다.
(저작권 © 2025 Alex Kim)
💬 문의 / 협업

    GitHub: wjmerkatz953

    Email: (비공개)

    연구 키워드: 도서관정보학, 분류체계, 유아문해력, AI 기반 분류연구

    ✨ "Library classification meets AI."
    — Alex Kim
