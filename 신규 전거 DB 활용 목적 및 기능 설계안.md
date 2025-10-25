Person_sample.json 이런 형식의 json을 sqplite  db로 전환하려한다.
{
    "@id" : "nlk:KAC199600018",
    "@type" : "nlon:Author",
    "associatedLanguage" : "영어",
    "birthYear" : "1938^^http://www.w3.org/2001/XMLSchema#int",
    "corporateName" : "캘리포니아 주립대학교 하스 경영대학원 (명예교수)프로핏 브랜드 전략 (부회장)",
    "create" : [ "nlk:WMO200902907", "nlk:KMO200746599", "nlk:WMO200602060", "nlk:KMO200415306", "nlk:CNTS-00099012993", "nlk:JMO200300047", "nlk:KMO199907475", "nlk:CNTS-00092115969", "nlk:CNTS-00047902970", "nlk:KMO199300857", "nlk:KMO199606849", "nlk:KMO200607125", "nlk:KMO199012190", "nlk:CNTS-00093075895", "nlk:KMO200330178", "nlk:WMO201703211", "nlk:CNTS-00091430665", "nlk:WMO200904554", "nlk:CNTS-00108698548", "nlk:CNTS-00047880740", "nlk:KMO200536512", "nlk:KMO199608303", "nlk:WMO199601718", "nlk:WMO000032420", "nlk:WMO200412476", "nlk:CNTS-00047914716", "nlk:KMO198908613", "nlk:WMO200300010", "nlk:WMO200712919", "nlk:KMO202124037", "nlk:WMO200601824", "nlk:KMO200634803", "nlk:CNTS-00077608461", "nlk:CNTS-00091438232", "nlk:CNTS-00099046372", "nlk:CNTS-00089710550", "nlk:CNTS-00047855835", "nlk:KMO201120719", "nlk:WMO200602227", "nlk:KVM201302676", "nlk:WMO199601992", "nlk:WMO199601283", "nlk:KMO201053924", "nlk:WMO200010683", "nlk:CNTS-00047915570", "nlk:KMO200909640", "nlk:WMO200006824", "nlk:JMO202003192", "nlk:KMO199506786", "nlk:KMO200911934", "nlk:WMO200412580", "nlk:KMO200933545", "nlk:KMO202008863", "nlk:CNTS-00086733631", "nlk:CNTS-00047863971" ],
    "datePublished" : "2022-12-02T14:05:19^^http://www.w3.org/2001/XMLSchema#dateTime",
    "fieldOfActivity" : [ "경영학[經營學]", "마케팅[marketing]" ],
    "isni" : "0000000122783868",
    "source" : [ "마케팅전략, (석정), 2010", "가상국제전거파일(VIAF) http://viaf.org/" ],
    "modified" : "2022-02-07T11:41:10^^http://www.w3.org/2001/XMLSchema#dateTime",
    "gender" : "남성",
    "jobTitle" : [ "임원[任員]", "교수(대학)[敎授]", "경영 컨설턴트[經營--]" ],
    "label" : "Aaker, David A.",
    "sameAs" : [ "http://viaf.org/viaf/37004329", "http://id.loc.gov/authorities/names/n79089154", "http://www.isni.org/isni/0000000122783868" ],
    "altLabel" : [ "アーカー, デービッド A.", "Aaker, D. A.", "Aaker, David Allen", "아커, 데이비드 A.", "아커, D. A.", "에이커, 데이비드 A." ],
    "prefLabel" : "Aaker, David A.",
    "name" : "Aaker, David A."
  },

실제 DB추출 스크립트: Final_build_kac_authority_and_biblio_db.py

