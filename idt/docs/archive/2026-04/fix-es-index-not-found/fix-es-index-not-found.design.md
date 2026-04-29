# Design: fix-es-index-not-found

> Created: 2026-04-28
> Plan: `docs/01-plan/features/fix-es-index-not-found.plan.md`
> Status: Draft

---

## 1. 변경 대상 및 현재 코드 분석

### 1-1. ElasticsearchRepository.search() (NotFoundError 미처리)

**현재 코드** (`src/infrastructure/elasticsearch/es_repository.py:110-149`):

```python
async def search(
    self, query: ESSearchQuery, request_id: str
) -> list[ESSearchResult]:
    try:
        es = self._client.get_client()
        kwargs = { "index": query.index, "query": query.query, ... }
        resp = await es.search(**kwargs)
        # ... 결과 변환
        return results
    except Exception as e:
        self._logger.error("ES search failed", exception=e, request_id=request_id)
        raise   # ← NotFoundError도 여기서 그대로 raise
```

**문제**: `get()`과 `delete()`는 `NotFoundError`를 catch하여 graceful하게 `None`/`False` 반환하지만,
`search()`는 모든 예외를 동일하게 raise. 인덱스 미존재 시 500 에러로 전파.

### 1-2. HybridSearchUseCase._fetch_both() (한쪽 실패 → 전체 실패)

**현재 코드** (`src/application/hybrid_search/use_case.py:80-142`):

```python
async def _fetch_both(self, request, request_id):
    # BM25 (ES)
    es_query = ESSearchQuery(index=self._es_index, query=..., size=...)
    es_results = await self._es_repo.search(es_query, request_id)  # ← 여기서 예외 → 전체 abort
    bm25_hits = [...]

    # Vector (Qdrant)
    query_vector = await self._embedding.embed_text(request.query)
    vector_docs = await self._vector_store.search_by_vector(...)    # ← 실행 기회 없음
    vector_hits = [...]

    return bm25_hits, vector_hits
```

**문제**: ES 검색이 실패하면 Vector 검색이 시도되지 않음.
하이브리드 검색은 두 소스의 독립적 실행이 핵심.

### 1-3. 앱 시작 시 ES 인덱스 보장 메커니즘 부재

**현재 코드** (`src/api/main.py:1609-1641` lifespan):

```python
async def lifespan(app: FastAPI):
    _hybrid_search_use_case = create_hybrid_search_use_case()
    # ... 기타 초기화
    await seed_llm_models_on_startup()
    await seed_embedding_models_on_startup()
    # ← ES 인덱스 존재 확인/생성 로직 없음
    yield
```

**문제**: ES 인덱스는 `bulk_index` 호출 시 자동 생성(ES 기본 동작)에만 의존.
ES 재시작 또는 첫 검색 전 문서 미업로드 시 인덱스 미존재.

---

## 2. 설계 상세

### 2-1. Phase 1: ES Repository — NotFoundError graceful 처리

**파일**: `src/infrastructure/elasticsearch/es_repository.py`

**변경**: `search()` 메서드에 `NotFoundError` catch 추가

```python
# 변경 후
async def search(
    self, query: ESSearchQuery, request_id: str
) -> list[ESSearchResult]:
    self._logger.info("ES search start", request_id=request_id, index=query.index)
    try:
        es = self._client.get_client()
        kwargs = { ... }
        resp = await es.search(**kwargs)
        # ... 결과 변환
        return results
    except NotFoundError:
        self._logger.warning(
            "ES index not found, returning empty results",
            request_id=request_id,
            index=query.index,
        )
        return []
    except Exception as e:
        self._logger.error("ES search failed", exception=e, request_id=request_id)
        raise
```

**설계 근거**:
- `get()`, `delete()`, `exists()` 모두 `NotFoundError`를 graceful 처리 → 일관성
- 인덱스 미존재는 "데이터 없음"과 동등 → 빈 리스트 반환이 의미적으로 정확
- `warning` 레벨 로그로 운영 모니터링 가능

### 2-2. Phase 1: HybridSearchUseCase — 독립 실행 fallback

**파일**: `src/application/hybrid_search/use_case.py`

**변경**: `_fetch_both()`에서 ES/Vector 검색을 각각 독립적으로 실행

