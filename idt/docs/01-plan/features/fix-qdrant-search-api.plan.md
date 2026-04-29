# Plan: fix-qdrant-search-api

> qdrant-client 1.16.x API Breaking Change 대응

---

## 1. 문제 정의

### 1-1. 현상

```
AttributeError: 'AsyncQdrantClient' object has no attribute 'search'
```

- **발생 시점**: Vector search 호출 시 (hybrid search의 vector 파트)
- **영향 범위**: 모든 벡터 검색 기능이 동작하지 않음 (fallback으로 빈 결과 반환)
- **심각도**: **Critical** — 검색 품질 저하 (BM25만으로 동작)

### 1-2. 근본 원인

| 항목 | 값 |
|------|-----|
| 설치된 버전 | `qdrant-client==1.16.2` |
| `pyproject.toml` 명시 | `qdrant-client>=1.7.0` (상한 없음) |
| Breaking Change | v1.12.0에서 `client.search()` deprecated → v1.13.0+ 에서 제거 |
| 대체 메서드 | `client.query_points()` |

### 1-3. API 변경 내역

**Before (제거됨)**:
```python
results = await client.search(
    collection_name="...",
    query_vector=vector,
    limit=top_k,
    query_filter=filter,
    with_vectors=True,
)
# results: List[ScoredPoint]
```

**After (현재 API)**:
```python
response = await client.query_points(
    collection_name="...",
    query=vector,          # query_vector → query
    limit=top_k,
    query_filter=filter,   # 동일
    with_vectors=True,     # 동일
)
# response: QueryResponse (response.points: List[ScoredPoint])
```

**핵심 차이점**:
1. 메서드명: `search()` → `query_points()`
2. 파라미터: `query_vector` → `query`
3. 반환값: `List[ScoredPoint]` → `QueryResponse` (`.points` 속성으로 접근)

---

## 2. 영향 범위 분석

### 2-1. 직접 영향 파일 (`.search()` 호출)

| 파일 | 위치 | 메서드 |
|------|------|--------|
| `src/infrastructure/vector/qdrant_vectorstore.py` | Line 89 | `search_by_vector()` |
| `src/infrastructure/retriever/qdrant_retriever.py` | Line 84 | `retrieve_with_scores()` |

### 2-2. 간접 영향 (호출자)

| 호출자 | 영향 |
|--------|------|
| `qdrant_vectorstore.search_by_text()` | `search_by_vector()` 내부 호출 |
| `application/hybrid_search/use_case.py:_fetch_vector()` | `search_by_vector()` 사용 |
| `QdrantRetriever.retrieve()` | `retrieve_with_scores()` 내부 호출 |

### 2-3. 영향 없는 API (확인 완료)

다음 메서드들은 `qdrant-client 1.16.2`에서 정상 동작:
- `upsert()`, `delete()`, `scroll()`, `retrieve()`, `get_collections()`, `create_collection()`

---

## 3. 수정 계획

### Task 1: `qdrant_vectorstore.py` — `search_by_vector()` 수정

- `self._client.search()` → `self._client.query_points()` 변경
- `query_vector=vector` → `query=vector` 파라미터명 변경
- 반환값 처리: `results` → `response.points`

### Task 2: `qdrant_retriever.py` — `retrieve_with_scores()` 수정

- 동일한 패턴으로 `search()` → `query_points()` 변경
- `query_vector=query_vector` → `query=query_vector`
- 반환값 처리: `results` → `response.points`

### Task 3: `pyproject.toml` — 버전 범위 명시

- `qdrant-client>=1.7.0` → `qdrant-client>=1.13.0` 로 하한 조정
- 이유: `query_points()` API를 사용하므로 1.13.0 미만에서는 동작하지 않음

### Task 4: 테스트 수정/추가

- 기존 테스트에서 mock된 `search()` 호출을 `query_points()` 로 변경
- `QueryResponse` 반환 객체 mock 구조 업데이트

---

## 4. 리스크 & 제약

| 리스크 | 대응 |
|--------|------|
| `query_points()` 반환값 구조가 다름 | `.points` 속성 접근 추가 |
| 기존 테스트가 `.search()` mock 사용 | mock 대상을 `query_points`로 변경 |
| 하위 호환성 (1.13.0 미만) | `pyproject.toml`에 하한 명시로 방지 |

---

## 5. 완료 기준

- [ ] `qdrant_vectorstore.py`에서 `query_points()` 사용
- [ ] `qdrant_retriever.py`에서 `query_points()` 사용
- [ ] `pyproject.toml` 버전 하한 조정
- [ ] 관련 단위 테스트 통과
- [ ] hybrid search API 호출 시 vector 결과 정상 반환

---

## 6. 예상 작업량

- **규모**: Small (버그 수정)
- **수정 파일**: 3~4개
- **예상 시간**: 30분 이내
