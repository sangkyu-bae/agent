# Elasticsearch BM25 검색 전략 문서

> 작성일: 2026-05-08  
> 범위: PDF 업로드 → 청킹 → 형태소 분석 → ES 적재 → BM25 검색 → RRF 하이브리드 병합

---

## 1. 전체 아키텍처 요약

```
PDF 업로드
    │
    ▼
┌─────────────────────────┐
│  PDF Parser              │  문서 → LangChain Document 변환
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Parent-Child Chunker    │  토큰 기반 2계층 청킹 (parent → child)
│  (tiktoken cl100k_base)  │
└──────────┬──────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐  ┌──────────────────────┐
│ Qdrant  │  │ Elasticsearch        │
│ (벡터)  │  │ (BM25 키워드 검색)    │
└────┬────┘  └──────────┬───────────┘
     │                  │
     └────────┬─────────┘
              ▼
     ┌─────────────────┐
     │  RRF Fusion      │  BM25 + 벡터 결과 순위 병합
     │  (k=60, 50:50)   │
     └─────────────────┘
```

**이중 저장소 전략**: Qdrant(의미 유사도)와 ES(키워드 매칭)를 동시에 사용하여 RRF로 병합한다.

---

## 2. 청킹 전략

### 2-1. 기본 전략: Parent-Child (2계층 계위 청킹)

| 구분 | 기본값 | 비고 |
|------|--------|------|
| Parent 청크 크기 | 2,000 토큰 | 전체 맥락 보존 |
| Parent 오버랩 | 0 | 부모끼리는 중복 없음 |
| Child 청크 크기 | 500 토큰 | 검색 단위 (사용자 설정 가능, 100~4000) |
| Child 오버랩 | 50 토큰 | 사용자 설정 가능 (0~500) |
| 토크나이저 | tiktoken `cl100k_base` | OpenAI 호환 인코딩 |

**동작 원리**:
1. 전체 텍스트를 Parent 단위(2000토큰)로 1차 분할
2. 각 Parent 안에서 Child 단위(500토큰, 50 오버랩)로 2차 분할
3. 각 청크에 UUID 기반 `chunk_id` 부여
4. Child는 `parent_id`로 부모를 참조, Parent는 `children_ids`로 자식 목록 보유

**구현 위치**: `src/infrastructure/chunking/strategies/parent_child_strategy.py`

### 2-2. 사용 가능한 청킹 전략 종류

| 전략 | 청크 크기 | 오버랩 | 용도 |
|------|----------|--------|------|
| `parent_child` | Parent 2000 / Child 500 | 0 / 50 | 기본 업로드 (계층 구조) |
| `full_token` | 2000 | 200 | 단일 수준 분할 |
| `semantic` | max 1000 / min 200 | - | 의미 단위 분할 |

### 2-3. 문서 카테고리별 청킹 설정

`src/domain/pipeline/config/chunking_strategy_config.py`에서 카테고리별로 다른 청크 크기를 적용:

| 카테고리 | 청크 크기 (토큰) | 오버랩 (토큰) | 설계 의도 |
|----------|-----------------|--------------|-----------|
| IT_SYSTEM | 2,000 | 200 | 기술 문서는 긴 맥락 필요 |
| HR | 400 | 100 | 인사 규정은 짧고 독립적 |
| LOAN_FINANCE | 800 | 100 | 여신/금융 조항 중간 길이 |
| SECURITY_ACCESS | 600 | 100 | 보안 정책 항목 단위 |
| ACCOUNTING_LEGAL | 1,000 | 150 | 회계/법무 조항 |
| GENERAL | 1,000 | 100 | 범용 기본값 |

---

## 3. ES 인덱스 설계

### 3-1. 인덱스 이름

- 기본값: `documents` (환경변수 `ES_INDEX`로 변경 가능)
- 단일 인덱스에 모든 청크를 저장하고 `collection_name`, `user_id`, `document_id` 필드로 필터링

### 3-2. 매핑 (필드 스키마)

```
src/infrastructure/elasticsearch/es_index_mappings.py
```

