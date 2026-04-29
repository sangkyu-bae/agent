# fix-qdrant-search-api Design Document

> **Summary**: qdrant-client 1.16.x에서 제거된 `client.search()` API를 `client.query_points()`로 마이그레이션
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-04-29
> **Status**: Draft
> **Planning Doc**: [fix-qdrant-search-api.plan.md](../../01-plan/features/fix-qdrant-search-api.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- `AsyncQdrantClient.search()` 호출을 `query_points()`로 전환
- 반환값 구조 변경 대응: `List[ScoredPoint]` → `QueryResponse.points`
- 파라미터명 변경 대응: `query_vector` → `query`
- `pyproject.toml` 버전 하한을 `>=1.13.0`으로 조정
- 기존 테스트 mock 구조를 새 API에 맞게 업데이트

### 1.2 Design Principles

- 최소 변경 원칙: API 호출부와 반환값 처리만 수정, 비즈니스 로직 변경 없음
- DDD 레이어 규칙 준수: infrastructure 레이어 내부 변경만 발생
- 외부 계약 유지: `search_by_vector()`, `retrieve_with_scores()` 등의 시그니처 불변

---

## 2. Architecture

### 2.1 영향 레이어

```
domain/          → 변경 없음 (인터페이스 시그니처 유지)
application/     → 변경 없음 (UseCase 호출 방식 동일)
infrastructure/  → 변경 대상 (Qdrant client 호출부)
interfaces/      → 변경 없음 (API 응답 구조 동일)
```

### 2.2 변경 흐름 (Before → After)

**Before (현재 — 런타임 에러 발생)**:
```
search_by_vector() / retrieve_with_scores()
  └─ client.search(query_vector=vector, ...)
       └─ AttributeError: 'AsyncQdrantClient' has no attribute 'search'
```

**After (수정 후)**:
```
search_by_vector() / retrieve_with_scores()
  └─ client.query_points(query=vector, ...)
       └─ QueryResponse
            └─ .points → List[ScoredPoint]  (기존과 동일한 구조)
```

---

## 3. Detailed Design

### 3.1 File: `src/infrastructure/vector/qdrant_vectorstore.py`

**변경 메서드**: `search_by_vector()` (Line 79-101)

| 항목 | Before | After |
|------|--------|-------|
| 메서드 | `self._client.search(...)` | `self._client.query_points(...)` |
| 파라미터 | `query_vector=vector` | `query=vector` |
| 반환값 처리 | `results` 직접 순회 | `response.points` 순회 |

```python
# Before (Line 89-96)
results = await self._client.search(
    collection_name=self._collection_name,
    query_vector=vector,
    limit=top_k,
    query_filter=query_filter,
    with_vectors=True,
)
return [self._point_to_document(point) for point in results]

# After
response = await self._client.query_points(
    collection_name=self._collection_name,
    query=vector,
    limit=top_k,
    query_filter=query_filter,
    with_vectors=True,
)
return [self._point_to_document(point) for point in response.points]
```

### 3.2 File: `src/infrastructure/retriever/qdrant_retriever.py`

**변경 메서드**: `retrieve_with_scores()` (Line 62-100)

| 항목 | Before | After |
|------|--------|-------|
| 메서드 | `self._client.search(...)` | `self._client.query_points(...)` |
| 파라미터 | `query_vector=query_vector` | `query=query_vector` |
| 반환값 처리 | `results` 직접 순회 | `response.points` 순회 |

```python
# Before (Line 84-93)
results = await self._client.search(
    collection_name=self._collection_name,
    query_vector=query_vector,
    limit=top_k,
    query_filter=query_filter,
    with_vectors=True,
)
for point in results:
    ...

# After
response = await self._client.query_points(
    collection_name=self._collection_name,
    query=query_vector,
    limit=top_k,
    query_filter=query_filter,
    with_vectors=True,
)
for point in response.points:
    ...
```

### 3.3 File: `pyproject.toml`

```toml
# Before (Line 22)
"qdrant-client>=1.7.0",

# After
"qdrant-client>=1.13.0",
```

**이유**: `query_points()` API는 v1.13.0에서 도입. 하한을 올려 호환 불가능한 버전 설치를 방지.

### 3.4 Test Changes

#### 3.4.1 `tests/infrastructure/vector/test_qdrant_vectorstore.py`

**변경 대상**: mock 설정 및 assertion에서 `search` → `query_points`

| 변경 포인트 | Before | After |
|------------|--------|-------|
| fixture mock 등록 | `client.search = AsyncMock(return_value=[])` | `client.query_points = AsyncMock(return_value=mock_response)` |
| 반환값 구조 | `return_value=[mock_point]` | `return_value=MagicMock(points=[mock_point])` |
| assertion 대상 | `mock_qdrant_client.search.assert_called_once()` | `mock_qdrant_client.query_points.assert_called_once()` |
| 파라미터 검증 | `call_args.kwargs["query_vector"]` | (제거 — `query` 파라미터는 positional도 가능) |

**영향 테스트 목록**:
- `test_search_by_vector_returns_documents`
- `test_search_by_text_embeds_and_searches`
- `test_search_with_filter_document_type`
- `test_search_with_filter_metadata`
- `test_default_top_k`

#### 3.4.2 `tests/infrastructure/retriever/test_qdrant_retriever.py`

**변경 대상**: 모든 `mock_client.search` 참조 → `mock_client.query_points`

| 변경 포인트 | Before | After |
|------------|--------|-------|
| mock 반환값 | `mock_client.search.return_value = [...]` | `mock_client.query_points.return_value = MagicMock(points=[...])` |
| assertion | `mock_client.search.assert_called_once()` | `mock_client.query_points.assert_called_once()` |
| 파라미터 검증 | `mock_client.search.call_args.kwargs` | `mock_client.query_points.call_args.kwargs` |

**영향 테스트 클래스**:
- `TestRetrieve` (6개 테스트)
- `TestRetrieveWithScores` (3개 테스트)
- `TestScoreThreshold` (2개 테스트)
- `TestMetadataFilterConversion` (2개 테스트)
- `TestDocumentConversion` (4개 테스트)

---

## 4. Implementation Order

```
Step 1: 테스트 수정 (Red → Green 준비)
  ├─ test_qdrant_vectorstore.py — mock을 query_points로 변경
  └─ test_qdrant_retriever.py — mock을 query_points로 변경

Step 2: 프로덕션 코드 수정
  ├─ qdrant_vectorstore.py — search() → query_points()
  └─ qdrant_retriever.py — search() → query_points()

Step 3: pyproject.toml 버전 하한 조정

Step 4: 전체 테스트 실행 및 검증
```

---

## 5. Risk & Mitigation

| 리스크 | 심각도 | 대응 |
|--------|--------|------|
| `QueryResponse.points` 속성명이 다를 수 있음 | Low | qdrant-client 1.16.2 소스 확인 완료 — `.points` 맞음 |
| 다른 모듈에서 `search()` 사용 가능성 | Low | Plan에서 grep 완료 — 2개 파일만 해당 |
| `scroll()`, `retrieve()` 등 다른 API도 변경되었을 수 있음 | Low | Plan에서 확인 완료 — 정상 동작 |
| 테스트에서 `QueryResponse` import 필요 | Low | `MagicMock(points=[...])` 으로 대체 가능 |

---

## 6. Acceptance Criteria

- [ ] `qdrant_vectorstore.py`의 `search_by_vector()`가 `query_points()` 사용
- [ ] `qdrant_retriever.py`의 `retrieve_with_scores()`가 `query_points()` 사용
- [ ] `pyproject.toml`의 qdrant-client 하한이 `>=1.13.0`
- [ ] 기존 단위 테스트 전체 통과 (mock 구조 업데이트)
- [ ] domain/application 레이어 변경 없음 확인
- [ ] 외부 API 계약 (인터페이스 시그니처) 변경 없음 확인