용도
1.저자 이름이나 KAC를 검색해서 저작목록을 획득한다.
2.qt_TabView_KACAuthorities.py  이 탭의 기능을 보조한다.
즉, qt_TabView_KACAuthorities.py 웹스크레이핑으로 불러온 데이터의 KAC를 검색키로 이용해 신규 전거 로컬 DB를 조회해서 고속으로 모든 저자들의 저작 목록 데이터를 보강한다.
3. 그러니 2번의 기능을 위해선 모든 NLK의 identifier 정보를 다 갖고 있는 로컬 서지 db가 필요하다. 그래서 이것도 새롭게 추출할 생각이다. 이건 3천만건 정도가 되지 않을까 싶다.
4. 각각 별도의 DB 파일을 구축한다.(저자 전거 db, 서지 db)
5. 저자 전거 db는 모든 항목을 다 추출한다.
6. 저자 전거 db의 핵심 항목은 id, create, name, prefLabel, jobTitle, fieldOfActivity

실제 주요 시나리오.

id 항목의 KAC 코드를 검색키로 사용해서 저자명을 획득한다.
create 항목의 identifier들을 서지 DB에서 조회해서 제목, 출판연도, KSH 등의 정보를 추출한다.
이름이나 KAC코드로 검색하면 json 내의 모든 항목을 정리해서 목록으로 앱에서 보여준다.

  }, {
    "@id" : "nlk:WMO202201384",
    "@type" : [ "nlon:OfflineMaterial", "nlon:Book", "bibo:Book" ],
    "extent" : [ "23 cm", "xii, 242 pages", "illustrations" ],
    "language" : "http://lod.nl.go.kr/language/eng",
    "place" : "http://lod.nl.go.kr/countries/us",
    "bibliography" : "Includes bibliographical references (pages 221-236) and index",
    "classificationNumberOfNLK" : "418.040285",
    "datePublished" : "2025-08-13T16:36:07^^http://www.w3.org/2001/XMLSchema#dateTime",
    "ddc" : "418.040285",
    "editionOfDDC" : "23",
    "issuedYear" : "2020",
    "itemNumberOfNLK" : "22-1",
    "localHolding" : "WM1047408, W",
    "publicationPlace" : "New York",
    "remainderOfTitle" : "challenges and opportunities",
    "titleOfSeries" : "Routledge advances in translation and interpreting studies",
    "typeOfData" : "nlk:dt_gm",
    "uniformTitleOfSeries" : "Routledge advances in translation and interpreting studies",
    "volumeOfSeries" : "42",
    "dc:creator" : "Youdale, Roy",
    "publisher" : "Routledge, Taylor & Francis Group",
    "creator" : "nlk:KAC202333977",
    "issued" : "2020",
    "subject" : [ "http://id.ndl.go.jp/auth/ndlsh/00563405", "http://id.ndl.go.jp/auth/ndlsh/00565743", "http://id.loc.gov/authorities/subjects/sh85079361", "http://id.loc.gov/authorities/subjects/sh85077507", "http://id.ndl.go.jp/auth/ndlsh/00560981", "http://id.ndl.go.jp/auth/ndlsh/00573560", "http://id.loc.gov/authorities/subjects/sh85136958" ],
    "title" : "Using computers in the translation of literary style",
    "isbn" : [ "036714123X (hbk)", "0367727420 (pbk)", "9780367727420 (pbk)", "9780367141233 (hbk)" ],
    "label" : "Using computers in the translation of literary style / Roy Youdale",
    "sameAs" : "http://libris.kb.se/bib/w6dfxp57t6zmgx20"
  },
위는 서지 db의 샘플 중 하니이다. creator에 KAC 코드가 존재하며 이를 통해 서지 db에서 책 제목을 검색해서 얻은 KAC를 검색키로 활용해 각 저자의 다른 저작물과 이름을 획득한다. 단독 저자의 저작물이면 이런 식으로 다른 DB를 이용해 저자명을 획득할 이유가 없지만, 복수의 저자가 있는 경우에는 서지 DB에 기재된 저자의 순서와 KAC 코드 순서가 일치하지 않아서, 신뢰할 수 없기 때문이다.




