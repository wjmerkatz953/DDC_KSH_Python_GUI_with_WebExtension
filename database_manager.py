# -*- coding: utf-8 -*-
"""파일명: database_manager.py
버전: v2.2.0
수정일: 2025-10-19

[2025-10-19 업데이트 내역 - v2.2.0]
⚡ 검색 성능 극대화 - FTS5 인덱스 도입
- _create_mapping_fts5() 메서드 추가
  * mapping_data_fts FTS5 가상 테이블 생성
  * ksh_korean 컬럼 전문 검색 최적화
  * 자동 동기화 트리거 3개 (INSERT/UPDATE/DELETE)
- _verify_mapping_db() 수정
  * DB 초기화 시 FTS5 테이블 자동 생성
- 효과: 한국어 주제명 검색 20초 → 1초 (95% 향상)

[이전 버전]
v2.1.0 (2025-10-05)
- search_query_manager.py로 역할이 이관된 DDC 캐시 관련 고수준 로직 메서드들을 모두 제거
- 순수한 데이터베이스 연결 및 저수준 작업으로 명확히 분리

v2.0.0 (2025-10-04)
- 모듈 분리됨. 검색 관련 코드를 대거 search_query_manager.py로 이동

v1.0.10 (2025-10-02)
- [버그 수정] search_integrated_ksh 메서드에서 복수 키워드 검색 시 컬럼명 불일치 문제 해결
- 중복 제거 시 "concept_id" 대신 "_concept_id" 사용
- 단일/복수 키워드 검색 결과의 컬럼 구조 일관성 확보

"""
import re
import time
import os
import json
import queue
import threading

import sqlite3
from db_perf_tweaks import apply_sqlite_pragmas  # ✅ 추가: PRAGMA 유틸 임포트
import pandas as pd  # 데이터를 DataFrame으로 반환할 때 유용
import logging

# 앱의 로그 핸들러와 연동되도록 명시적 이름 사용
logger = logging.getLogger("qt_main_app.database_manager")


# 언어태그 처리 함수들 추가
LANG_TAG_RE = re.compile(r"@([A-Za-z]{2,3})$")


