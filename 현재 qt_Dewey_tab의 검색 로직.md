{"id":"https://id.oclc.org/worldcat/ddc/E37yQ6jKcj8VqkypgYVCyj3b63","altLabel":{"sv":["Internetresurser","Webbplatser--bibliografier","Webbplatser--informationssystem","Webbdatabaser--informationssystem"],"de":["Websites--Informationssysteme","Webdatenbanken--Informationssysteme","Websites--Bibliografien","Internetquellen"],"no":["Internettressurser","Nettsteder--bibliografier","Webdatabaser--informasjonssystemer","Nettsteder--informasjonssystemer"],"en":["Web sites--bibliographies","Web sites--information systems","Web databases--information systems","Internet resources"],"it":["Siti web--sistemi informativi","Risorse di Internet","Siti web--bibliografie","Database web--sistemi informativi"],"fr":["Sites Web--systèmes d'information","Ressources Internet","Sites Web--bibliographies","Bases de données Web--systèmes d'information","Portails Web--bibliographies"]},"related":["https://id.oclc.org/worldcat/ddc/E3pdK7wtKYVRbJKdFTyrg9rTd8","https://id.oclc.org/worldcat/ddc/E3h74Y87yHXrmHRPwqhrghtKvH"],"scopeNote":{"en":["Class here directories of web sites, portals"],"no":["Her: Registre over nettsteder; nettportaler"],"sv":["Klassificera här register över webbplatser, nätportaler"],"de":["Hier auch: Webverzeichnisse, Portale"],"fr":["Classer ici les répertoires de sites Web ; les portails"],"it":["Classificare qui le cartelle dei siti web, i portali"]},"prefLabel":{"fr":"Sites Web","it":"Siti web","sv":"Webbplatser","no":"Nettsteder","de":"Websites","en":"Web sites"},"notation":"025.0422","historyNote":{"de":["Erweitert aus 025.04, 2008-08, Edition 22"],"sv":["Webbplatser under 025.04, 2008-08, Edition 22"],"no":["Nettsteder utvidet fra 025.04, 2008-08, Edition 22"],"en":["Web sites continued from 025.04, 2008-08, Edition 22"],"it":["I siti web specificati da 025.04, 2008-08, Edition 22"],"fr":["Sites Web prolongé à partir de 025.04, 2008-08, Edition 22"]},"type":"Concept","modified":"2021-01-19T07:51:53Z","inScheme":"https://id.oclc.org/worldcat/ddc/","created":"2008-08-28","broader":"https://id.oclc.org/worldcat/ddc/E3BfQcQb8xjtVxb8Br6p8xyRPP","narrower":"https://id.oclc.org/worldcat/ddc/E3M6jGBd49y8kFHCxpwTXMP9Jr","@context":"https://id.oclc.org/worldcat/ddc/context.json"}


현재 DDC 검색 로직 (DeweyClient._get_json)
✅ 이미 3단계 캐싱이 구현되어 있습니다!
사용자가 "140" 검색
    ↓
1️⃣ LRU 메모리 캐시 확인 (256개)
    ├─ 있음 → 즉시 반환 ⚡ (밀리초)
    └─ 없음 → 2단계로
    ↓
2️⃣ DB 캐시 확인 (notation 기반)
    ├─ db.get_dewey_by_notation("140")
    ├─ 있음 → LRU에 저장 후 반환 ⚡⚡ (10~50ms)
    └─ 없음 → 3단계로
    ↓
3️⃣ DB 캐시 확인 (IRI/URL 기반, 하위 호환)
    ├─ db.get_dewey_from_cache(url)
    ├─ 있음 → LRU에 저장 후 반환 ⚡⚡
    └─ 없음 → 4단계로
    ↓
4️⃣ DLD API 호출 (최후 수단)
    ├─ requests.get(url) 🐌 (1~3초)
    ├─ 성공 → DB에 저장 + LRU에 저장
    ├─ 401 오류 → 토큰 갱신 후 재시도 (최대 3회)
    ├─ 429 오류 → 30초 대기 후 재시도
    └─ 반환


그동안의 비밀
사용자 체감
"140 검색했는데 왜 이렇게 느리지? 🤔"
"분명 캐시 있다고 했는데..."
"93MB나 만들었는데 왜 여전히 느릴까?"
실제 내부 동작
# 매번 이렇게 작동했음 😱
검색 버튼 클릭
  ↓
API 호출 1: /api/url?ddc=140  (IRI 매핑)  ← 이게 문제!
  → 500ms~1초
  ↓
API 호출 2: /worldcat/ddc/E37xXj...  (본문)
  → 캐시 히트! 10ms
  ↓
"왜 1초나 걸리지?" 😕
캐시는 있었지만
✅ main 데이터 캐시: 작동함 (2번째 호출)
❌ IRI 매핑 캐시: 안 씀 (1번째 호출은 항상 API)
결과: 절반만 캐시 활용! 😭


이제 수정 후
검색 버튼 클릭
  ↓
DB에서 IRI 조회  ← 10ms ⚡
  ↓
DB에서 main 조회  ← 10ms ⚡
  ↓
"와 빠르다!" 🚀

총 소요 시간: ~20ms (기존의 1/50!)


OCLC API Rate Limit 정보
제한 기준:
✅ WSKey (API Key) 기반 - IP 주소가 아닌 API 키 단위로 제한
하루 50,000 쿼리 제한
Rolling 24시간 제한 (고정된 시간이 아닌 슬라이딩 윈도우)
수감 기간:
정확한 기간은 공식 문서에 명시되어 있지 않음
일반적으로 Rolling 24시간이므로, 첫 요청부터 24시간 동안의 요청 수를 세는 방식
즉, 요청이 점진적으로 "만료"되면서 다시 사용 가능해짐
확인 방법: 429 응답 헤더에 Retry-After 또는 X-RateLimit-Reset 같은 헤더가 있을 수 있으니, 다음번에 429 에러 발생 시 응답 헤더를 로깅해보면 정확한 대기 시간을 알 수 있습니다. 다행인 점:
IP 기반이 아니라서 IP 변경으로는 우회 불가능
하지만 Rolling 방식이라 최대 24시간만 기다리면 됨
요청이 점진적으로 풀리므로, 몇 시간 후에 조금씩 사용 가능할 수도 있음