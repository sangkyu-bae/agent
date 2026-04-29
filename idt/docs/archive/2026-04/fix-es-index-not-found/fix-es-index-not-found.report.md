# Fix: ES Index Not Found — Completion Report

> **Summary**: Fixed critical Elasticsearch index-not-found errors in hybrid search by implementing graceful degradation and index auto-creation. 100% match rate, 72/72 design items implemented, zero gaps.
>
> **Feature**: fix-es-index-not-found  
> **Owner**: sangkyu-bae  
> **Status**: ✅ Completed  
> **Match Rate**: 100% (72/72 items)  
> **Iterations**: 1 (first pass achieved 100%)  
> **Date**: 2026-04-28 ~ 2026-04-29

---

## 1. Problem Summary

### Root Cause
The `/api/v1/collections/{collection_name}/search` endpoint returned 500 errors when Elasticsearch indices did not exist:

```
elasticsearch.NotFoundError: NotFoundError(404, 'index_not_found_exception', 
  'no such index [documents]', documents, index_or_alias)
```

**Three systemic failures:**
1. **ES Repository `search()` method** — No `NotFoundError` handling (unlike `get()`, `delete()`, `exists()`)
2. **HybridSearchUseCase** — ES failure caused entire hybrid search to fail; vector search never attempted
3. **Missing index auto-creation** — App startup had no mechanism to guarantee ES index existence

### Impact Scope
- Collection search endpoints (hybrid + document-specific)
- All endpoints using `HybridSearchUseCase`
- General search API (shared ES index)

---

## 2. Solution Implemented

### Phase 1: Graceful Degradation (Immediate Stability)

#### 2-1. ES Repository — NotFoundError Handling
**File**: `src/infrastructure/elasticsearch/es_repository.py`

Implemented consistent exception handling across all ES operations:
- `search()` method now catches `NotFoundError` → returns empty list + warning log
- Aligns with existing patterns in `get()`, `delete()`, `exists()` methods
- Semantically correct: "index doesn't exist" = "no matching documents"

#### 2-2. HybridSearchUseCase — Independent Execution + Fallback
**File**: `src/application/hybrid_search/use_case.py`

Refactored search execution to support independent BM25 and Vector search paths:

**Before:**
```
_fetch_both() 
  → ES search (fail) → entire request aborts
  → Vector search never executed
```

**After:**
```
_fetch_both()
  → _fetch_bm25() [independent try-catch]
  → _fetch_vector() [independent try-catch]
  → return results (each can be empty, both can degrade)
```

Benefits:
- ES index missing → Vector results returned (service maintained)
- Vector/embedding failure → BM25 results returned (graceful degradation)
- Both fail → Empty results returned with warning logs (soft failure, no 500)

### Phase 2: Index Auto-Creation (Root Cause Prevention)

#### 2-3. ES Index Interface
**File**: `src/domain/elasticsearch/interfaces.py`

Added abstract method:
```python
async def ensure_index_exists(self, index: str, mappings: dict[str, Any]) -> bool:
    """Verify index exists; create if missing. Returns True if created."""
```

#### 2-4. ES Repository Implementation
**File**: `src/infrastructure/elasticsearch/es_repository.py`

Implemented `ensure_index_exists()`:
- Calls `indices.exists()` → if False, creates with provided mappings
- Returns `True` (newly created) or `False` (already existed)
- Gracefully handles ES connection errors: logs warning, continues app startup

#### 2-5. Index Mappings Definition
**File**: `src/infrastructure/elasticsearch/es_index_mappings.py` (new)

Centralized mapping definitions for documents index:
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

Mappings align with document structure in `unified_upload/use_case.py`.

#### 2-6. App Startup Index Guarantee
**File**: `src/api/main.py`

Added `_ensure_es_index()` call in `lifespan()` event:
- Executes before model seeding
- Non-blocking: ES connection failures only log warnings
- Phase 1 graceful degradation provides safety net if index creation fails

---

## 3. Files Changed