class DatabaseManager:
    """
    애플리케이션의 모든 SQLite 데이터베이스 작업을 중앙에서 관리하는 클래스입니다.
    glossary.db와 ksh_data.db를 모두 처리합니다.
    각 데이터베이스 작업마다 새로운 연결을 열고 닫아 스레드 안전성을 보장합니다.
    """

    def __init__(self, concepts_db_path, kdc_ddc_mapping_db_path):
        self.concepts_db_path = concepts_db_path
        self.kdc_ddc_mapping_db_path = kdc_ddc_mapping_db_path
        self.glossary_db_path = "glossary.db"

        # ✅ [동시성 개선] 히트 카운트 비동기 배치 업데이트
        from collections import defaultdict

        self._hit_count_pending = defaultdict(int)  # {iri: count}
        self._hit_count_lock = threading.Lock()
        self._hit_count_timer = None
        self.dewey_db_path = "dewey_cache.db"

        # ✅ [동시성 개선] Dewey 캐시 쓰기 큐 + 전담 워커 스레드
        self._dewey_write_queue = queue.Queue()
        self._dewey_writer_running = True
        self._dewey_writer_thread = threading.Thread(
            target=self._process_dewey_write_queue,
            daemon=False,  # ✅ daemon=False로 변경하여 명시적 종료 보장
            name="DeweyWriterThread",
        )
        self._dewey_writer_thread.start()
        logger.info("✅ Dewey 캐시 쓰기 전담 스레드 시작됨")

        # ✅ [동시성 개선] 키워드 추출 큐 + 전담 워커 스레드
        self._keyword_write_queue = queue.Queue()
        self._keyword_writer_running = True
        self._keyword_writer_thread = threading.Thread(
            target=self._process_keyword_write_queue,
            daemon=False,  # ✅ daemon=False로 변경하여 명시적 종료 보장
            name="KeywordWriterThread",
        )
        self._keyword_writer_thread.start()
        logger.info("✅ 키워드 추출 전담 스레드 시작됨")

        # ⚡ Covering Index 생성 (성능 최적화)
        self._create_covering_indexes()

    def _get_concepts_connection(self):
        """개념 DB에 대한 새로운 연결을 반환합니다."""
        conn = sqlite3.connect(self.concepts_db_path)
        conn.row_factory = sqlite3.Row
        apply_sqlite_pragmas(conn)  # ⚡ PRAGMA 최적화 적용
        return conn

    def _create_covering_indexes(self):
        """
        ⚡ Covering Index 생성: 검색 성능 최적화
        value_normalized로 검색 시 테이블 접근 없이 인덱스만으로 결과 반환
        """
        try:
            # 1. Concepts DB 인덱스
            conn = self._get_concepts_connection()
            cursor = conn.cursor()

            # Covering Index: value_normalized + concept_id + prop + value
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_literal_props_covering
                ON literal_props(value_normalized, concept_id, prop, value)
            """
            )

            # concept_id 기반 조회 최적화
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_literal_props_concept_id
                ON literal_props(concept_id, prop)
            """
            )

            conn.commit()
            conn.close()
            print("✅ Concepts DB Covering Index 생성 완료")

            # 2. Mapping DB (KDC-DDC) 인덱스
            mapping_conn = self._get_mapping_connection()
            mapping_cursor = mapping_conn.cursor()

            # DDC 컬럼 인덱스 (LIKE 전방 매칭 최적화)
            mapping_cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_mapping_ddc
                ON mapping_data(ddc)
            """
            )

            # KSH 컬럼 인덱스
            mapping_cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_mapping_ksh
                ON mapping_data(ksh)
            """
            )

            # 복합 인덱스: ddc + publication_year (정렬 최적화)
            mapping_cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_mapping_ddc_year
                ON mapping_data(ddc, publication_year)
            """
            )

            # ✅ [추가] 키워드 검색 최적화를 위한 커버링 인덱스
            print(
                "⏳ 키워드 검색용 커버링 인덱스를 생성합니다. (시간이 다소 걸릴 수 있습니다)..."
            )
            mapping_cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_mapping_data_korean_search_cover
                ON mapping_data (
                    ksh_korean,
                    ddc,
                    publication_year DESC,
                    identifier,
                    title,
                    ksh,
                    ksh_labeled
                );
                """
            )
            print("✅ 키워드 검색용 커버링 인덱스 확인/생성 완료.")

            mapping_conn.commit()
            mapping_conn.close()
            print("✅ Mapping DB Index 생성 완료")

        except Exception as e:
            print(f"⚠️ Covering Index 생성 중 오류 (무시 가능): {e}")

    def _get_glossary_connection(self):
        """용어집 데이터베이스에 대한 새로운 연결을 반환합니다."""
        conn = sqlite3.connect(self.glossary_db_path)
        conn.row_factory = sqlite3.Row
        apply_sqlite_pragmas(conn)  # ⚡ PRAGMA 최적화 적용
        return conn

    def _get_ksh_connection(self):
        """기존 ksh_entries 테이블이 들어있는 로컬 KSH DB 연결"""
        conn = sqlite3.connect(self.ksh_db_path)
        conn.row_factory = sqlite3.Row
        apply_sqlite_pragmas(conn)  # ⚡ PRAGMA 최적화 적용
        return conn

    # 헬퍼: 새로운 DB 연결
    def _get_mapping_connection(self):
        """kdc_ddc_mapping.db에 대한 새로운 연결을 반환합니다."""
        conn = sqlite3.connect(self.kdc_ddc_mapping_db_path)
        conn.row_factory = sqlite3.Row
        apply_sqlite_pragmas(conn)  # ⚡ PRAGMA 최적화 적용
        return conn

    def _get_dewey_connection(self):
        """DDC 전용 데이터베이스에 대한 새로운 연결을 반환합니다."""
        conn = sqlite3.connect(self.dewey_db_path)
        conn.row_factory = sqlite3.Row
        apply_sqlite_pragmas(conn)  # ⚡ PRAGMA 최적화 적용
        return conn

    def _create_dewey_cache_table(self):
        """DDC 전용 데이터베이스에 테이블을 생성합니다."""
        conn = None
        try:
            conn = self._get_dewey_connection()
            cursor = conn.cursor()

            # 1. DDC 캐시 테이블
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dewey_cache (
                    iri TEXT PRIMARY KEY,
                    ddc_code TEXT,
                    raw_json TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    hit_count INTEGER DEFAULT 1,
                    file_size INTEGER DEFAULT 0
                )
            """
            )

            # 2. 인덱스 생성
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dewey_cache_ddc_code
                ON dewey_cache(ddc_code)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dewey_cache_updated
                ON dewey_cache(last_updated)
            """
            )

            # 3. DDC 통계 테이블
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dewey_stats (
                    stat_date DATE PRIMARY KEY,
                    total_entries INTEGER DEFAULT 0,
                    cache_hits INTEGER DEFAULT 0,
                    api_calls INTEGER DEFAULT 0,
                    db_size_mb REAL DEFAULT 0.0
                )
            """
            )

            # 4. 검색 히스토리 테이블
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ddc_code TEXT NOT NULL,
                    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_search_history_time
                ON search_history(searched_at DESC)
            """
            )

            # 5. ✅ [누락 수정] ddc_keyword 테이블 (키워드 인덱스용)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ddc_keyword (
                    iri TEXT NOT NULL,
                    ddc TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    term_type TEXT NOT NULL,
                    source TEXT DEFAULT 'auto', /* ✅ [핵심 추가] 데이터 출처 컬럼 */
                    PRIMARY KEY (iri, keyword, term_type)
                )
            """
            )

            # 6. ✅ [누락 수정] FTS5 가상 테이블 (전문 검색용)
            cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS ddc_keyword_fts USING fts5(
                    ddc,
                    keyword,
                    term_type,
                    content='ddc_keyword',
                    content_rowid='rowid',
                    tokenize='porter unicode61'
                )
            """
            )

            # 7. ✅ [누락 수정] FTS 동기화 트리거들
            # 트리거 존재 확인 후 생성
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name='ddc_keyword_ai'"
            )
            if not cursor.fetchone():
                cursor.execute(
                    """
                    CREATE TRIGGER ddc_keyword_ai AFTER INSERT ON ddc_keyword
                    BEGIN
                        INSERT INTO ddc_keyword_fts(rowid, ddc, keyword, term_type)
                        VALUES (new.rowid, new.ddc, new.keyword, new.term_type);
                    END
                """
                )

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name='ddc_keyword_ad'"
            )
            if not cursor.fetchone():
                cursor.execute(
                    """
                    CREATE TRIGGER ddc_keyword_ad AFTER DELETE ON ddc_keyword
                    BEGIN
                        INSERT INTO ddc_keyword_fts(ddc_keyword_fts, rowid, ddc, keyword, term_type)
                        VALUES ('delete', old.rowid, old.ddc, old.keyword, old.term_type);
                    END
                """
                )

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name='ddc_keyword_au'"
            )
            if not cursor.fetchone():
                cursor.execute(
                    """
                    CREATE TRIGGER ddc_keyword_au AFTER UPDATE ON ddc_keyword
                    BEGIN
                        INSERT INTO ddc_keyword_fts(ddc_keyword_fts, rowid, ddc, keyword, term_type)
                        VALUES ('delete', old.rowid, old.ddc, old.keyword, old.term_type);
                        INSERT INTO ddc_keyword_fts(rowid, ddc, keyword, term_type)
                        VALUES (new.rowid, new.ddc, new.keyword, new.term_type);
                    END
                """
                )

            conn.commit()
            print(f"✅ DDC 전용 데이터베이스 '{self.dewey_db_path}' 초기화 완료")
            print("   - dewey_cache, dewey_stats, search_history 테이블 생성")
            print("   - ddc_keyword, ddc_keyword_fts (FTS5) 테이블 생성")
            print("   - FTS 동기화 트리거 3개 생성")

        except Exception as e:
            print(f"❌ 오류: DDC 데이터베이스 테이블 생성 실패: {e}")
        finally:
            if conn:
                conn.close()

    def _create_glossary_table(self):
        """translations 테이블을 생성하고 초기 용어집 데이터를 삽입합니다."""
        conn = None
        try:
            conn = self._get_glossary_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    original_term TEXT PRIMARY KEY COLLATE NOCASE,
                    translated_term TEXT NOT NULL
                )
                """
            )
            conn.commit()
            # 초기 용어집 데이터 삽입 (예시, 이미 존재하는 경우 삽입하지 않음)
            initial_terms = {
                "正義": "정의",
                "自由主義": "자유주의",
                "Gerechtigkeit": "정의",
                "Politische Philosophie": "정치 철학",
                "Justice": "정의",
                "Liberalism": "자유주의",
                "Ethics": "윤리학",
                "Values": "가치",
            }
            for original, translated in initial_terms.items():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO translations (original_term, translated_term)
                    VALUES (?, ?)
                """,
                    (original, translated),
                )
            conn.commit()
            print(
                f"정보: 용어집 데이터베이스 '{self.glossary_db_path}'의 'translations' 테이블 및 초기 용어 확인/생성 완료."
            )
        except Exception as e:
            print(f"오류: 용어집 테이블 생성 중 오류 발생: {e}")
        finally:
            if conn:
                conn.close()

    def initialize_databases(self):
        """모든 데이터베이스 테이블을 초기화합니다."""
        self._verify_concepts_db()  # 🆕 새 DB 존재 확인
        self._verify_mapping_db()  # 👈 [누락된 부분 추가]
        self._create_glossary_table()
        self._create_settings_table()  # API 키 세팅용
        self._create_dewey_cache_table()  # 🆕 DDC 캐시 테이블 생성

    def _create_concepts_fts5(self, cursor, conn):
        """
        ✅ [신규 추가] literal_props 테이블용 FTS5 가상 테이블 생성
        - value_normalized 컬럼을 기준으로 전문 검색 인덱스를 생성합니다.
        """
        try:
            # -------------------
            # ✅ [핵심 수정] FTS5 테이블이 이미 존재하는지 먼저 확인합니다.
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='literal_props_fts'")
            if cursor.fetchone():
                print("✅ literal_props_fts 테이블이 이미 존재하여 재생성을 건너뜁니다.")
                return  # 테이블이 존재하면 함수를 즉시 종료합니다.
            # -------------------

            print("⏳ literal_props_fts 테이블 재구성 시작... (value_normalized 기준)")

            # 기존 FTS 테이블 및 트리거 삭제 (최초 생성 시 혹시 모를 잔여물 제거)
            cursor.executescript("""
                DROP TRIGGER IF EXISTS literal_props_ai;
                DROP TRIGGER IF EXISTS literal_props_ad;
                DROP TRIGGER IF EXISTS literal_props_au;
                DROP TABLE IF EXISTS literal_props_fts;
            """)
            print("   - 기존 FTS 테이블 및 트리거 삭제 완료.")

            # FTS5 가상 테이블 생성 (value_normalized 컬럼만 인덱싱)
            cursor.execute("""
                CREATE VIRTUAL TABLE literal_props_fts USING fts5(
                    value_normalized,
                    content='literal_props',
                    content_rowid='rowid'
                )
            """)
            print("   - FTS5 가상 테이블 `literal_props_fts` 생성 완료.")

            # 기존 데이터로 FTS5 채우기
            cursor.execute("""
                INSERT INTO literal_props_fts(rowid, value_normalized)
                SELECT rowid, value_normalized
                FROM literal_props
                WHERE value_normalized IS NOT NULL AND value_normalized != ''
            """)
            print("   - 기존 데이터 FTS5 인덱싱 완료.")

            # 동기화 트리거 생성
            cursor.executescript("""
                CREATE TRIGGER literal_props_ai AFTER INSERT ON literal_props BEGIN
                    INSERT INTO literal_props_fts(rowid, value_normalized)
                    VALUES (new.rowid, new.value_normalized);
                END;
                CREATE TRIGGER literal_props_ad AFTER DELETE ON literal_props BEGIN
                    DELETE FROM literal_props_fts WHERE rowid = old.rowid;
                END;
                CREATE TRIGGER literal_props_au AFTER UPDATE ON literal_props BEGIN
                    DELETE FROM literal_props_fts WHERE rowid = old.rowid;
                    INSERT INTO literal_props_fts(rowid, value_normalized)
                    VALUES (new.rowid, new.value_normalized);
                END;
            """)
            print("   - 동기화 트리거 3개 생성 완료.")
            
            conn.commit()
            print("✅ literal_props_fts 테이블 재구성 성공!")

        except Exception as e:
            print(f"⚠️ FTS5 테이블(concepts) 생성 실패 (무시 가능): {e}")

    def _verify_concepts_db(self):
        """새 개념 DB의 존재와 테이블 구조를 확인합니다."""
        try:
            conn = self._get_concepts_connection()
            cursor = conn.cursor()

            # -------------------
            # ✅ [핵심 추가] DB 검증 시 FTS5 테이블을 재생성하는 함수 호출
            self._create_concepts_fts5(cursor, conn)
            # -------------------

            # 필수 테이블들 존재 확인
            required_tables = [
                "concepts",
                "literal_props",
                "uri_props",
                "category_mapping",
                "ddc_mapping",
                "kdc_mapping",
            ]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]

            missing_tables = [
                table for table in required_tables if table not in existing_tables
            ]

            if missing_tables:
                print(f"경고: 다음 테이블들이 누락되었습니다: {missing_tables}")
                print("새로운 nlk_concepts.sqlite 파일을 확인해주세요.")
            else:
                print("정보: 모든 필수 테이블이 존재합니다.")

            # 데이터 개수 확인
            cursor.execute(
                "SELECT COUNT(*) FROM concepts WHERE concept_id LIKE 'nlk:KSH%'"
            )
            concept_count = cursor.fetchone()[0]
            print(f"정보: KSH 개념 {concept_count:,}개가 로드되어 있습니다.")

            conn.close()

        except Exception as e:
            print(f"오류: 개념 DB 확인 중 오류 발생: {e}")
            print("nlk_concepts.sqlite 파일이 올바른 위치에 있는지 확인해주세요.")

    def _verify_mapping_db(self):
        """kdc_ddc_mapping.db의 존재와 테이블/인덱스 구조를 확인합니다."""
        conn = None
        try:
            conn = self._get_mapping_connection()
            cursor = conn.cursor()

            # 1. 테이블 존재 확인
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='mapping_data'"
            )
            if not cursor.fetchone():
                raise FileNotFoundError(
                    "'mapping_data' 테이블을 찾을 수 없습니다. kdc_ddc_mapping.db 파일이 올바른지 확인해주세요."
                )

            # 2. 데이터 개수 확인
            cursor.execute("SELECT COUNT(*) FROM mapping_data")
            record_count = cursor.fetchone()[0]
            if record_count > 0:
                print(
                    f"정보: kdc_ddc_mapping.db 확인 완료. {record_count:,}개의 서지 데이터가 로드되었습니다."
                )
            else:
                print("경고: kdc_ddc_mapping.db는 로드되었으나 서지 데이터가 없습니다.")

            # 3. ✅ [성능 개선] FTS5 가상 테이블 생성 (한국어 주제명 검색 최적화)
            self._create_mapping_fts5(cursor, conn)

        except Exception as e:
            print(
                f"❌ 치명적 오류: kdc_ddc_mapping.db를 열거나 검증하는 데 실패했습니다. 파일 경로와 파일 상태를 확인해주세요. 오류: {e}"
            )
        finally:
            if conn:
                conn.close()

    def _create_mapping_fts5(self, cursor, conn):
        """
        ✅ [성능 개선] mapping_data 테이블용 FTS5 가상 테이블 생성
        - ksh_korean 컬럼 전문 검색 최적화
        - 380만 건에서 1초 이내 검색 가능
        """
        try:
            # FTS5 가상 테이블 존재 확인
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='mapping_data_fts'
            """)

            if cursor.fetchone():
                print("✅ mapping_data FTS5 테이블이 이미 존재합니다.")
                return

            print("⏳ mapping_data FTS5 테이블 생성 중... (수 분 소요 가능)")

            # FTS5 가상 테이블 생성
            cursor.execute("""
                CREATE VIRTUAL TABLE mapping_data_fts USING fts5(
                    identifier UNINDEXED,
                    ksh_korean,
                    content='mapping_data',
                    content_rowid='rowid'
                )
            """)

            # 기존 데이터로 FTS5 채우기
            cursor.execute("""
                INSERT INTO mapping_data_fts(rowid, identifier, ksh_korean)
                SELECT rowid, identifier, ksh_korean
                FROM mapping_data
                WHERE ksh_korean IS NOT NULL AND ksh_korean != ''
            """)

            # 동기화 트리거 생성
            cursor.execute("""
                CREATE TRIGGER mapping_data_fts_insert AFTER INSERT ON mapping_data BEGIN
                    INSERT INTO mapping_data_fts(rowid, identifier, ksh_korean)
                    VALUES (new.rowid, new.identifier, new.ksh_korean);
                END
            """)

            cursor.execute("""
                CREATE TRIGGER mapping_data_fts_delete AFTER DELETE ON mapping_data BEGIN
                    DELETE FROM mapping_data_fts WHERE rowid = old.rowid;
                END
            """)

            cursor.execute("""
                CREATE TRIGGER mapping_data_fts_update AFTER UPDATE ON mapping_data BEGIN
                    DELETE FROM mapping_data_fts WHERE rowid = old.rowid;
                    INSERT INTO mapping_data_fts(rowid, identifier, ksh_korean)
                    VALUES (new.rowid, new.identifier, new.ksh_korean);
                END
            """)

            conn.commit()
            print("✅ mapping_data FTS5 테이블 및 트리거 생성 완료!")

        except Exception as e:
            print(f"⚠️ FTS5 테이블 생성 실패 (무시 가능): {e}")
            # 실패해도 앱은 계속 실행 (기존 방식으로 검색)

    def close_connections(self):
        """
        경고: DatabaseManager.close_connections()는 더 이상 필요하지 않습니다. 각 작업마다 연결이 자동으로 닫힙니다.
        """
        # ✅ [추가] 앱 종료 시 남은 히트 카운트 flush
        if self._hit_count_timer:
            self._hit_count_timer.cancel()
        self._flush_hit_counts()

        # ✅ [추가] Dewey 쓰기 워커 안전 종료
        self.stop_dewey_writer()

        # ✅ [추가] 키워드 워커 안전 종료
        self.stop_keyword_writer()

        print(
            "경고: DatabaseManager.close_connections()는 더 이상 필요하지 않습니다. 각 작업마다 연결이 자동으로 닫힙니다."
        )

    # --- KSH 데이터 관련 함수 ---

    def insert_ksh_entries_from_dataframe(self, df_to_insert):
        """
        DataFrame의 KSH 데이터를 ksh_entries 테이블에 삽입합니다.
        이 함수는 test2.py와 같은 초기 데이터 로드 스크립트에서 사용됩니다.
        """
        conn = None
        try:
            conn = self._get_ksh_connection()
            df_to_insert.to_sql("ksh_entries", conn, if_exists="append", index=False)
            conn.commit()
            print(
                f"정보: {len(df_to_insert)}건의 KSH 데이터가 'ksh_entries' 테이블에 삽입되었습니다."
            )
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"오류: KSH 데이터 삽입 중 오류 발생: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def get_ksh_categories(self):
        """
        사용 가능한 모든 주제 카테고리를 가져옵니다.
        🔧 개선: 실제로 주제어가 할당된 주제모음만 반환 (빈 주제모음 자동 제외)
        """
        conn = None
        try:
            conn = self._get_concepts_connection()
            cursor = conn.cursor()

            # 🎯 핵심 개선: 실제 개념이 있는 주제모음만 조회
            query = """
            SELECT DISTINCT cm.main_category, COUNT(c.concept_id) as concept_count
            FROM category_mapping cm
            INNER JOIN concepts c ON cm.concept_id = c.concept_id
            WHERE cm.main_category IS NOT NULL
            AND cm.main_category != ''
            GROUP BY cm.main_category
            HAVING concept_count > 0
            ORDER BY cm.main_category
            """

            cursor.execute(query)
            results = cursor.fetchall()

            categories = [row[0] for row in results]

            # 🔍 디버깅: 각 카테고리와 개수 출력
            print(f"📊 주제모음 목록 ({len(categories)}개):")
            for cat, count in results:
                print(f"  - {cat}: {count}개")

            categories.insert(0, "전체")

            # 🗑️ 추가: 빈 주제모음 정리 (옵션)
            self._cleanup_empty_categories(conn)

            return categories

        except Exception as e:
            print(f"오류: 카테고리 로드 중 오류: {e}")
            return ["전체"]
        finally:
            if conn:
                conn.close()

    def _cleanup_empty_categories(self, conn):
        """
        🗑️ 빈 주제모음 자동 정리 함수
        실제 개념과 연결되지 않은 category_mapping 행들을 삭제합니다.
        """
        try:
            cursor = conn.cursor()

            # 1. 빈 주제모음 찾기
            cleanup_query = """
            DELETE FROM category_mapping
            WHERE concept_id NOT IN (
                SELECT concept_id FROM concepts WHERE concept_id IS NOT NULL
            )
            """

            cursor.execute(cleanup_query)
            deleted_count = cursor.rowcount

            if deleted_count > 0:
                print(f"🧹 정보: {deleted_count}개의 빈 주제모음 매핑을 정리했습니다.")
                conn.commit()

            # 2. 고아 주제모음 찾기 및 보고 (삭제하지는 않고 로그만)
            orphan_query = """
            SELECT DISTINCT main_category, COUNT(*) as orphan_count
            FROM category_mapping cm
            LEFT JOIN concepts c ON cm.concept_id = c.concept_id
            WHERE c.concept_id IS NULL
            GROUP BY cm.main_category
            """

            cursor.execute(orphan_query)
            orphans = cursor.fetchall()

            if orphans:
                print(f"⚠️ 경고: 다음 주제모음들이 유효하지 않은 개념을 참조합니다:")
                for category, count in orphans:
                    print(f"   - '{category}': {count}개 항목")

        except Exception as e:
            print(f"❌ 오류: 빈 주제모음 정리 중 오류: {e}")

    def get_empty_categories_report(self):
        """
        📊 빈 주제모음 상세 보고서 생성
        관리자가 수동으로 확인할 때 사용
        """
        conn = None
        try:
            conn = self._get_concepts_connection()
            cursor = conn.cursor()

            # 1. 전체 주제모음 통계
            cursor.execute(
                """
                SELECT
                    cm.main_category,
                    COUNT(cm.concept_id) as total_mappings,
                    COUNT(c.concept_id) as valid_concepts,
                    COUNT(cm.concept_id) - COUNT(c.concept_id) as invalid_mappings
                FROM category_mapping cm
                LEFT JOIN concepts c ON cm.concept_id = c.concept_id
                WHERE cm.main_category IS NOT NULL AND cm.main_category != ''
                GROUP BY cm.main_category
                ORDER BY invalid_mappings DESC, cm.main_category
            """
            )

            results = cursor.fetchall()

            print("=" * 60)
            print("📊 주제모음 상태 보고서")
            print("=" * 60)
            print(f"{'주제모음':<20} {'전체':<8} {'유효':<8} {'무효':<8} {'상태'}")
            print("-" * 60)

            empty_categories = []
            for row in results:
                category, total, valid, invalid = row
                if valid == 0:
                    status = "🗑️ 완전히 비어있음"
                    empty_categories.append(category)
                elif invalid > 0:
                    status = f"⚠️ 일부 무효 ({invalid}개)"
                else:
                    status = "✅ 정상"

                print(f"{category:<20} {total:<8} {valid:<8} {invalid:<8} {status}")

            print("=" * 60)

            if empty_categories:
                print(f"\n🗑️ 삭제 권장 주제모음: {len(empty_categories)}개")
                for cat in empty_categories:
                    print(f"   - {cat}")
            else:
                print("\n✅ 모든 주제모음이 정상 상태입니다.")

            return {
                "total_categories": len(results),
                "empty_categories": empty_categories,
                "valid_categories": len(results) - len(empty_categories),
            }

        except Exception as e:
            print(f"❌ 오류: 주제모음 보고서 생성 실패: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def force_delete_empty_categories(self):
        """
        🚨 강제 삭제: 완전히 비어있는 주제모음들을 데이터베이스에서 제거
        주의: 이 함수는 되돌릴 수 없습니다!
        """
        conn = None
        try:
            conn = self._get_concepts_connection()
            cursor = conn.cursor()

            # 1. 삭제할 빈 주제모음 목록 조회
            cursor.execute(
                """
                SELECT DISTINCT cm.main_category
                FROM category_mapping cm
                LEFT JOIN concepts c ON cm.concept_id = c.concept_id
                WHERE c.concept_id IS NULL
            """
            )

            empty_categories = [row[0] for row in cursor.fetchall()]

            if not empty_categories:
                print("ℹ️ 정보: 삭제할 빈 주제모음이 없습니다.")
                return 0

            print(f"🗑️ 다음 {len(empty_categories)}개 주제모음을 삭제합니다:")
            for cat in empty_categories:
                print(f"   - {cat}")

            # 2. 실제 삭제 실행
            placeholders = ",".join("?" for _ in empty_categories)
            delete_query = f"""
            DELETE FROM category_mapping
            WHERE main_category IN ({placeholders})
            AND concept_id NOT IN (SELECT concept_id FROM concepts)
            """

            cursor.execute(delete_query, empty_categories)
            deleted_count = cursor.rowcount
            conn.commit()

            print(f"✅ 성공: {deleted_count}개의 빈 주제모음 매핑을 삭제했습니다.")

            return deleted_count

        except Exception as e:
            print(f"❌ 오류: 빈 주제모음 강제 삭제 실패: {e}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if conn:
                conn.close()

    def update_ksh_entry(self, db_id, column_name, new_value):
        """
        KSH 항목의 특정 필드를 업데이트합니다.
        Args:
            db_id (int): 업데이트할 항목의 고유 ID.
            column_name (str): 업데이트할 컬럼의 이름.
            new_value (str): 새로운 값.
        Returns:
            bool: 업데이트 성공 여부.
        """
        conn = None
        try:
            conn = self._get_ksh_connection()
            cursor = conn.cursor()
            # SQL Injection을 방지하기 위해 컬럼 이름을 직접 포맷팅하지 않고,
            # 안전한 문자만 허용하도록 화이트리스트 검사를 수행합니다.
            allowed_columns = [
                "original_subject",
                "main_category",
                "classification_ddc",
                "classification_kdc_like",
                "pure_subject_name",
                "qualifier_parentheses",
                "qualifier_square_brackets",
                "ksh_code",
                "ksh_link_url",
            ]
            if column_name not in allowed_columns:
                print(f"오류: 허용되지 않은 컬럼 업데이트 시도: {column_name}")
                return False

            # 안전하게 포맷팅된 쿼리 생성
            query = f"UPDATE ksh_entries SET {column_name} = ? WHERE id = ?"
            cursor.execute(query, (new_value, db_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"오류: KSH 항목 업데이트 실패 (ID: {db_id}): {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    # --- 용어집(Glossary) 데이터 관련 함수 ---

    def get_translation(self, original_term):
        """
        SQLite 용어집 데이터베이스에서 캐시된 번역을 조회합니다.
        """
        conn = None
        try:
            conn = self._get_glossary_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT translated_term FROM translations WHERE original_term = ?",
                (original_term,),
            )
            row = cursor.fetchone()
            return row["translated_term"] if row else None
        except sqlite3.Error as e:
            print(f"오류: 용어집에서 번역 조회 실패: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def get_all_custom_translations(self):
        """
        SQLite 용어집 데이터베이스에서 모든 맞춤형 번역 매핑을 가져옵니다.
        """
        conn = None
        translations = {}
        try:
            conn = self._get_glossary_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT original_term, translated_term FROM translations")
            for row in cursor.fetchall():
                translations[row["original_term"]] = row["translated_term"]
        except sqlite3.Error as e:
            print(f"오류: 용어집에서 맞춤형 번역 가져오기 실패: {e}")
        finally:
            if conn:
                conn.close()
        return translations

    def add_translation(self, original, translated):
        """
        SQLite 용어집 데이터베이스에 번역 매핑을 추가하거나 업데이트합니다.
        """
        conn = None
        try:
            conn = self._get_glossary_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO translations (original_term, translated_term)
                VALUES (?, ?)
            """,
                (original, translated),
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"오류: 용어집 번역 추가/업데이트 실패: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def delete_custom_translation(self, original):
        """
        SQLite 용어집 데이터베이스에서 맞춤형 번역 매핑을 삭제합니다.
        """
        conn = None
        try:
            conn = self._get_glossary_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM translations WHERE original_term = ?", (original,)
            )
            conn.commit()
            print(f"정보: 용어집 번역 삭제 성공: '{original}'")
            return True
        except sqlite3.Error as e:
            print(f"오류: 용어집 번역 삭제 실패: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def _create_settings_table(self):
        """API 설정 정보를 저장할 settings 테이블을 생성합니다."""
        conn = None
        try:
            conn = self._get_glossary_connection()  # 용어집 DB에 설정도 함께 저장
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()
            print(f"정보: 설정 테이블 'settings'가 생성되었습니다.")
        except Exception as e:
            print(f"오류: 설정 테이블 생성 중 오류 발생: {e}")
        finally:
            if conn:
                conn.close()

    def get_setting(self, key):
        """설정값을 조회합니다."""
        conn = None
        try:
            conn = self._get_glossary_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            return result["value"] if result else None
        except Exception as e:
            print(f"오류: 설정 조회 실패 ({key}): {e}")
            return None
        finally:
            if conn:
                conn.close()

    def set_setting(self, key, value, description=None):
        """설정값을 저장/업데이트합니다."""
        conn = None
        try:
            conn = self._get_glossary_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO settings (key, value, description, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (key, value, description),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"오류: 설정 저장 실패 ({key}): {e}")
            return False
        finally:
            if conn:
                conn.close()

    def get_naver_api_credentials(self):
        """네이버 API 인증 정보를 조회합니다."""
        client_id = self.get_setting("naver_client_id")
        client_secret = self.get_setting("naver_client_secret")
        return client_id, client_secret

    def set_naver_api_credentials(self, client_id, client_secret):
        """네이버 API 인증 정보를 저장합니다."""
        try:
            id_result = self.set_setting(
                "naver_client_id", client_id, "네이버 API 클라이언트 ID"
            )
            secret_result = self.set_setting(
                "naver_client_secret", client_secret, "네이버 API 클라이언트 시크릿"
            )

            if id_result and secret_result:
                print(
                    "정보: 네이버 API 클라이언트 ID와 시크릿이 데이터베이스에 안전하게 저장되었습니다."
                )
                return True
            else:
                print("오류: 네이버 API 인증 정보 저장 중 일부 실패")
                return False
        except Exception as e:
            print(f"오류: 네이버 API 인증 정보 저장 실패: {e}")
            return False

    def delete_setting(self, key):
        """설정값을 삭제합니다."""
        conn = None
        try:
            conn = self._get_glossary_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0  # True if a row was deleted
        except Exception as e:
            print(f"오류: 설정 삭제 실패 ({key}): {e}")
            return False
        finally:
            if conn:
                conn.close()

    def delete_naver_api_credentials(self):
        """네이버 API 인증 정보를 삭제합니다."""
        try:
            self.delete_setting("naver_client_id")
            self.delete_setting("naver_client_secret")
            print("정보: 네이버 API 인증 정보가 데이터베이스에서 삭제되었습니다.")
            return True
        except Exception as e:
            print(f"오류: 네이버 API 인증 정보 삭제 실패: {e}")
            return False

    # database_manager.py에 추가할 NLK API 키 관련 함수들

    def get_nlk_api_key(self):
        """NLK API 키를 조회합니다."""
        return self.get_setting("nlk_api_key")

    def set_nlk_api_key(self, api_key):
        """NLK API 키를 저장합니다."""
        try:
            result = self.set_setting("nlk_api_key", api_key, "NLK OpenAPI 키")
            if result:
                print("정보: NLK API 키가 데이터베이스에 안전하게 저장되었습니다.")
                return True
            else:
                print("오류: NLK API 키 저장 실패")
                return False
        except Exception as e:
            print(f"오류: NLK API 키 저장 실패: {e}")
            return False

    def delete_nlk_api_key(self):
        """NLK API 키를 삭제합니다."""
        try:
            result = self.delete_setting("nlk_api_key")
            if result:
                print("정보: NLK API 키가 데이터베이스에서 삭제되었습니다.")
            return result
        except Exception as e:
            print(f"오류: NLK API 키 삭제 실패: {e}")
            return False

    # database_manager.py에 추가할 Google API 키 관련 함수들
    def get_google_api_key(self):
        """Google API 키를 조회합니다."""
        return self.get_setting("google_api_key")

    def set_google_api_key(self, api_key):
        """Google API 키를 저장합니다."""
        try:
            result = self.set_setting("google_api_key", api_key, "Google OpenAPI 키")
            if result:
                print("정보: Google API 키가 데이터베이스에 안전하게 저장되었습니다.")
                return True
            else:
                print("오류: Google API 키 저장 실패")
                return False
        except Exception as e:
            print(f"오류: Google API 키 저장 실패: {e}")
            return False

    def delete_google_api_key(self):
        """Google API 키를 삭제합니다."""
        try:
            result = self.delete_setting("google_api_key")
            if result:
                print("정보: Google API 키가 데이터베이스에서 삭제되었습니다.")
            return result
        except Exception as e:
            print(f"오류: Google API 키 삭제 실패: {e}")
            return False

    # database_manager.py에 추가할 Gemini API 키 관련 함수들
    def get_gemini_api_key(self):
        """Gemini API 키를 조회합니다."""
        return self.get_setting("gemini_api_key")

    def set_gemini_api_key(self, api_key):
        """Gemini API 키를 저장합니다."""
        try:
            result = self.set_setting("gemini_api_key", api_key, "Gemini OpenAPI 키")
            if result:
                print("정보: Gemini API 키가 데이터베이스에 안전하게 저장되었습니다.")
                return True
            else:
                print("오류: Gemini API 키 저장 실패")
                return False
        except Exception as e:
            print(f"오류: Gemini API 키 저장 실패: {e}")
            return False

    def delete_gemini_api_key(self):
        """Gemini API 키를 삭제합니다."""
        try:
            result = self.delete_setting("gemini_api_key")
            if result:
                print("정보: Gemini API 키가 데이터베이스에서 삭제되었습니다.")
            return result
        except Exception as e:
            print(f"오류: Gemini API 키 삭제 실패: {e}")
            return False

    # ========================================
    # Upstage SOLAR API 키 관련 함수들
    # ========================================

    def get_solar_api_key(self):
        """Upstage SOLAR API 키를 조회합니다."""
        return self.get_setting("solar_api_key")

    def set_solar_api_key(self, api_key):
        """Upstage SOLAR API 키를 저장합니다."""
        try:
            result = self.set_setting("solar_api_key", api_key, "Upstage SOLAR API 키")
            if result:
                logger.info(
                    "Upstage SOLAR API 키가 데이터베이스에 안전하게 저장되었습니다."
                )
                return True
            else:
                logger.error("Upstage SOLAR API 키 저장 실패")
                return False
        except Exception as e:
            logger.error(f"Upstage SOLAR API 키 저장 실패: {e}")
            return False

    def delete_solar_api_key(self):
        """Upstage SOLAR API 키를 삭제합니다."""
        try:
            result = self.delete_setting("solar_api_key")
            if result:
                logger.info("Upstage SOLAR API 키가 데이터베이스에서 삭제되었습니다.")
            return result
        except Exception as e:
            logger.error(f"Upstage SOLAR API 키 삭제 실패: {e}")
            return False

    # ========================================
    # DDC 캐시 관련 함수들 (수정된 버전)
    # ========================================

    def get_dewey_from_cache(self, iri: str) -> str | None:
        """DDC 전용 DB에서 캐시 조회 (읽기 전용 - 히트 카운트는 비동기 배치 업데이트)"""
        conn = None
        try:
            conn = self._get_dewey_connection()
            cursor = conn.cursor()

            # 캐시 조회 (읽기 전용 - UPDATE 제거로 락 충돌 완전 해소)
            cursor.execute("SELECT raw_json FROM dewey_cache WHERE iri = ?", (iri,))
            result = cursor.fetchone()

            if result:
                # ✅ [동시성 개선] 히트 카운트를 메모리에 누적만 하고 즉시 반환
                # 실제 DB 업데이트는 3초마다 배치로 처리
                self._schedule_hit_count_update(iri)
                return result[0]

            return None

        except Exception as e:
            print(f"경고: DDC 캐시 조회 실패: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def _schedule_hit_count_update(self, iri: str):
        """히트 카운트를 메모리에 누적하고 3초 후 배치 업데이트 예약"""
        with self._hit_count_lock:
            self._hit_count_pending[iri] += 1

            # 기존 타이머 취소하고 새로 시작 (3초 idle 후 실행)
            if self._hit_count_timer:
                self._hit_count_timer.cancel()

            import threading

            self._hit_count_timer = threading.Timer(3.0, self._flush_hit_counts)
            self._hit_count_timer.daemon = True
            self._hit_count_timer.start()

    def _flush_hit_counts(self):
        """누적된 히트 카운트를 DB에 배치 업데이트"""
        with self._hit_count_lock:
            if not self._hit_count_pending:
                return

            pending = dict(self._hit_count_pending)
            self._hit_count_pending.clear()
            self._hit_count_timer = None

        # 락 밖에서 DB 업데이트 (I/O 작업)
        conn = None
        try:
            conn = self._get_dewey_connection()
            cursor = conn.cursor()

            for iri, count in pending.items():
                cursor.execute(
                    """
                    UPDATE dewey_cache
                    SET hit_count = hit_count + ?,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE iri = ?
                    """,
                    (count, iri),
                )

            conn.commit()
            logger.debug(f"✅ 히트 카운트 배치 업데이트 완료: {len(pending)}개 항목")

        except Exception as e:
            logger.warning(f"경고: 히트 카운트 배치 업데이트 실패: {e}")
        finally:
            if conn:
                conn.close()

    def _process_dewey_write_queue(self):
        """
        ✅ [동시성 개선] Dewey 캐시 쓰기 전담 워커 스레드
        큐에서 작업을 꺼내 순차적으로 DB에 저장합니다.
        """
        logger.info("🚀 Dewey 캐시 쓰기 워커 스레드 시작")
        conn = None
        try:
            # 워커 전용 DB 연결 (스레드당 하나의 연결)
            conn = self._get_dewey_connection()
            cursor = conn.cursor()

            while self._dewey_writer_running:
                try:
                    # 0.5초 타임아웃으로 큐에서 작업 가져오기
                    task = self._dewey_write_queue.get(timeout=0.5)

                    if task is None:  # 종료 신호
                        logger.info("🛑 Dewey 쓰기 워커: 종료 신호 수신")
                        break

                    # 작업 실행: (iri, ddc_code, raw_json, json_size)
                    iri, ddc_code, raw_json, json_size = task

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO dewey_cache
                        (iri, ddc_code, raw_json, last_updated, hit_count, file_size)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1, ?)
                        """,
                        (iri, ddc_code, raw_json, json_size),
                    )
                    conn.commit()

                    # ✅ 성공 로그 (앱 화면에 표시)
                    logger.info(f"✅ DDC {ddc_code} 캐시 DB 저장 완료")

                    self._dewey_write_queue.task_done()

                except queue.Empty:
                    # 타임아웃 - 계속 대기
                    continue
                except Exception as e:
                    logger.error(f"❌ Dewey 캐시 쓰기 실패: {e}")
                    # 에러 발생해도 계속 실행
                    try:
                        self._dewey_write_queue.task_done()
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"❌ Dewey 쓰기 워커 스레드 치명적 오류: {e}")
        finally:
            if conn:
                conn.close()
            logger.info("⏹️ Dewey 캐시 쓰기 워커 스레드 종료됨")

    def enqueue_dewey_cache_write(self, iri: str, ddc_code: str, raw_json: str):
        """
        ✅ [동시성 개선] Dewey 캐시 쓰기 작업을 큐에 추가
        여러 스레드에서 안전하게 호출 가능합니다.
        """
        try:
            json_size = len(raw_json.encode("utf-8"))
            self._dewey_write_queue.put((iri, ddc_code, raw_json, json_size))
            logger.debug(f"📝 Dewey 캐시 쓰기 큐에 추가: {ddc_code}")
        except Exception as e:
            logger.error(f"❌ Dewey 캐시 쓰기 큐 추가 실패: {e}")

    def stop_dewey_writer(self):
        """
        ✅ [동시성 개선] Dewey 쓰기 워커 스레드를 안전하게 종료
        애플리케이션 종료 시 호출됩니다.
        """
        if not self._dewey_writer_running:
            return

        logger.info("🛑 Dewey 쓰기 워커 종료 시작...")
        self._dewey_writer_running = False

        # 종료 신호 전송 (먼저 전송하여 워커가 종료 준비하도록)
        try:
            self._dewey_write_queue.put(None, timeout=1.0)
        except queue.Full:
            logger.warning("⚠️ Dewey 쓰기 큐가 가득 참")

        # 워커 스레드 종료 대기 (최대 5초)
        if self._dewey_writer_thread.is_alive():
            self._dewey_writer_thread.join(timeout=5.0)
            if self._dewey_writer_thread.is_alive():
                logger.warning("⚠️ Dewey 쓰기 워커가 5초 내 종료되지 않음")
            else:
                logger.info("✅ Dewey 쓰기 워커 정상 종료됨")
        else:
            logger.info("✅ Dewey 쓰기 워커 이미 종료됨")

    def _process_keyword_write_queue(self):
        """
        ✅ [동시성 개선] 키워드 추출 전담 워커 스레드
        큐에서 키워드 추출 작업을 꺼내 순차적으로 처리합니다.
        """
        logger.info("🚀 키워드 추출 워커 스레드 시작")
        conn = None
        try:
            conn = self._get_dewey_connection()
            cursor = conn.cursor()

            while self._keyword_writer_running:
                try:
                    task = self._keyword_write_queue.get(timeout=0.5)

                    if task is None:  # 종료 신호
                        logger.info("🛑 키워드 워커: 종료 신호 수신")
                        break

                    # 작업 실행: (iri, ddc_code, keyword_entries)
                    iri, ddc_code, keyword_entries = task

                    # -------------------
                    # ✅ [핵심 수정] 앱이 자동으로 생성한('auto') 키워드만 삭제하도록 변경
                    # 사용자가 직접 추가한(source='user' 등) 데이터는 보존됩니다.
                    cursor.execute(
                        "DELETE FROM ddc_keyword WHERE iri = ? AND source = 'auto'",
                        (iri,),
                    )

                    # 새 키워드 삽입 (source는 기본값 'auto'로 자동 설정됨)
                    if keyword_entries:
                        cursor.executemany(
                            """
                            INSERT OR IGNORE INTO ddc_keyword (iri, ddc, keyword, term_type)
                            VALUES (?, ?, ?, ?)
                            """,
                            keyword_entries,
                        )
                    # -------------------

                    conn.commit()
                    self._keyword_write_queue.task_done()

                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"❌ 키워드 추출 실패: {e}")
                    try:
                        self._keyword_write_queue.task_done()
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"❌ 키워드 워커 스레드 치명적 오류: {e}")
        finally:
            if conn:
                conn.close()
            logger.info("⏹️ 키워드 추출 워커 스레드 종료됨")

    def enqueue_keyword_extraction(
        self, iri: str, ddc_code: str, keyword_entries: list
    ):
        """
        ✅ [동시성 개선] 키워드 추출 작업을 큐에 추가
        """
        try:
            self._keyword_write_queue.put((iri, ddc_code, keyword_entries))
            logger.debug(f"📝 키워드 추출 큐에 추가: {ddc_code}")
        except Exception as e:
            logger.error(f"❌ 키워드 큐 추가 실패: {e}")

    def stop_keyword_writer(self):
        """
        ✅ [동시성 개선] 키워드 워커 스레드를 안전하게 종료
        """
        if not self._keyword_writer_running:
            return

        logger.info("🛑 키워드 워커 종료 시작...")
        self._keyword_writer_running = False

        # 종료 신호 전송
        try:
            self._keyword_write_queue.put(None, timeout=1.0)
        except queue.Full:
            logger.warning("⚠️ 키워드 큐가 가득 참")

        # 워커 스레드 종료 대기 (최대 5초)
        if self._keyword_writer_thread.is_alive():
            self._keyword_writer_thread.join(timeout=5.0)
            if self._keyword_writer_thread.is_alive():
                logger.warning("⚠️ 키워드 워커가 5초 내 종료되지 않음")
            else:
                logger.info("✅ 키워드 워커 정상 종료됨")
        else:
            logger.info("✅ 키워드 워커 이미 종료됨")

    # --- Dewey Linked Data (DLD) API 자격 증명 저장/조회/삭제 ---
    def get_dewey_api_credentials(
        self,
    ):
        """
        Returns:
            tuple[str|None, str|None]: (client_id, client_secret)
        """
        try:
            client_id = self.get_setting("dewey_client_id")
            client_secret = self.get_setting("dewey_client_secret")
            return client_id, client_secret
        except Exception as e:
            print(f"오류: DLD API 자격 증명 조회 실패: {e}")
            return None, None

    def set_dewey_api_credentials(self, client_id: str, client_secret: str) -> bool:
        """
        두 값을 각각 settings에 저장합니다.
        """
        try:
            ok1 = self.set_setting("dewey_client_id", client_id, "Dewey Client ID")
            ok2 = self.set_setting(
                "dewey_client_secret", client_secret, "Dewey Client Secret"
            )
            if ok1 and ok2:
                print(
                    "정보: DLD API 자격 증명이 데이터베이스에 안전하게 저장되었습니다."
                )
                return True
            print("오류: DLD API 자격 증명 저장 실패")
            return False
        except Exception as e:
            print(f"오류: DLD API 자격 증명 저장 실패: {e}")
            return False

    def delete_dewey_api_credentials(self) -> bool:
        """저장된 두 값을 모두 삭제합니다."""
        try:
            ok1 = self.delete_setting("dewey_client_id")
            ok2 = self.delete_setting("dewey_client_secret")
            if ok1 or ok2:
                print("정보: DLD API 자격 증명이 데이터베이스에서 삭제되었습니다.")
            return bool(ok1 or ok2)
        except Exception as e:
            print(f"오류: DLD API 자격 증명 삭제 실패: {e}")
            return False

    # AFTER (수정된 코드 - 상세한 로그 메시지 추가):
    def update_ksh_entry_by_ksh_code(self, ksh_code, field_name, new_value):
        """KSH 코드로 특정 필드 업데이트 - 삭제/수정 로그 개선"""
        conn = None
        try:
            conn = self._get_concepts_connection()
            cursor = conn.cursor()
            concept_id = f"nlk:{ksh_code}"

            # 🔧 핵심 수정: 빈 값 처리 및 상세 로그 추가
            new_value_stripped = (new_value or "").strip()

            if field_name == "main_category":
                # 먼저 기존 주제모음 이름을 가져옴
                old_category_query = (
                    "SELECT main_category FROM category_mapping WHERE concept_id = ?"
                )
                cursor.execute(old_category_query, (concept_id,))
                old_category_result = cursor.fetchone()
                old_category = old_category_result[0] if old_category_result else None

                if new_value_stripped:
                    # 🔍 디버깅: UPDATE 전 상태 확인
                    if old_category:
                        print(f"🔍 변경 전: {ksh_code}의 주제모음 = '{old_category}'")
                        # 기존 주제모음 항목 수 확인
                        count_query = "SELECT COUNT(*) FROM category_mapping WHERE main_category = ?"
                        cursor.execute(count_query, (old_category,))
                        old_count = cursor.fetchone()[0]
                        print(f"🔍 '{old_category}' 주제모음 항목 수: {old_count}개")

                    # 값이 있으면 UPDATE (명시적 DELETE 후 INSERT)
                    # 먼저 기존 행 삭제
                    delete_query = "DELETE FROM category_mapping WHERE concept_id = ?"
                    cursor.execute(delete_query, (concept_id,))

                    # 새 값으로 INSERT
                    insert_query = "INSERT INTO category_mapping (concept_id, main_category) VALUES (?, ?)"
                    cursor.execute(insert_query, (concept_id, new_value_stripped))
                    print(
                        f"✅ 정보: {ksh_code}의 주제모음을 '{old_category or '없음'}' → '{new_value_stripped}'로 변경했습니다."
                    )

                    # 기존 주제모음이 비어있게 되었는지 확인하고 정리
                    if old_category and old_category != new_value_stripped:
                        # 기존 주제모음을 사용하는 다른 항목이 있는지 확인
                        check_query = "SELECT COUNT(*) FROM category_mapping WHERE main_category = ?"
                        cursor.execute(check_query, (old_category,))
                        count = cursor.fetchone()[0]
                        print(
                            f"🔍 변경 후: '{old_category}' 주제모음 남은 항목 수: {count}개"
                        )
                        if count == 0:
                            print(
                                f"🗑️ 정보: '{old_category}' 주제모음이 비어있어 자동 정리되었습니다."
                            )
                else:
                    # 값이 비어있으면 DELETE (완전 삭제)
                    query = "DELETE FROM category_mapping WHERE concept_id = ?"
                    cursor.execute(query, (concept_id,))
                    affected_rows = cursor.rowcount
                    if affected_rows > 0:
                        print(
                            f"🗑️ 정보: {ksh_code}의 주제모음 매핑을 삭제했습니다. (삭제된 행: {affected_rows}개)"
                        )

                        # 기존 주제모음이 비어있게 되었는지 확인
                        if old_category:
                            check_query = "SELECT COUNT(*) FROM category_mapping WHERE main_category = ?"
                            cursor.execute(check_query, (old_category,))
                            count = cursor.fetchone()[0]
                            if count == 0:
                                print(
                                    f"🗑️ 정보: '{old_category}' 주제모음이 비어있어 자동 정리되었습니다."
                                )
                    else:
                        print(f"ℹ️ 정보: {ksh_code}의 주제모음 매핑이 이미 없습니다.")

            elif field_name == "classification_ddc":
                if new_value_stripped:
                    query = "INSERT OR REPLACE INTO ddc_mapping (concept_id, ddc_classification) VALUES (?, ?)"
                    cursor.execute(query, (concept_id, new_value_stripped))
                    print(
                        f"✅ 정보: {ksh_code}의 DDC 분류를 '{new_value_stripped}'로 설정했습니다."
                    )
                else:
                    query = "DELETE FROM ddc_mapping WHERE concept_id = ?"
                    cursor.execute(query, (concept_id,))
                    affected_rows = cursor.rowcount
                    if affected_rows > 0:
                        print(
                            f"🗑️ 정보: {ksh_code}의 DDC 분류 매핑을 삭제했습니다. (삭제된 행: {affected_rows}개)"
                        )
                    else:
                        print(f"ℹ️ 정보: {ksh_code}의 DDC 분류 매핑이 이미 없습니다.")

            elif field_name == "classification_kdc_like":
                if new_value_stripped:
                    query = "INSERT OR REPLACE INTO kdc_mapping (concept_id, kdc_like_classification) VALUES (?, ?)"
                    cursor.execute(query, (concept_id, new_value_stripped))
                    print(
                        f"✅ 정보: {ksh_code}의 KDC-Like 분류를 '{new_value_stripped}'로 설정했습니다."
                    )
                else:
                    query = "DELETE FROM kdc_mapping WHERE concept_id = ?"
                    cursor.execute(query, (concept_id,))
                    affected_rows = cursor.rowcount
                    if affected_rows > 0:
                        print(
                            f"🗑️ 정보: {ksh_code}의 KDC-Like 분류 매핑을 삭제했습니다. (삭제된 행: {affected_rows}개)"
                        )
                    else:
                        print(
                            f"ℹ️ 정보: {ksh_code}의 KDC-Like 분류 매핑이 이미 없습니다."
                        )
            else:
                print(f"⚠️ 경고: 알 수 없는 필드명: {field_name}")
                return False

            conn.commit()
            return True

        except Exception as e:
            if conn:
                conn.rollback()
            print(f"❌ 오류: KSH 항목 업데이트 실패 ({ksh_code}, {field_name}): {e}")
            return False
        finally:
            if conn:
                conn.close()

    # ========================================
    # DDC 캐시 관리 유틸리티 함수들
    # ========================================

    def get_dewey_cache_stats(self):
        """DDC 캐시 통계 정보 반환"""
        conn = None
        try:
            conn = self._get_dewey_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    SUM(hit_count) as total_hits,
                    SUM(file_size) as total_size_bytes,
                    MIN(last_updated) as oldest_entry,
                    MAX(last_updated) as newest_entry
                FROM dewey_cache
            """
            )

            result = cursor.fetchone()
            if result:
                return {
                    "total_entries": result[0],
                    "total_hits": result[1],
                    "total_size_mb": (
                        round(result[2] / (1024 * 1024), 2) if result[2] else 0
                    ),
                    "oldest_entry": result[3],
                    "newest_entry": result[4],
                }
            return {}

        except Exception as e:
            print(f"오류: DDC 캐시 통계 조회 실패: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def cleanup_dewey_cache(self, days_old=30):
        """오래된 DDC 캐시 항목 정리"""
        conn = None
        try:
            conn = self._get_dewey_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                DELETE FROM dewey_cache
                WHERE last_updated < datetime('now', '-{} days')
                AND hit_count < 2
            """.format(
                    days_old
                )
            )

            deleted_count = cursor.rowcount
            conn.commit()

            print(f"정보: {deleted_count}개의 오래된 DDC 캐시 항목을 삭제했습니다.")
            return deleted_count

        except Exception as e:
            print(f"오류: DDC 캐시 정리 실패: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    def export_dewey_cache(self, export_path: str):
        """DDC 캐시를 다른 경로로 복사 (공유용)"""
        try:
            import shutil

            shutil.copy2(self.dewey_db_path, export_path)
            print(f"정보: DDC 캐시를 '{export_path}'로 내보냈습니다.")
            return True
        except Exception as e:
            print(f"오류: DDC 캐시 내보내기 실패: {e}")
            return False

    def import_dewey_cache(self, import_path: str, merge=True):
        """외부 DDC 캐시 가져오기"""
        if not os.path.exists(import_path):
            print(f"오류: 가져올 파일이 존재하지 않습니다: {import_path}")
            return False

        try:
            if merge:
                # 기존 캐시와 병합
                import_conn = sqlite3.connect(import_path)
                local_conn = self._get_dewey_connection()

                # 가져오기 로직 구현
                # ... 병합 코드 ...

            else:
                # 완전 교체
                import shutil

                backup_path = f"{self.dewey_db_path}.backup"
                shutil.move(self.dewey_db_path, backup_path)
                shutil.copy2(import_path, self.dewey_db_path)
                print(f"정보: DDC 캐시를 '{import_path}'에서 가져왔습니다.")
                print(f"정보: 기존 캐시는 '{backup_path}'에 백업되었습니다.")

            return True

        except Exception as e:
            print(f"오류: DDC 캐시 가져오기 실패: {e}")
            return False

    def get_all_ddc_keywords_by_numbers(self, ddc_numbers: list[str]) -> list:
        """
        ✅ [신규 최적화] DDC 번호 리스트를 받아 ddc_keyword 테이블에서 모든 관련 데이터를 조회합니다.
        SearchQueryManager의 get_all_ddc_labels_bulk가 호출하는 실제 DB 접근 함수입니다.
        """
        if not ddc_numbers:
            return []

        conn = None
        all_results = []
        CHUNK_SIZE = 100  # ✅ [핵심 추가] 100개씩 청크로 분할

        try:
            # DDC 캐시 DB에 연결
            conn = self._get_dewey_connection()
            cursor = conn.cursor()

            # -------------------
            # ✅ [핵심 수정] 청크로 분할하여 쿼리를 실행합니다.
            for i in range(0, len(ddc_numbers), CHUNK_SIZE):
                chunk = ddc_numbers[i:i + CHUNK_SIZE]
                placeholders = ",".join("?" for _ in chunk)

                query = f"""
                    SELECT ddc, keyword, term_type
                    FROM ddc_keyword
                    WHERE ddc IN ({placeholders})
                """
                cursor.execute(query, chunk)
                all_results.extend(cursor.fetchall())

            # (ddc, keyword, term_type) 형태의 튜플 리스트를 반환
            return all_results
            # -------------------

        except Exception as e:
            logger.error(f"❌ DDC 키워드 대량 조회 실패: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_all_db_statistics(self) -> dict:
        """
        ✅ [신규 추가] 앱에 연결된 모든 데이터베이스의 통계 정보를 종합하여 반환합니다.
        """
        stats = {}

        # 1. KSH 개념 DB (nlk_concepts.sqlite)
        try:
            conn = self._get_concepts_connection()
            count = conn.execute(
                "SELECT COUNT(*) FROM concepts WHERE concept_id LIKE 'nlk:KSH%'"
            ).fetchone()[0]
            conn.close()
            stats["concepts_db"] = {
                "path": self.concepts_db_path,
                "ksh_concept_count": count,
            }
        except Exception as e:
            stats["concepts_db"] = {"path": self.concepts_db_path, "error": str(e)}

        # 2. 서지 매핑 DB (kdc_ddc_mapping.db)
        try:
            conn = self._get_mapping_connection()
            count = conn.execute("SELECT COUNT(*) FROM mapping_data").fetchone()[0]
            conn.close()
            stats["mapping_db"] = {
                "path": self.kdc_ddc_mapping_db_path,
                "biblio_count": count,
            }
        except Exception as e:
            stats["mapping_db"] = {
                "path": self.kdc_ddc_mapping_db_path,
                "error": str(e),
            }

        # 3. DDC 캐시 DB (dewey_cache.db) - 기존 통계 함수 재활용
        try:
            dewey_stats = self.get_dewey_cache_stats()
            stats["dewey_cache_db"] = {"path": self.dewey_db_path, "stats": dewey_stats}
        except Exception as e:
            stats["dewey_cache_db"] = {"path": self.dewey_db_path, "error": str(e)}

        # 4. 용어/설정 DB (glossary.db)
        try:
            conn = self._get_glossary_connection()
            trans_count = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[
                0
            ]
            settings_count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
            conn.close()
            stats["glossary_db"] = {
                "path": self.glossary_db_path,
                "translation_count": trans_count,
                "settings_count": settings_count,
            }
        except Exception as e:
            stats["glossary_db"] = {"path": self.glossary_db_path, "error": str(e)}

        return stats


# 모듈이 직접 실행될 때 (테스트용)
if __name__ == "__main__":
    import re  # KSH 코드 추출용

    # -------------------
    # [핵심] 새로운 생성자 규칙에 맞게 두 개의 DB 경로를 전달하도록 수정합니다.
    concepts_path = "nlk_concepts.sqlite"
    mapping_path = "kdc_ddc_mapping.db"

    db = DatabaseManager(
        concepts_db_path=concepts_path, kdc_ddc_mapping_db_path=mapping_path
    )
    # -------------------
    db.initialize_databases()

    print("\n--- KSH 검색 테스트 ---")
    df = db.get_ksh_entries(search_term="파이썬", limit=5)

    if df.empty:
        print("검색 결과 없음")
    else:
        # get_ksh_entries가 실제로 반환하는 컬럼들만 출력
        show_cols = [
            c
            for c in [
                "subject",
                "matched",
                "main_category",
                "classification_ddc",
                "classification_kdc_like",
                "ksh_link_url",
                "synonyms",
            ]
            if c in df.columns
        ]
        print(df[show_cols].head())

        # 첫 결과에서 KSH 코드 추출 (ksh_link_url 우선, 없으면 subject 포맷에서)
        row0 = df.iloc[0]
        ksh_code = None
        if "ksh_link_url" in df.columns and pd.notna(row0.get("ksh_link_url", "")):
            m = re.search(r"controlNo=([A-Za-z0-9]+)", str(row0["ksh_link_url"]))
            if m:
                ksh_code = m.group(1)
        if not ksh_code:
            m = re.search(r"▼0([A-Za-z0-9]+)▲", str(row0.get("subject", "")))
            if m:
                ksh_code = m.group(1)

        # KSH 매핑 업데이트 테스트 (새로운 API)
        if ksh_code:
            print(f"\n--- KSH 매핑 업데이트 테스트 (KSH: {ksh_code}) ---")
            ok = db.update_ksh_entry_by_ksh_code(
                ksh_code, "main_category", "테스트 주제"
            )
            print("업데이트 성공 여부:", ok)
        else:
            print("KSH 코드 추출 실패: 업데이트 테스트 생략")

    print("\n--- 용어집 테스트 ---")
    all_glossary = db.get_all_custom_translations()
    print(f"현재 용어집: {all_glossary}")

import faiss
import numpy as np
import json # ✅ json 임포트 추가
from database_manager import DatabaseManager

class VectorDDCManager(DatabaseManager):
    def __init__(self, concepts_db_path, kdc_ddc_mapping_db_path):
        super().__init__(concepts_db_path, kdc_ddc_mapping_db_path)
        # ✅ 지연 로딩: 실제 검색 시점에 모델을 로드합니다
        self.vector_model = None
        self.vector_index = None
        self.ddc_mapping = {}
        self._model_loaded = False
        # ✅ 앱 시작 시 생성 대신 '로드' 하도록 변경
        self._load_vector_db()

    def _ensure_model_loaded(self):
        """필요할 때만 SentenceTransformer 모델을 로드합니다 (지연 로딩)"""
        if self._model_loaded:
            return

        try:
            from sentence_transformers import SentenceTransformer
            import torch

            # ✅ build_vector_db.py와 동일한 모델 사용 (모델 통일)
            # GPU 사용 가능하면 GPU 사용 (훨씬 빠름)
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

            # ⚡ 성능 최적화: all-MiniLM-L6-v2는 mpnet보다 5배 빠르고 정확도는 95% 유지
            # mpnet: 109M params, 25초 | MiniLM: 22M params, ~1초
            self.vector_model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
            self._model_loaded = True
            print(f"✅ SentenceTransformer 모델을 로드했습니다 (all-MiniLM-L6-v2, device: {device})")
        except ImportError:
            print("⚠️ sentence-transformers 라이브러리가 설치되지 않았습니다.")
            print("   벡터 검색 기능을 사용하려면 'pip install sentence-transformers'를 실행하세요.")
        except Exception as e:
            print(f"⚠️ 모델 로드 실패: {e}")

    def _load_vector_db(self):
        """미리 생성된 faiss 인덱스와 매핑 파일을 로드합니다."""
        try:
            self.vector_index = faiss.read_index("ddc_index_from_json.faiss")
            with open("ddc_mapping_from_json.json", "r", encoding="utf-8") as f:
                # JSON은 키를 문자열로 저장하므로, 로드 후 다시 정수 키로 변환해야 합니다.
                loaded_mapping = json.load(f)
                self.ddc_mapping = {int(k): v for k, v in loaded_mapping.items()}
            
            # self.log_message("✅ DDC 벡터 DB를 성공적으로 로드했습니다.", "INFO") # 로거가 있다면 사용
            print("✅ DDC 벡터 DB를 성공적으로 로드했습니다.")

        except Exception as e:
            # self.log_message(f"⚠️ DDC 벡터 DB 로드 실패: {e}. build_vector_db.py를 실행해야 합니다.", "WARNING")
            print(f"⚠️ DDC 벡터 DB 로드 실패: {e}. build_vector_db.py를 실행해야 합니다.")

    def search_ddc_by_vector(self, query: str, top_k: int = 5) -> list:
        if not self.vector_index:
            print("오류: 벡터 인덱스가 로드되지 않았습니다.")
            return []

        # ✅ [핵심] 검색 시점에 모델을 로드합니다
        self._ensure_model_loaded()

        if not self.vector_model:
            print("오류: SentenceTransformer 모델을 로드할 수 없습니다.")
            return []

        query_embedding = self.vector_model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True # 검색 시에도 정규화
        )
        
        distances, indices = self.vector_index.search(query_embedding.astype('float32'), top_k)
        
        results = []
        for j, i in enumerate(indices[0]):
            if i in self.ddc_mapping:
                # ✅ 매핑 구조가 딕셔너리로 변경되었으므로 수정
                data = self.ddc_mapping[i]
                results.append({
                    "ddc": data["ddc"],
                    "label": data.get("prefLabel", ""),  # prefLabel을 label로 매핑
                    "document": data.get("document", ""),  # 전체 문서 내용
                    "similarity": float(distances[0][j])  # 유사도 점수 (1에 가까울수록 유사)
                })
        return results