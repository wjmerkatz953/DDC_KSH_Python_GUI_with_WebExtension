dewey_cache.pdf 이 DB에는 아래와 같은 자료가 115k 건 있다. 그래서 KSH Local 탭 하단의 biblio db(kdc to ddc db) 검색 결과 테이블뷰에 컬럼을 하나 추가하고 ddc 컬럼의 ddc를 이 db에서 검색하여 ddc_keyword 테이블의 keyword 컬럼에 있는 내용을 보여주려고 한다.
신규 컬럼의 이름은

따라서 이 작업은 총 5개의 탭에 대해서도 실시할 예정이다. 우선
qt_TabView_KSH_Local.py     # DDC 컬럼 오른쪽에 신규 컬럼 추가(신규 컬럼명 DDC Label)
qt_TabView_NLK.py    # 082 컬럼 오른쪽에 신규 컬럼 추가(신규 컬럼명 082 Label)
qt_TabView_Western.py    # 082 컬럼 오른쪽에 신규 컬럼 추가(신규 컬럼명 082 Label)
qt_TabView_Global.py    # 082 컬럼 오른쪽에 신규 컬럼 추가(신규 컬럼명 082 Label)
qt_TabView_Dewey.py     # DDC 컬럼 오른쪽에 신규 컬럼 추가(신규 컬럼명 DDC Label)

- 기본 사항
하나의 ddc 번호에 대해 복수의 label이 존재하기에
DDC Label 컬럼에는 복수의 행에 나뉘어진 내용들을 합쳐서 보여준다.
아래와 같이 한 ddc 번호당 label이 여러개 있는 경우에는 모든 행의 레이블을 다 합치고 세미콜론으로 구분한다.
202.113	Male gods	pref
202.113	Male gods	alt
202.113	Gods--male	alt
202.114	Female goddesses	pref
202.114	Femininity of God	alt
202.114	Goddesses	alt
202.114	Female goddesses	alt

-컬럼 표시 형식 예시
DDC: 202.113
DDC Label: Male gods(pref); Male gods(alt); Gods--male(alt)



- 엣지 케이스 대응
DDC 컬럼에 데이터가 없는 경우: DDC Label도 blank 처리
DDC 컬럼에 복수의 DDC 번호가 존재하는 경우: 복수의 DDC에 대해 전부 다 Dewey cache를 조회해서 보여준다. 이경우에는 각 DDC 번호를 각 번호의 첫 label 앞에 붙여주고 DDC 번호와 label은 세미콜론으로 구분한다.
DDC: 202.113, 202.114
DDC Label: 202.113; Male gods(pref); Male gods(alt); Gods--male(alt); 202.114; Female goddesses(pref); Femininity of God(alt); Goddesses(alt); Female goddesses(alt);

Western 과 Global 탭에서는 DDC 번호 추출을 위한 정규식 적용이 필요함.