저자 전거 json 초반부
{
  "@graph" : [ {
    "@id" : "http://listinc.kr/id/member/joyhong",
    "rdf:type" : "http://xmlns.com/foaf/0.1/Person",
    "mbox" : [ "mailto:joyhong@listinc.kr", "mailto:joyhong@li-st.com" ],
    "name" : [ "허홍수@ko", "JoyHong@en" ]
  }, {
    "@id" : "http://listinc.kr/id/member/wonseok.oh",
    "rdf:type" : "http://xmlns.com/foaf/0.1/Person",
    "mbox" : [ "mailto:wonseok.oh@listinc.kr", "mailto:wonseok.oh@li-st.com" ],
    "name" : [ "오원석@ko", "Wonseok Oh@en" ]
  }, {
    "@id" : "nlk:046",
    "associatedLanguage" : "영어",
    "birthYear" : "1952^^http://www.w3.org/2001/XMLSchema#int",
    "corporateName" : [ "[前]서던일리노이주립대학교 인류학 (조교수)", "[前]펜실베니아주립대학교 (강사)", "Dartmouth College 인류학 (교수)" ],
    "deathYear" : "2022^^http://www.w3.org/2001/XMLSchema#int",
    "fieldOfActivity" : "인류학[人類學]",
    "isni" : "0000000026552912",
    "source" : [ "Rethinking the Aztec economy, (University of Arizona Press), 2017", "가상국제전거파일(VIAF) http://viaf.org/" ],
    "modified" : "2023-05-23T16:09:19^^http://www.w3.org/2001/XMLSchema#dateTime",
    "gender" : "여성",
    "jobTitle" : "교수(대학)[敎授]",
    "rdf:type" : "http://xmlns.com/foaf/0.1/Person",
    "label" : "Nichols, Deborah L.",
    "sameAs" : "http://www.isni.org/isni/0000000026552912",
    "prefLabel" : "Nichols, Deborah L.",
    "name" : "Nichols, Deborah L."
  }, {
    "@id" : "nlk:KAC199600018",
    "@type" : "nlon:Author",
    "associatedLanguage" : "영어",
    "birthYear" : "1938^^http://www.w3.org/2001/XMLSchema#int",
    "corporateName" : [ "프로핏 브랜드 전략 (부회장)", "캘리포니아 주립대학교 하스 경영대학원 (명예교수)" ],
    "create" : [ "nlk:KMO200746599", "nlk:WMO200602060", "nlk:KMO200415306", "nlk:CNTS-00099012993", "nlk:JMO200300047", "nlk:KMO199907475", "nlk:CNTS-00092115969", "nlk:CNTS-00047902970", "nlk:KMO199300857", "nlk:CNTS-00130087620", "nlk:KMO199606849", "nlk:KMO200607125", "nlk:KMO199012190", "nlk:CNTS-00093075895", "nlk:KMO200330178", "nlk:WMO201703211", "nlk:CNTS-00091430665", "nlk:CNTS-00108698548", "nlk:CNTS-00047880740", "nlk:KMO200536512", "nlk:KMO199608303", "nlk:WMO199601718", "nlk:WMO000032420", "nlk:CNTS-00132096903", "nlk:WMO200412476", "nlk:CNTS-00047914716", "nlk:KMO198908613", "nlk:WMO200300010", "nlk:WMO200712919", "nlk:KMO202124037", "nlk:WMO200601824", "nlk:KMO200634803", "nlk:CNTS-00077608461", "nlk:CNTS-00091438232", "nlk:CNTS-00099046372", "nlk:CNTS-00089710550", "nlk:CNTS-00047855835", "nlk:KMO201120719", "nlk:WMO200602227", "nlk:KVM201302676", "nlk:WMO199601992", "nlk:WMO199601283", "nlk:WMO200010683", "nlk:CNTS-00047915570", "nlk:WMO200006824", "nlk:KMO199506786", "nlk:JMO202003192", "nlk:WMO200412580", "nlk:KMO202008863", "nlk:KMO200933545", "nlk:CNTS-00086733631", "nlk:CNTS-00047863971" ],
    "fieldOfActivity" : [ "경영학[經營學]", "마케팅[marketing]" ],
    "isni" : "0000000122783868",
    "source" : [ "마케팅전략, (석정), 2010", "가상국제전거파일(VIAF) http://viaf.org/" ],
    "modified" : "2025-04-22T08:40:24^^http://www.w3.org/2001/XMLSchema#dateTime",
    "gender" : "남성",
    "jobTitle" : [ "임원[任員]", "교수(대학)[敎授]", "경영 컨설턴트[經營--]" ],
    "rdf:type" : "http://xmlns.com/foaf/0.1/Person",
    "label" : "Aaker, David A.",
    "sameAs" : [ "http://d-nb.info/gnd/123018641", "http://id.ndl.go.jp/auth/entity/00430845", "http://www.idref.fr/033173672/id", "http://viaf.org/viaf/37004329", "http://dbpedia.org/resource/David_Aaker", "http://datos.bne.es/resource/XX1645510", "http://www.wikidata.org/entity/Q1173491", "https://id.oclc.org/worldcat/entity/E39PBJbRjGYtHr7dy9MWw9RdwC", "http://data.bnf.fr/#foaf:Person", "http://id.loc.gov/authorities/names/n79089154", "http://www.isni.org/isni/0000000122783868" ],
    "altLabel" : [ "アーカー, デービッド A.", "Aaker, D. A.", "Aaker, David Allen", "아커, 데이비드 A.", "아커, D. A.", "에이커, 데이비드 A." ],
    "prefLabel" : "Aaker, David A.",
    "name" : "Aaker, David A."
  },



  아래는 저자 전거 json의 끝부분
    }, {
    "@id" : "nlk:KAC2018H4729",
    "@type" : "nlon:Author",
    "associatedLanguage" : "한국어",
    "create" : [ "nlk:CNTS-00092629557", "nlk:CNTS-00071095074" ],
    "fieldOfActivity" : "음악(예술)[音樂]",
    "isni" : "0000000480101898",
    "source" : [ "네이버뮤직 https://music.naver.com/", "한국음악저작권협회 https://www.komca.or.kr", "COME FLY, 2016", "Dear.My Life, 2016" ],
    "modified" : "2019-09-19T13:36:24^^http://www.w3.org/2001/XMLSchema#dateTime",
    "gender" : "여성",
    "jobTitle" : [ "가수[歌手]", "작사가[作詞家]", "작곡가[作曲家]" ],
    "url" : "https://www.facebook.com/beautifulplacewina",
    "rdf:type" : "http://xmlns.com/foaf/0.1/Person",
    "label" : "위나",
    "sameAs" : [ "http://www.isni.org/isni/0000000480101898", "http://viaf.org/viaf/168154590223543082153" ],
    "altLabel" : [ "김민정", "Kim, Minjeong" ],
    "prefLabel" : "위나",
    "name" : "위나"
  }, {
    "@id" : "nlk:KAC2018H4730",
    "@type" : "nlon:Author",
    "associatedLanguage" : "한국어",
    "create" : [ "nlk:CNTS-00086368161", "nlk:KMU201703382" ],
    "fieldOfActivity" : "음악(예술)[音樂]",
    "isni" : "0000000472230358",
    "source" : [ "네이버 뮤직 https://music.naver.com", "권태민의 사랑초, 2016" ],
    "modified" : "2018-11-15T11:02:29^^http://www.w3.org/2001/XMLSchema#dateTime",
    "gender" : "남성",
    "jobTitle" : [ "가수[歌手]", "트로트가수" ],
    "rdf:type" : "http://xmlns.com/foaf/0.1/Person",
    "label" : "권태민",
    "sameAs" : [ "http://www.isni.org/isni/0000000472230358", "http://viaf.org/viaf/14155103914276201205" ],
    "prefLabel" : "권태민",
    "name" : "권태민"
  }, {
    "@id" : "nlk:KAC2018H4731",
    "associatedLanguage" : "한국어",
    "corporateName" : "한국방송통신전파진흥원",
    "fieldOfActivity" : "정보 기술[情報技術]",
    "isni" : "0000000473459883",
    "source" : "한국과학기술정보연구원(KISTI) https://www.kisti.re.kr/",
    "modified" : "2018-10-24T16:12:58^^http://www.w3.org/2001/XMLSchema#dateTime",
    "jobTitle" : "연구원(연구자)[硏究員]",
    "rdf:type" : "http://xmlns.com/foaf/0.1/Person",
    "label" : "라유선",
    "sameAs" : [ "http://www.isni.org/isni/0000000473459883", "http://viaf.org/viaf/200154590232743082381" ],
    "prefLabel" : "라유선",
    "name" : "라유선"
  }, {
    "@id" : "nlk:KAC2018H4732",
    "@type" : "nlon:Author",
    "associatedLanguage" : "한국어",
    "birthYear" : "1968^^http://www.w3.org/2001/XMLSchema#int",
    "corporateName" : [ "한국해양과학기술원 (책임기술원)", "[前]미국 우즈홀해양연구소 (방문연구원)" ],
    "create" : [ "nlk:CNTS-00118458133", "nlk:KDM201267113", "nlk:KSI000616922", "nlk:KDM199523985" ],
    "fieldOfActivity" : [ "지구 과학[地球科學]", "해양학[海洋學]" ],
    "isni" : "0000000473692191",
    "source" : [ "한국과학기술정보연구원(KISTI) https://www.kisti.re.kr", "한국연구자정보(KRI) https://www.kri.go.kr", "1994년 여름 동해 표층 해수의 pC0₂ 및 pCH₄ 분포 특성, (서울대학교), 1995" ],
    "modified" : "2021-11-12T15:43:40^^http://www.w3.org/2001/XMLSchema#dateTime",
    "gender" : "여성",
    "jobTitle" : "연구원(연구자)[硏究員]",
    "rdf:type" : "http://xmlns.com/foaf/0.1/Person",
    "label" : "최상화",
    "sameAs" : [ "http://viaf.org/viaf/204154590234643082394", "http://www.isni.org/isni/0000000473692191" ],
    "prefLabel" : "최상화",
    "name" : "최상화"
  }, {
    "@id" : "nlk:KAC2018H4733",
    "associatedLanguage" : "한국어"
  } ],
  "@context" : {
    "prefLabel" : {
      "@id" : "http://www.w3.org/2004/02/skos/core#prefLabel"
    },
    "corporateName" : {
      "@id" : "http://lod.nl.go.kr/ontology/corporateName"
    },
    "associatedLanguage" : {
      "@id" : "http://lod.nl.go.kr/ontology/associatedLanguage"
    },
    "jobTitle" : {
      "@id" : "http://schema.org/jobTitle"
    },
    "modified" : {
      "@id" : "http://purl.org/dc/terms/modified"
    },
    "isni" : {
      "@id" : "http://lod.nl.go.kr/ontology/isni"
    },
    "label" : {
      "@id" : "http://www.w3.org/2000/01/rdf-schema#label"
    },
    "sameAs" : {
      "@id" : "http://www.w3.org/2002/07/owl#sameAs"
    },
    "name" : {
      "@id" : "http://xmlns.com/foaf/0.1/name"
    },
    "source" : {
      "@id" : "http://purl.org/dc/elements/1.1/source"
    },
    "fieldOfActivity" : {
      "@id" : "http://lod.nl.go.kr/ontology/fieldOfActivity"
    },
    "altLabel" : {
      "@id" : "http://www.w3.org/2004/02/skos/core#altLabel"
    },
    "create" : {
      "@id" : "http://lod.nl.go.kr/ontology/create",
      "@type" : "@id"
    },
    "gender" : {
      "@id" : "http://schema.org/gender"
    },
    "birthYear" : {
      "@id" : "http://lod.nl.go.kr/ontology/birthYear"
    },
    "relatedOrganization" : {
      "@id" : "http://lod.nl.go.kr/ontology/relatedOrganization",
      "@type" : "@id"
    },
    "birthPlace" : {
      "@id" : "http://schema.org/birthPlace"
    },
    "deathYear" : {
      "@id" : "http://lod.nl.go.kr/ontology/deathYear"
    },
    "url" : {
      "@id" : "http://schema.org/url"
    },
    "location" : {
      "@id" : "http://schema.org/location"
    },
    "comment" : {
      "@id" : "http://www.w3.org/2000/01/rdf-schema#comment"
    },
    "datePublished" : {
      "@id" : "http://lod.nl.go.kr/ontology/datePublished"
    },
    "personalName" : {
      "@id" : "http://lod.nl.go.kr/ontology/personalName"
    },
    "relatedPerson" : {
      "@id" : "http://lod.nl.go.kr/ontology/relatedPerson",
      "@type" : "@id"
    },
    "schema" : "http://schema.org/",
    "@vocab" : "http://lod.nl.go.kr/resource/",
    "nlloc" : "http://lod.nl.go.kr/location/",
    "geonames" : "http://www.geonames.org/ontology#",
    "nlcon" : "http://lod.nl.go.kr/countries/",
    "owl" : "http://www.w3.org/2002/07/owl#",
    "nllib" : "http://lod.nl.go.kr/library/",
    "xsd" : "http://www.w3.org/2001/XMLSchema#",
    "skos" : "http://www.w3.org/2004/02/skos/core#",
    "rdfs" : "http://www.w3.org/2000/01/rdf-schema#",
    "units" : "http://lod.nl.go.kr/units/",
    "nlfloc" : "http://lod.nl.go.kr/foreignLocation/",
    "geo" : "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "nlgov" : "http://lod.nl.go.kr/government/",
    "dcterms" : "http://purl.org/dc/terms/",
    "vann" : "http://purl.org/vocab/vann/",
    "event" : "http://purl.org/NET/c4dm/event.owl#",
    "foaf" : "http://xmlns.com/foaf/0.1/",
    "cc" : "http://creativecommons.org/ns#",
    "nla" : "http://lod.nl.go.kr/author/",
    "org" : "http://www.w3.org/ns/org#",
    "nlddc" : "http://lod.nl.go.kr/ddc/",
    "voaf" : "http://purl.org/vocommons/voaf#",
    "nlkdc" : "http://lod.nl.go.kr/kdc/",
    "nluv" : "http://lod.nl.go.kr/university/",
    "nlk" : "http://lod.nl.go.kr/resource/",
    "nlon" : "http://lod.nl.go.kr/ontology/",
    "tmon" : "http://t-mon/",
    "nls" : "http://lod.nl.go.kr/subject/",
    "rdf" : "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "bibo" : "http://purl.org/ontology/bibo/",
    "vs" : "http://www.w3.org/2003/06/sw-vocab-status/ns#",
    "bibframe" : "http://id.loc.gov/ontologies/bibframe/",
    "nlsc" : "http://lod.nl.go.kr/scheme/",
    "dc" : "http://purl.org/dc/elements/1.1/"
  }
}



