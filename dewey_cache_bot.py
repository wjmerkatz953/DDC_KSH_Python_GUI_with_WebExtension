# -*- coding: utf-8 -*-
# 파일명: dewey_cache_bot.py
# DDC 캐시를 미리 채우는 봇 스크립트
# Version: v1.1.0 (커스텀 모드 추가)

import sys
import time
import re
import threading
from typing import List, Set, Dict, Optional
import logging
from pathlib import Path
from collections import OrderedDict
import requests  # ✨ 이 줄을 추가해주세요!
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# 프로젝트 모듈들 임포트 (메인 앱과 동일한 경로에 위치 가정)
from database_manager import DatabaseManager
from Search_Dewey import DeweyClient

# 로깅 설정 (한글 이모지 오류 방지)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("dewey_cache_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class DeweyCache강력Bot:
    def __init__(
        self,
        concepts_db_path="nlk_concepts.sqlite",
        mapping_db_path="kdc_ddc_mapping.db",
    ):
        """
        Args:
            concepts_db_path: KSH 개념 데이터베이스 경로
            mapping_db_path: 서지 매핑 데이터베이스 경로
        """
        # -------------------
        # ✅ 올바른 인수를 사용하여 DatabaseManager를 생성합니다.
        self.db_manager = DatabaseManager(concepts_db_path, mapping_db_path)
        # -------------------
        self.db_manager.initialize_databases()

        self.dewey_client = DeweyClient(self.db_manager)

        self.consecutive_failures = 0
        self.max_consecutive_failures = 5

        # -------------------
        # ✅ 스레드 안전성을 위한 Lock 객체 추가
        self.lock = threading.Lock()
        # -------------------

        # 봇 설정
        self.processed_codes: Set[str] = set()
        self.failed_codes: Set[str] = set()
        self.success_count = 0
        self.error_count = 0
        self.request_delay = 1.0  # API 요청 간격 (초)
        self.max_retries = 3
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5

        # 우선순위 DDC 코드 목록들
        self.priority_ranges = {
            "기본_백의자리": [f"{i}00" for i in range(10)],
            "십의자리": [f"{i}{j}0" for i in range(10) for j in range(10)],
            "주요_학문분야": [
                "004",
                "005",
                "006",
                "016",
                "017",
                "018",
                "019",
                "025",
                "027",
                "028",
                "070",
                "071",
                "072",
                "074",
                "079",
                "150",
                "152",
                "153",
                "155",
                "158",
                "170",
                "171",
                "172",
                "173",
                "174",
                "177",
                "179",
                "200",
                "201",
                "202",
                "203",
                "204",
                "206",
                "207",
                "208",
                "209",
                "220",
                "221",
                "222",
                "223",
                "224",
                "225",
                "226",
                "227",
                "228",
                "229",
                "290",
                "291",
                "292",
                "293",
                "294",
                "295",
                "296",
                "297",
                "298",
                "299",
                "300",
                "301",
                "302",
                "303",
                "304",
                "305",
                "306",
                "307",
                "308",
                "309",
                "320",
                "321",
                "322",
                "323",
                "324",
                "325",
                "326",
                "327",
                "328",
                "329",
                "330",
                "331",
                "332",
                "333",
                "334",
                "335",
                "336",
                "337",
                "338",
                "339",
                "340",
                "341",
                "342",
                "343",
                "344",
                "345",
                "346",
                "347",
                "348",
                "349",
                "350",
                "351",
                "352",
                "353",
                "354",
                "355",
                "356",
                "357",
                "358",
                "359",
                "370",
                "371",
                "372",
                "373",
                "374",
                "375",
                "376",
                "377",
                "378",
                "379",
                "380",
                "381",
                "382",
                "383",
                "384",
                "385",
                "386",
                "387",
                "388",
                "389",
                "390",
                "391",
                "392",
                "393",
                "394",
                "395",
                "396",
                "397",
                "398",
                "399",
                "400",
                "401",
                "402",
                "403",
                "404",
                "405",
                "406",
                "407",
                "408",
                "409",
                "410",
                "411",
                "412",
                "413",
                "414",
                "415",
                "416",
                "417",
                "418",
                "419",
                "420",
                "421",
                "422",
                "423",
                "424",
                "425",
                "426",
                "427",
                "428",
                "429",
                "430",
                "431",
                "432",
                "433",
                "434",
                "435",
                "436",
                "437",
                "438",
                "439",
                "440",
                "441",
                "442",
                "443",
                "444",
                "445",
                "446",
                "447",
                "448",
                "449",
                "450",
                "451",
                "452",
                "453",
                "454",
                "455",
                "456",
                "457",
                "458",
                "459",
                "460",
                "461",
                "462",
                "463",
                "464",
                "465",
                "466",
                "467",
                "468",
                "469",
                "470",
                "471",
                "472",
                "473",
                "474",
                "475",
                "476",
                "477",
                "478",
                "479",
                "480",
                "481",
                "482",
                "483",
                "484",
                "485",
                "486",
                "487",
                "488",
                "489",
                "490",
                "491",
                "492",
                "493",
                "494",
                "495",
                "496",
                "497",
                "498",
                "499",
                "500",
                "501",
                "502",
                "503",
                "504",
                "505",
                "506",
                "507",
                "508",
                "509",
                "510",
                "511",
                "512",
                "513",
                "514",
                "515",
                "516",
                "517",
                "518",
                "519",
                "520",
                "521",
                "522",
                "523",
                "524",
                "525",
                "526",
                "527",
                "528",
                "529",
                "530",
                "531",
                "532",
                "533",
                "534",
                "535",
                "536",
                "537",
                "538",
                "539",
                "540",
                "541",
                "542",
                "543",
                "544",
                "545",
                "546",
                "547",
                "548",
                "549",
                "550",
                "551",
                "552",
                "553",
                "554",
                "555",
                "556",
                "557",
                "558",
                "559",
                "560",
                "561",
                "562",
                "563",
                "564",
                "565",
                "566",
                "567",
                "568",
                "569",
                "570",
                "571",
                "572",
                "573",
                "574",
                "575",
                "576",
                "577",
                "578",
                "579",
                "580",
                "581",
                "582",
                "583",
                "584",
                "585",
                "586",
                "587",
                "588",
                "589",
                "590",
                "591",
                "592",
                "593",
                "594",
                "595",
                "596",
                "597",
                "598",
                "599",
                "600",
                "601",
                "602",
                "603",
                "604",
                "605",
                "606",
                "607",
                "608",
                "609",
                "610",
                "611",
                "612",
                "613",
                "614",
                "615",
                "616",
                "617",
                "618",
                "619",
                "620",
                "621",
                "622",
                "623",
                "624",
                "625",
                "626",
                "627",
                "628",
                "629",
                "630",
                "631",
                "632",
                "633",
                "634",
                "635",
                "636",
                "637",
                "638",
                "639",
                "640",
                "641",
                "642",
                "643",
                "644",
                "645",
                "646",
                "647",
                "648",
                "649",
                "650",
                "651",
                "652",
                "653",
                "654",
                "655",
                "656",
                "657",
                "658",
                "659",
                "660",
                "661",
                "662",
                "663",
                "664",
                "665",
                "666",
                "667",
                "668",
                "669",
                "670",
                "671",
                "672",
                "673",
                "674",
                "675",
                "676",
                "677",
                "678",
                "679",
                "680",
                "681",
                "682",
                "683",
                "684",
                "685",
                "686",
                "687",
                "688",
                "689",
                "690",
                "691",
                "692",
                "693",
                "694",
                "695",
                "696",
                "697",
                "698",
                "699",
                "700",
                "701",
                "702",
                "703",
                "704",
                "705",
                "706",
                "707",
                "708",
                "709",
                "710",
                "711",
                "712",
                "713",
                "714",
                "715",
                "716",
                "717",
                "718",
                "719",
                "720",
                "721",
                "722",
                "723",
                "724",
                "725",
                "726",
                "727",
                "728",
                "729",
                "730",
                "731",
                "732",
                "733",
                "734",
                "735",
                "736",
                "737",
                "738",
                "739",
                "740",
                "741",
                "742",
                "743",
                "744",
                "745",
                "746",
                "747",
                "748",
                "749",
                "750",
                "751",
                "752",
                "753",
                "754",
                "755",
                "756",
                "757",
                "758",
                "759",
                "760",
                "761",
                "762",
                "763",
                "764",
                "765",
                "766",
                "767",
                "768",
                "769",
                "770",
                "771",
                "772",
                "773",
                "774",
                "775",
                "776",
                "777",
                "778",
                "779",
                "780",
                "781",
                "782",
                "783",
                "784",
                "785",
                "786",
                "787",
                "788",
                "789",
                "790",
                "791",
                "792",
                "793",
                "794",
                "795",
                "796",
                "797",
                "798",
                "799",
                "800",
                "801",
                "802",
                "803",
                "804",
                "805",
                "806",
                "807",
                "808",
                "809",
                "810",
                "811",
                "812",
                "813",
                "814",
                "815",
                "816",
                "817",
                "818",
                "819",
                "820",
                "821",
                "822",
                "823",
                "824",
                "825",
                "826",
                "827",
                "828",
                "829",
                "830",
                "831",
                "832",
                "833",
                "834",
                "835",
                "836",
                "837",
                "838",
                "839",
                "840",
                "841",
                "842",
                "843",
                "844",
                "845",
                "846",
                "847",
                "848",
                "849",
                "850",
                "851",
                "852",
                "853",
                "854",
                "855",
                "856",
                "857",
                "858",
                "859",
                "860",
                "861",
                "862",
                "863",
                "864",
                "865",
                "866",
                "867",
                "868",
                "869",
                "870",
                "871",
                "872",
                "873",
                "874",
                "875",
                "876",
                "877",
                "878",
                "879",
                "880",
                "881",
                "882",
                "883",
                "884",
                "885",
                "886",
                "887",
                "888",
                "889",
                "890",
                "891",
                "892",
                "893",
                "894",
                "895",
                "896",
                "897",
                "898",
                "899",
                "900",
                "901",
                "902",
                "903",
                "904",
                "905",
                "906",
                "907",
                "908",
                "909",
                "910",
                "911",
                "912",
                "913",
                "914",
                "915",
                "916",
                "917",
                "918",
                "919",
                "920",
                "921",
                "922",
                "923",
                "924",
                "925",
                "926",
                "927",
                "928",
                "929",
                "930",
                "931",
                "932",
                "933",
                "934",
                "935",
                "936",
                "937",
                "938",
                "939",
                "940",
                "941",
                "942",
                "943",
                "944",
                "945",
                "946",
                "947",
                "948",
                "949",
                "950",
                "951",
                "952",
                "953",
                "954",
                "955",
                "956",
                "957",
                "958",
                "959",
                "960",
                "961",
                "962",
                "963",
                "964",
                "965",
                "966",
                "967",
                "968",
                "969",
                "970",
                "971",
                "972",
                "973",
                "974",
                "975",
                "976",
                "977",
                "978",
                "979",
                "980",
                "981",
                "982",
                "983",
                "984",
                "985",
                "986",
                "987",
                "988",
                "989",
                "990",
                "991",
                "992",
                "993",
                "994",
                "995",
                "996",
                "997",
                "998",
                "999",
            ],
            "소수점_주요": [
                "025.1",
                "025.2",
                "025.3",
                "025.4",
                "025.5",
                "004.1",
                "004.2",
                "004.6",
                "004.7",
                "004.9",
                "150.1",
                "150.7",
                "150.9",
                "370.1",
                "370.9",
                "616.07",
                "616.1",
                "616.2",
                "616.3",
                "616.4",
                "616.5",
                "616.6",
                "616.7",
                "616.8",
                "616.9",
                "006.3",
                "006.7",
                "616.025",
                "616.075",
            ],
        }

    def show_statistics(self):
        """현재 캐시 통계 표시"""
        logger.info("📦 DDC 캐시는 영구 보존됩니다 (URI는 불변!)")
        logger.info("=" * 60)
        logger.info("📊 현재 DDC 캐시 통계")
        logger.info("=" * 60)

        stats = self.db_manager.get_dewey_cache_stats()
        if stats:
            logger.info(f"📦 총 캐시 항목: {stats.get('total_entries', 0):,}개")
            logger.info(f"🎯 총 히트 수: {stats.get('total_hits', 0):,}회")
            logger.info(f"💾 캐시 크기: {stats.get('total_size_mb', 0)}MB")
            logger.info(f"📅 가장 오래된 항목: {stats.get('oldest_entry', 'N/A')}")
            logger.info(f"📅 가장 최근 항목: {stats.get('newest_entry', 'N/A')}")
        else:
            logger.info("📦 캐시가 비어있습니다.")

        logger.info(f"✅ 봇 처리 성공: {self.success_count}개")
        logger.info(f"❌ 봇 처리 실패: {self.error_count}개")
        logger.info("=" * 60)

    @staticmethod
    def normalize_ddc_code(ddc_code: str) -> str:
        """DDC 코드 정규화"""
        if not ddc_code:
            return ""

        code = re.sub(r"[^0-9.\- ]", "", str(ddc_code)).strip()

        if "-" in code:
            # ... (범위 처리 로직은 그대로 유지) ...
            parts = code.split("-")
            normalized_parts = []
            for part in parts:
                part = part.strip()
                if "." in part:
                    base, decimal = part.split(".", 1)
                    decimal = decimal.rstrip("0")
                    # ✅ 소수점이 있는 범위에도 zfill(3) 적용
                    if base.isdigit():
                        base = base.zfill(3)
                    normalized_parts.append(
                        base if not decimal else f"{base}.{decimal}"
                    )
                else:
                    normalized_parts.append(part)
            return "-".join(normalized_parts)

        if "." in code:
            base, decimal = code.split(".", 1)
            decimal = decimal.rstrip("0")
            # -------------------
            # ✅ [핵심 수정] 정수 부분이 숫자일 경우, zfill(3)으로 앞을 0으로 채워 3자리를 보장합니다.
            if base.isdigit():
                base = base.zfill(3)
            # -------------------
            return base if not decimal else f"{base}.{decimal}"

        # ✅ 소수점이 없는 숫자 코드도 zfill 처리를 할 수 있으나,
        #    다른 곳에서 이미 zfill(3) 처리를 하고 있으므로 여기서는 그대로 둡니다.
        return code

    def _fetch_single_code(self, ddc_code: str) -> bool:
        """단일 DDC 코드를 가져와서 캐시에 저장 (병렬 처리 및 스레드 안전성 적용)"""
        normalized_code = self.normalize_ddc_code(ddc_code)
        if normalized_code != ddc_code:
            logger.info(f"📝 DDC 코드 정규화: {ddc_code} → {normalized_code}")

        if normalized_code in self.processed_codes:
            logger.debug(f"⏭️ 이미 처리됨: {normalized_code}")
            return True

        logger.info(f"🔍 DDC {normalized_code} 요청 중...")

        for attempt in range(self.max_retries):
            try:
                context = self.dewey_client.get_dewey_context(normalized_code)
                if context and context.get("main"):
                    # -------------------
                    # ✅ [핵심] 여러 스레드가 동시에 공유 변수를 수정하는 것을 방지합니다.
                    with self.lock:
                        self.processed_codes.add(normalized_code)
                        self.success_count += 1
                        self.consecutive_failures = 0
                    # -------------------

                    related_codes = self._extract_related_codes(context)
                    logger.debug(
                        f"  ↳ 관련 코드 {len(related_codes)}개 발견: {related_codes}"
                    )
                    logger.info(f"✅ DDC {normalized_code} 캐시 저장 완료")
                    return True
                else:
                    logger.warning(
                        f"⚠️ DDC {normalized_code} 빈 응답 (시도 {attempt + 1}/{self.max_retries})"
                    )

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    logger.error(
                        "🔐 인증 오류! 토큰이 만료되었거나 자격증명에 문제가 있습니다."
                    )
                    logger.error("  해결방법: 잠시 대기 후 재시도 또는 API 설정 재확인")
                    with self.lock:
                        self.consecutive_failures += 1
                    if self.consecutive_failures >= self.max_consecutive_failures:
                        logger.error(
                            f"⚠️ 연속 {self.consecutive_failures}회 실패! 봇을 일시 중지합니다."
                        )
                        return False
                elif e.response.status_code == 429:
                    logger.warning("🚦 API 할당량 초과! 잠시 대기합니다...")
                    time.sleep(30)
                    with self.lock:
                        self.consecutive_failures += 1
                elif e.response.status_code >= 500:
                    logger.warning(
                        f"🔧 서버 오류 ({e.response.status_code}): OCLC 서버 일시 장애"
                    )
                    with self.lock:
                        self.consecutive_failures += 1
                else:
                    logger.error(
                        f"❌ DDC {normalized_code} HTTP 오류 (시도 {attempt + 1}/{self.max_retries}): {e}"
                    )
                    with self.lock:
                        self.consecutive_failures += 1

            except ConnectionRefusedError as e:
                logger.error("🔐 DDC API 자격증명이 설정되지 않았습니다!")
                logger.error("  해결방법: 메인 앱 → Web Dewey 탭 → API 설정")
                return False

            except Exception as e:
                if "DLD URL을 찾지 못했습니다" in str(e):
                    logger.error(f"❌ DDC {normalized_code} 오류: {e} (재시도 불필요)")
                    # -------------------
                    # ✅ [핵심] 스레드 안전성을 위해 Lock 사용
                    with self.lock:
                        self.failed_codes.add(normalized_code)
                        self.error_count += 1
                    # -------------------
                    return False

                logger.error(
                    f"❌ DDC {normalized_code} 오류 (시도 {attempt + 1}/{self.max_retries}): {e}"
                )

                if attempt == self.max_retries - 1:
                    # -------------------
                    # ✅ [핵심] 스레드 안전성을 위해 Lock 사용
                    with self.lock:
                        self.failed_codes.add(normalized_code)
                        self.error_count += 1
                    # -------------------
                    return False

            time.sleep(self.request_delay * (attempt + 1))

        return False

    def _extract_related_codes(self, context: dict) -> List[str]:
        """컨텍스트에서 관련된 DDC 코드들 추출"""
        related_codes = []
        for key in ["narrower", "related", "hierarchy"]:
            for item in context.get(key, []):
                if isinstance(item, dict):
                    code = item.get("notation")
                    if code and isinstance(code, str):
                        related_codes.append(code)
        return related_codes

    # 🆕 커스텀 모드를 위한 코드 생성 헬퍼 메서드
    def _generate_custom_codes(self, start: int, end: int, decimals: int) -> List[str]:
        """지정된 범위와 소수점 자릿수에 대한 DDC 코드 목록을 생성합니다."""
        if start > end:
            logger.error("❌ 시작 범위는 종료 범위보다 클 수 없습니다.")
            return []

        logger.info(
            f"🔧 커스텀 코드 생성 중... (범위: {start}-{end}, 소수점: {decimals}자리)"
        )

        # 중복을 제거하면서 순서를 유지하기 위해 OrderedDict 사용
        codes = OrderedDict()

        # 1. 정수 코드 추가 (e.g., 500, 501, ...)
        for i in range(start, end + 1):
            codes[str(i)] = None

        # 2. 소수점 코드 추가
        if decimals > 0:
            for i in range(start, end + 1):
                # 10의 거듭제곱을 이용하여 소수점 생성 (e.g., 10^3 -> 1~999)
                limit = 10**decimals
                for j in range(1, limit):
                    # 정규화된 코드를 생성하여 추가 (e.g., "500.100" -> "500.1")
                    code_str = f"{i}.{j}"
                    normalized_code = self.normalize_ddc_code(code_str)
                    codes[normalized_code] = None

        generated_list = list(codes.keys())
        logger.info(f"✅ 총 {len(generated_list):,}개의 유니크한 코드 생성 완료.")
        return generated_list

    def run_priority_caching(
        self,
        mode: str = "기본",
        max_requests: int = 100,
        custom_params: Optional[Dict] = None,
    ):
        logger.info(
            f"🚀 DDC 캐시 봇 시작 (모드: {mode}, 최대: {max_requests}건, 병렬 처리)"
        )
        start_time = time.time()
        target_codes = []
        if mode == "기본":
            target_codes = (
                self.priority_ranges["기본_백의자리"]
                + self.priority_ranges["주요_학문분야"][:50]
            )
        elif mode == "전체":
            target_codes = self.priority_ranges["십의자리"]
        elif mode == "소수점":
            target_codes = (
                self.priority_ranges["기본_백의자리"]
                + self.priority_ranges["주요_학문분야"]
                + self.priority_ranges["소수점_주요"]
            )
        # 🆕 커스텀 모드 처리 로직 추가
        elif mode == "커스텀" and custom_params:
            target_codes = self._generate_custom_codes(
                start=custom_params["start"],
                end=custom_params["end"],
                decimals=custom_params["decimals"],
            )
        else:
            logger.error(f"❌ 알 수 없는 모드 또는 커스텀 파라미터 오류: {mode}")
            return

        if not target_codes:
            logger.warning("📋 처리할 대상 코드가 없습니다. 봇을 종료합니다.")
            return

        target_codes = target_codes[:max_requests]
        logger.info(f"📋 처리 대상: {len(target_codes)}개 DDC 코드 (최대 요청 수 적용)")

        # -------------------
        # ✅ ThreadPoolExecutor를 사용한 병렬 처리
        # API 서버에 과부하를 주지 않도록 max_workers는 5~10 사이가 적절합니다.
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 작업을 제출하고 future 객체를 관리합니다.
            futures = {
                executor.submit(self._fetch_single_code, code): code
                for code in target_codes
            }

            # tqdm을 사용하여 실시간 진행률 표시
            with tqdm(total=len(target_codes), desc="DDC 캐시 수집 중") as pbar:
                for future in as_completed(futures):
                    # 작업이 완료될 때마다 진행률 바를 업데이트합니다.
                    pbar.update(1)
                    try:
                        future.result()  # 작업 중 발생한 예외가 있다면 여기서 발생합니다.
                    except Exception as exc:
                        logger.error(f"❌ 코드 처리 중 예외 발생: {exc}")

                    # 연속 실패 시 봇 중지 로직
                    if self.consecutive_failures >= self.max_consecutive_failures:
                        logger.warning(
                            f"⚠️ 연속 {self.consecutive_failures}회 실패로 봇을 중지합니다."
                        )
                        # 남은 작업들을 취소합니다.
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
        # -------------------

        elapsed = time.time() - start_time
        logger.info("🎉 DDC 캐시 봇 완료!")
        logger.info(f"⏱️ 총 소요시간: {elapsed:.1f}초")
        if self.success_count + self.error_count > 0:
            success_rate = (
                self.success_count / (self.success_count + self.error_count)
            ) * 100
            logger.info(
                f"📊 처리 결과: 성공 {self.success_count}개, 실패 {self.error_count}개 (성공률: {success_rate:.1f}%)"
            )
        if self.failed_codes:
            logger.warning(f"❌ 실패한 코드들: {sorted(list(self.failed_codes))}")
        self.show_statistics()

    def run_random_exploration(self, num_codes: int = 50):
        """랜덤한 DDC 코드들을 탐색하여 캐시 확장"""
        import random

        logger.info(f"🎲 랜덤 DDC 코드 {num_codes}개 탐색 시작")
        for i in range(num_codes):
            random_code = f"{random.randint(0, 999):03d}"
            logger.info(f"🎯 랜덤 코드 {i+1}/{num_codes}: {random_code}")
            self._fetch_single_code(random_code)
            time.sleep(self.request_delay)
        logger.info("🎲 랜덤 탐색 완료")
        self.show_statistics()

    def extract_ddcs_from_biblio(self) -> List[str]:
        """Biblio DB(mapping_data)에서 모든 고유 DDC 코드 추출"""
        logger.info("📚 Biblio DB에서 고유 DDC 코드 추출 중...")

        try:
            import sqlite3
            conn = sqlite3.connect(self.db_manager.kdc_ddc_mapping_db_path)
            cursor = conn.cursor()

            # 모든 DDC 추출 (NULL, 빈 문자열 제외)
            cursor.execute("""
                SELECT DISTINCT ddc
                FROM mapping_data
                WHERE ddc IS NOT NULL
                  AND ddc != ''
                ORDER BY ddc
            """)

            raw_ddcs = [row[0] for row in cursor.fetchall()]
            conn.close()

            # DDC 코드 분리 및 정규화
            unique_ddcs = set()
            for raw_ddc in raw_ddcs:
                # 콤마, 세미콜론, 슬래시로 구분된 경우 분리
                parts = re.split(r'[,;/]', raw_ddc)

                for part in parts:
                    code = part.strip()

                    # 범위 코드 제외 (예: "500-599", "500~599")
                    if '-' in code or '~' in code:
                        continue

                    # 빈 문자열 제외
                    if not code:
                        continue

                    # 정규화
                    normalized = self.normalize_ddc_code(code)
                    if normalized:
                        unique_ddcs.add(normalized)

            ddcs = sorted(list(unique_ddcs))
            logger.info(f"✅ Biblio DB에서 {len(ddcs):,}개 고유 DDC 추출 완료")
            logger.info(f"   (원본 {len(raw_ddcs):,}개 → 분리/정규화 후 {len(ddcs):,}개)")
            return ddcs

        except Exception as e:
            logger.error(f"❌ Biblio DB에서 DDC 추출 실패: {e}")
            return []

    def check_biblio_cache_coverage(self):
        """Biblio DB의 DDC 캐시 커버리지만 확인 (API 호출 없음)"""
        logger.info("🔍 Biblio DB 캐시 커버리지 분석 중...")
        logger.info("=" * 60)

        # 1. Biblio에서 고유 DDC 추출
        biblio_ddcs = self.extract_ddcs_from_biblio()
        if not biblio_ddcs:
            logger.warning("📋 Biblio DB에 DDC 코드가 없습니다.")
            return []

        # 2. 이미 캐시된 DDC 확인
        logger.info("🔍 기존 캐시와 비교 중...")
        try:
            conn = self.db_manager._get_dewey_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT ddc_code FROM ddc_keyword")
            cached_ddcs = set(row[0] for row in cursor.fetchall())
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ 캐시 조회 실패: {e}")
            cached_ddcs = set()

        # 3. 누락된 DDC 찾기
        missing_ddcs = [ddc for ddc in biblio_ddcs if ddc not in cached_ddcs]

        logger.info("=" * 60)
        logger.info(f"📊 Biblio DDC 총 개수: {len(biblio_ddcs):,}개")
        logger.info(f"✅ 이미 캐시됨: {len(cached_ddcs):,}개")
        logger.info(f"❌ 누락됨: {len(missing_ddcs):,}개")

        coverage = (len(cached_ddcs) / len(biblio_ddcs) * 100) if biblio_ddcs else 0
        logger.info(f"📈 캐시 커버리지: {coverage:.1f}%")
        logger.info("=" * 60)

        if missing_ddcs:
            logger.info(f"🔍 누락된 DDC 샘플 (처음 20개):")
            for i, ddc in enumerate(missing_ddcs[:20], 1):
                logger.info(f"   {i}. {ddc}")
            if len(missing_ddcs) > 20:
                logger.info(f"   ... 외 {len(missing_ddcs) - 20}개")
        else:
            logger.info("🎉 모든 Biblio DDC가 캐시되어 있습니다!")

        return missing_ddcs

    def run_biblio_caching(self, max_requests: int = None, missing_ddcs: List[str] = None):
        """Biblio DB의 모든 DDC를 캐시에 저장"""
        logger.info("🚀 Biblio DB 기반 DDC 캐싱 시작")
        logger.info("=" * 60)

        # missing_ddcs가 제공되지 않으면 자동으로 추출
        if missing_ddcs is None:
            # 1. Biblio에서 고유 DDC 추출
            biblio_ddcs = self.extract_ddcs_from_biblio()
            if not biblio_ddcs:
                logger.warning("📋 Biblio DB에 DDC 코드가 없습니다.")
                return

            # 2. 이미 캐시된 DDC 확인
            logger.info("🔍 기존 캐시와 비교 중...")
            try:
                conn = self.db_manager._get_dewey_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT ddc_code FROM ddc_keyword")
                cached_ddcs = set(row[0] for row in cursor.fetchall())
                conn.close()
            except Exception as e:
                logger.warning(f"⚠️ 캐시 조회 실패, 전체 조회 진행: {e}")
                cached_ddcs = set()

            # 3. 누락된 DDC 찾기
            missing_ddcs = [ddc for ddc in biblio_ddcs if ddc not in cached_ddcs]

            logger.info(f"📊 Biblio DDC 총 개수: {len(biblio_ddcs):,}개")
            logger.info(f"✅ 이미 캐시됨: {len(cached_ddcs):,}개")
            logger.info(f"🔍 조회 필요: {len(missing_ddcs):,}개")

        if not missing_ddcs:
            logger.info("🎉 모든 Biblio DDC가 이미 캐시되어 있습니다!")
            return

        # 4. 최대 요청 수 제한 적용
        if max_requests:
            missing_ddcs = missing_ddcs[:max_requests]
            logger.info(f"📋 최대 요청 수 제한: {len(missing_ddcs):,}개만 처리")

        # 5. 병렬 처리로 누락된 DDC 조회
        logger.info(f"⏱️  예상 소요 시간: 약 {len(missing_ddcs) // 50} 분")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self._fetch_single_code, code): code
                for code in missing_ddcs
            }

            with tqdm(total=len(missing_ddcs), desc="Biblio DDC 캐싱") as pbar:
                for future in as_completed(futures):
                    pbar.update(1)
                    try:
                        future.result()
                    except Exception as exc:
                        logger.error(f"❌ 코드 처리 중 예외: {exc}")

                    if self.consecutive_failures >= self.max_consecutive_failures:
                        logger.warning(
                            f"⚠️ 연속 {self.consecutive_failures}회 실패로 중지"
                        )
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info("🎉 Biblio DDC 캐싱 완료!")
        logger.info(f"⏱️  총 소요시간: {elapsed/60:.1f}분")

        if self.success_count + self.error_count > 0:
            success_rate = (
                self.success_count / (self.success_count + self.error_count)
            ) * 100
            logger.info(
                f"📊 성공: {self.success_count}개, 실패: {self.error_count}개 "
                f"(성공률: {success_rate:.1f}%)"
            )

        if self.failed_codes:
            logger.warning(f"❌ 실패 코드: {sorted(list(self.failed_codes))[:20]}...")

        self.show_statistics()

    def analyze_cache_efficiency(self):
        """캐시 효율성 분석"""
        logger.info("📊 DDC 캐시 효율성 분석 중...")
        stats = self.db_manager.get_dewey_cache_stats()
        if stats and stats.get("total_entries", 0) > 0:
            avg_hits = stats.get("total_hits", 0) / stats.get("total_entries", 1)
            logger.info(f"📈 평균 히트율: {avg_hits:.2f}회/항목")
            if avg_hits >= 2.0:
                logger.info("🏆 캐시가 매우 효율적으로 활용되고 있습니다!")
            elif avg_hits >= 1.5:
                logger.info("✅ 캐시가 잘 활용되고 있습니다.")
            elif avg_hits >= 1.0:
                logger.info("⚖️ 캐시 활용도가 보통입니다.")
            else:
                logger.info("💡 더 많은 캐시가 필요할 수 있습니다.")
        logger.info("💾 참고: DDC URI는 대부분 불변이므로 캐시를 영구 보존합니다!")

    def check_cache_freshness(self, days_threshold: int = 365):
        """캐시 신선도 검사 - 1년 이상 된 캐시만 재검증"""
        logger.info(f"🔍 {days_threshold}일 이상 된 캐시 신선도 검사 중...")
        conn = None
        try:
            conn = self.db_manager._get_dewey_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT iri, ddc_code, last_updated, hit_count
                FROM dewey_cache
                WHERE last_updated < datetime('now', '-{days_threshold} days')
                ORDER BY hit_count DESC, ddc_code
            """
            )
            old_caches = cursor.fetchall()
            if not old_caches:
                logger.info("✅ 신선도 검사 결과: 모든 캐시가 최신 상태입니다!")
                return
            logger.info(f"⚠️ {len(old_caches)}개의 오래된 캐시 발견")
            high_priority = [cache for cache in old_caches if cache[3] >= 5]
            if high_priority:
                logger.info(
                    f"🔥 우선 재검증 대상: {len(high_priority)}개 (히트 5회 이상)"
                )
                for cache in high_priority[:10]:
                    iri, ddc_code, last_updated, hit_count = cache
                    logger.info(
                        f"🔄 재검증: {ddc_code} (마지막 업데이트: {last_updated}, 히트: {hit_count}회)"
                    )
                    self._revalidate_cache_entry(iri, ddc_code)
        except Exception as e:
            logger.error(f"❌ 캐시 신선도 검사 실패: {e}")
        finally:
            if conn:
                conn.close()

    def _revalidate_cache_entry(self, iri: str, ddc_code: str):
        """개별 캐시 항목 재검증"""
        try:
            fresh_context = self.dewey_client.get_dewey_context(ddc_code)
            if fresh_context and fresh_context.get("main"):
                logger.info(f"✅ {ddc_code} 재검증 완료 - 캐시 업데이트됨")
            else:
                logger.warning(f"⚠️ {ddc_code} 재검증 실패 - 기존 캐시 유지")
        except Exception as e:
            logger.warning(f"⚠️ {ddc_code} 재검증 중 오류: {e} - 기존 캐시 유지")


def main():
    """메인 실행 함수"""
    print("🤖 DDC 캐시 프리로딩 봇")
    print("=" * 50)
    bot = DeweyCache강력Bot()
    try:
        client_id, client_secret = bot.db_manager.get_dewey_api_credentials()
        if not client_id or not client_secret:
            print("❌ DDC API 자격증명이 설정되지 않았습니다.")
            print("   해결방법: 메인 앱 → 'Web Dewey' 탭 → 'API 설정' 버튼")
            return
        print("✅ DDC API 자격증명 확인됨")
        try:
            if bot.dewey_client._fetch_token():
                print("✅ DDC API 인증 테스트 성공")
            else:
                print("❌ DDC API 인증 테스트 실패")
                return
        except Exception as auth_error:
            print(f"❌ DDC API 인증 테스트 실패: {auth_error}")
            print("   Client ID나 Client Secret을 다시 확인해주세요.")
            return
    except Exception as e:
        print(f"❌ 자격증명 확인 중 오류: {e}")
        return

    bot.show_statistics()

    while True:
        print("\n🎛️ 실행 모드 선택:")
        print("1. 기본 모드 (백의자리 + 주요 학문분야 50개)")
        print("2. 전체 모드 (모든 십의자리 1000개)")
        print("3. 소수점 모드 (소수점 세분류 포함)")
        print("4. 커스텀 모드 (범위 및 소수점 지정) ✨")
        print("5. 📚 Biblio DB 캐시 커버리지 확인 (API 호출 없음) 🔍")
        print("6. 📚 Biblio DB 모드 (실제 사용 중인 DDC만) ⭐")
        print("7. 랜덤 탐색 (랜덤 DDC 코드)")
        print("8. 캐시 신선도 검사 (1년 이상 된 항목)")
        print("9. 캐시 효율성 분석")
        print("10. 통계 보기")
        print("0. 종료")

        choice = input("\n선택 (0-10): ").strip()

        if choice == "1":
            max_req = input("최대 요청 수 (기본 60): ").strip()
            bot.run_priority_caching("기본", int(max_req) if max_req.isdigit() else 60)
        elif choice == "2":
            max_req = input("최대 요청 수 (기본 200): ").strip()
            bot.run_priority_caching("전체", int(max_req) if max_req.isdigit() else 200)
        elif choice == "3":
            max_req = input("최대 요청 수 (기본 100): ").strip()
            bot.run_priority_caching(
                "소수점", int(max_req) if max_req.isdigit() else 100
            )

        # 🆕 커스텀 모드 입력 처리
        elif choice == "4":
            try:
                start_range = int(input("시작 분류번호 (예: 500): ").strip())
                end_range = int(input("종료 분류번호 (예: 999): ").strip())
                decimals = int(input("소수점 자릿수 (0-3, 0은 정수만): ").strip())
                max_req = int(input("최대 요청 수 (기본 500): ").strip() or "500")

                if not 0 <= decimals <= 3:
                    print("❌ 소수점 자릿수는 0에서 3 사이여야 합니다.")
                    continue
                if start_range > end_range:
                    print("❌ 시작 번호는 종료 번호보다 클 수 없습니다.")
                    continue

                custom_params = {
                    "start": start_range,
                    "end": end_range,
                    "decimals": decimals,
                }
                bot.run_priority_caching(
                    mode="커스텀",
                    max_requests=max_req,
                    custom_params=custom_params,
                )
            except ValueError:
                print("❌ 잘못된 숫자 형식입니다. 다시 시도해주세요.")

        # 🆕 Biblio DB 캐시 커버리지 확인
        elif choice == "5":
            print("\n🔍 Biblio DB 캐시 커버리지 확인 - API 호출 없이 현황만 확인합니다.")
            missing_ddcs = bot.check_biblio_cache_coverage()

            if missing_ddcs:
                print("\n" + "=" * 60)
                proceed = input(f"\n❓ 누락된 {len(missing_ddcs):,}개 DDC를 지금 조회하시겠습니까? (y/n): ").strip().lower()
                if proceed == 'y':
                    max_req = input("최대 요청 수 (제한 없으려면 Enter): ").strip()
                    max_limit = int(max_req) if max_req and max_req.isdigit() else None
                    bot.run_biblio_caching(max_limit, missing_ddcs)
                else:
                    print("✅ 캐시 조회를 건너뜁니다.")

        # 🆕 Biblio DB 모드 (바로 실행)
        elif choice == "6":
            print("\n📚 Biblio DB 모드 - 실제 사용 중인 DDC만 캐싱합니다.")
            max_req = input("최대 요청 수 (제한 없으려면 Enter): ").strip()
            max_limit = int(max_req) if max_req and max_req.isdigit() else None
            bot.run_biblio_caching(max_limit)

        elif choice == "7":
            num_codes = input("랜덤 탐색 코드 수 (기본 50): ").strip()
            bot.run_random_exploration(int(num_codes) if num_codes.isdigit() else 50)
        elif choice == "8":
            days = input("몇 일 이상 된 캐시를 검사할까요? (기본 365일): ").strip()
            bot.check_cache_freshness(int(days) if days.isdigit() else 365)
        elif choice == "9":
            bot.analyze_cache_efficiency()
        elif choice == "10":
            bot.show_statistics()
        elif choice == "0":
            print("👋 DDC 캐시 봇을 종료합니다.")
            break
        else:
            print("❌ 잘못된 선택입니다.")


if __name__ == "__main__":
    main()
