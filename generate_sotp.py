#!/usr/bin/env python3
# generate_sotp.py v2.1 (개선 버전)
# AI가 실행 → 최신 SOTP 문서 자동 생성
# 사용법: python generate_sotp.py > SOTP.md

import os
import json
import sqlite3
import datetime
import re  # ✅ [추가] Git 로그 파싱을 위해 re 모듈 임포트
from pathlib import Path
from collections import defaultdict

# -------------------------------
# 1. 설정
# -------------------------------
ROOT = Path(__file__).parent
OUTPUT = ROOT / "SOTP.md"
CHANGELOG = ROOT / "CHANGELOG.md"
DB_NLK = ROOT / "nlk_concepts.sqlite"
DB_KDC = ROOT / "kdc_ddc_mapping.db"
DB_DEWEY = ROOT / "dewey_cache.db"
DB_GLOSSARY = ROOT / "glossary.db"

# -------------------------------
# 2. 헬퍼 함수
# -------------------------------

# ===== BEFORE (수정 전: get_git_log) =====
# def get_git_log(limit=5):
#     try:
#         import subprocess
#         result = subprocess.run(
#             ["git", "log", f"-n{limit}", "--oneline", "--no-merges"],
#             capture_output=True, text=True, check=True
#         )
#         return [f"# {line.split(' ', 1)[0][:7]} {line.split(' ', 1)[1]}"
#                 for line in result.stdout.strip().splitlines()]
#     except:
#         return ["_git 로그 없음_"]