iri   / ddc / keyword / term_type
https://id.oclc.org/worldcat/ddc/E3rqXwVb6WwVfgQtt3DfPdFFYT	201.77	Environmental abuse--social theology	alt
https://id.oclc.org/worldcat/ddc/E3rqXwVb6WwVfgQtt3DfPdFFYT	201.77	Ecology--social theology	alt
https://id.oclc.org/worldcat/ddc/E3rqXwVb6WwVfgQtt3DfPdFFYT	201.77	Pollution--social theology	alt
https://id.oclc.org/worldcat/ddc/E3rqXwVb6WwVfgQtt3DfPdFFYT	201.77	Environment--social theology	alt
https://id.oclc.org/worldcat/ddc/E3rqXwVb6WwVfgQtt3DfPdFFYT	201.77	Natural resources--social theology	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Doctrines	pref
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Creeds	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Doctrinal theology	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Contextual theology	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Theology	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Apologetics	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Dogma	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Catechisms	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Confessions of faith	alt
https://id.oclc.org/worldcat/ddc/E3MCMjdXp9WyXKGbDtVTYPtR3f	202	Polemics--comparative religion	alt
https://id.oclc.org/worldcat/ddc/E3hCk3PmcWcBGwCVHRmWj48tCc	202.05	Theology--serials	pref
https://id.oclc.org/worldcat/ddc/E3hCk3PmcWcBGwCVHRmWj48tCc	202.05	Theology--serials	alt
https://id.oclc.org/worldcat/ddc/E3cQPfVvx7QGtx8PMKGrqdF69T	202.082	Feminist theology	pref
https://id.oclc.org/worldcat/ddc/E3cQPfVvx7QGtx8PMKGrqdF69T	202.082	Feminist theology	alt
https://id.oclc.org/worldcat/ddc/E44kY8Ycm3KJ6hBRVjyc8W9X97	202.08996	Black theology	pref
https://id.oclc.org/worldcat/ddc/E44kY8Ycm3KJ6hBRVjyc8W9X97	202.08996	Black theology	alt
https://id.oclc.org/worldcat/ddc/E3CWqhyPr9CYQfGMcBTTKqbchd	202.092	Theologians	pref
https://id.oclc.org/worldcat/ddc/E3CWqhyPr9CYQfGMcBTTKqbchd	202.092	Theologians	alt
https://id.oclc.org/worldcat/ddc/E3htMvd96t33HgkvDRYJxwrQ87	202.1	Objects of worship and veneration	pref
https://id.oclc.org/worldcat/ddc/E3htMvd96t33HgkvDRYJxwrQ87	202.1	Spiritualism--comparative religion	alt
https://id.oclc.org/worldcat/ddc/E3htMvd96t33HgkvDRYJxwrQ87	202.1	Spiritual beings	alt
https://id.oclc.org/worldcat/ddc/E3htMvd96t33HgkvDRYJxwrQ87	202.1	Animism--comparative religion	alt
https://id.oclc.org/worldcat/ddc/E3htMvd96t33HgkvDRYJxwrQ87	202.1	Fetishism--religion	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	God, gods, goddesses, divinities and deities	pref
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	Knowledge of God--comparative religion	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	Totemism	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	Gods	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	Gods and goddesses	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	Deities	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	God--comparative religion	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	Divinities	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	Monotheism--comparative religion	alt
https://id.oclc.org/worldcat/ddc/E3hyc97kRwFFpB6DF6jKqxCxtQ	202.11	Existence of God--comparative religion	alt
https://id.oclc.org/worldcat/ddc/E37mdHhHHQxwMB6qVwWbBkyJ7q	202.113	Male gods	pref
https://id.oclc.org/worldcat/ddc/E37mdHhHHQxwMB6qVwWbBkyJ7q	202.113	Male gods	alt
https://id.oclc.org/worldcat/ddc/E37mdHhHHQxwMB6qVwWbBkyJ7q	202.113	Gods--male	alt
https://id.oclc.org/worldcat/ddc/E3KXPRYymWGkWHjG8T6RVdxGvK	202.114	Female goddesses	pref
https://id.oclc.org/worldcat/ddc/E3KXPRYymWGkWHjG8T6RVdxGvK	202.114	Femininity of God	alt
https://id.oclc.org/worldcat/ddc/E3KXPRYymWGkWHjG8T6RVdxGvK	202.114	Goddesses	alt
https://id.oclc.org/worldcat/ddc/E3KXPRYymWGkWHjG8T6RVdxGvK	202.114	Female goddesses	alt
https://id.oclc.org/worldcat/ddc/E3H6mFpY4xWD6BjM9hC7yJq8q4	202.11409012	Goddesses--to 4000 B.C.	pref
https://id.oclc.org/worldcat/ddc/E3H6mFpY4xWD6BjM9hC7yJq8q4	202.11409012	Goddesses--to 4000 B.C.	alt


문서를 검토한 결과, 몇 가지 명확히 할 부분이 있습니다:
데이터베이스 연결 정보: dewey_cache.pdf라고 되어 있는데 실제로는 DB 파일인가요? 파일명과 경로를 확인하고 싶습니다. (예: SQLite DB인지, 다른 형식인지)
컬럼 표시 형식의 불일치:
Line 25에서는 Male gods(pref); Male gods(alt); Gods--male(alt) (세미콜론 뒤 2칸 공백)
Line 33에서는 202.113; Male gods(pref); Male gods(alt) (세미콜론 뒤 1칸 공백 또는 2칸 공백) 정확한 구분자 형식이 무엇인가요?
Line 33의 오류: Goddesses Female goddesses(alt) 부분에 세미콜론이 누락된 것 같습니다. 정확한 형식은 Goddesses(alt); Female goddesses(alt)인가요?
Western/Global 탭의 정규식: "DDC 번호 추출을 위한 정규식 적용이 필요함"이라고만 되어 있는데, 현재 Western/Global 탭의 082 컬럼에는 어떤 형식으로 데이터가 저장되어 있나요? (예: 082$a 같은 MARC 필드 형식인지)
DB 테이블명: ddc_keyword 테이블에서 조회한다고 하셨는데, 정확한 DB 파일명과 테이블 구조를 확인하고 싶습니다.


1.self.dewey_db_path = "dewey_cache.db"  이 db는  search_query_manager.py, database_manager.py 에서  관련 정보를 많이 얻을 수 있다.
2. 세미콜론 뒤 공백 1개로 통일했다.
3. 수정했음.
4. 일단 이 부분은 이 작업이 끝난 후에 처리하자.
5. 정확한 DB 파일명과 테이블 구조를 확인하고 싶습니다. -> 테이블 구조는  프로젝트 폴더 내에 있는 dewey_cache.pdf 를 참고하면 된다.



# DDC 캐시 관련 함수
    search_query_manager.py
        get_dewey_from_cache
        search_ddc_by_keyword