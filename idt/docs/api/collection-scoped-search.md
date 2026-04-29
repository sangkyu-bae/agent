# collection-scoped-search API

> 컬렉션/문서 범위 하이브리드 검색 API — BM25/벡터 가중치 조정 및 검색 히스토리 제공

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/collections` |
| Auth | JWT Bearer Token (Authorization 헤더 필수) |
| Tags | `collection-search` |

### Weighted RRF 알고리즘

```
score(d) = bm25_weight * 1/(k + bm25_rank) + vector_weight * 1/(k + vector_rank)
```

- `bm25_weight`, `vector_weight` 기본값 = 0.5 (기존 RRF와 동일 효과)
- 가중치는 독립적인 배율. 합이 1.0일 필요 없음
- weight=0.0 → 해당 소스의 기여도가 0

### 가중치 사용 예시

| 시나리오 | bm25_weight | vector_weight | 효과 |
|----------|:-----------:|:-------------:|------|
| 키워드 정확 매칭 중시 | 0.8 | 0.2 | 정확한 용어가 있는 문서 우선 |
| 의미적 유사도 중시 | 0.2 | 0.8 | 유사한 의미의 문서 우선 |
| 균형 (기본) | 0.5 | 0.5 | 기존 RRF와 동일 |
| BM25만 | 1.0 | 0.0 | 벡터 검색 결과 무시 |
| 벡터만 | 0.0 | 1.0 | BM25 결과 무시 |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/{collection_name}/search` | 컬렉션 범위 하이브리드 검색 |
| POST | `/{collection_name}/documents/{document_id}/search` | 문서 범위 하이브리드 검색 |
| GET | `/{collection_name}/search-history` | 검색 히스토리 조회 |

---

## 상세 스펙

### POST `/{collection_name}/search`

특정 컬렉션 내 모든 문서를 대상으로 BM25 + 벡터 하이브리드 검색을 수행한다.
검색 실행 시 히스토리가 자동 저장된다 (Fire-and-Forget).

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `collection_name` | string | 대상 컬렉션 이름 |

**Request**

```json
{
    "query": "금융 정책 문서",
    "top_k": 10,
    "bm25_top_k": 20,
    "vector_top_k": 20,
    "rrf_k": 60,
    "bm25_weight": 0.5,
    "vector_weight": 0.5
}
```

| 필드 | 타입 | 필수 | 기본값 | 제약조건 | 설명 |
|------|------|:----:|:------:|----------|------|
| `query` | string | O | - | min_length=1 | 검색 쿼리 |
| `top_k` | int | X | 10 | 1~50 | 최종 반환 결과 수 |
| `bm25_top_k` | int | X | 20 | 1~100 | BM25 후보 수 |
| `vector_top_k` | int | X | 20 | 1~100 | 벡터 검색 후보 수 |
| `rrf_k` | int | X | 60 | >= 1 | RRF 상수 |
| `bm25_weight` | float | X | 0.5 | 0.0~1.0 | BM25 가중치 |
| `vector_weight` | float | X | 0.5 | 0.0~1.0 | 벡터 검색 가중치 |

**Response (200)**

