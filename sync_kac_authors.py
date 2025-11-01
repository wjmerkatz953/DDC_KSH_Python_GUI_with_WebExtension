# -*- coding: utf-8 -*-
"""
파일명: sync_kac_authors.py
Version: 1.0.0
생성일: 2025-11-01

KAC 저자명 동기화 스크립트
nlk_biblio.sqlite의 kac_codes와 NLK_Authorities.sqlite를 조인하여
KAC 순서대로 정확한 저자명을 kac_authors 컬럼에 추가

작업 목표:
1. nlk_biblio.sqlite의 biblio 테이블에서 kac_codes 추출
2. NLK_Authorities.sqlite의 authority 테이블에서 해당 pref_label 조회
3. "저자명 KAC코드" 형태의 kac_authors 컬럼 생성
4. KAC 코드 순서와 100% 일치하는 저자명 제공

기존 author_names 컬럼 문제:
- KAC 코드 순서와 불일치
- 공저자 있는 경우 신뢰성 없음

새 kac_authors 컬럼 장점:
- KAC 코드 순서 100% 일치
- authority DB에서 직접 조회한 정확한 저자명
- FTS5 검색 가능

작업자: Claude Code
"""
import sqlite3
import logging
from typing import List, Optional
from pathlib import Path
from tqdm import tqdm

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("sync_kac_authors.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class KACAuthorSyncer:
    """KAC 코드와 저자명을 동기화하는 클래스"""

    def __init__(
        self,
        biblio_db_path: str = "nlk_biblio.sqlite",
        authority_db_path: str = "NLK_Authorities.sqlite",
    ):
        """
        초기화

        Args:
            biblio_db_path: 서지 데이터베이스 경로
            authority_db_path: 전거 데이터베이스 경로
        """
        self.biblio_db_path = biblio_db_path
        self.authority_db_path = authority_db_path

        # KAC → 저자명 캐시 (성능 최적화)
        self._kac_cache = {}

        # 데이터베이스 파일 존재 확인
        self._verify_database_files()

    def _verify_database_files(self):
        """데이터베이스 파일들이 존재하는지 확인"""
        for db_path in [self.biblio_db_path, self.authority_db_path]:
            if not Path(db_path).exists():
                raise FileNotFoundError(
                    f"데이터베이스 파일을 찾을 수 없습니다: {db_path}"
                )
        logger.info("✅ 모든 데이터베이스 파일 확인 완료")

    def _parse_kac_codes(self, kac_codes: str) -> List[str]:
        """
        KAC 코드 문자열을 리스트로 파싱합니다.

        Args:
            kac_codes: "KAC2020H3683;KAC200610166" 형태의 문자열

        Returns:
            KAC 코드 리스트 (예: ['KAC2020H3683', 'KAC200610166'])
        """
        if not kac_codes:
            return []

        # 세미콜론으로 분리 후 공백 제거
        codes = [code.strip() for code in kac_codes.split(";") if code.strip()]
        return codes

    def _get_kac_author(self, kac_code: str, authority_cursor=None) -> Optional[str]:
        """
        KAC 코드에 해당하는 저자명을 조회합니다 (캐시 사용).

        Args:
            kac_code: KAC 코드 (예: 'KAC2020H3683')
            authority_cursor: 재사용할 Authority DB 커서 (선택)

        Returns:
            저자명 (pref_label) 또는 None
        """
        # 캐시 확인
        if kac_code in self._kac_cache:
            return self._kac_cache[kac_code]

        # 캐시에 없으면 DB 조회
        try:
            # 커서가 제공되면 재사용, 아니면 새 연결
            if authority_cursor:
                cursor = authority_cursor
            else:
                conn = sqlite3.connect(self.authority_db_path)
                cursor = conn.cursor()

            # pref_label 조회 (kac_id로 검색, nlk: 프리픽스는 이미 제거됨)
            cursor.execute(
                "SELECT pref_label FROM authority WHERE kac_id = ? LIMIT 1",
                (kac_code,),
            )
            result = cursor.fetchone()

            # 새 연결을 만들었으면 닫기
            if not authority_cursor:
                conn.close()

            if result and result[0]:
                author_name = result[0].strip()
                # 캐시에 저장
                self._kac_cache[kac_code] = author_name
                return author_name

        except Exception as e:
            logger.warning(f"저자명 조회 실패 - {kac_code}: {e}")

        # 조회 실패도 캐시 (반복 조회 방지)
        self._kac_cache[kac_code] = None
        return None

    def _rebuild_fts5_with_kac_authors(self, conn: sqlite3.Connection):
        """
        FTS5 테이블을 재구축하여 kac_authors를 포함시킵니다.

        Args:
            conn: 이미 열린 biblio DB 연결
        """
        cursor = conn.cursor()

        try:
            # [1단계] 기존 FTS5 및 트리거 제거
            logger.info("  [1/5] 기존 FTS5 테이블 제거 중...")
            cursor.execute("DROP TRIGGER IF EXISTS biblio_ai")
            cursor.execute("DROP TRIGGER IF EXISTS biblio_au")
            cursor.execute("DROP TRIGGER IF EXISTS biblio_ad")
            cursor.execute("DROP TABLE IF EXISTS biblio_title_fts")

            # [2단계] 새 FTS5 테이블 생성 (kac_authors 포함)
            logger.info("  [2/5] 새 FTS5 테이블 생성 중 (kac_authors 포함)...")
            cursor.execute(
                """
                CREATE VIRTUAL TABLE biblio_title_fts USING fts5(
                    nlk_id UNINDEXED,
                    title,
                    author_names,
                    kac_codes,
                    kac_authors,
                    content='biblio',
                    content_rowid='rowid',
                    tokenize='unicode61 remove_diacritics 2'
                )
            """
            )

            # [3단계] 트리거 생성
            logger.info("  [3/5] 트리거 생성 중...")
            cursor.execute(
                """
                CREATE TRIGGER biblio_ai AFTER INSERT ON biblio BEGIN
                    INSERT INTO biblio_title_fts(rowid, nlk_id, title, author_names, kac_codes, kac_authors)
                    VALUES (new.rowid, new.nlk_id, new.title, new.author_names, new.kac_codes, new.kac_authors);
                END
            """
            )

            cursor.execute(
                """
                CREATE TRIGGER biblio_ad AFTER DELETE ON biblio BEGIN
                    DELETE FROM biblio_title_fts WHERE rowid = old.rowid;
                END
            """
            )

            cursor.execute(
                """
                CREATE TRIGGER biblio_au AFTER UPDATE ON biblio BEGIN
                    UPDATE biblio_title_fts
                    SET title = new.title,
                        author_names = new.author_names,
                        kac_codes = new.kac_codes,
                        kac_authors = new.kac_authors
                    WHERE rowid = new.rowid;
                END
            """
            )

            # [4단계] REBUILD (기존 데이터 인덱싱)
            logger.info("  [4/5] FTS5 인덱스 재구축 중... (시간이 걸릴 수 있습니다)")
            cursor.execute(
                "INSERT INTO biblio_title_fts(biblio_title_fts) VALUES('rebuild')"
            )

            # [5단계] 최적화
            logger.info("  [5/5] 최적화 중...")
            cursor.execute(
                "INSERT INTO biblio_title_fts(biblio_title_fts) VALUES('optimize')"
            )

            conn.commit()

        except Exception as e:
            logger.error(f"FTS5 재구축 실패: {e}")
            raise

    def _create_kac_authors_column(self, kac_codes: str, authority_cursor=None) -> str:
        """
        KAC 코드를 "저자명 KAC코드" 형태로 변환합니다.

        Args:
            kac_codes: 원본 KAC 코드 (예: "KAC2020H3683;KAC200610166")
            authority_cursor: 재사용할 Authority DB 커서 (선택)

        Returns:
            저자명이 결합된 문자열 (예: "후수자오 KAC2020H3683;리더주 KAC200610166")
        """
        if not kac_codes:
            return ""

        # KAC 코드 파싱
        codes = self._parse_kac_codes(kac_codes)
        if not codes:
            return ""

        # 각 KAC 코드에 대해 저자명 조회 및 결합
        author_parts = []
        for kac_code in codes:
            author_name = self._get_kac_author(kac_code, authority_cursor)
            if author_name:
                # "저자명 KAC코드" 형태로 결합
                author_part = f"{author_name} {kac_code}"
            else:
                # 저자명이 없으면 코드만 사용
                author_part = kac_code
            author_parts.append(author_part)

        # 여러 KAC 코드가 있을 경우 세미콜론으로 구분
        return ";".join(author_parts)

    def add_kac_authors_column(self):
        """
        biblio 테이블에 kac_authors 컬럼을 추가하고 데이터를 채웁니다.

        이어하기(Resume): 이미 처리된 행은 건너뛰고, 아직 비어있는 행만 처리합니다.
        """
        logger.info("KAC 저자명 동기화 작업 시작")

        try:
            with sqlite3.connect(self.biblio_db_path) as conn:
                cursor = conn.cursor()

                # PRAGMA 튜닝 (성능 최적화)
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA temp_store=MEMORY;")
                cursor.execute("PRAGMA mmap_size=268435456;")  # 256MB

                # 1. 새 컬럼 추가 (이미 존재하면 무시)
                try:
                    cursor.execute("ALTER TABLE biblio ADD COLUMN kac_authors TEXT")
                    logger.info("kac_authors 컬럼 추가 완료")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.info("kac_authors 컬럼이 이미 존재합니다")
                    else:
                        raise

                # 필수 인덱스 선생성 (시작 지연 방지)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_biblio_kac_codes ON biblio(kac_codes);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_biblio_kac_authors ON biblio(kac_authors);"
                )
                conn.commit()

                # 2. 전체/대상 레코드 수 확인
                cursor.execute(
                    "SELECT COUNT(*) FROM biblio WHERE kac_codes IS NOT NULL AND kac_codes != ''"
                )
                total_records = cursor.fetchone()[0]

                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM biblio
                    WHERE kac_codes IS NOT NULL AND kac_codes != ''
                      AND (kac_authors IS NULL OR kac_authors = '')
                    """
                )
                pending_records = cursor.fetchone()[0]
                logger.info(
                    f"전체 KAC 보유: {total_records:,}개 / 처리 대상(미처리): {pending_records:,}개"
                )

                if pending_records == 0:
                    logger.info(
                        "처리할 대상이 없습니다. 이미 모든 레코드가 동기화되었습니다."
                    )
                    return

                # 3. 배치 단위로 처리
                batch_size = 300000  # 배치 크기 증가 (10K → 50K → 300K)
                processed = 0
                updated = 0

                logger.info(f"💾 캐시 초기화 완료 (메모리 사용)")
                logger.info(f"⚡ 배치 크기: {batch_size:,}개")

                # Authority DB 연결 생성 (재사용)
                logger.info(f"🔗 Authority DB 연결 생성 (재사용 모드)")
                authority_conn = sqlite3.connect(self.authority_db_path)
                authority_cursor = authority_conn.cursor()

                # tqdm 진행률 표시
                pbar = tqdm(total=pending_records, desc="KAC 저자명 동기화", unit="row")

                # 대상 행만 선택 + 정렬(안정적 진행/재실행)
                # 별도 커서 사용 (UPDATE와 SELECT 충돌 방지)
                select_cursor = conn.cursor()
                select_cursor.execute(
                    """
                    SELECT rowid, kac_codes
                    FROM biblio
                    WHERE kac_codes IS NOT NULL AND kac_codes != ''
                      AND (kac_authors IS NULL OR kac_authors = '')
                    ORDER BY rowid
                    """
                )

                while True:
                    rows = select_cursor.fetchmany(batch_size)
                    if not rows:
                        break

                    updates = []
                    for rowid, kac_codes in rows:
                        # Authority 커서 전달 (연결 재사용)
                        kac_authors = self._create_kac_authors_column(
                            kac_codes, authority_cursor
                        )
                        updates.append((kac_authors, rowid))
                        processed += 1
                        pbar.update(1)

                        if kac_authors:  # 실제로 저자명이 추가된 경우만 카운트
                            updated += 1

                    # 배치 업데이트 실행
                    cursor.executemany(
                        "UPDATE biblio SET kac_authors = ? WHERE rowid = ?",
                        updates,
                    )

                    # 주기적 커밋으로 안전성 확보
                    conn.commit()

                # tqdm 종료
                pbar.close()
                select_cursor.close()

                # Authority DB 연결 닫기
                authority_cursor.close()
                authority_conn.close()
                logger.info(f"🔗 Authority DB 연결 종료")

                conn.commit()

                logger.info(f"\n✅ KAC 저자명 동기화 완료!")
                logger.info(
                    f"처리 결과: 총 {processed:,}개 처리, {updated:,}개 업데이트"
                )

                # 4. FTS5에 kac_authors 자동 추가
                logger.info("\n🔧 FTS5 인덱스에 kac_authors 추가 중...")
                self._rebuild_fts5_with_kac_authors(conn)
                logger.info("✅ FTS5 인덱스 재구축 완료!")

                return processed, updated

        except Exception as e:
            logger.error(f"KAC 저자명 동기화 실패: {e}")
            raise

    def get_statistics(self):
        """동기화 통계 정보를 반환합니다."""
        stats = {
            "total_records": 0,
            "kac_records": 0,
            "synced_records": 0,
            "unsynced_records": 0,
            "column_exists": False,
        }

        try:
            with sqlite3.connect(self.biblio_db_path) as conn:
                cursor = conn.cursor()

                # 전체 레코드 수
                cursor.execute("SELECT COUNT(*) FROM biblio")
                stats["total_records"] = cursor.fetchone()[0]

                # KAC 코드가 있는 레코드 수
                cursor.execute(
                    "SELECT COUNT(*) FROM biblio WHERE kac_codes IS NOT NULL AND kac_codes != ''"
                )
                stats["kac_records"] = cursor.fetchone()[0]

                # kac_authors 컬럼 존재 여부 확인
                cursor.execute("PRAGMA table_info(biblio)")
                columns = [row[1] for row in cursor.fetchall()]
                stats["column_exists"] = "kac_authors" in columns

                if stats["column_exists"]:
                    # 동기화된 레코드 수
                    cursor.execute(
                        "SELECT COUNT(*) FROM biblio WHERE kac_authors IS NOT NULL AND kac_authors != ''"
                    )
                    stats["synced_records"] = cursor.fetchone()[0]
                else:
                    stats["synced_records"] = 0

                # 미동기화 레코드 수
                stats["unsynced_records"] = (
                    stats["kac_records"] - stats["synced_records"]
                )

        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")

        return stats

    def sample_results(self, limit: int = 5):
        """샘플 결과를 출력합니다."""
        try:
            with sqlite3.connect(self.biblio_db_path) as conn:
                cursor = conn.cursor()

                # kac_authors 컬럼 존재 여부 확인
                cursor.execute("PRAGMA table_info(biblio)")
                columns = [row[1] for row in cursor.fetchall()]

                if "kac_authors" in columns:
                    cursor.execute(
                        """
                        SELECT title, author_names, kac_codes, kac_authors
                        FROM biblio
                        WHERE kac_codes IS NOT NULL AND kac_codes != ''
                        AND kac_authors IS NOT NULL AND kac_authors != ''
                        ORDER BY RANDOM()
                        LIMIT ?
                    """,
                        (limit,),
                    )

                    samples = cursor.fetchall()
                    logger.info("\n📋 샘플 결과:")
                    for i, (title, author_names, kac_codes, kac_authors) in enumerate(
                        samples, 1
                    ):
                        logger.info(f"\n{i}. 제목: {title[:50]}...")
                        logger.info(f"   기존 author_names: {author_names}")
                        logger.info(f"   KAC 코드: {kac_codes}")
                        logger.info(f"   ✅ 새 kac_authors: {kac_authors}")
                else:
                    logger.info("kac_authors 컬럼이 아직 생성되지 않았습니다")

        except Exception as e:
            logger.error(f"샘플 조회 실패: {e}")


def main():
    """메인 실행 함수"""
    try:
        # KAC 저자명 동기화 생성
        syncer = KACAuthorSyncer()

        # 현재 상태 확인
        logger.info("현재 데이터베이스 상태 확인")
        stats = syncer.get_statistics()
        logger.info(f"  - 전체 레코드: {stats['total_records']:,}개")
        logger.info(f"  - KAC 코드 보유: {stats['kac_records']:,}개")

        if stats["column_exists"]:
            logger.info(f"  - 동기화 완료: {stats['synced_records']:,}개")
            logger.info(f"  - 동기화 필요: {stats['unsynced_records']:,}개")
        else:
            logger.info("  - kac_authors 컬럼: 아직 생성되지 않음")
            logger.info(f"  - 동기화 필요: {stats['kac_records']:,}개")

        # 동기화 실행 여부 확인
        needs_sync = stats["unsynced_records"] > 0 or not stats["column_exists"]

        if needs_sync:
            sync_count = (
                stats["unsynced_records"]
                if stats["column_exists"]
                else stats["kac_records"]
            )
            user_input = input(
                f"\n{sync_count:,}개 레코드에 KAC 저자명을 동기화하시겠습니까? (y/N): "
            )
            if user_input.lower() in ["y", "yes", "ㅇ"]:
                syncer.add_kac_authors_column()

                # 결과 재확인
                logger.info("\n동기화 완료 후 상태")
                final_stats = syncer.get_statistics()
                logger.info(f"  - 동기화 완료: {final_stats['synced_records']:,}개")
                logger.info(f"  - 동기화 필요: {final_stats['unsynced_records']:,}개")

                # 샘플 결과 출력
                syncer.sample_results(5)
            else:
                logger.info("동기화 작업을 취소했습니다")
        else:
            logger.info("모든 레코드가 이미 동기화되어 있습니다")
            # 샘플만 출력
            syncer.sample_results(5)

    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
