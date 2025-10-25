# 파일명: build_vector_db.py
# 버전: 3.0
# 설명: dewey_cache.db의 dewey_cache 테이블에서 '원본 JSON'을 직접 읽어,
#      의미적으로 훨씬 풍부한 벡터 DB를 생성하는 개선된 스크립트.
#
# --- v2.0 개선점 ---
# 1. (데이터 소스) 단일 키워드가 아닌 원본 JSON 전체를 활용하여 정보 손실을 최소화.
# 2. (문맥 강화) prefLabel, altLabel, scopeNote를 조합하여 각 DDC 항목에 대한
#    상세한 "설명 문서"를 동적으로 생성.
# 3. (검색 품질) 모델이 단어의 의미를 더 깊은 문맥 속에서 학습하게 하여 검색 정확도를 극대화.
#
# --- v3.0 개선점 ---
# 1. (유사어 확장) ConceptNet을 사용하여 각 DDC 항목의 관련 용어를 자동 생성
# 2. (검색 품질 향상) "bitcoin" 검색 시 "blockchain" DDC를 찾을 수 있도록 의미적 연결 강화

import sqlite3
import json
import time
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ConceptNet 임포트 (없으면 유사어 생성 건너뜀)
try:
    from conceptnet_lite import Label
    CONCEPTNET_AVAILABLE = True
    print("✅ ConceptNet 사용 가능")
except ImportError:
    CONCEPTNET_AVAILABLE = False
    print("⚠️ ConceptNet 미설치. 유사어 확장 기능이 비활성화됩니다.")
    print("   설치: pip install conceptnet-lite")

# --- 설정 ---
DB_PATH = "dewey_cache.db"
# ⚡ 성능 최적화: all-MiniLM-L6-v2는 all-mpnet-base-v2보다 5배 빠르고 정확도는 95% 유지
# all-mpnet-base-v2: 109M params, 검색 25초 | all-MiniLM-L6-v2: 22M params, 검색 1초
MODEL_NAME = "all-MiniLM-L6-v2"
INDEX_FILE = "ddc_index_from_json.faiss"
MAPPING_FILE = "ddc_mapping_from_json.json"
ENABLE_SYNONYM_EXPANSION = True  # 유사어 확장 활성화 (느려질 수 있음)
MAX_SYNONYMS = 10  # 각 용어당 최대 유사어 개수
# -----------


def get_related_terms(term):
    """
    ConceptNet을 사용하여 주어진 용어의 관련 용어를 추출합니다.

    Args:
        term: 검색할 용어 (예: "blockchain")

    Returns:
        관련 용어 리스트 (예: ["cryptocurrency", "bitcoin", "distributed ledger"])
    """
    if not CONCEPTNET_AVAILABLE or not ENABLE_SYNONYM_EXPANSION:
        return []

    try:
        # 용어를 정제 (소문자, 특수문자 제거)
        clean_term = term.lower().strip()
        if not clean_term or len(clean_term) < 3:
            return []

        # ConceptNet에서 레이블 검색
        label = Label.get(text=clean_term, language='en')
        if not label:
            return []

        # 관련 용어 추출
        related = []
        for edge in label.edges_out[:MAX_SYNONYMS]:
            if edge.relation.name in ['RelatedTo', 'Synonym', 'IsA', 'PartOf', 'UsedFor']:
                related_term = edge.end.text
                if related_term and related_term != clean_term:
                    related.append(related_term)

        return related[:MAX_SYNONYMS]

    except Exception as e:
        # ConceptNet 오류 무시하고 계속 진행
        return []


def expand_terms_with_synonyms(terms_list):
    """
    용어 리스트의 각 용어에 대해 ConceptNet에서 유사어를 찾아 확장합니다.

    Args:
        terms_list: 원본 용어 리스트 (예: ["blockchain", "NoSQL"])

    Returns:
        확장된 용어 리스트 (원본 + 유사어)
    """
    if not terms_list:
        return []

    expanded = list(terms_list)  # 원본 복사

    # 각 용어에 대해 유사어 추가
    for term in terms_list[:5]:  # 처리 시간을 위해 처음 5개만 확장
        related = get_related_terms(term)
        expanded.extend(related)

    # 중복 제거
    return list(set(expanded))