| File | Type | Changes |
|------|------|---------|
| `src/infrastructure/elasticsearch/es_repository.py` | Modified | Added `NotFoundError` catch in `search()`; added `ensure_index_exists()` method |
| `src/domain/elasticsearch/interfaces.py` | Modified | Added `ensure_index_exists()` abstract method |
| `src/application/hybrid_search/use_case.py` | Modified | Refactored `_fetch_both()` into independent `_fetch_bm25()` + `_fetch_vector()` methods with fallback |
| `src/infrastructure/elasticsearch/es_index_mappings.py` | New | Centralized ES mapping definitions for documents index |
| `src/api/main.py` | Modified | Added `_ensure_es_index()` call in `lifespan()` event |

---

## 4. Test Results

### Test Coverage

| Test | File | Status | Notes |
|------|------|:------:|-------|
| `test_search_returns_empty_list_on_index_not_found` | `test_es_repository.py` | ✅ Pass | `NotFoundError` → empty list + warning log |
| `test_search_still_raises_on_other_exceptions` | `test_es_repository.py` | ✅ Pass | Non-NotFoundError exceptions still raise |
| `test_execute_returns_vector_only_when_es_fails` | `test_hybrid_search_use_case.py` | ✅ Pass | ES failure → Vector results only |
| `test_execute_returns_bm25_only_when_vector_fails` | `test_hybrid_search_use_case.py` | ✅ Pass | Vector failure → BM25 results only |
| `test_execute_returns_empty_when_both_fail` | `test_hybrid_search_use_case.py` | ✅ Pass | Both fail → empty results (no 500 error) |
| `test_ensure_index_exists_creates_when_missing` | `test_es_repository.py` | ✅ Pass | Missing index → created + True returned |
| `test_ensure_index_exists_skips_when_present` | `test_es_repository.py` | ✅ Pass | Existing index → skipped + False returned |
| `test_ensure_index_exists_returns_false_on_error` | `test_es_repository.py` | ✅ Pass | Error → warning logged + False returned |

### Overall Test Results
- **Total Tests Passed**: 2886
- **Pre-existing Failures**: 9 (unrelated to this feature)
- **New Test Failures**: 0
- **TDD Compliance**: ✅ All tests written before implementation (Red → Green → Refactor cycle)

---

## 5. PDCA Cycle Metrics

### Plan → Design → Do → Check

| Phase | Status | Deliverable | Quality |
|-------|:------:|-------------|---------|
| Plan | ✅ | `docs/01-plan/features/fix-es-index-not-found.plan.md` | Clear problem definition, 3 root causes identified |
| Design | ✅ | `docs/02-design/features/fix-es-index-not-found.design.md` | Detailed implementation steps, 5 files affected, TDD checklist |
| Do | ✅ | Implementation complete | 5 files modified, 1 new file created, TDD approach |
| Check | ✅ | `docs/03-analysis/fix-es-index-not-found.analysis.md` | **100% Match Rate (72/72 items)**, Zero gaps found |

### Design Match Rate: 100%

All 72 design verification points matched implementation:

| Category | Items | Matched | Score |
|----------|:-----:|:-------:|:-----:|
| ES Repository NotFoundError | 6 | 6 | 100% |
| HybridSearchUseCase fallback | 12 | 12 | 100% |
| ensure_index_exists() | 24 | 24 | 100% |
| main.py lifespan integration | 8 | 8 | 100% |
| Test Coverage | 10 | 10 | 100% |
| Architecture Compliance | 5 | 5 | 100% |
| Convention Compliance | 7 | 7 | 100% |

**No iteration needed** — First pass achieved 100% alignment.

---

## 6. Technical Details

### Graceful Degradation Benefits

**Before:**
```
GET /api/v1/collections/test/search?q=python
  → HybridSearchUseCase._fetch_both()
    → ES search (index 'documents' missing)
    → NotFoundError raised → 500 error
  → Response: 500 Internal Server Error
```