서지 DB

아래 버전으로 일단 저자 전거 DB는 완성했다.

남은 건 서지 DB 이다.

- 서지 DB를 쓰게 되는 주요 시나리오
1.저자 이름이나 KAC를 검색해서 저작목록을 획득한다.
2.nlk_id 를 검색해서 title을 획득한다. 이 기능을 통해 qt_TabView_KACAuthorities.py 이 탭의 기능을 보조한다.
  즉, 저작목록 컬럼을 추가하며 별도의 추가 검색 없이도 저작목록을 상당부분 확인할 수 있도록 하는 것이다.

DB 용량을 감소시키기 위해 Turbo build 왼쪽에 Light Mode 를 추가한다.
Light Mode 를 선택하면, 색인, FTS5, raw_json 없이 추출한다.

아래는 샘플 중 하나이다.
 {
    "@id" : "nlk:KDM200218346",
    "@type" : [ "bibo:Thesis", "nlon:OfflineMaterial", "nlon:Book" ],
    "extent" : [ "삽도", "iv, 28장", "26cm" ],
    "language" : "http://lod.nl.go.kr/language/kor",
    "place" : "http://lod.nl.go.kr/countries/jjk",
    "classificationNumberOfNLK" : "528.1",
    "datePublished" : "2025-08-13T16:36:07^^http://www.w3.org/2001/XMLSchema#dateTime",
    "ddc" : "636.089",
    "ddcn" : "http://lod.nl.go.kr/ddc/636_e21",
    "degreeYear" : "2002",
    "department" : "수의학과",
    "editionOfDDC" : "21",
    "editionOfKDC" : "4",
    "issuedYear" : "2002",
    "itemNumberOfNLK" : "2-15",
    "kdc" : "528.1",
    "kdcn" : "http://lod.nl.go.kr/kdc/528_e4",
    "keyword" : [ "연충류", "영남지방", "장", "장내", "감염", "일부지역", "고양이" ],
    "localHolding" : [ "EM2572088, 2, DM", "EM2572087" ],
    "publicationPlace" : "제주",
    "typeOfData" : "nlk:dt_dm",
    "creator" : "최규형",
    "publisher" : "濟州大學校",
    "issued" : "2002",
    "dcterms:language" : "http://id.loc.gov/vocabulary/languages/kor",
    "title" : "영남지방 일부지역 고양이의 장내 연충류 감염상황",
    "degree" : "nlk:master",
    "label" : "영남지방 일부지역 고양이의 장내 연충류 감염상황 / 崔圭瀅",
    "sameAs" : "http://data.riss.kr/resource/Thesis/000009574939"
  },

