# collection-scoped-search Plan

> Feature: 컬렉션/문서 범위 하이브리드 검색 API
> Created: 2026-04-28
> Status: Draft
> Dependencies: HYBRID-001 (Done)

---

## 1. 문제 정의

현재 하이브리드 검색 API(`POST /api/v1/hybrid-search/search`)는 **글로벌 범위**로만 동작한다.
유저가 특정 컬렉션에 진입한 후 그 컬렉션 내 문서를 검색하거나,
특정 문서 내에서만 검색하는 기능이 없다.

프론트엔드의 CollectionDocumentsPage에서 유저가 자율적으로 검색을 테스트하려면
**컬렉션 스코프 + 문서 스코프** 검색 API가 필요하다.

---

## 2. 목표

| 목표 | 설명 |
|------|------|
| 컬렉션 범위 검색 | 특정 컬렉션 내 모든 문서를 대상으로 하이브리드 검색 |
| 문서 범위 검색 | 특정 컬렉션의 특정 문서 내에서만 하이브리드 검색 |
| BM25/벡터 가중치 조정 | 유저가 BM25와 벡터 검색 비율을 지정하여 결과 편향 조정 |
| 권한 검사 | 컬렉션 scope(PERSONAL/SHARED/DEPARTMENT)에 따른 읽기 권한 검증 |
| 검색 히스토리 | 유저별 검색 기록 저장 및 조회 API |
| 기존 모듈 재사용 | HybridSearchUseCase + RRFFusionPolicy + CollectionPermissionService 재사용 |
| 백엔드 API만 | 프론트엔드는 이번 스코프에서 제외 |

---

## 3. API 설계

### 3-1. 컬렉션 스코프 검색

```
POST /api/v1/collections/{collection_name}/search
```

**Request Body:**
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

| 파라미터 | 타입 | 기본값 | 범위 | 설명 |
|----------|------|--------|------|------|
| `query` | string | (필수) | - | 검색 쿼리 |
| `top_k` | int | 10 | 1-50 | 최종 반환 결과 수 |
| `bm25_top_k` | int | 20 | 1-100 | BM25 후보 수 |
| `vector_top_k` | int | 20 | 1-100 | 벡터 검색 후보 수 |
| `rrf_k` | int | 60 | 1+ | RRF 상수 |
| `bm25_weight` | float | 0.5 | 0.0-1.0 | BM25 가중치 |
| `vector_weight` | float | 0.5 | 0.0-1.0 | 벡터 검색 가중치 |

> `bm25_weight + vector_weight`는 반드시 1.0일 필요 없음.
> 각각 독립적인 배율로 동작. 기본값(0.5/0.5)은 기존 RRF와 동일 효과.

**가중치 사용 예시:**

| 시나리오 | bm25_weight | vector_weight | 효과 |
|----------|-------------|---------------|------|
| 키워드 정확 매칭 중시 | 0.8 | 0.2 | 정확한 용어가 있는 문서 우선 |
| 의미적 유사도 중시 | 0.2 | 0.8 | 유사한 의미의 문서 우선 |
| 균형 (기본) | 0.5 | 0.5 | 기존 RRF와 동일 |
| BM25만 | 1.0 | 0.0 | 벡터 검색 결과 무시 |
| 벡터만 | 0.0 | 1.0 | BM25 결과 무시 |

**Response:**
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
    "request_id": "uuid"
}
```

### 3-2. 문서 스코프 검색

```
POST /api/v1/collections/{collection_name}/documents/{document_id}/search
```

**Request/Response**: 3-1과 동일 구조. 추가로 `document_id` 필드가 응답에 포함.

### 3-3. 검색 히스토리 조회

```
GET /api/v1/collections/{collection_name}/search-history
```

**Query Parameters:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `limit` | int | 20 | 최대 반환 수 (max 100) |
| `offset` | int | 0 | 페이지네이션 오프셋 |

**Response:**
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
            "created_at": "2026-04-28T10:30:00Z"
        }
    ],
    "total": 42,
    "limit": 20,
    "offset": 0
}
```