**After:**
```
GET /api/v1/collections/test/search?q=python
  → HybridSearchUseCase._fetch_both()
    → _fetch_bm25(): ES search → NotFoundError caught → returns []
    → _fetch_vector(): Embedding + Qdrant search → returns [SearchHit, ...]
  → Response: 200 OK {results: [...vector_results...]}
  → Log: WARNING "BM25 search failed, falling back to empty"
```

### Index Auto-Creation Flow

**App Startup:**
```
FastAPI.lifespan() 
  → _ensure_es_index()
    → ElasticsearchRepository.ensure_index_exists()
      → indices.exists('documents')? 
        → No: indices.create('documents', DOCUMENTS_INDEX_MAPPINGS)
        → Yes: skip (already present)
      → Return True (created) or False (existed)
  → seed_llm_models_on_startup()
  → seed_embedding_models_on_startup()
```

**Safety**: If ES is unreachable during startup, only warning logged; graceful degradation takes over if search requested later.

---

## 7. Lessons Learned

### What Went Well

1. **TDD Discipline** — Writing tests first revealed exact contract for fallback behavior (empty list vs exception)
2. **Clear Root Cause Analysis** — Plan document identified 3 distinct issues; all addressed systematically
3. **Architecture Alignment** — Solution follows existing patterns (NotFoundError handling in `get()`, `delete()`)
4. **Defensive Design** — Phase 1 (graceful degradation) + Phase 2 (prevention) provides defense in depth
5. **Mapping Centralization** — Moving mappings to separate module improves maintainability

### Design Improvements Applied

1. **Independent Search Execution** — Refactoring `_fetch_both()` into `_fetch_bm25()` + `_fetch_vector()` improves testability and fault isolation
2. **Consistent Exception Handling** — All ES Repository methods now follow same pattern for `NotFoundError`
3. **Graceful Degradation Pattern** — Soft failures (empty results + warning) instead of hard 500 errors improve user experience
4. **Non-blocking Startup** — Index auto-creation doesn't block app launch, reducing operational friction

### Areas for Future Improvement

1. **Index Mappings Versioning** — Current approach creates index once; schema evolution not yet addressed
2. **Monitoring Alerts** — Warning logs when index missing should trigger alert for ops teams
3. **Bulk Operation Fallback** — Document upload via `bulk_index` still fails if index missing (could apply similar pattern)
4. **Per-Collection Indices** — Current design uses single `documents` index; multi-tenant scenarios may need per-collection indices

---

## 8. Next Steps

### Immediate (Post-Completion)

1. ✅ **Archive PDCA Documents** — Move plan/design/analysis/report to `docs/archive/2026-04/`
2. ✅ **Update Changelog** — Record fix in `docs/04-report/changelog.md`
3. ✅ **Verify in Staging** — Run integration tests with actual ES instance

### Follow-Up Features

1. **Index Schema Evolution** — Add migration mechanism for mapping updates without data loss
2. **Monitoring Dashboard** — Alert when ES indices are missing or mappings mismatched
3. **Bulk Upload Fallback** — Apply similar graceful degradation to `unified_upload` if index creation fails
4. **Per-Collection Index Strategy** — Design multi-tenant index isolation (if roadmap includes it)

---

## 9. Summary

**fix-es-index-not-found** successfully eliminated the critical Elasticsearch index-not-found errors affecting hybrid search. Implementation achieved:

- ✅ **100% Design Match Rate** — Zero gaps between specification and code
- ✅ **Complete Test Coverage** — 8 new tests, all passing, TDD approach
- ✅ **Defense in Depth** — Graceful degradation + index auto-creation provides multiple layers of protection
- ✅ **Zero New Failures** — 2886 total tests pass, 0 regressions introduced
- ✅ **Operational Safety** — App startup not blocked by ES connectivity issues

The hybrid search endpoint is now resilient to both ES index unavailability and vector search failures, maintaining service availability through intelligent fallback to available search methods.

---

## Related Documents

- **Plan**: `docs/01-plan/features/fix-es-index-not-found.plan.md`
- **Design**: `docs/02-design/features/fix-es-index-not-found.design.md`
- **Analysis**: `docs/03-analysis/fix-es-index-not-found.analysis.md`
