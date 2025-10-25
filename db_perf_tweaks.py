# -*- coding: utf-8 -*-
# 파일명: db_perf_tweaks.py
# 설명: SQLite PRAGMA 적용 + 워밍업 쿼리 유틸 (안전한 기본값)
# 사용처: database_manager.py에서 연결 직후 apply_sqlite_pragmas() 호출,
#         main_app.py(또는 앱 시작 훅)에서 warm_up_queries() 백그라운드 실행.

from __future__ import annotations
import sqlite3
import threading
import time
from typing import Iterable, Optional, Dict

# --- PRAGMA 기본 세트 ---
# - 로컬 읽기 중심 워크로드 기준의 안전한 값
# - 필요 시 프로젝트 설정값과 연동하여 토글 가능
PRAGMA_STATEMENTS = [
    ("PRAGMA journal_mode=WAL;", None),
    ("PRAGMA synchronous=NORMAL;", None),
    ("PRAGMA temp_store=MEMORY;", None),
    # 페이지 캐시: -262144 => 약 256MB. 메모리 상황에 맞게 조정.
    ("PRAGMA cache_size=-262144;", None),
    # 메모리 매핑: 256MB. OS/환경에 따라 0 또는 더 큰 값으로 조정 가능.
    ("PRAGMA mmap_size=268435456;", None),
    # 🚀 [추가] 동시 쓰기 시도 시 잠금 대기 시간 설정 (10초)
    ("PRAGMA busy_timeout=10000;", None),
    # 🚀 [추가] WAL 자동 체크포인트 임계값 증가 (기본 1000 -> 5000 페이지)
    # 더 많은 동시 읽기/쓰기 허용, 체크포인트 빈도 감소
    ("PRAGMA wal_autocheckpoint=5000;", None),
]


def apply_sqlite_pragmas(conn: sqlite3.Connection) -> None:
    """
    연결 직후 호출하여 PRAGMA 적용.
    커밋 불필요. 예외 발생시 전파(초기화 단계에서 알아야 함).
    """
    cur = conn.cursor()
    for stmt, param in PRAGMA_STATEMENTS:
        if param is None:
            cur.execute(stmt)
        else:
            cur.execute(stmt, param)
    cur.close()


# --- 워밍업 쿼리 ---

# 워밍업 완료 플래그를 저장하는 전역 딕셔너리
_warmup_events: Dict[str, threading.Event] = {}


DEFAULT_WARMUP_QUERIES = (
    # 가장 가벼운 존재 확인
    "SELECT 1",
)


def warm_up_queries(
    get_conn_callable,
    extra_queries: Optional[Iterable[str]] = None,
    delay_sec: float = 0.0,
    warmup_key: Optional[str] = None,
) -> threading.Event:
    """
    앱 시작 직후 백그라운드에서 실행하여 OS/SQLite 캐시를 예열.
    - get_conn_callable: 연결을 반환하는 콜러블 (ex. lambda: db_manager.get_readonly_conn())
    - extra_queries: 자주 쓰는 인덱스/FTS 테이블에 대한 가벼운 쿼리들
    - delay_sec: 0.0으로 변경하여 즉시 워밍업 시작 (WAL 초기화 지연 최소화)
    - warmup_key: 워밍업 완료를 추적할 키 (예: "mapping_data")

    ✅ [성능 개선] WAL 모드 초기화를 앱 시작 직후 즉시 수행하여
    첫 쿼리 실행 시 발생하는 메인 스레드 블로킹(10-15초) 방지

    Returns:
        threading.Event: 워밍업 완료 시 set()되는 이벤트 객체
    """
    queries = list(DEFAULT_WARMUP_QUERIES)
    if extra_queries:
        queries.extend([q for q in extra_queries if isinstance(q, str) and q.strip()])

    # 완료 이벤트 생성
    event = threading.Event()
    if warmup_key:
        _warmup_events[warmup_key] = event

    def _run():
        try:
            time.sleep(delay_sec)
            conn = get_conn_callable()
            cur = conn.cursor()
            for q in queries:
                try:
                    cur.execute(q)
                    cur.fetchone()
                except Exception:
                    # 특정 테이블이 없는 환경에서도 앱이 죽지 않도록 워밍업은 best-effort로 수행
                    pass
            cur.close()
            # 읽기 전용 커넥션이면 close, 아니면 유지 정책에 따름
            try:
                conn.close()
            except Exception:
                pass
        except Exception:
            # 워밍업 실패는 앱 치명상은 아님. 로그인/테이블 준비 전이라도 넘어감.
            pass
        finally:
            # 성공/실패 관계없이 완료 플래그 설정
            event.set()

    threading.Thread(target=_run, daemon=True).start()
    return event


def wait_for_warmup(warmup_key: str, timeout: float = 30.0) -> bool:
    """
    특정 워밍업이 완료될 때까지 대기

    Args:
        warmup_key: 워밍업 키 (warm_up_queries 호출 시 지정한 키)
        timeout: 최대 대기 시간 (초)

    Returns:
        bool: 워밍업 완료 시 True, 타임아웃 시 False
    """
    event = _warmup_events.get(warmup_key)
    if event is None:
        # 워밍업이 시작되지 않았거나 이미 완료됨
        return True

    return event.wait(timeout)