> 검색 히스토리는 검색 실행 시 자동 저장 (Fire-and-Forget 비동기).
> 유저 본인의 히스토리만 조회 가능.

---

## 4. 아키텍처

```
POST /api/v1/collections/{collection_name}/search
POST /api/v1/collections/{collection_name}/documents/{document_id}/search
GET  /api/v1/collections/{collection_name}/search-history
         │
         ▼
CollectionSearchRouter (api/routes)
    ├── Depends(get_current_user) ← JWT 인증
         │
         ▼
CollectionSearchUseCase (application)
    ├── 1. 권한 검사 (CollectionPermissionService.check_read_access)
    ├── 2. 컬렉션 존재 검증 (CollectionRepositoryInterface)
    ├── 3. 임베딩 모델 해석 (EmbeddingModelRepo + EmbeddingFactory)
    ├── 4. QdrantVectorStore 동적 생성 (대상 컬렉션)
    ├── 5. HybridSearchUseCase.execute() 위임
    │         ├── ES BM25 검색 (collection_name / document_id 필터)
    │         ├── Qdrant 벡터 검색 (대상 컬렉션에서 직접 검색)
    │         └── Weighted RRF 병합
    └── 6. 검색 히스토리 저장 (Fire-and-Forget, SearchHistoryRepository)

GET /search-history
         │
         ▼
SearchHistoryUseCase (application)
    └── SearchHistoryRepository.find_by_user_and_collection()
```

### 핵심 설계 결정

| 항목 | 결정 | 이유 |
|------|------|------|
| Qdrant 검색 범위 | 대상 컬렉션으로 VectorStore 동적 생성 | Qdrant는 컬렉션별 물리적 분리 |
| ES 검색 범위 | `collection_name` term filter 추가 | ES는 단일 인덱스, 메타데이터로 필터링 |
| 문서 스코프 | `document_id` metadata_filter 추가 | 양쪽 모두 document_id 필드 존재 |
| UseCase 재사용 | HybridSearchUseCase를 내부에서 조립하여 위임 | RRF 로직 중복 방지 |
| 임베딩 모델 | 컬렉션 생성 시 사용된 모델 자동 해석 | UnifiedUploadUseCase와 동일 패턴 |
| RRF 가중치 | RRFFusionPolicy.merge()에 weight 파라미터 추가 | 기존 동작 호환 유지 (기본값 0.5/0.5) |

### Weighted RRF 알고리즘

기존 RRF:
```
score(d) = 1/(k + bm25_rank) + 1/(k + vector_rank)
```

가중치 적용 RRF:
```
score(d) = bm25_weight * 1/(k + bm25_rank) + vector_weight * 1/(k + vector_rank)
```

- `bm25_weight`, `vector_weight` 기본값 = 0.5 → 기존 RRF와 동일 효과
- 가중치는 독립적인 배율. 합이 1.0일 필요 없음
- weight=0.0이면 해당 소스의 기여도가 0이 됨 (검색 자체는 실행)

---

## 5. 구현 대상

### Domain Layer (신규)
| 파일 | 설명 |
|------|------|
| `src/domain/collection_search/schemas.py` | `CollectionSearchRequest`, `CollectionSearchResponse` VO |
| `src/domain/collection_search/search_history_schemas.py` | `SearchHistoryEntry`, `SearchHistoryListResult` VO |
| `src/domain/collection_search/search_history_interfaces.py` | `SearchHistoryRepositoryInterface` 추상 인터페이스 |

### Domain Layer (변경)
| 파일 | 변경 내용 |
|------|----------|
| `src/domain/hybrid_search/schemas.py` | `HybridSearchRequest`에 `bm25_weight`, `vector_weight` 필드 추가 |
| `src/domain/hybrid_search/policies.py` | `RRFFusionPolicy.merge()`에 `bm25_weight`, `vector_weight` 파라미터 추가 |

