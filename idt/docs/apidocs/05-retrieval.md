# 문서 검색 API (RAG Retrieval)

> **태그**: `retrieval`
> **Base Path**: `/api/v1/retrieval`

---

## 개요

Qdrant 벡터 DB에서 질문과 유사한 문서를 검색합니다.

### 내부 처리 흐름

```
사용자 질의
     ↓ (선택) 쿼리 재작성 (LLM으로 검색어 최적화)
     ↓
벡터 유사도 검색 (Qdrant)
     ↓ (선택) LLM 압축 (관련 없는 문서 필터링)
     ↓ (선택) Parent 문서 조회 (더 넓은 맥락 포함)
     ↓
결과 반환
```

**Child-first 전략**: 작은 청크로 정밀 검색 후, 필요 시 상위 Parent 청크를 함께 반환합니다.

---

## 엔드포인트

### 문서 검색

**`POST /api/v1/retrieval/search`**

#### 요청 (JSON)

```json
{
  "query": "2024년 금리 인상 정책",
  "user_id": "user_001",
  "top_k": 10,
  "document_id": null,
  "use_query_rewrite": false,
  "use_compression": true,
  "use_parent_context": true
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `query` | string | ✅ | - | 검색 질문 |
| `user_id` | string | ✅ | - | 사용자 ID (벡터 필터링에 사용) |
| `top_k` | int | ❌ | 10 | 최대 반환 문서 수 (1~50) |
| `document_id` | string | ❌ | null | 특정 문서만 검색 (null이면 전체) |
| `use_query_rewrite` | bool | ❌ | false | LLM으로 쿼리 재작성 여부 |
| `use_compression` | bool | ❌ | true | LLM 관련성 필터링 여부 |
| `use_parent_context` | bool | ❌ | true | Parent 청크 내용 포함 여부 |

#### 응답 (200 OK)

```json
{
  "query": "2024년 금리 인상 정책",
  "rewritten_query": "2024년 기준금리 인상 통화정책",
  "documents": [
    {
      "id": "chunk_001",
      "content": "한국은행은 2024년 1월 기준금리를 3.5%로 동결하였으며...",
      "score": 0.892,
      "metadata": {
        "document_id": "doc_abc",
        "user_id": "user_001",
        "chunk_type": "child",
        "page": "3"
      },
      "parent_content": "제2장 통화정책 방향... (더 넓은 문맥)"
    }
  ],
  "total_found": 7,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 필드 | 설명 |
|------|------|
| `rewritten_query` | 재작성된 쿼리 (use_query_rewrite=true 일 때) |
| `documents[].score` | 유사도 점수 (0.0~1.0, 높을수록 관련성 높음) |
| `documents[].metadata` | 문서 메타데이터 (문서 ID, 페이지 등) |
| `documents[].parent_content` | 상위 청크 내용 (use_parent_context=true 일 때) |
| `total_found` | LLM 압축 후 남은 문서 수 |

#### 예제

```bash
# 기본 검색
curl -X POST "http://localhost:8000/api/v1/retrieval/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "환율 변동 원인",
    "user_id": "user_001"
  }'

# 특정 문서 내 검색 + 쿼리 재작성
curl -X POST "http://localhost:8000/api/v1/retrieval/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "환율 변동 원인",
    "user_id": "user_001",
    "document_id": "doc_abc123",
    "use_query_rewrite": true,
    "top_k": 5
  }'
```

---

## 옵션 선택 가이드

| 상황 | 권장 설정 |
|------|---------|
| 빠른 검색 필요 | `use_compression=false`, `use_query_rewrite=false` |
| 정확한 답변 필요 | `use_compression=true`, `use_parent_context=true` |
| 짧은 검색어 입력 | `use_query_rewrite=true` |
| 특정 문서만 검색 | `document_id` 지정 |

> **참고**: 이 API는 벡터 검색(Qdrant)만 사용합니다. BM25 키워드 검색까지 함께 사용하려면 [하이브리드 검색 API](./06-hybrid-search.md)를 사용하세요.