```python
# 변경 후
async def _fetch_both(
    self, request: HybridSearchRequest, request_id: str
) -> tuple[list[SearchHit], list[SearchHit]]:
    bm25_hits = await self._fetch_bm25(request, request_id)
    vector_hits = await self._fetch_vector(request, request_id)

    if not bm25_hits and not vector_hits:
        raise RuntimeError("Both BM25 and vector search returned no results or failed")

    return bm25_hits, vector_hits

async def _fetch_bm25(
    self, request: HybridSearchRequest, request_id: str
) -> list[SearchHit]:
    try:
        # ... 기존 BM25 검색 로직 (ES 쿼리 빌드 + 검색 + 변환)
        return bm25_hits
    except Exception as e:
        self._logger.warning(
            "BM25 search failed, falling back to empty",
            exception=e,
            request_id=request_id,
        )
        return []

async def _fetch_vector(
    self, request: HybridSearchRequest, request_id: str
) -> list[SearchHit]:
    try:
        # ... 기존 Vector 검색 로직 (embed + search + 변환)
        return vector_hits
    except Exception as e:
        self._logger.warning(
            "Vector search failed, falling back to empty",
            exception=e,
            request_id=request_id,
        )
        return []
```

**설계 근거**:
- 하이브리드 검색의 핵심 가치: 한쪽 실패 시 다른 쪽으로 서비스 유지
- 단일 책임 원칙: BM25 / Vector 검색 로직을 별도 메서드로 분리
- 양쪽 모두 빈 결과일 때만 에러 raise → 완전 장애 시에만 실패

**양쪽 빈 결과 시 동작**: `RuntimeError` raise → `execute()` catch → 에러 로그 + raise.
단, "양쪽 모두 실패"와 "양쪽 모두 결과 0건"은 구분 필요:
- 실패: exception 발생 → warning 로그 후 `[]` 반환
- 결과 0건: 정상 동작 → `[]` 반환

따라서 "양쪽 모두 결과 없음"은 에러가 아닌 정상 빈 응답으로 처리해야 함.
에러를 raise하지 않고 빈 결과를 그대로 반환하도록 수정:

```python
async def _fetch_both(...) -> tuple[list[SearchHit], list[SearchHit]]:
    bm25_hits = await self._fetch_bm25(request, request_id)
    vector_hits = await self._fetch_vector(request, request_id)
    return bm25_hits, vector_hits
```

### 2-3. Phase 2: ensure_index_exists() — 인덱스 자동 생성

**파일 1**: `src/domain/elasticsearch/interfaces.py`

인터페이스에 `ensure_index_exists` 추상 메서드 추가:

```python
@abstractmethod
async def ensure_index_exists(self, index: str, mappings: dict[str, Any]) -> bool:
    """인덱스 존재 확인 후 없으면 생성.

    Returns:
        True: 새로 생성됨, False: 이미 존재
    """
```

**파일 2**: `src/infrastructure/elasticsearch/es_repository.py`

구현 추가:

```python
async def ensure_index_exists(self, index: str, mappings: dict[str, Any]) -> bool:
    try:
        es = self._client.get_client()
        exists = await es.indices.exists(index=index)
        if exists:
            return False
        await es.indices.create(index=index, mappings=mappings)
        self._logger.info("ES index created", index=index)
        return True
    except Exception as e:
        self._logger.warning(
            "ES ensure_index_exists failed",
            exception=e,
            index=index,
        )
        return False
```

**ES 매핑 정의** (문서 인덱스용):

```python
DOCUMENTS_INDEX_MAPPINGS = {
    "properties": {
        "content": {"type": "text"},
        "morph_text": {"type": "text"},
        "morph_keywords": {"type": "keyword"},
        "chunk_id": {"type": "keyword"},
        "chunk_type": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
        "total_chunks": {"type": "integer"},
        "document_id": {"type": "keyword"},
        "user_id": {"type": "keyword"},
        "collection_name": {"type": "keyword"},
        "parent_id": {"type": "keyword"},
    }
}
```

이 매핑은 `unified_upload/use_case.py:246-259`의 `body` 구조와 일치.

### 2-4. Phase 2: main.py lifespan — 인덱스 보장

**파일**: `src/api/main.py`

lifespan 함수에 ES 인덱스 보장 로직 추가:

```python
async def lifespan(app: FastAPI):
    # ... 기존 초기화 ...

    # ES 인덱스 보장
    await _ensure_es_index()

    await seed_llm_models_on_startup()
    await seed_embedding_models_on_startup()
    yield
    # ...


async def _ensure_es_index() -> None:
    """앱 시작 시 ES 문서 인덱스 존재를 보장한다."""
    from src.infrastructure.elasticsearch.es_index_mappings import DOCUMENTS_INDEX_MAPPINGS

    es_config = ElasticsearchConfig(...)
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=get_app_logger())
    await es_repo.ensure_index_exists(settings.es_index, DOCUMENTS_INDEX_MAPPINGS)
```

**매핑 정의 파일**: `src/infrastructure/elasticsearch/es_index_mappings.py`
- 인덱스 매핑을 별도 모듈로 분리하여 관리

---

## 3. 파일 변경 목록

