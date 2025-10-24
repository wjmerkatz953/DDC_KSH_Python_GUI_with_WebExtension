# -*- coding: utf-8 -*-
"""
KSH 레이블 매핑 스크립트
kdc_ddc_mapping.db의 KSH 코드에 nlk_concepts.sqlite의 레이블을 결합하여
새로운 정규 컬럼을 생성하는 스크립트

작업 목표:
1. kdc_ddc_mapping.db의 mapping_data 테이블에서 KSH 코드 추출
2. nlk_concepts.sqlite의 literal_props에서 해당 레이블 조회
3. "레이블 + KSH코드" 형태의 새로운 컬럼 생성
4. 추후 업데이트를 위한 인덱스 및 함수 제공

실행일: 2025-08-30
작성자: 메르카츠
"""

import sqlite3
import re
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from tqdm import tqdm  # tqdm 라이브러리 임포트

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("ksh_label_mapping.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class KSHLabelMapper:
    """KSH 코드와 레이블을 매핑하여 새로운 컬럼을 생성하는 클래스"""

    def __init__(
        self,
        mapping_db_path: str = "kdc_ddc_mapping.db",
        concepts_db_path: str = "nlk_concepts.sqlite",
    ):
        """
        초기화

        Args:
            mapping_db_path: 매핑 데이터베이스 경로
            concepts_db_path: 개념 데이터베이스 경로
        """
        self.mapping_db_path = mapping_db_path
        self.concepts_db_path = concepts_db_path

        # 데이터베이스 파일 존재 확인
        self._verify_database_files()

    def _verify_database_files(self):
        """데이터베이스 파일들이 존재하는지 확인"""
        for db_path in [self.mapping_db_path, self.concepts_db_path]:
            if not Path(db_path).exists():
                raise FileNotFoundError(
                    f"데이터베이스 파일을 찾을 수 없습니다: {db_path}"
                )
        logger.info("✅ 모든 데이터베이스 파일 확인 완료")

    def _extract_ksh_codes_from_text(self, text: str) -> List[str]:
        """
        텍스트에서 KSH 코드를 완벽하게 추출합니다.

        Args:
            text: KSH 코드가 포함된 텍스트

        Returns:
            KSH 코드 리스트 (예: ['KSH1997000392', 'KSH1998027764'])
        """
        if not text:
            return []

        # KSH 코드 패턴을 정확하게 지원 (KSH + 10자리 숫자)
        patterns = [
            r"KSH\d{10}",  # 기본 KSH 패턴 - KSH + 10자리 숫자
            r"▼0(KSH\d{10})▲",  # 포맷된 KSH 패턴
            r"nlk:(KSH\d{10})",  # 네임스페이스 포함 패턴
        ]

        ksh_codes = []
        for pattern in patterns:
            if "(" in pattern:  # 그룹이 있는 패턴
                matches = re.findall(pattern, text)
                ksh_codes.extend(matches)
            else:  # 직접 매치 패턴
                matches = re.findall(pattern, text)
                ksh_codes.extend(matches)

        # 중복 제거하고 정렬
        return sorted(list(set(ksh_codes)))

    def _get_ksh_label(self, ksh_code: str) -> Optional[str]:
        """
        KSH 코드에 해당하는 레이블을 조회합니다.

        Args:
            ksh_code: KSH 코드 (예: 'KSH199000001')

        Returns:
            레이블 문자열 또는 None
        """
        concept_id = f"nlk:{ksh_code}"

        try:
            with sqlite3.connect(self.concepts_db_path) as conn:
                cursor = conn.cursor()

                # prefLabel 우선 조회
                cursor.execute(
                    "SELECT value FROM literal_props WHERE concept_id = ? AND prop = 'prefLabel' LIMIT 1",
                    (concept_id,),
                )
                result = cursor.fetchone()
                if result and result[0]:
                    return result[0].strip()

                # prefLabel이 없으면 label 조회
                cursor.execute(
                    "SELECT value FROM literal_props WHERE concept_id = ? AND prop = 'label' LIMIT 1",
                    (concept_id,),
                )
                result = cursor.fetchone()
                if result and result[0]:
                    return result[0].strip()

        except Exception as e:
            logger.warning(f"레이블 조회 실패 - {ksh_code}: {e}")

        return None

    def _create_labeled_ksh_column(self, ksh_text: str) -> str:
        """
        KSH 텍스트를 "레이블[한자] - 코드" 형태로 변환합니다.

        Args:
            ksh_text: 원본 KSH 텍스트

        Returns:
            레이블이 결합된 KSH 텍스트 (예: "당시(시)[唐詩] - KSH2002034702")
        """
        if not ksh_text:
            return ""

        # KSH 코드들을 추출
        ksh_codes = self._extract_ksh_codes_from_text(ksh_text)
        if not ksh_codes:
            return ksh_text  # KSH 코드가 없으면 원본 반환

        # 각 KSH 코드에 대해 레이블 조회 및 결합
        labeled_parts = []
        for ksh_code in ksh_codes:
            label = self._get_ksh_label(ksh_code)
            if label:
                # "레이블[한자] - 코드" 형태로 결합
                labeled_part = f"{label} - {ksh_code}"
            else:
                # 레이블이 없으면 코드만 사용
                labeled_part = ksh_code
            labeled_parts.append(labeled_part)

        # 여러 KSH 코드가 있을 경우 세미콜론으로 구분
        return "; ".join(labeled_parts)

    def add_ksh_labeled_column(self):
        """
        mapping_data 테이블에 ksh_labeled와 ksh_korean 컬럼을 추가하고 데이터를 채웁니다.
        - ksh_labeled: 완전한 형태 (한글[한자] (코드) 형태)
        - ksh_korean: 한글만 추출한 정렬용 컬럼
        """
        logger.info("KSH 레이블 매핑 작업 시작")

        try:
            with sqlite3.connect(self.mapping_db_path) as conn:
                cursor = conn.cursor()

                # 1. 새 컬럼들 추가 (이미 존재하면 무시)
                try:
                    cursor.execute(
                        "ALTER TABLE mapping_data ADD COLUMN ksh_labeled TEXT"
                    )
                    logger.info("ksh_labeled 컬럼 추가 완료")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.info("ksh_labeled 컬럼이 이미 존재합니다")
                    else:
                        raise

                try:
                    cursor.execute(
                        "ALTER TABLE mapping_data ADD COLUMN ksh_korean TEXT"
                    )
                    logger.info("ksh_korean 컬럼 추가 완료")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.info("ksh_korean 컬럼이 이미 존재합니다")
                    else:
                        raise

                # ===== BEFORE (수정 전) =====
                # # 2. 전체 레코드 수 확인
                # cursor.execute(
                #     "SELECT COUNT(*) FROM mapping_data WHERE ksh IS NOT NULL AND ksh != ''"
                # )
                # total_records = cursor.fetchone()[0]
                # logger.info(f"처리할 KSH 레코드 수: {total_records:,}개")
                #
                # # 3. 배치 단위로 처리
                # batch_size = 100
                # processed = 0
                # updated = 0
                #
                # cursor.execute(
                #     "SELECT id, ksh FROM mapping_data WHERE ksh IS NOT NULL AND ksh != ''"
                # )
                #
                # while True:
                #     rows = cursor.fetchmany(batch_size)
                #     if not rows:
                #         break
                #
                #     # 각 행에 대해 레이블 처리
                #     updates = []
                #     for row_id, ksh_text in rows:
                #         labeled_ksh = self._create_labeled_ksh_column(ksh_text)
                #         korean_only = self._extract_korean_only(labeled_ksh)
                #         updates.append((labeled_ksh, korean_only, row_id))
                #         processed += 1
                #
                #         if labeled_ksh != ksh_text:  # 실제로 변경된 경우만 카운트
                #             updated += 1
                #
                #     # 배치 업데이트 실행
                #     cursor.executemany(
                #         "UPDATE mapping_data SET ksh_labeled = ?, ksh_korean = ? WHERE id = ?",
                #         updates,
                #     )
                #
                #     # 진행상황 로그
                #     if processed % (batch_size * 5) == 0:  # 5000개마다 로그
                #         logger.info(
                #             f"진행상황: {processed:,}/{total_records:,} ({processed/total_records*100:.1f}%)"
                #         )

                # ===== AFTER (수정 후) =====
                # 2. 처리할 레코드 수 확인 (중단된 부분부터 이어하기 위해 ksh_labeled가 NULL인 것만 카운트)
                # -------------------
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM mapping_data 
                    WHERE ksh IS NOT NULL AND ksh != '' 
                    AND (ksh_labeled IS NULL OR ksh_labeled = '')
                    """
                )
                total_records = cursor.fetchone()[0]

                if total_records == 0:
                    logger.info(
                        "✅ 모든 KSH 레코드에 이미 레이블이 매핑되어 있습니다. 작업을 건너뜁니다."
                    )
                else:
                    logger.info(f"처리할 KSH 레코드 수: {total_records:,}개")

                    # 3. 배치 단위로 처리 (tqdm 적용)
                    batch_size = 1000  # 처리 속도 향상을 위해 배치 크기 증가
                    updated = 0

                    # 처리되지 않은 레코드만 선택하는 쿼리
                    cursor.execute(
                        """
                        SELECT id, ksh FROM mapping_data 
                        WHERE ksh IS NOT NULL AND ksh != '' 
                        AND (ksh_labeled IS NULL OR ksh_labeled = '')
                        """
                    )

                    with tqdm(
                        total=total_records, desc="KSH 레이블 매핑", unit="건"
                    ) as pbar:
                        while True:
                            rows = cursor.fetchmany(batch_size)
                            if not rows:
                                break

                            updates = []
                            for row_id, ksh_text in rows:
                                labeled_ksh = self._create_labeled_ksh_column(ksh_text)
                                korean_only = self._extract_korean_only(labeled_ksh)
                                updates.append((labeled_ksh, korean_only, row_id))
                                if labeled_ksh != ksh_text:
                                    updated += 1

                            cursor.executemany(
                                "UPDATE mapping_data SET ksh_labeled = ?, ksh_korean = ? WHERE id = ?",
                                updates,
                            )
                            conn.commit()  # 배치마다 커밋하여 중단 시에도 데이터 보존
                            pbar.update(len(rows))
                # -------------------

                # 4. 인덱스 생성 (성능 향상)
                try:
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_ksh_labeled ON mapping_data(ksh_labeled)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_ksh_korean ON mapping_data(ksh_korean)"
                    )
                    logger.info("인덱스 생성 완료")
                except Exception as e:
                    logger.warning(f"인덱스 생성 실패: {e}")

                conn.commit()

        except Exception as e:
            logger.error(f"KSH 레이블 매핑 실패: {e}")
            raise

        logger.info(f"KSH 레이블 매핑 완료!")
        # -------------------
        # tqdm이 진행률을 보여주므로 최종 처리 건수는 생략
        # -------------------

    def _extract_korean_only(self, labeled_text: str) -> str:
        """
        레이블 텍스트에서 한글 부분만 추출합니다.

        Args:
            labeled_text: "조선사[朝鮮史] - KSH1998006369; 조선 통신사[朝鮮通信使] - KSH2002017168"

        Returns:
            "조선사; 조선 통신사"
        """
        if not labeled_text:
            return ""

        # 각 항목을 세미콜론으로 분리
        items = [item.strip() for item in labeled_text.split(";")]
        korean_parts = []

        for item in items:
            # 한자 부분 [한자] 제거
            korean_part = re.sub(r"\[.*?\]", "", item)
            # KSH 코드 부분 - KSH코드 제거
            korean_part = re.sub(r"\s*-\s*KSH\d+", "", korean_part)
            # 앞뒤 공백 제거
            korean_part = korean_part.strip()
            if korean_part:
                korean_parts.append(korean_part)

        return "; ".join(korean_parts)

    def get_mapping_statistics(self) -> Dict[str, int]:
        """
        매핑 통계 정보를 반환합니다.

        Returns:
            통계 정보 딕셔너리
        """
        stats = {
            "total_records": 0,
            "ksh_records": 0,
            "labeled_records": 0,
            "unlabeled_records": 0,
            "column_exists": False,
        }

        try:
            with sqlite3.connect(self.mapping_db_path) as conn:
                cursor = conn.cursor()

                # 전체 레코드 수
                cursor.execute("SELECT COUNT(*) FROM mapping_data")
                stats["total_records"] = cursor.fetchone()[0]

                # KSH 필드가 있는 레코드 수
                cursor.execute(
                    "SELECT COUNT(*) FROM mapping_data WHERE ksh IS NOT NULL AND ksh != ''"
                )
                stats["ksh_records"] = cursor.fetchone()[0]

                # ksh_labeled 컬럼 존재 여부 확인
                cursor.execute("PRAGMA table_info(mapping_data)")
                columns = [row[1] for row in cursor.fetchall()]
                stats["column_exists"] = "ksh_labeled" in columns

                if stats["column_exists"]:
                    # 레이블이 있는 레코드 수
                    cursor.execute(
                        "SELECT COUNT(*) FROM mapping_data WHERE ksh_labeled IS NOT NULL AND ksh_labeled != ''"
                    )
                    stats["labeled_records"] = cursor.fetchone()[0]
                else:
                    stats["labeled_records"] = 0

                # 레이블이 없는 레코드 수
                stats["unlabeled_records"] = (
                    stats["ksh_records"] - stats["labeled_records"]
                )

        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")

        return stats

    def sample_results(self, limit: int = 10) -> List[Tuple[str, str, str]]:
        """
        샘플 결과를 반환합니다.

        Args:
            limit: 반환할 샘플 개수

        Returns:
            (title, ksh, ksh_labeled) 튜플 리스트
        """
        samples = []

        try:
            with sqlite3.connect(self.mapping_db_path) as conn:
                cursor = conn.cursor()

                # ksh_labeled 컬럼 존재 여부 확인
                cursor.execute("PRAGMA table_info(mapping_data)")
                columns = [row[1] for row in cursor.fetchall()]

                if "ksh_labeled" in columns:
                    cursor.execute(
                        """
                        SELECT title, ksh, ksh_labeled 
                        FROM mapping_data 
                        WHERE ksh IS NOT NULL AND ksh != '' 
                        AND ksh_labeled IS NOT NULL AND ksh_labeled != ''
                        ORDER BY RANDOM() 
                        LIMIT ?
                    """,
                        (limit,),
                    )
                else:
                    # ksh_labeled 컬럼이 없으면 ksh만 조회
                    cursor.execute(
                        """
                        SELECT title, ksh, '' as ksh_labeled
                        FROM mapping_data 
                        WHERE ksh IS NOT NULL AND ksh != ''
                        ORDER BY RANDOM() 
                        LIMIT ?
                    """,
                        (limit,),
                    )

                samples = cursor.fetchall()

        except Exception as e:
            logger.error(f"샘플 조회 실패: {e}")

        return samples

    def rollback_ksh_labeled_column(self):
        """
        ksh_labeled 컬럼을 완전히 제거합니다.
        """
        logger.info("🔄 기존 ksh_labeled 컬럼 롤백 시작")

        try:
            with sqlite3.connect(self.mapping_db_path) as conn:
                cursor = conn.cursor()

                # 컬럼 존재 여부 확인
                cursor.execute("PRAGMA table_info(mapping_data)")
                columns = [row[1] for row in cursor.fetchall()]

                if "ksh_labeled" in columns:
                    # SQLite에서는 컬럼을 직접 DROP할 수 없으므로 테이블 재생성
                    logger.info("⚠️ SQLite 제약으로 인해 테이블을 재생성합니다...")

                    # 임시 테이블 생성
                    cursor.execute(
                        """
                        CREATE TABLE mapping_data_temp AS 
                        SELECT id, identifier, kdc, ddc, ksh, kdc_edition, ddc_edition, 
                               publication_year, title, data_type, source_file
                        FROM mapping_data
                    """
                    )

                    # 기존 테이블 삭제
                    cursor.execute("DROP TABLE mapping_data")

                    # 임시 테이블을 원래 이름으로 변경
                    cursor.execute(
                        "ALTER TABLE mapping_data_temp RENAME TO mapping_data"
                    )

                    # 인덱스 재생성
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_ddc_ksh ON mapping_data(ddc, ksh)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_identifier ON mapping_data(identifier)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_kdc ON mapping_data(kdc)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_ksh ON mapping_data(ksh)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_ksh_ddc ON mapping_data(ksh, ddc)"
                    )

                    conn.commit()
                    logger.info("✅ ksh_labeled 컬럼 제거 완료")
                else:
                    logger.info("ℹ️ ksh_labeled 컬럼이 존재하지 않습니다")

        except Exception as e:
            logger.error(f"❌ 롤백 실패: {e}")
            raise

    def test_ksh_extraction(self, sample_size: int = 10):
        """
        KSH 추출 로직을 테스트합니다.

        Args:
            sample_size: 테스트할 샘플 수
        """
        logger.info(f"🧪 KSH 추출 로직 테스트 ({sample_size}개 샘플)")

        try:
            with sqlite3.connect(self.mapping_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT title, ksh 
                    FROM mapping_data 
                    WHERE ksh IS NOT NULL AND ksh != ''
                    ORDER BY RANDOM() 
                    LIMIT ?
                """,
                    (sample_size,),
                )

                samples = cursor.fetchall()

                for i, (title, ksh_text) in enumerate(samples, 1):
                    logger.info(f"\n테스트 {i}:")
                    logger.info(f"  제목: {title[:50]}...")
                    logger.info(f"  원본 KSH: {ksh_text}")

                    # KSH 코드 추출 테스트
                    extracted_codes = self._extract_ksh_codes_from_text(ksh_text)
                    logger.info(f"  추출된 코드: {extracted_codes}")

                    # 각 코드의 레이블 조회 테스트
                    for code in extracted_codes:
                        label = self._get_ksh_label(code)
                        logger.info(f"    {code} → {label if label else '레이블 없음'}")

                    # 최종 결합 결과 테스트
                    labeled_result = self._create_labeled_ksh_column(ksh_text)
                    logger.info(f"  최종 결과: {labeled_result}")

        except Exception as e:
            logger.error(f"테스트 실패: {e}")


