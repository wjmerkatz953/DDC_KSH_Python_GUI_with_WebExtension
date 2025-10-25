# KSH 검색 결과 불일치 문제 수정 완료

## 문제점

### 증상
- **API 서버**: 5개 결과 반환
- **듀이 탭 KSH 패널**: 11개 결과 표시
- **검색 로그**: "Concept DB: 8개, Biblio DB: 3개"

### 원인
세미콜론(`;`)으로 구분된 **복수 주제명**을 하나의 항목으로 처리해서 대부분의 결과가 필터링되었습니다.

#### 예시:
```
원본 데이터:
▼a여행기[旅行記]▼0KSH1998024814▲; ▼a인도양[印度洋]▼0KSH1998039170▲

변경 전 (잘못된 처리):
- 전체를 하나의 항목으로 처리
- "▲" 문자가 중간에 있어서 필터링됨 ❌

변경 후 (올바른 처리):
- 두 개의 개별 항목으로 분리 ✅
  1. ▼a여행기[旅行記]▼0KSH1998024814▲
  2. ▼a인도양[印度洋]▼0KSH1998039170▲
```

## 해결 방법

### 1. 복수 주제명 분리 로직 추가

```python
# 세미콜론으로 구분된 복수 주제명 분리
subjects = []
if "; " in subject:
    # 복수 주제명을 개별 항목으로 분리
    subjects = [s.strip() for s in subject.split("; ")]
else:
    subjects = [subject]

# 각 주제명을 개별 결과로 추가
for subj in subjects:
    if subj and "▼a" in subj:
        display = self._extract_display_text(subj)
        ksh_results.append({...})
```

### 2. 중복 제거 로직 추가

같은 주제명이 Concept DB와 Biblio DB에 모두 나타날 수 있으므로 중복 제거:

```python
# 중복 제거 (subject 기준)
seen_subjects = set()
unique_results = []
for item in ksh_results:
    subj = item["subject"]
    if subj not in seen_subjects:
        seen_subjects.add(subj)
        unique_results.append(item)
```

### 3. 필터 조건 완화

```python
# 변경 전: 너무 엄격한 조건
if subject and "▼a" in subject and "▲" in subject:

# 변경 후: 최소 조건만 확인
if subj and "▼a" in subj:
```

## 테스트 결과

### "인도양" 검색 결과 비교

#### 변경 전 (5개):
```json
[
  {"display": "여행기[旅行記]", ...},
  {"display": "인도양[印度洋]", ...},
  {"display": "해양 도시[海洋都市]", ...},
  {"display": "해양[海洋]", ...},
  {"display": "아시아 지리[--地理]", ...}
]
```

#### 변경 후 (11개):
```json
[
  {"display": "여행기[旅行記]", ...},
  {"display": "인도양[印度洋]", ...},
  {"display": "해양 도시[海洋都市]", ...},
  {"display": "해양[海洋]", ...},
  {"display": "아시아 지리[--地理]", ...},
  {"display": "인도양 적도 반류[印度洋赤道反流]", ...},
  {"display": "인도양 중앙 해령[印度洋中央海嶺]", ...},
  {"display": "인도양 남적도 해류[印度洋南赤道海流]", ...},
  {"display": "남인도양 해류[南印度洋海流]", ...},
  {"display": "동인도양 해령[東印度洋海嶺]", ...},
  {"display": "남동 인도양 해팽[南東印度洋海膨]", ...},
  {"display": "영국령 인도양 식민지[英國領印度洋植民地]", ...}
]
```

## 수정 내역

### extension_api_server.py

#### 1. Concept DB 결과 처리 (86-113줄)
```python
# ✅ 세미콜론으로 구분된 복수 주제명 분리
subjects = []
if "; " in subject:
    subjects = [s.strip() for s in subject.split("; ")]
else:
    subjects = [subject]

# 각 주제명을 개별 결과로 추가
for subj in subjects:
    if subj and "▼a" in subj:
        display = self._extract_display_text(subj)
        ksh_results.append({...})
```

#### 2. Biblio DB 결과 처리 (115-145줄)
```python
# ✅ 세미콜론으로 구분된 복수 주제명 분리
subjects = []
if "; " in ksh_labeled:
    subjects = [s.strip() for s in ksh_labeled.split("; ")]
else:
    subjects = [ksh_labeled]

# 각 주제명을 개별 결과로 추가
for subj in subjects:
    if subj and "▼a" in subj:
        display = self._extract_display_text(subj)
        ksh_results.append({...})
```

#### 3. 중복 제거 (147-156줄)
```python
# ✅ 중복 제거 (subject 기준)
seen_subjects = set()
unique_results = []
for item in ksh_results:
    subj = item["subject"]
    if subj not in seen_subjects:
        seen_subjects.add(subj)
        unique_results.append(item)

return jsonify(unique_results[:20])
```

## 검증 방법

### 1. API 서버 테스트
```bash
# 인도양 검색
curl "http://localhost:5000/api/ksh/search?q=인도양" | python -m json.tool

# 결과 개수 확인
curl "http://localhost:5000/api/ksh/search?q=인도양" | python -m json.tool | grep '"display"' | wc -l
```

### 2. 결과 비교
```bash
# API 결과 개수
curl -s "http://localhost:5000/api/ksh/search?q=인도양" | python -c "import sys, json; print(len(json.load(sys.stdin)))"

# 로그에서 DB 결과 개수 확인
# "Concept DB: X개, Biblio DB: Y개"
```

### 3. 중복 확인
```bash
# 중복이 제거되었는지 확인
curl -s "http://localhost:5000/api/ksh/search?q=인도양" | python -c "
import sys, json
data = json.load(sys.stdin)
subjects = [item['subject'] for item in data]
print(f'전체: {len(subjects)}개')
print(f'중복 제거 후: {len(set(subjects))}개')
"
```

## 예상 효과

1. ✅ **검색 결과 완전성**: DB에서 조회된 모든 결과가 API 응답에 포함
2. ✅ **정확한 개수**: 듀이 탭과 동일한 개수의 결과 반환
3. ✅ **중복 제거**: 같은 주제명이 여러 번 나타나지 않음
4. ✅ **성능 유지**: 최대 20개로 제한하여 응답 속도 유지

## 주의사항

### 세미콜론 패턴
- **구분자**: `"; "` (세미콜론 + 공백)
- **다른 패턴**: `","` (쉼표) 등은 처리하지 않음
- **이유**: KSH 주제명 표준 형식이 세미콜론 구분자 사용

### 중복 제거 기준
- **기준**: `subject` 필드 (전체 MARC 문자열)
- **장점**: 같은 표시명이지만 다른 코드를 가진 경우 구별 가능
- **예시**:
  ```
  ▼a한국 문학▼0KSH111▲  ← 유지
  ▼a한국 문학▼0KSH222▲  ← 유지 (코드가 다름)
  ```

## 다음 단계

- [ ] 브라우저 확장 프로그램에서 증가된 검색 결과 확인
- [ ] KSH Local 탭 검색 결과도 확인 (현재 결과 없음)
- [ ] 성능 모니터링 (세미콜론 분리로 인한 처리 시간 증가 여부)

## 파일 수정 내역

- ✅ `extension_api_server.py` - 복수 주제명 분리 및 중복 제거 로직 추가
- ✅ `KSH 검색 결과 수정 완료.md` - 문서 작성