### Application Layer (신규)
| 파일 | 설명 |
|------|------|
| `src/application/collection_search/use_case.py` | `CollectionSearchUseCase` — 권한 검사 + 컬렉션 검증 + 검색 + 히스토리 저장 |
| `src/application/collection_search/search_history_use_case.py` | `SearchHistoryUseCase` — 히스토리 조회 |

### Application Layer (변경)
| 파일 | 변경 내용 |
|------|----------|
| `src/application/hybrid_search/use_case.py` | `execute()`에서 가중치를 `RRFFusionPolicy.merge()`로 전달 |

### Infrastructure Layer (신규)
| 파일 | 설명 |
|------|------|
| `src/infrastructure/collection_search/models.py` | `SearchHistoryModel` SQLAlchemy 모델 |
| `src/infrastructure/collection_search/search_history_repository.py` | MySQL 기반 히스토리 저장/조회 구현체 |

### API Layer (신규)
| 파일 | 설명 |
|------|------|
| `src/api/routes/collection_search_router.py` | 3개 엔드포인트 (검색 2개 + 히스토리 조회 1개) |

### API Layer (변경)
| 파일 | 변경 내용 |
|------|----------|
| `src/api/routes/hybrid_search_router.py` | 기존 API에도 `bm25_weight`, `vector_weight` 파라미터 추가 (하위호환) |

### 등록
| 파일 | 변경 |
|------|------|
| `src/api/main.py` | 라우터 등록 + DI 오버라이드 |

### DB 마이그레이션
| 파일 | 설명 |
|------|------|
| `db/migration/V015__create_search_history.sql` | `search_history` 테이블 생성 DDL |

---

## 6. 데이터 흐름 상세

### 컬렉션 스코프 (collection_name = "finance-docs")

```
1. Router: collection_name 경로 파라미터 추출 + get_current_user → User
2. UseCase:
   a. PermissionService.check_read_access("finance-docs", user) → 403 or pass
   b. CollectionRepo.collection_exists("finance-docs") → 404 or pass
   c. ActivityLogRepo에서 컬렉션 생성 로그 조회 → embedding_model 확인
   d. EmbeddingFactory.create_from_string() → EmbeddingInterface 생성
   e. QdrantVectorStore(client, embedding, "finance-docs") 동적 생성
   f. HybridSearchRequest(query, metadata_filter={"collection_name": "finance-docs"},
                           bm25_weight=0.5, vector_weight=0.5)
   g. HybridSearchUseCase(es_repo, embedding, vector_store, es_index, logger)
   h. use_case.execute(request, request_id) → Weighted RRF 병합 결과
   i. SearchHistoryRepo.save() → Fire-and-Forget 비동기 저장
3. Router: 응답 변환
```

### 문서 스코프 (collection_name = "finance-docs", document_id = "doc-123")

```
위와 동일하되:
   f. metadata_filter={"collection_name": "finance-docs", "document_id": "doc-123"}
   → ES: bool query에 두 term filter 추가
   → Qdrant: payload filter에 document_id 조건 추가
```

### 권한 검사 흐름

```
기존 CollectionPermissionService.check_read_access() 재사용:
  1. collection_permissions 테이블에서 scope 조회
  2. CollectionPermissionPolicy.can_read(user, perm, user_dept_ids) 판정
  3. 실패 시 PermissionError → Router에서 403 반환

| Scope       | Owner | Same Dept | Others | Admin |
|-------------|-------|-----------|--------|-------|
| PERSONAL    | ✅    | ❌        | ❌     | ✅    |
| DEPARTMENT  | ✅    | ✅        | ❌     | ✅    |
| PUBLIC      | ✅    | ✅        | ✅     | ✅    |
```

### 검색 히스토리 DB 스키마

```sql
CREATE TABLE search_history (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     VARCHAR(100) NOT NULL,
    collection_name VARCHAR(100) NOT NULL,
    document_id VARCHAR(100) NULL,
    query       TEXT NOT NULL,
    bm25_weight FLOAT NOT NULL DEFAULT 0.5,
    vector_weight FLOAT NOT NULL DEFAULT 0.5,
    top_k       INT NOT NULL DEFAULT 10,
    result_count INT NOT NULL DEFAULT 0,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX ix_sh_user_collection (user_id, collection_name),
    INDEX ix_sh_created (created_at)
);
```

