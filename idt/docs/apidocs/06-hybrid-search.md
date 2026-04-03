# 하이브리드 검색 API

> **태그**: `hybrid-search`
> **Base Path**: `/api/v1/hybrid-search`

---

## 개요

BM25 키워드 검색(Elasticsearch)과 벡터 의미 검색(Qdrant)을 결합하여 더 정확한 검색 결과를 반환합니다.

### BM25 vs. 벡터 검색 비교

| | BM25 (키워드) | 벡터 (의미) |
|-|--------------|------------|
| 강점 | 정확한 단어 일치 | 의미상 유사한 문서 검색 |
| 약점 | 동의어·맥락 인식 불가 | 전문 용어 정확 검색 약함 |
| 예시 | "기준금리 인상" 검색 | "금리를 올리다" 검색 |

### RRF (Reciprocal Rank Fusion)

두 검색 결과의 **순위**를 RRF 알고리즘으로 병합합니다. 점수 척도가 달라도 공정하게 합산됩니다.

```
RRF 점수 = 1/(k + BM25순위) + 1/(k + 벡터순위)
           (k=60이 기본값, 높은 순위일수록 점수 높음)
```

---

## 엔드포인트

### 하이브리드 검색

**`POST /api/v1/hybrid-search/search`**

#### 요청 (JSON)

```json
{
  "query": "금리 인상 영향",
  "top_k": 10,
  "bm25_top_k": 20,
  "vector_top_k": 20,
  "rrf_k": 60
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `query` | string | ✅ | - | 검색 질의 |
| `top_k` | int | ❌ | 10 | 최종 반환 문서 수 (1~50) |
| `bm25_top_k` | int | ❌ | 20 | BM25 후보 수 (1~100) |
| `vector_top_k` | int | ❌ | 20 | 벡터 검색 후보 수 (1~100) |
| `rrf_k` | int | ❌ | 60 | RRF 상수 (클수록 순위 차이 감소) |

> `bm25_top_k`와 `vector_top_k`는 내부 후보 수입니다. 최종 반환은 `top_k`개입니다.

#### 응답 (200 OK)

```json
{
  "query": "금리 인상 영향",
  "results": [
    {
      "id": "chunk_001",
      "content": "기준금리 인상은 대출 금리 상승으로 이어져...",
      "score": 0.031,
      "bm25_rank": 1,
      "bm25_score": 12.4,
      "vector_rank": 3,
      "vector_score": 0.87,
      "source": "monetary_policy_2024.pdf",
      "metadata": {
        "document_id": "doc_001",
        "chunk_type": "child"
      }
    }
  ],
  "total_found": 8,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 필드 | 설명 |
|------|------|
| `results[].score` | RRF 최종 점수 |
| `results[].bm25_rank` | BM25 결과에서의 순위 (null이면 BM25에서 미검색) |
| `results[].bm25_score` | BM25 원점수 (Elasticsearch TF-IDF) |
| `results[].vector_rank` | 벡터 결과에서의 순위 (null이면 벡터에서 미검색) |
| `results[].vector_score` | 벡터 유사도 점수 (0.0~1.0) |
| `results[].source` | 원본 파일명 |

#### 예제

```bash
# 기본 하이브리드 검색
curl -X POST "http://localhost:8000/api/v1/hybrid-search/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "부동산 정책 변화",
    "top_k": 5
  }'

# 후보 수 확대 + RRF 조정
curl -X POST "http://localhost:8000/api/v1/hybrid-search/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "부동산 정책 변화",
    "top_k": 10,
    "bm25_top_k": 50,
    "vector_top_k": 50,
    "rrf_k": 30
  }'
```

---

## 검색 API 선택 가이드

| 상황 | 추천 API |
|------|---------|
| 정확한 단어 일치 중요 | 하이브리드 검색 (BM25 강점) |
| 의미 기반 검색 | [문서 검색 API](./05-retrieval.md) (벡터 강점) |
| LLM 압축 + 맥락 필요 | [문서 검색 API](./05-retrieval.md) |
| RAG 에이전트 연동 | [RAG 에이전트 API](./09-rag-agent.md) (내부에서 하이브리드 검색 사용) |