def build_from_json():
    print("=" * 70)
    print("DDC 벡터 DB 생성 스크립트 v3.0")
    print("=" * 70)
    print(f"✅ 임베딩 모델: {MODEL_NAME}")
    print(f"✅ 유사어 확장: {'활성화' if ENABLE_SYNONYM_EXPANSION and CONCEPTNET_AVAILABLE else '비활성화'}")
    if ENABLE_SYNONYM_EXPANSION and CONCEPTNET_AVAILABLE:
        print(f"   - ConceptNet을 사용하여 각 DDC 항목당 최대 {MAX_SYNONYMS}개의 유사어 추가")
        print(f"   - 예: 'blockchain' → 'cryptocurrency', 'bitcoin', 'distributed ledger' 등")
    print("=" * 70)
    start_time = time.time()

    # DB에서 원본 JSON 데이터 가져오기 (테이블명: dewey_cache)
    try:
        conn = sqlite3.connect(DB_PATH)
        # 개선점: 단일 키워드 테이블이 아닌, 모든 정보가 담긴 raw_json 컬럼을 직접 조회.
        query = "SELECT ddc_code, raw_json FROM dewey_cache"
        cursor = conn.execute(query)
        raw_data = cursor.fetchall()
        conn.close()
        print(f"✅ 데이터베이스에서 {len(raw_data):,}개의 JSON 데이터를 로드했습니다.")
    except Exception as e:
        print(f"❌ 데이터베이스 조회 실패: {e}")
        return

    # 임베딩할 텍스트 문서 생성
    documents_to_encode = []
    processed_data_map = {}

    print("JSON 데이터를 파싱하여 임베딩용 문서를 생성합니다...")
    for i, row in enumerate(raw_data):
        ddc_code = row[0]
        json_str = row[1]
        try:
            data = json.loads(json_str)

            # --- 💡 핵심 개선점: 풍부한 문맥을 가진 "문서" 생성 ---
            # 1. 'prefLabel': 주제의 핵심이 되는 선호 용어를 추출.
            pref_label = data.get("prefLabel", {}).get("en", "")

            # 2. 'altLabel': 동의어, 유의어 등 대안 용어를 모두 추출하여 포함.
            # ✅ [개선] 영어 altLabel을 모두 추출 (리스트로 되어 있음)
            alt_labels = data.get("altLabel", {}).get("en", [])
            if isinstance(alt_labels, list):
                alt_labels_list = alt_labels
                alt_text = ", ".join(alt_labels)
            else:
                alt_labels_list = []
                alt_text = str(alt_labels) if alt_labels else ""

            # 3. 'scopeNote': 해당 주제의 상세한 정의/설명문을 추출.
            #    모델이 의미를 이해하는 데 가장 중요한 정보.
            scope_notes = data.get("scopeNote", {}).get("en", [])
            if isinstance(scope_notes, list):
                scope_note = " ".join(scope_notes)
            else:
                scope_note = str(scope_notes) if scope_notes else ""

            # 4. ✅ [v3.0 신규] ConceptNet을 사용하여 유사어 확장
            #    예: "blockchain" → "cryptocurrency", "bitcoin", "distributed ledger" 추가
            expanded_terms = []
            if ENABLE_SYNONYM_EXPANSION and CONCEPTNET_AVAILABLE:
                # prefLabel과 주요 altLabel에서 유사어 추출
                terms_to_expand = [pref_label] + alt_labels_list[:3]
                expanded_terms = expand_terms_with_synonyms(terms_to_expand)
                ai_synonyms = ", ".join(expanded_terms[:15])  # 최대 15개
            else:
                ai_synonyms = ""

            # 5. 위 정보들을 조합하여 모델이 학습할 하나의 완결된 문서를 생성.
            # ✅ [개선] altLabel + AI 유사어를 강조하여 유사어 검색 성능 향상
            document = (
                f"Topic: {pref_label}. "
                f"Synonyms: {alt_text}. "
                f"Related concepts: {ai_synonyms}. "  # AI가 생성한 유사어
                f"{alt_text}. "  # 원본 동의어 한 번 더 반복
                f"Description: {scope_note}"
            )

            documents_to_encode.append(document)
            processed_data_map[i] = {
                "ddc": ddc_code,
                "prefLabel": pref_label,
                "document": document,
            }

        except (json.JSONDecodeError, AttributeError):
            print(f"⚠️ DDC {ddc_code}의 JSON 파싱 실패. 건너뜁니다.")
            continue

    print("✅ 문서 생성 완료.")

    # 임베딩 모델 로드 및 인코딩
    print(f"모델 '{MODEL_NAME}'을 로딩합니다... (최초 실행 시 시간이 걸릴 수 있습니다)")
    model = SentenceTransformer(MODEL_NAME)
    print("✅ 모델 로딩 완료.")

    print(f"총 {len(documents_to_encode):,}개의 문서를 벡터로 변환합니다.")
    embeddings = model.encode(
        documents_to_encode,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    # FAISS 인덱스 구축 및 저장
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings.astype("float32"))
    faiss.write_index(index, INDEX_FILE)
    print(f"✅ 인덱스를 '{INDEX_FILE}' 파일로 저장했습니다.")

    # 매핑 파일 저장
    with open(MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(processed_data_map, f, ensure_ascii=False, indent=2)
    print(f"✅ 매핑 정보를 '{MAPPING_FILE}' 파일로 저장했습니다.")

    end_time = time.time()
    print(f"\n🎉 모든 작업 완료! (총 소요 시간: {end_time - start_time:.2f}초)")


if __name__ == "__main__":
    build_from_json()
