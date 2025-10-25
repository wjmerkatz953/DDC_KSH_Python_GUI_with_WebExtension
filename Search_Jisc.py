import requests
import json
import time
from urllib.parse import urlencode


def search_jisc_like_browser(
    author=None,
    title=None,
    subject=None,
    keyword=None,
    publisher=None,
    isbn=None,
    publisher_place=None,
    date=None,
):
    """
    실제 웹브라우저처럼 JISC Library Hub Discover에서 검색합니다.
    웹사이트의 실제 검색 방식을 모방합니다.

    Args:
        author (str): 저자명
        title (str): 제목
        subject (str): 주제
        keyword (str): 키워드
        publisher (str): 출판사
        isbn (str): ISBN
        publisher_place (str): 출판지
        date (str): 출판연도

    Returns:
        dict: JSON 응답 또는 None
    """

    # 1. 실제 브라우저 헤더 완벽 모방
    session = requests.Session()

    # Chrome 브라우저 헤더 완벽 복사
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "DNT": "1",
        "Host": "discover.libraryhub.jisc.ac.uk",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    session.headers.update(headers)

    # 2. 먼저 메인 페이지에 방문하여 쿠키와 세션 설정
    print("🏠 메인 페이지 방문하여 세션 설정...")
    try:
        main_response = session.get(
            "https://discover.libraryhub.jisc.ac.uk/", timeout=15
        )
        print(f"✅ 메인 페이지: {main_response.status_code}")

        # 쿠키 확인
        cookies = session.cookies.get_dict()
        print(f"🍪 받은 쿠키: {len(cookies)}개")

    except Exception as e:
        print(f"⚠️ 메인 페이지 방문 실패: {e}")
        return None

    # 3. 검색 파라미터 구성 (실제 웹사이트 방식 따라하기)
    params = {}

    # 검색 조건 추가
    if author:
        params["author"] = author
    if title:
        params["title"] = title
    if subject:
        params["subject"] = subject
    if keyword:
        params["keyword"] = keyword
    if publisher:
        params["publisher"] = publisher
    if isbn:
        params["isbn"] = isbn
    if publisher_place:
        params["publisher-place"] = publisher_place
    if date:
        params["date"] = date

    if not params:
        print("❌ 검색 조건을 하나 이상 입력해주세요.")
        return None

    # 4. 첫 번째 시도: HTML 검색 (실제 브라우저 동작)
    search_url = "https://discover.libraryhub.jisc.ac.uk/search"
    print(f"\n🔍 HTML 검색 요청: {urlencode(params)}")

    try:
        # Referer 헤더 추가 (중요!)
        session.headers.update({"Referer": "https://discover.libraryhub.jisc.ac.uk/"})

        html_response = session.get(search_url, params=params, timeout=20)
        print(f"📄 HTML 응답: {html_response.status_code}")

        if html_response.status_code == 200:
            # HTML에서 결과 정보 추출
            html_content = html_response.text

            # 검색 결과 수 추출
            import re

            results_match = re.search(r"Results \d+ - \d+ of (\d+)", html_content)
            total_results = results_match.group(1) if results_match else "알 수 없음"

            print(f"📊 총 검색 결과: {total_results}건")

            # 제목들 추출
            title_pattern = r'<h3[^>]*><a[^>]*href="[^"]*">([^<]+)</a></h3>'
            titles = re.findall(title_pattern, html_content)

            if titles:
                print(f"\n📚 검색된 도서 제목들:")
                for i, title in enumerate(titles[:5], 1):
                    # HTML 엔티티 디코딩
                    import html

                    clean_title = html.unescape(title.strip())
                    print(f"  {i}. {clean_title}")

            # 5. 두 번째 시도: JSON API 요청 (HTML 요청 후)
            print(f"\n🔄 JSON API 시도...")
            json_params = params.copy()
            json_params["format"] = "json"

            # 쿠키와 세션 유지한 상태에서 JSON 요청
            session.headers.update(
                {
                    "Accept": "application/json, text/plain, */*",
                    "Referer": html_response.url,
                    "X-Requested-With": "XMLHttpRequest",  # AJAX 요청임을 명시
                }
            )

            json_response = session.get(search_url, params=json_params, timeout=20)
            print(f"📋 JSON 응답: {json_response.status_code}")
            print(
                f"📋 Content-Type: {json_response.headers.get('content-type', 'N/A')}"
            )

            if json_response.status_code == 200:
                try:
                    json_data = json_response.json()
                    print(f"🎉 JSON 파싱 성공!")
                    print(f"📊 hits: {json_data.get('hits', 0)}")
                    print(f"📄 records: {len(json_data.get('records', []))}")

                    # 상세 정보 출력
                    records = json_data.get("records", [])
                    if records:
                        print(f"\n📖 상세 정보:")
                        for i, record in enumerate(records[:3], 1):
                            print(f"\n{i}. 제목: {record.get('title', 'N/A')}")
                            print(f"   저자: {record.get('author', 'N/A')}")
                            print(f"   출판: {record.get('publisher', 'N/A')}")
                            print(f"   연도: {record.get('date', 'N/A')}")
                            print(f"   ISBN: {record.get('isbn', 'N/A')}")

                    return json_data

                except json.JSONDecodeError as e:
                    print(f"❌ JSON 파싱 실패: {e}")
                    print(f"📝 응답 내용 (처음 300자): {json_response.text[:300]}")
            else:
                print(f"❌ JSON 요청 실패: {json_response.status_code}")

            # HTML은 성공했으므로 부분 성공으로 간주
            return {
                "html_success": True,
                "total_results": total_results,
                "titles": titles,
            }

        else:
            print(f"❌ HTML 요청도 실패: {html_response.status_code}")
            print(f"📝 에러 내용: {html_response.text[:200]}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ 네트워크 오류: {e}")
        return None


