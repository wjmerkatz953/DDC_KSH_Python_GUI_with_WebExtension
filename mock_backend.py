# 파일명: mock_backend.py
# 설명: 실제 API 서버 없이 UI 테스트를 위한 가짜(Mock) 데이터를 반환하는 함수 모음.
import time


def search_lc_orchestrated_mock(
    title_query=None,
    author_query=None,
    isbn_query=None,
    year_query=None,
    app_instance=None,
    **kwargs,
):
    """search_lc_orchestrated의 가상(Mock) 버전 (100개 데이터 생성)

    Args:
        title_query (str, optional): 제목 검색어
        author_query (str, optional): 저자 검색어
        isbn_query (str, optional): ISBN 검색어
        year_query (str, optional): 연도 검색어  # ← 새로 추가!
        app_instance: 애플리케이션 인스턴스
        **kwargs: 기타 추가 인수들 (year_query 등)
    """

    if hasattr(app_instance, "log_message"):
        app_instance.log_message(
            "--- 📢 MOCK MODE ACTIVE --- (100개 가상 데이터 사용)", "WARNING"
        )

    time.sleep(0.5)  # 실제 네트워크 딜레이 흉내

    # -------------------
    # ✅ [FIX] 100개의 패턴화된 가짜 데이터를 생성하는 로직
    results = []
    for i in range(1, 5001):
        record = {
            "제목": f"Title A{i}",
            "저자": f"Author B{i}",
            "082": f"082.C{i}",
            "082 ind": f"{i % 10}{i % 5}",  # 예시 패턴
            "245 필드": f"245 Field D{i}",
            "250": f"250 Field E{i}",
            "발행지": f"Publisher F{i}",
            "연도": f"{2024 - i}",
            "출판사": f"Publisher G{i}",
            "650 필드": f"Subject H{i}",
            "상세 링크": f"https://example.com/link/{i}",
        }
        results.append(record)
    # -------------------

    return results