# ===== AFTER (수정 후: get_git_log) =====
def get_git_log(limit=5):
    """✅ [개선] 변경된 파일 목록(--name-status)을 포함하는 Git 로그를 가져옵니다."""
    try:
        import subprocess

        # --name-status 옵션 추가
        result = subprocess.run(
            ["git", "log", f"-n{limit}", "--oneline", "--name-status", "--no-merges"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        output_lines = []
        for line in result.stdout.strip().splitlines():
            if re.match(r"^[AMD]\t", line):  # M, A, D (Modified, Added, Deleted)
                # 파일 경로는 2-space 들여쓰기
                output_lines.append(f"  {line.strip()}")
            elif re.match(r"^[RC]\d+\t", line):  # R, C (Renamed, Copied)
                output_lines.append(f"  {line.strip()}")
            else:
                # 커밋 메시지 (앞에 개행 추가하여 그룹화)
                hash_msg = line.split(" ", 1)
                output_lines.append(f"\n# {hash_msg[0][:7]} {hash_msg[1]}")

        # 첫 줄의 불필요한 \n 제거
        if output_lines and output_lines[0].startswith("\n"):
            output_lines[0] = output_lines[0][1:]

        return output_lines
    except Exception as e:
        return [f"_git 로그 없음 ({e})_"]


# ===== BEFORE (수정 전: get_db_stats) =====
# def get_db_stats(db_path, table_query):
#     if not db_path.exists():
#         return "N/A", "N/A"
#     try:
#         conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
#         cur = conn.cursor()
#         cur.execute(table_query)
#         tables = len(cur.fetchall())
#         cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
#         indexes = len([row for row in cur.fetchall() if not row[0].startswith("sqlite_autoindex")])
#         conn.close()
#         return tables, indexes
#     except Exception as e:
#         return "ERR", f"ERR ({e})"


# ===== AFTER (수정 후: get_db_stats) =====
def get_db_stats(db_path, core_tables=[]):
    """✅ [개선] DB 파일 존재 여부와 핵심 테이블 존재 여부를 확인합니다."""
    if not db_path.exists():
        return "❌ `DB 파일 없음`"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        statuses = []
        for table in core_tables:
            cur.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';"
            )
            status_emoji = "✅" if cur.fetchone() else "❌"
            statuses.append(f"{status_emoji} `{table}`")
        conn.close()
        # 테이블 1~2개면 한 줄로, 그 이상이면 줄바꿈
        separator = " " if len(statuses) <= 2 else "<br>"
        return separator.join(statuses)
    except Exception as e:
        return f"⚠️ `ERR ({e})`"


def read_changelog():
    if not CHANGELOG.exists():
        return ["_CHANGELOG.md 없음_"]
    lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    entries = []
    current = None
    for line in lines:
        if line.startswith("### 20"):
            if current:
                entries.append(current)
            current = {"date": line[4:].strip(), "items": []}
        elif line.startswith("- ") and current:
            current["items"].append(line[2:].strip())
        if len(entries) >= 5:
            break
    if current:
        entries.append(current)
    return [
        f"### {e['date']}\n" + "\n".join([f"- {i}" for i in e["items"]])
        for e in entries
    ]


# -------------------------------
# 3. 데이터 수집
# -------------------------------
print("SOTP v2.1 (개선 버전) 자동 생성 중...")

# 3-1. 탭 목록
tabs = []
# Ensure the TABS attribute is correctly loaded from the qt_Tab_configs.py module
try:
    import importlib.util

    spec = importlib.util.spec_from_file_location("configs", ROOT / "qt_Tab_configs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tabs = [
        {
            "name": t.get("tab_name", "Unknown"),
            "file": t.get("file", "N/A"),
            "group": t.get("group", "기타"),
            "icon": t.get("icon", ""),
        }
        for t in getattr(mod, "TABS", [])
    ]
except Exception as e:
    tabs = [{"name": f"ERROR: {e}", "file": "", "group": "", "icon": ""}]

# -------------------
# 3-2. DB 상태 (✅ [개선] 핵심 테이블 위주로 변경)
# -------------------
nlk_status = get_db_stats(
    DB_NLK, ["concepts", "literal_props", "literal_props_fts", "uri_props"]
)
kdc_status = get_db_stats(DB_KDC, ["mapping_data", "mapping_data_fts"])
dewey_status = get_db_stats(DB_DEWEY, ["dewey_cache", "ddc_keyword_fts"])
glossary_status = get_db_stats(DB_GLOSSARY, ["settings", "glossary"])
# -------------------

# -------------------
# 3-3. 최근 변경 (✅ [개선] git_log 파싱 방식 변경)
# -------------------
changelog = read_changelog()
git_log_lines = get_git_log(5)  # This now returns formatted lines
# git_log_lines 리스트를 하나의 문자열로 결합
git_log_str = "\n".join(git_log_lines)
# changelog가 있으면 changelog를, 없으면 git_log를 사용
change_log_md = (
    "\n\n".join(changelog[:5]) if changelog else f"```bash\n{git_log_str}\n```"
)
# -------------------

# 3-4. 상태
status_emoji = "All Green"
timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# -------------------------------
# 4. 탭 그룹화
# -------------------------------
group_map = defaultdict(list)
for t in tabs:
    group_map[t["group"]].append(t)

# -------------------------------
# 5. Markdown 생성
# -------------------------------
md = f"""# SOTP – Status of the Project (자동 생성)
> **생성 시각**: {timestamp}
> **상태**: {status_emoji} **All Green** > **AI 전용 초고속 컨텍스트 문서** | 30초 파악 완료

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

## 2. 탭 요약 (총 {len(tabs)}개)

| 그룹 | 탭 | 파일 | 아이콘 |
|------|----|------|-------|
"""

# Adjust Markdown generation to fit within line limits
for group, items in sorted(group_map.items()):
    for i, t in enumerate(items):
        prefix = "└─" if i == len(items) - 1 else "├─"
        md += (
            f"| **{group}** | {prefix} `{t['name']}` | "
            f"`{t['file']}` | {t['icon']} |\n"
        )

md += f"""

---

## 3. DB 상태 (✅ [개선] 핵심 테이블 확인)

| DB | 핵심 테이블 상태 |
|----|------------------|
| `nlk_concepts.sqlite` | {nlk_status} |
| `kdc_ddc_mapping.db` | {kdc_status} |
| `dewey_cache.db` | {dewey_status} |
| `glossary.db` | {glossary_status} |

---

## 4. 최근 변경 (✅ [개선] 파일 변경 내역 포함)

{change_log_md}

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
├── nlk_biblio.sqlite (NLK 서지 7.1M건, FTS5)
├── kdc_ddc_mapping.db (KDC↔DDC)
├── dewey_cache.db (API 캐시)
├── glossary.db (UI 설정)
└── FAISS 벡터 인덱스 (임베딩 검색)
```

---

## 6. 브라우저 확장 프로그램 (Browser Extension)

### 구성 파일
| 파일 | 역할 |
|------|------|
| `manifest.json` | 확장 프로그램 메타데이터 (v6.5.6) |
| `background.js` | 백그라운드 서비스 워커, 메시지 중계 |
| `content.js` | KSH 패널 UI 및 MARC 650 필드 삽입 |
| `search-addon.js` | DDC/KSH 검색 패널, ISBN 조회 |
| `article-processor.js` | 정관사 처리, 090 청구기호 검색 |

### 주요 기능
- **KSH 패널**: MARC 650 필드 자동 삽입, 프리셋 관리, 082 필드 연동
- **검색 패널**: DDC/KSH 검색 (Flask API 연동), ISBN 서지정보 조회
- **정관사 처리**: 246 필드 정관사 제거 및 자동 변환
- **단축키**: `Ctrl+Shift+Q` (KSH 패널), `Ctrl+Shift+S` (검색 패널)

### Flask API 연동
```
extension_api_server.py (Flask, 포트 5000)
├── GET /api/dewey/search?ddc={{코드}}
└── GET /api/ksh/search?q={{쿼리}}
```

---

> **자동 생성 완료** | `generate_sotp.py` 실행
> **수정 금지** – 자동 갱신 전용
"""

# -------------------------------
# 6. 출력
# -------------------------------
OUTPUT.write_text(md, encoding="utf-8")
print(f"생성 완료 → {OUTPUT}")
print("\n미리보기:")
print("\n".join(md.splitlines()[:20]))