def search_with_delays(author=None, title=None, **kwargs):
    """
    지연 시간을 두고 더욱 자연스러운 요청을 보냅니다.
    """
    print("⏳ 자연스러운 검색을 위해 잠시 대기...")
    time.sleep(2)  # 2초 대기

    return search_jisc_like_browser(author=author, title=title, **kwargs)


def test_realistic_search():
    """
    실제 브라우저 동작을 완벽 모방한 테스트
    """
    print("=" * 70)
    print("🎯 실제 브라우저 동작 모방 테스트")
    print("=" * 70)

    # 테스트 1: Sandel + Justice (웹사이트에서 확인된 조합)
    print("\n🔍 테스트 1: Michael Sandel의 Justice 검색")
    result1 = search_with_delays(author="sandel", title="justice")

    # 테스트 2: 단일 조건 검색
    print("\n" + "=" * 50)
    print("🔍 테스트 2: 저자명만으로 검색 (Sandel)")
    result2 = search_with_delays(author="Michael J. Sandel")

    # 테스트 3: ISBN 검색
    print("\n" + "=" * 50)
    print("🔍 테스트 3: ISBN 검색")
    result3 = search_with_delays(isbn="9781846142802")

    return result1, result2, result3


def test_advanced_combinations():
    """
    고급 검색 조합 테스트
    """
    print("\n" + "=" * 70)
    print("🧪 고급 검색 조합 테스트")
    print("=" * 70)

    # 복합 검색
    test_cases = [
        {"title": "liberalism", "author": "sandel", "description": "제목+저자"},
        {"subject": "political philosophy", "date": "2009", "description": "주제+연도"},
        {"keyword": "justice", "publisher": "harvard", "description": "키워드+출판사"},
        {
            "publisher-place": "cambridge",
            "date": "1990-2020",
            "description": "출판지+연도범위",
        },
    ]

    for i, test_case in enumerate(test_cases, 1):
        description = test_case.pop("description")
        print(f"\n🔬 고급 테스트 {i}: {description}")
        result = search_with_delays(**test_case)
        time.sleep(3)  # 요청 간 간격


if __name__ == "__main__":
    # 기본 테스트
    test_realistic_search()

    # 고급 테스트
    test_advanced_combinations()

    print("\n" + "=" * 70)
    print("✅ 모든 테스트 완료!")
    print("💡 웹브라우저 동작을 모방하여 봇 차단을 우회하려고 시도했습니다.")
    print("=" * 70)