> 히스토리 저장은 검색 성능에 영향 없도록 **Fire-and-Forget** 패턴 적용.
> 기존 `FireAndForgetActivityLogger`와 동일한 비동기 패턴 사용.

---

## 7. 테스트 계획

| 테스트 파일 | 대상 | 케이스 수 |
|------------|------|----------|
| `tests/domain/collection_search/test_schemas.py` | VO 생성/검증 | ~6 |
| `tests/domain/collection_search/test_search_history_schemas.py` | 히스토리 VO 검증 | ~4 |
| `tests/application/collection_search/test_use_case.py` | UseCase 오케스트레이션 (mock) | ~12 |
| `tests/application/collection_search/test_search_history_use_case.py` | 히스토리 조회 UseCase | ~4 |
| `tests/api/test_collection_search_router.py` | API 엔드포인트 (mock) | ~12 |

### 주요 테스트 시나리오

**검색 기능:**
- 컬렉션 존재하지 않을 때 404
- 컬렉션 스코프 검색 정상 동작
- 문서 스코프 검색 정상 동작
- 빈 결과 반환
- 쿼리 파라미터 유효성 검증 (top_k 범위, weight 범위 등)
- 임베딩 모델 해석 실패 시 에러 처리

**가중치 검증:**
- 가중치 기본값(0.5/0.5) 검색 → 기존 RRF와 동일 결과
- BM25 가중치 1.0 / 벡터 0.0 → BM25 결과만 반영
- BM25 가중치 0.0 / 벡터 1.0 → 벡터 결과만 반영
- 가중치 0.8/0.2 → BM25 상위 문서가 더 높은 score
- 가중치 범위 초과 시 422 에러 (음수, 1.0 초과)

**권한 검사:**
- PERSONAL 컬렉션: 소유자만 검색 가능, 타인은 403
- DEPARTMENT 컬렉션: 같은 부서원 검색 가능, 다른 부서 403
- PUBLIC 컬렉션: 누구나 검색 가능
- ADMIN: 모든 컬렉션 검색 가능
- 미인증 요청 시 401

**검색 히스토리:**
- 검색 실행 후 히스토리 자동 저장 확인
- GET 히스토리 조회: 본인 기록만 반환
- 페이지네이션 (limit, offset) 동작
- 히스토리 저장 실패해도 검색 결과는 정상 반환 (Fire-and-Forget)

---

## 8. 비기능 요구사항

| 항목 | 기준 |
|------|------|
| 로깅 | LOG-001 준수 (request_id, 시작/완료/에러) |
| 인증 | JWT 기반 인증 필수 (get_current_user) |
| 인가 | CollectionPermissionService.check_read_access() — 403 on fail |
| 에러 처리 | 401 미인증, 403 권한 없음, 404 컬렉션 미존재, 422 파라미터 오류, 500 내부 에러 |
| 성능 | 기존 하이브리드 검색과 동일 수준, 히스토리 저장은 Fire-and-Forget |

---

## 9. 제외 사항 (Out of Scope)

- 프론트엔드 UI (별도 feature로 진행)
- 검색 결과 캐싱
- 검색 필터 추가 (chunk_type, user_id 등 추가 메타데이터 필터)
- 검색 히스토리 삭제 API

---

## 10. 확장 포인트

| 확장 | 설명 |
|------|------|
| 프론트엔드 연동 | CollectionDocumentsPage에 검색 UI + 히스토리 표시 추가 |
| 검색 필터 추가 | chunk_type, user_id 등 추가 메타데이터 필터 |
| 히스토리 삭제 | 유저별 검색 히스토리 삭제 API |
| 히스토리 기반 추천 | 최근 검색어 자동완성, 인기 검색어 |
