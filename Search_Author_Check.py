# -*- coding: utf-8 -*-
# 파일명: Search_NLK_Biblio.py
# 버전: v1.0.0
# 생성일: 2025-10-31
# 설명: nlk_biblio.db 데이터베이스 검색 모듈 (FTS5 기반)

import sqlite3
import pandas as pd
from pathlib import Path

# ==============================================================================
# 🎯 1. 설정
# ==============================================================================

DB_PATH = Path(__file__).parent / "nlk_biblio.db"

# ==============================================================================
# 🎯 2. 메인 검색 함수
# ==============================================================================


def search_nlk_biblio(
    title_query=None,
    author_query=None,
    kac_query=None,
    year_query=None,
    app_instance=None,
    db_manager=None,
):
    """
    nlk_biblio.db 데이터베이스에서 서지 정보를 검색합니다.

    ✅ 복수 검색 지원:
    - title_query에 여러 제목을 줄바꿈으로 구분하여 입력 가능
    - 단일 FTS5 쿼리로 일괄 검색

    Args:
        title_query (str): 제목 검색어 (줄바꿈으로 여러 개 가능)
        author_query (str): 저자 검색어
        kac_query (str): KAC 코드 검색어
        year_query (str): 연도 검색어
        app_instance: 앱 인스턴스 (로깅용)
        db_manager: DB 관리자 (미사용, 인터페이스 통일용)

    Returns:
        list[dict]: 검색 결과 레코드 리스트
    """
    try:
        # 입력 검증
        if not any([title_query, author_query, kac_query, year_query]):
            if app_instance:
                app_instance.log_message("오류: 최소 하나의 검색어를 입력해야 합니다.", "ERROR")
            return []

        # DB 연결
        if not DB_PATH.exists():
            if app_instance:
                app_instance.log_message(
                    f"오류: nlk_biblio.db 파일을 찾을 수 없습니다: {DB_PATH}", "ERROR"
                )
            return []

        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cursor = conn.cursor()

        # ✅ FTS5 쿼리 구성
        fts_conditions = []
        sql_conditions = []
        params = []

        # 제목 검색 (FTS5)
        if title_query and title_query.strip():
            # 줄바꿈으로 여러 제목 분리
            titles = [t.strip() for t in title_query.split("\n") if t.strip()]
            if titles:
                # FTS5 OR 쿼리 생성: "제목1" OR "제목2" OR "제목3"
                title_fts_query = " OR ".join([f'title:"{t}"' for t in titles])
                fts_conditions.append(f"({title_fts_query})")
                if app_instance:
                    app_instance.log_message(
                        f"정보: 제목 검색 ({len(titles)}개): {', '.join(titles[:3])}...",
                        "INFO",
                    )

        # 저자 검색 (FTS5)
        if author_query and author_query.strip():
            fts_conditions.append(f'author_names:"{author_query.strip()}"')

        # KAC 코드 검색 (FTS5) - ✅ 복수 입력 지원
        if kac_query and kac_query.strip():
            # 줄바꿈으로 여러 KAC 코드 분리
            kac_codes = [k.strip() for k in kac_query.split("\n") if k.strip()]
            if kac_codes:
                # FTS5 OR 쿼리 생성: "코드1" OR "코드2" OR "코드3"
                kac_fts_query = " OR ".join([f'kac_codes:"{k}"' for k in kac_codes])
                fts_conditions.append(f"({kac_fts_query})")
                if app_instance:
                    app_instance.log_message(
                        f"정보: KAC 코드 검색 ({len(kac_codes)}개): {', '.join(kac_codes[:3])}...",
                        "INFO",
                    )

        # ✅ FTS5 쿼리 실행
        if fts_conditions:
            fts_match = " AND ".join(fts_conditions)
            query = f"""
                SELECT
                    b.nlk_id,
                    b.title,
                    b.author_names,
                    b.kac_codes,
                    b.year
                FROM biblio_title_fts fts
                JOIN biblio b ON fts.rowid = b.rowid
                WHERE biblio_title_fts MATCH ?
            """
            params.append(fts_match)

            # 연도 필터 (SQL WHERE)
            if year_query and year_query.strip():
                query += " AND b.year = ?"
                params.append(int(year_query.strip()))

            query += " ORDER BY b.kac_codes, rank LIMIT 500"

            if app_instance:
                app_instance.log_message(f"정보: FTS5 쿼리 실행: {fts_match}", "DEBUG")

            cursor.execute(query, params)

        else:
            # FTS5 조건이 없고 연도만 있는 경우
            if year_query and year_query.strip():
                query = """
                    SELECT nlk_id, title, author_names, kac_codes, year
                    FROM biblio
                    WHERE year = ?
                    LIMIT 500
                """
                cursor.execute(query, (int(year_query.strip()),))
            else:
                return []

        # ✅ 결과 처리
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            nlk_id, title, author_names, kac_codes, year = row
            # ✅ UI 표시용으로 "nlk:" 프리픽스 제거
            display_kac = kac_codes.replace("nlk:", "") if kac_codes else ""
            results.append(
                {
                    "제목": title or "",
                    "저자": author_names or "",
                    "KAC 코드": display_kac,
                    "연도": str(year) if year else "",
                    "상세 링크": (
                        f"https://www.nl.go.kr/NL/contents/search.do?pageNum=1&pageSize=30&srchTarget=total&kwd={nlk_id}"
                        if nlk_id
                        else ""
                    ),
                    "nlk_id": nlk_id or "",
                }
            )

        if app_instance:
            app_instance.log_message(
                f"정보: 검색 완료. {len(results)}건 결과 반환.", "INFO"
            )

        return results

    except sqlite3.Error as e:
        if app_instance:
            app_instance.log_message(f"오류: SQLite 오류 발생: {e}", "ERROR")
        return []
    except ValueError as e:
        if app_instance:
            app_instance.log_message(f"오류: 연도 형식 오류: {e}", "ERROR")
        return []
    except Exception as e:
        if app_instance:
            app_instance.log_message(f"오류: 검색 중 예상치 못한 오류 발생: {e}", "ERROR")
        return []


# ==============================================================================
# 🎯 3. 테스트 코드
# ==============================================================================

if __name__ == "__main__":
    print("=== nlk_biblio.db 검색 테스트 ===\n")

    # 테스트 1: 단일 제목 검색
    print("1. 단일 제목 검색:")
    results = search_nlk_biblio(title_query="도서관")
    print(f"   결과: {len(results)}건")
    if results:
        print(f"   첫 번째: {results[0]['제목']}")

    # 테스트 2: 복수 제목 검색
    print("\n2. 복수 제목 검색:")
    results = search_nlk_biblio(title_query="도서관\n목록\n분류")
    print(f"   결과: {len(results)}건")

    # 테스트 3: 저자 검색
    print("\n3. 저자 검색:")
    results = search_nlk_biblio(author_query="황전후")
    print(f"   결과: {len(results)}건")

    # 테스트 4: KAC 코드 검색
    print("\n4. KAC 코드 검색:")
    results = search_nlk_biblio(kac_query="nlk:KAC200702805")
    print(f"   결과: {len(results)}건")

    print("\n=== 테스트 완료 ===")