| 필드 | ES 타입 | 용도 |
|------|---------|------|
| `content` | `text` | 원본 청크 텍스트 (BM25 검색 대상) |
| `morph_text` | `text` | 형태소 분석 키워드 결합 텍스트 (BM25 부스팅 대상) |
| `morph_keywords` | `keyword` | 추출된 형태소 키워드 배열 |
| `chunk_id` | `keyword` | 청크 고유 ID (UUID) |
| `chunk_type` | `keyword` | `parent` / `child` / `full` / `semantic` |
| `chunk_index` | `integer` | 문서 내 청크 순서 |
| `total_chunks` | `integer` | 문서 전체 청크 수 |
| `document_id` | `keyword` | 원본 문서 ID |
| `user_id` | `keyword` | 업로드한 사용자 ID |
| `collection_name` | `keyword` | 소속 컬렉션명 |
| `parent_id` | `keyword` | Child 청크의 부모 참조 (선택) |

### 3-3. 현재 설정의 특징

- **커스텀 analyzer 없음**: ES 기본 Standard Analyzer 사용 (한국어 토큰화에 제약)
- **한국어 보완**: `morph_text` 필드에 Kiwi 형태소 분석 결과를 저장하여 BM25 성능 보강
- **settings (분석기/샤드) 미지정**: ES 기본값 (primary shard 1, replica 1) 사용

---

## 4. 한국어 형태소 분석 (Kiwi)

### 4-1. 분석 흐름

```
청크 텍스트
    │
    ▼
KiwiMorphAnalyzer.analyze()     ← kiwipiepy 기반
    │
    ▼
형태소 토큰 추출 (NNG, NNP, VV, VA 태그만 선별)
    │
    ├── morph_keywords: ["대출", "심사", "진행하다", ...]   (keyword 배열)
    └── morph_text: "대출 심사 진행하다 ..."                (공백 결합 텍스트)
```

### 4-2. 추출 대상 품사 태그

| 태그 | 의미 | 처리 |
|------|------|------|
| NNG | 일반 명사 | 원형 그대로 |
| NNP | 고유 명사 | 원형 그대로 |
| VV | 동사 | `surface + "다"` (기본형 변환) |
| VA | 형용사 | `surface + "다"` (기본형 변환) |

**구현 위치**: `src/infrastructure/morph/kiwi_morph_analyzer.py`, `src/application/unified_upload/use_case.py:_extract_morph_keywords()`

### 4-3. 설계 의도

ES Standard Analyzer는 한국어 어절 단위로만 분리하므로 "대출심사기준"과 같은 복합어를 분리하지 못한다. Kiwi 형태소 분석으로 "대출", "심사", "기준"을 추출하여 `morph_text` 필드에 저장하고, BM25 검색 시 이 필드에 1.5배 가중치를 부여하여 한국어 검색 품질을 보강한다.

---

## 5. ES 적재 파이프라인

### 5-1. 흐름 (asyncio.gather로 Qdrant와 병렬 실행)

```python
# src/application/unified_upload/use_case.py

1. PDF 파싱 → List[Document]
2. Parent-Child 청킹 → List[Document] (parent + child 포함)
3. 메타데이터 주입 (document_id, user_id, collection_name)
4. asyncio.gather(
       _store_to_qdrant(chunks),   # 벡터 임베딩 → Qdrant
       _store_to_es(chunks),       # 형태소 분석 → ES bulk_index
   )
```

### 5-2. ES 적재 상세 (`_store_to_es`)

각 청크에 대해:
1. `KiwiMorphAnalyzer.analyze(chunk.page_content)` 실행
2. NNG/NNP/VV/VA 품사만 추출 → `morph_keywords` 리스트
3. 키워드를 공백으로 결합 → `morph_text` 문자열
4. `ESDocument` 생성 (id=chunk_id, body=필드 데이터, index=인덱스명)
5. `es_repo.bulk_index(es_docs)` → ES Bulk API로 일괄 색인

### 5-3. Bulk 색인 처리

- ES Bulk API 사용 (`_index` + `_id` 방식)
- 부분 실패 감지: 개별 문서 status 400+ 체크 후 warning 로깅
- 성공 건수 반환

---

## 6. BM25 검색 쿼리 전략

### 6-1. 쿼리 구조

```json
{
  "multi_match": {
    "query": "사용자 검색어",
    "fields": ["content", "morph_text^1.5"],
    "type": "most_fields"
  }
}
```

| 항목 | 값 | 의미 |
|------|-----|------|
| 검색 필드 | `content` | 원본 텍스트에서 BM25 점수 계산 |
| 검색 필드 | `morph_text^1.5` | 형태소 키워드 필드에 1.5배 가중치 |
| 매칭 타입 | `most_fields` | 두 필드 모두에서 매칭하고 점수 합산 |
| 기본 top_k | 20 | BM25에서 상위 20건 가져옴 |

