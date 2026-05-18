# Gap Analysis: rag-collection-scoped-search

> Design vs Implementation 비교 분석

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | rag-collection-scoped-search |
| Design 참조 | `docs/02-design/features/rag-collection-scoped-search.design.md` |
| 분석일 | 2026-05-11 |
| Match Rate | **100%** |
| 상태 | **PASS** |

### Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | `collection_name`/`es_index`가 HybridSearchRequest에 전달되지 않아 글로벌 컬렉션만 검색되던 문제 |
| Solution | Domain → Application → Infrastructure 3개 레이어에 걸쳐 optional 파라미터 전달 체인 완성 |
| Function UX Effect | 에이전트별 지정 컬렉션 범위 내에서만 문서 검색 |
| Core Value | 부서별 정보 격리 + 검색 정확도 향상 |

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | PASS |
| Architecture Compliance | 100% | PASS |
| Convention Compliance | 100% | PASS |
| Test Coverage | 100% | PASS |
| **Overall** | **100%** | **PASS** |

---

## Per-File Comparison

### 1. `src/domain/hybrid_search/schemas.py` — HybridSearchRequest

| Design Item | Implementation | Match |
|-------------|---------------|:-----:|
| `collection_name: str \| None = None` | line 21 | PASS |
| `es_index: str \| None = None` | line 22 | PASS |
| `frozen=True` preserved | line 9 | PASS |
| Field order (after `vector_weight`) | lines 21-22 | PASS |

### 2. `src/application/rag_agent/tools.py` — InternalDocumentSearchTool._arun()

| Design Item | Implementation | Match |
|-------------|---------------|:-----:|
| `self.collection_name` field exists | line 34 | PASS |
| `self.es_index` field exists | line 35 | PASS |
| `collection_name=self.collection_name` in HybridSearchRequest | line 59 | PASS |
| `es_index=self.es_index` in HybridSearchRequest | line 60 | PASS |

### 3. `src/application/hybrid_search/use_case.py` — HybridSearchUseCase

| Design Item | Implementation | Match |
|-------------|---------------|:-----:|
| `_fetch_bm25`: `target_es_index` override 분기 | line 110 | PASS |
| `_fetch_bm25`: `ESSearchQuery(index=target_es_index)` | lines 111-115 | PASS |
| `_fetch_vector`: `collection_name=request.collection_name` | line 149 | PASS |

### 4. `src/domain/vector/interfaces.py` — VectorStoreInterface.search_by_vector()

| Design Item | Implementation | Match |
|-------------|---------------|:-----:|
| `collection_name` optional parameter added | line 81 | PASS |
| Docstring updated | line 89 | PASS |

### 5. `src/infrastructure/vector/qdrant_vectorstore.py` — QdrantVectorStore.search_by_vector()

| Design Item | Implementation | Match |
|-------------|---------------|:-----:|
| `collection_name: Optional[str] = None` parameter | line 84 | PASS |
| `target_collection` fallback 분기 | line 87 | PASS |
| `collection_name=target_collection` in `query_points()` | line 92 | PASS |
| Error logging uses `target_collection` | line 101 | PASS |

---

## Test Coverage

| Test Case (Design 3-2) | Test File | Match |
|-------------------------|-----------|:-----:|
| **(A) HybridSearchRequest schema** | | |
| `test_default_collection_name_is_none` | `test_schemas.py:52` | PASS |
| `test_default_es_index_is_none` | `test_schemas.py:57` | PASS |
| `test_explicit_collection_name` | `test_schemas.py:62` | PASS |
| `test_explicit_es_index` | `test_schemas.py:67` | PASS |
| `test_both_collection_and_es_index` | `test_schemas.py:72` | PASS |
| **(B) HybridSearchUseCase override** | | |
| `test_fetch_bm25_uses_request_es_index_when_provided` | `test_hybrid_search_use_case.py:263` | PASS |
| `test_fetch_bm25_uses_global_es_index_when_none` | `test_hybrid_search_use_case.py:275` | PASS |
| `test_fetch_vector_uses_request_collection_when_provided` | `test_hybrid_search_use_case.py:287` | PASS |
| `test_fetch_vector_passes_none_when_no_collection` | `test_hybrid_search_use_case.py:300` | PASS |
| `test_both_overrides_applied` (bonus) | `test_hybrid_search_use_case.py:312` | PASS |
| **(C) InternalDocumentSearchTool passing** | | |
| `test_arun_passes_collection_name_to_request` | `test_internal_document_search_tool.py:103` | PASS |
| `test_arun_passes_none_when_no_collection` | `test_internal_document_search_tool.py:112` | PASS |
| `test_arun_passes_only_collection_name` (bonus) | `test_internal_document_search_tool.py:121` | PASS |
| **(D) QdrantVectorStore collection override** | | |
| `test_search_uses_override_collection` | `test_qdrant_vectorstore.py:441` | PASS |
| `test_search_uses_default_collection_when_none` | `test_qdrant_vectorstore.py:459` | PASS |
| `test_search_uses_default_collection_when_omitted` | `test_qdrant_vectorstore.py:479` | PASS |

---

## Backward Compatibility

| Scenario | Expected | Verified |
|----------|----------|:--------:|
| `HybridSearchRequest(query="q")` — no new fields | `collection_name=None, es_index=None` | PASS |
| Existing `search_by_vector()` calls without `collection_name` | Falls back to default collection | PASS |
| Existing UseCase calls without override | Uses global defaults | PASS |

---

## Architecture Compliance

| Rule | Status |
|------|:------:|
| Domain layer has no external dependencies | PASS |
| Domain interface defines contract, infrastructure implements | PASS |
| Application layer orchestrates only | PASS |
| No cross-layer violations | PASS |
| Dependency direction: Domain ← Application ← Infrastructure | PASS |

---

## Differences Found

### Missing Features
None.

### Added Features (beneficial)

| Item | Location | Description |
|------|----------|-------------|
| `test_both_overrides_applied` | `test_hybrid_search_use_case.py:312` | 두 오버라이드 동시 적용 통합 테스트 |
| `test_arun_passes_only_collection_name` | `test_internal_document_search_tool.py:121` | collection_name만 설정된 엣지 케이스 |

### Style Differences (no impact)

| Item | Design | Implementation |
|------|--------|----------------|
| Type annotation in `interfaces.py` | `str \| None` | `Optional[str]` (파일 내 기존 스타일과 일관) |

---

## Conclusion

설계 문서의 모든 항목이 100% 구현 완료. 파라미터 전달 체인이 `InternalDocumentSearchTool._arun()` → `HybridSearchRequest` → `HybridSearchUseCase._fetch_bm25()`/`_fetch_vector()` → `VectorStoreInterface`/`QdrantVectorStore.search_by_vector()`로 정확히 연결됨. 하위 호환성 유지, DDD 레이어 규칙 준수, 테스트 커버리지 충분.