모든 자료를 다 수집할 것이라서 컬럼을 많이 추가할 수도 없어. 간단하게 몇 개만 추가할 거야.

아래는 json에서 추출할 항목들이다.
1.
"@id" : "nlk:WMO202201384",
# db의 컬럼명은 "nlk_id"

2.
------------------------------
"issuedYear" : "2020",
"issued" : "2020",
"datePublished" : "2025-08-07T12:33:06^^http://www.w3.org/2001/XMLSchema#dateTime",

# 먼저 "issuedYear"를 찾아보고 있으면  우선 저장, 없으면 그 다음은 "datePublished", 둘 다 없으면 "issued"를 저장한다.
# db의 컬럼명은 "year"
------------------------------------

3.
"creator" : "nlk:KAC202333977",
# 저자가 여러 명 있으면 한 셀에 모두 저장하고 세미콜론으로 구분한다.
# db의 컬럼명은 "creator"

4.
"dc:creator" : "Youdale, Roy",
# 저자가 여러 명 있으면 한 셀에 모두 저장하고 세미콜론으로 구분한다.
# db의 컬럼명은 "dc:creator"

5.
"dcterms:creator" : {"@id" : "nlk:KAC202275703"},
# 저자가 여러 명 있으면 한 셀에 모두 저장하고 세미콜론으로 구분한다.
# db의 컬럼명은 "dc:creator"
# 추출하는 데이터는 "nlk:KAC202275703" 이다. {"@id" :  와  } 는 제거한다.

6.
"title" : "含金鑛産物買入業免許取消"
# db의 컬럼명은 "title"


7. raw_json
# 이 항목은 옵션.