### 6-2. 메타데이터 필터링

`collection_name`, `user_id` 등 필터가 있을 경우 `bool` + `filter` 절 추가:

```json
{
  "bool": {
    "must": [{ "multi_match": { ... } }],
    "filter": [
      { "term": { "collection_name": "my_collection" } },
      { "term": { "user_id": "user_123" } }
    ]
  }
}
```

### 6-3. BM25 파라미터

- ES 기본 BM25 설정 사용 (`k1=1.2`, `b=0.75`)
- 별도 커스터마이징 없음

---

## 7. 하이브리드 검색 (RRF 병합)

### 7-1. RRF 공식

```
score(d) = Σ weight_i × (1 / (k + rank_i(d)))
```

- 논문: Cormack et al., 2009
- 순위(rank) 기반이므로 스코어 스케일이 다른 BM25와 벡터를 직접 비교할 필요 없음

### 7-2. 기본 파라미터

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `rrf_k` | 60 | RRF 상수 (표준값) |
| `bm25_weight` | 0.5 | BM25 결과 가중치 |
| `vector_weight` | 0.5 | 벡터 결과 가중치 |
| `bm25_top_k` | 20 | BM25에서 가져올 후보 수 |
| `vector_top_k` | 20 | 벡터에서 가져올 후보 수 |
| `top_k` (최종) | 10 | 사용자에게 반환할 결과 수 |

### 7-3. 결과 출처 분류

| source 값 | 의미 |
|-----------|------|
| `both` | BM25와 벡터 모두에서 검색됨 (높은 신뢰도) |
| `bm25_only` | BM25에서만 검색됨 (키워드 매칭) |
| `vector_only` | 벡터에서만 검색됨 (의미 유사도) |

---

## 8. 핵심 파일 위치 요약

| 구성 요소 | 파일 경로 |
|-----------|----------|
| ES 설정 | `src/infrastructure/config/elasticsearch_config.py` |
| ES 클라이언트 | `src/infrastructure/elasticsearch/es_client.py` |
| ES Repository | `src/infrastructure/elasticsearch/es_repository.py` |
| ES 인덱스 매핑 | `src/infrastructure/elasticsearch/es_index_mappings.py` |
| 청킹 값 객체 | `src/domain/chunking/value_objects.py` |
| 토큰 청커 | `src/infrastructure/chunking/base_token_chunker.py` |
| Parent-Child 전략 | `src/infrastructure/chunking/strategies/parent_child_strategy.py` |
| 카테고리별 청킹 설정 | `src/domain/pipeline/config/chunking_strategy_config.py` |
| 형태소 분석기 | `src/infrastructure/morph/kiwi_morph_analyzer.py` |
| 업로드 UseCase (적재) | `src/application/unified_upload/use_case.py` |
| 하이브리드 검색 UseCase | `src/application/hybrid_search/use_case.py` |
| RRF 정책 | `src/domain/hybrid_search/policies.py` |
| 검색 스키마 | `src/domain/hybrid_search/schemas.py` |

---

## 9. 현재 전략의 강점과 한계

### 강점
- **이중 저장소**: 키워드 매칭(BM25)과 의미 유사도(벡터)를 RRF로 병합하여 단일 검색 대비 recall 개선
- **한국어 형태소 분석**: Kiwi로 복합어를 분리하고 morph_text에 부스팅하여 한국어 검색 품질 보강
- **Parent-Child 계층**: 검색은 작은 Child로 정밀하게, 컨텍스트는 Parent로 넓게 가져올 수 있음
- **카테고리별 청크 크기**: 문서 유형에 맞는 최적 청크 크기 적용

### 한계 / 개선 가능 영역
- **ES Analyzer 미설정**: Standard Analyzer만 사용 → `nori` 분석기를 ES 매핑에 추가하면 morph_text 없이도 한국어 토큰화 가능
- **BM25 파라미터 기본값**: `k1=1.2`, `b=0.75` 고정 → 도메인 특성에 맞게 튜닝 여지
- **단일 인덱스**: 모든 문서가 `documents` 하나에 → 대규모 시 컬렉션별 인덱스 분리 고려
- **검색 시 Parent/Child 구분 없음**: 현재 BM25 검색이 Parent와 Child를 구분하지 않고 모두 대상으로 함
