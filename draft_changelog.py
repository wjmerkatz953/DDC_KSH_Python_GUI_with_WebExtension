#!/usr/bin/env python3
# draft_changelog.py
# 설명: CHANGELOG.md 작성을 돕는 비서 스크립트.
# 사용법: python draft_changelog.py
#
# 1. CHANGELOG.md에서 마지막 작성일을 읽음
# 2. 그 이후의 git log와 변경된 파일 목록을 가져옴
# 3. 고품질 템플릿 초안을 생성하여 콘솔에 출력
# 4. 사용자는 이 템플릿을 복사하여 CHANGELOG.md에 붙여넣고 세부 내용을 채움

import re
import subprocess
import datetime
from pathlib import Path
from collections import defaultdict

# --- 설정 ---
CHANGELOG_FILE = Path(__file__).parent / "CHANGELOG.md"
# ---

def get_last_changelog_date():
    """CHANGELOG.md 파일에서 가장 최근 날짜를 찾습니다. (예: 2025-10-28)"""
    if not CHANGELOG_FILE.exists():
        print(f"경고: {CHANGELOG_FILE} 파일을 찾을 수 없습니다. 7일 전 내역부터 조회합니다.")
        return datetime.date.today() - datetime.timedelta(days=7)
    
    try:
        content = CHANGELOG_FILE.read_text(encoding="utf-8")
        # 정규식으로 '### 2025-10-28' 형식의 날짜를 찾음
        dates = re.findall(r"###\s*(\d{4}-\d{2}-\d{2})", content)
        if dates:
            last_date_str = max(dates)
            return datetime.date.fromisoformat(last_date_str)
    except Exception as e:
        print(f"오류: CHANGELOG.md 파싱 실패 - {e}")
    
    # 날짜를 못 찾으면 기본값으로 7일 전 반환
    return datetime.date.today() - datetime.timedelta(days=7)

def get_git_log_since(since_date: datetime.date):
    """지정된 날짜 이후의 git log를 (커밋 메시지, 파일 목록) 형태로 파싱합니다."""
    
    # 마지막 로그 날짜의 다음 날부터 조회
    query_date = since_date + datetime.timedelta(days=1)
    
    try:
        cmd = [
            "git", "log",
            f"--since={query_date.isoformat()}",
            "--oneline",
            "--name-status",
            "--no-merges"
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, encoding="utf-8"
        )
        
        # 로그 파싱 (커밋별로 파일 그룹화)
        commits_dict = defaultdict(list)
        current_commit_msg = None
        
        for line in result.stdout.strip().splitlines():
            # M, A, D, R100, C050 등 파일 상태로 시작하는지 확인
            if re.match(r"^[AMDCR]\d*\t", line.split('\t', 1)[0]):
                if current_commit_msg:
                    parts = line.split('\t')
                    # R (Rename) 또는 C (Copy) 처리
                    if (parts[0].startswith('R') or parts[0].startswith('C')) and len(parts) == 3:
                        commits_dict[current_commit_msg].append(f"`{parts[2]}` (from `{parts[1]}`)")
                    else:
                        # M, A, D 처리
                        commits_dict[current_commit_msg].append(f"`{parts[1]}`")
            else:
                # 커밋 메시지 라인 (해시 제외)
                current_commit_msg = line.split(' ', 1)[1]
        
        return commits_dict

    except FileNotFoundError:
        print("오류: 'git' 명령을 찾을 수 없습니다. Git이 설치되어 있고 PATH에 등록되어 있는지 확인하세요.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"오류: git log 실행 실패 - {e.stderr}")
        return None
    except Exception as e:
        print(f"오류: git log 파싱 중 예외 발생 - {e}")
        return None

def generate_draft(commits_dict):
    """파싱된 커밋 딕셔너리를 기반으로 Markdown 초안을 생성합니다."""
    
    if not commits_dict:
        return "✅ 최신 `CHANGELOG.md` 이후 새로운 커밋이 없습니다. (업데이트 불필요)"
        
    today = datetime.date.today().isoformat()
    draft = []
    
    draft.append(f"### {today} (세션 1 - [여기에 세션 제목 입력])")
    draft.append("")

    for i, (commit_msg, files) in enumerate(commits_dict.items(), 1):
        # 커밋 메시지에서 feat/fix/refactor 등 태그 제거 (선택 사항)
        clean_msg = re.sub(r"^\w+(\(.+\))?:\s*", "", commit_msg)
        
        draft.append(f"- **[수정 내역 {i}: {clean_msg}]**")
        draft.append(f"  - **원인**: [여기에 원인 입력]")
        draft.append(f"  - **해결**: [여기에 해결 방안 입력]")
        draft.append(f"  - **수정 파일**:")
        
        # 파일 목록 추가
        for file_path in sorted(list(set(files))): # 중복 제거 후 정렬
            draft.append(f"    - {file_path}")
        draft.append("") # 섹션 간 공백

    return "\n".join(draft)

def main():
    print("--- 📜 CHANGELOG.md 초안 생성기 ---")
    
    last_date = get_last_changelog_date()
    print(f"ℹ️ 마지막 로그 날짜: {last_date} (이후 커밋을 검색합니다...)")
    print("-" * 30)
    
    commits = get_git_log_since(last_date)
    
    if commits is not None:
        draft_content = generate_draft(commits)
        print("\n👇 아래 내용을 복사하여 CHANGELOG.md 파일 맨 위에 붙여넣고 수정하세요 👇\n")
        print("=" * 60)
        print(draft_content)
        print("=" * 60)

if __name__ == "__main__":
    main()