```json
{
    "query": "금융 정책 문서",
    "collection_name": "my-collection",
    "results": [
        {
            "id": "chunk-uuid",
            "content": "문서 내용...",
            "score": 0.032,
            "bm25_rank": 1,
            "bm25_score": 12.5,
            "vector_rank": 3,
            "vector_score": 0.85,
            "source": "both",
            "metadata": {
                "document_id": "doc-uuid",
                "user_id": "u1",
                "chunk_type": "child"
            }
        }
    ],
    "total_found": 10,
    "bm25_weight": 0.5,
    "vector_weight": 0.5,
    "request_id": "uuid",
    "document_id": null
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `query` | string | 요청 쿼리 |
| `collection_name` | string | 검색 대상 컬렉션 |
| `results` | SearchResultItem[] | 검색 결과 목록 |
| `results[].id` | string | 청크 ID |
| `results[].content` | string | 청크 내용 |
| `results[].score` | float | Weighted RRF 점수 |
| `results[].bm25_rank` | int \| null | BM25 순위 (해당 소스에 없으면 null) |
| `results[].bm25_score` | float \| null | BM25 원본 점수 |
| `results[].vector_rank` | int \| null | 벡터 검색 순위 |
| `results[].vector_score` | float \| null | 벡터 유사도 점수 |
| `results[].source` | string | 결과 출처: `"bm25"`, `"vector"`, `"both"` |
| `results[].metadata` | dict | 청크 메타데이터 |
| `total_found` | int | 검색된 결과 총 수 |
| `bm25_weight` | float | 적용된 BM25 가중치 |
| `vector_weight` | float | 적용된 벡터 가중치 |
| `request_id` | string | 요청 추적 ID (UUID) |
| `document_id` | string \| null | 문서 스코프 검색 시 문서 ID |

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | JWT 토큰 없음 또는 만료 |
| 403 | 컬렉션 읽기 권한 없음 (PERSONAL/DEPARTMENT scope 위반) |
| 404 | 컬렉션이 존재하지 않음 |
| 422 | 파라미터 유효성 검증 실패 (가중치 범위 초과, 빈 쿼리 등) |
| 500 | 내부 서버 에러 |

---

### POST `/{collection_name}/documents/{document_id}/search`

특정 컬렉션의 특정 문서 내에서만 하이브리드 검색을 수행한다.
Request/Response 구조는 컬렉션 검색과 동일하며, 응답의 `document_id` 필드에 값이 포함된다.

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `collection_name` | string | 대상 컬렉션 이름 |
| `document_id` | string | 대상 문서 ID |

**Request**

```json
{
    "query": "금융 정책 문서",
    "top_k": 10,
    "bm25_weight": 0.8,
    "vector_weight": 0.2
}
```

필드 목록은 [컬렉션 검색](#post-collection_namesearch)과 동일.

**Response (200)**

```json
{
    "query": "금융 정책 문서",
    "collection_name": "my-collection",
    "results": [ ... ],
    "total_found": 5,
    "bm25_weight": 0.8,
    "vector_weight": 0.2,
    "request_id": "uuid",
    "document_id": "doc-123"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | JWT 토큰 없음 또는 만료 |
| 403 | 컬렉션 읽기 권한 없음 |
| 404 | 컬렉션이 존재하지 않음 |
| 422 | 파라미터 유효성 검증 실패 |
| 500 | 내부 서버 에러 |

---

### GET `/{collection_name}/search-history`

현재 인증된 유저의 해당 컬렉션 검색 히스토리를 조회한다.
본인의 히스토리만 반환되며, 최신순으로 정렬된다.

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `collection_name` | string | 대상 컬렉션 이름 |

**Query Parameters**

| 파라미터 | 타입 | 필수 | 기본값 | 제약조건 | 설명 |
|----------|------|:----:|:------:|----------|------|
| `limit` | int | X | 20 | 1~100 | 최대 반환 수 |
| `offset` | int | X | 0 | >= 0 | 페이지네이션 오프셋 |

**Response (200)**

```json
{
    "collection_name": "my-collection",
    "histories": [
        {
            "id": 1,
            "query": "금융 정책 문서",
            "document_id": null,
            "bm25_weight": 0.5,
            "vector_weight": 0.5,
            "top_k": 10,
            "result_count": 8,
            "created_at": "2026-04-28T10:30:00"
        }
    ],
    "total": 42,
    "limit": 20,
    "offset": 0
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `collection_name` | string | 대상 컬렉션 이름 |
| `histories` | SearchHistoryItem[] | 히스토리 목록 (최신순) |
| `histories[].id` | int | 히스토리 PK |
| `histories[].query` | string | 검색 쿼리 |
| `histories[].document_id` | string \| null | 문서 스코프 검색이면 문서 ID |
| `histories[].bm25_weight` | float | 사용된 BM25 가중치 |
| `histories[].vector_weight` | float | 사용된 벡터 가중치 |
| `histories[].top_k` | int | 사용된 top_k 값 |
| `histories[].result_count` | int | 검색 결과 수 |
| `histories[].created_at` | string | ISO 8601 형식 생성 시각 |
| `total` | int | 전체 히스토리 수 |
| `limit` | int | 적용된 limit |
| `offset` | int | 적용된 offset |

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | JWT 토큰 없음 또는 만료 |
| 500 | 내부 서버 에러 |

---

## 권한 모델

컬렉션 검색/문서 검색은 `CollectionPermissionService.check_read_access()`로 권한 검사를 수행한다.

| Scope | Owner | Same Dept | Others | Admin |
|-------|:-----:|:---------:|:------:|:-----:|
| PERSONAL | O | X | X | O |
| DEPARTMENT | O | O | X | O |
| PUBLIC | O | O | O | O |

---

## 비고

- 검색 히스토리는 검색 실행 시 **Fire-and-Forget** 패턴으로 자동 저장된다. 저장 실패 시에도 검색 결과는 정상 반환된다.
- 임베딩 모델은 컬렉션 생성 시 ActivityLog에 기록된 모델을 자동 해석한다.
- Qdrant는 컬렉션별 물리적 분리이므로, 컬렉션 스코프 검색 시 해당 컬렉션의 VectorStore를 동적으로 생성한다.
- Elasticsearch는 단일 인덱스 구조이므로 `collection_name` / `document_id` term filter로 범위를 제한한다.