def main():
    """메인 실행 함수"""
    try:
        # KSH 레이블 매퍼 생성
        mapper = KSHLabelMapper()

        # 현재 상태 확인
        logger.info("현재 데이터베이스 상태 확인")
        stats = mapper.get_mapping_statistics()
        logger.info(f"  - 전체 레코드: {stats['total_records']:,}개")
        logger.info(f"  - KSH 필드 보유: {stats['ksh_records']:,}개")

        if stats["column_exists"]:
            logger.info(f"  - 레이블 매핑 완료: {stats['labeled_records']:,}개")
            logger.info(f"  - 레이블 매핑 필요: {stats['unlabeled_records']:,}개")

            # 기존 컬럼이 있으면 롤백 옵션 제공
            rollback = input(
                "\n기존 ksh_labeled 컬럼을 제거하고 다시 시작하시겠습니까? (y/N): "
            )
            if rollback.lower() in ["y", "yes", "ㅇ"]:
                mapper.rollback_ksh_labeled_column()
                stats = mapper.get_mapping_statistics()  # 상태 재확인
        else:
            logger.info("  - ksh_labeled 컬럼: 아직 생성되지 않음")
            logger.info(f"  - 레이블 매핑 필요: {stats['ksh_records']:,}개")

        # 테스트 실행 여부 확인
        test_extraction = input("\nKSH 추출 로직을 먼저 테스트해보시겠습니까? (Y/n): ")
        if test_extraction.lower() not in ["n", "no"]:
            mapper.test_ksh_extraction(10)

            continue_mapping = input(
                "\n테스트 결과가 정확합니까? 매핑을 계속 진행하시겠습니까? (y/N): "
            )
            if continue_mapping.lower() not in ["y", "yes", "ㅇ"]:
                logger.info("매핑 작업을 취소했습니다")
                return 0

        # KSH 레이블 매핑 실행
        needs_mapping = stats["unlabeled_records"] > 0 or not stats["column_exists"]

        if needs_mapping:
            mapping_count = (
                stats["unlabeled_records"]
                if stats["column_exists"]
                else stats["ksh_records"]
            )
            user_input = input(
                f"\n{mapping_count:,}개 레코드에 KSH 레이블을 매핑하시겠습니까? (y/N): "
            )
            if user_input.lower() in ["y", "yes", "ㅇ"]:
                mapper.add_ksh_labeled_column()

                # 결과 재확인
                logger.info("\n매핑 완료 후 상태")
                final_stats = mapper.get_mapping_statistics()
                logger.info(
                    f"  - 레이블 매핑 완료: {final_stats['labeled_records']:,}개"
                )
                logger.info(
                    f"  - 레이블 매핑 필요: {final_stats['unlabeled_records']:,}개"
                )

                # 샘플 결과 출력
                logger.info("\n샘플 결과 (처음 5개):")
                samples = mapper.sample_results(5)
                for i, (title, ksh, ksh_labeled) in enumerate(samples, 1):
                    logger.info(f"{i}. 제목: {title[:50]}...")
                    logger.info(f"   원본 KSH: {ksh}")
                    if ksh_labeled:
                        logger.info(f"   레이블 KSH: {ksh_labeled}")
                    logger.info("")
            else:
                logger.info("매핑 작업을 취소했습니다")
        else:
            logger.info("모든 레코드에 이미 KSH 레이블이 매핑되어 있습니다")

            # 샘플만 출력
            logger.info("\n현재 매핑 상태 샘플:")
            samples = mapper.sample_results(5)
            for i, (title, ksh, ksh_labeled) in enumerate(samples, 1):
                logger.info(f"{i}. 제목: {title[:50]}...")
                if ksh_labeled:
                    logger.info(f"   레이블 KSH: {ksh_labeled}")
                else:
                    logger.info(f"   원본 KSH: {ksh}")
                logger.info("")

    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