| # | 파일 | 변경 유형 | 변경 내용 |
|---|------|----------|----------|
| 1 | `src/infrastructure/elasticsearch/es_repository.py` | 수정 | `search()` NotFoundError catch + `ensure_index_exists()` 추가 |
| 2 | `src/domain/elasticsearch/interfaces.py` | 수정 | `ensure_index_exists()` 추상 메서드 추가 |
| 3 | `src/application/hybrid_search/use_case.py` | 수정 | `_fetch_both()` → `_fetch_bm25()` + `_fetch_vector()` 분리, fallback 적용 |
| 4 | `src/infrastructure/elasticsearch/es_index_mappings.py` | **신규** | `DOCUMENTS_INDEX_MAPPINGS` 상수 정의 |
| 5 | `src/api/main.py` | 수정 | lifespan에 `_ensure_es_index()` 호출 추가 |

---

## 4. 테스트 설계

### 4-1. ES Repository 테스트 (Phase 1)

**파일**: `tests/infrastructure/elasticsearch/test_es_repository.py`

| 테스트 | 시나리오 | 기대 결과 |
|--------|----------|----------|
| `test_search_returns_empty_list_on_index_not_found` | `es.search()`가 `NotFoundError` raise | 빈 리스트 반환 + warning 로그 |
| `test_search_still_raises_on_other_exceptions` | `es.search()`가 `RuntimeError` raise | 기존대로 raise (기존 테스트 유지) |

### 4-2. HybridSearchUseCase 테스트 (Phase 1)

**파일**: `tests/application/hybrid_search/test_hybrid_search_use_case.py`

| 테스트 | 시나리오 | 기대 결과 |
|--------|----------|----------|
| `test_execute_returns_vector_only_when_es_fails` | ES repo raises → Vector 정상 | Vector 결과만 포함된 응답, warning 로그 |
| `test_execute_returns_bm25_only_when_vector_fails` | Vector store raises → ES 정상 | BM25 결과만 포함된 응답, warning 로그 |
| `test_execute_returns_empty_when_both_fail` | 양쪽 모두 raises | 빈 결과 응답 (에러 아님), warning 로그 2건 |

**기존 테스트 변경**:
- `test_execute_logs_error_and_reraises_on_es_failure` → **삭제 또는 수정**: ES 실패 시 더 이상 raise하지 않으므로, fallback 동작 검증으로 대체

### 4-3. ensure_index_exists 테스트 (Phase 2)

**파일**: `tests/infrastructure/elasticsearch/test_es_repository.py`

| 테스트 | 시나리오 | 기대 결과 |
|--------|----------|----------|
| `test_ensure_index_exists_creates_when_missing` | `indices.exists()` → False | `indices.create()` 호출, True 반환 |
| `test_ensure_index_exists_skips_when_present` | `indices.exists()` → True | `indices.create()` 미호출, False 반환 |
| `test_ensure_index_exists_returns_false_on_error` | `indices.exists()` raises | warning 로그, False 반환 (앱 시작 안 막음) |

---

## 5. 구현 순서 (TDD)

```
Phase 1: Graceful Degradation
─────────────────────────────────────
1. [RED]   test_search_returns_empty_list_on_index_not_found
2. [GREEN] es_repository.py search() — NotFoundError catch
3. [RED]   test_execute_returns_vector_only_when_es_fails
4. [RED]   test_execute_returns_bm25_only_when_vector_fails
5. [RED]   test_execute_returns_empty_when_both_fail
6. [GREEN] use_case.py — _fetch_bm25() / _fetch_vector() 분리 + fallback
7. [REFACTOR] 기존 실패 테스트 수정

Phase 2: 인덱스 자동 생성
─────────────────────────────────────
8.  [RED]   test_ensure_index_exists_creates_when_missing
9.  [RED]   test_ensure_index_exists_skips_when_present
10. [RED]   test_ensure_index_exists_returns_false_on_error
11. [GREEN] interfaces.py — ensure_index_exists 추상 메서드
12. [GREEN] es_repository.py — ensure_index_exists 구현
13. [NEW]   es_index_mappings.py — DOCUMENTS_INDEX_MAPPINGS
14. [MOD]   main.py — lifespan에 _ensure_es_index() 추가
```

---

## 6. 주의사항

- `es_repository.py` `search()`의 `NotFoundError` 처리는 **모든 ES 검색 경로에 적용**됨
  → `/api/v1/search`, `/api/v1/collections/{name}/search` 모두 혜택
- `_fetch_bm25()` / `_fetch_vector()` 분리 시 기존 `_fetch_both()`의 로직 그대로 이동 (리팩터링만)
- `ensure_index_exists()` 실패 시 앱 시작을 **막지 않음** (warning 로그만)
  → ES가 아직 시작 안 된 상황에서도 앱은 정상 기동, Phase 1 graceful degradation이 방어
- ES 매핑의 `morph_text` 필드는 별도 analyzer 없이 기본 text 타입 사용
  → 한국어 형태소 분석은 앱 레벨(KiwiMorphAnalyzer)에서 처리하므로 ES analyzer 불필요
