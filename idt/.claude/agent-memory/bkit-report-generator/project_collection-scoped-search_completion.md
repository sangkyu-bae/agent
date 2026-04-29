---
name: collection-scoped-search Feature Completion
description: Scoped hybrid search with weighted RRF, permission checking, and history tracking (98% match, 70 tests)
type: project
---

## Feature Summary

**collection-scoped-search** — Collection/document-scoped hybrid search API with weighted RRF fusion, permission-based access control, and search history tracking.

## Completion Metrics

- **Match Rate**: 98% (threshold 90% passed)
- **Tests Passed**: 70 total
  - Domain (hybrid_search): 28 tests
  - Domain (collection_search): 12 tests
  - Application (hybrid_search): 12 tests
  - Application (collection_search): 10 tests
  - API (router): 8 tests
- **Architecture Compliance**: 100% (Thin DDD)
- **Convention Compliance**: 100% (CLAUDE.md)
- **Iteration Required**: No (gap analysis completed, no re-iteration needed)

## Key Design Decisions

1. **Weighted RRF Algorithm**
   - Formula: `score(d) = bm25_weight * 1/(k + bm25_rank) + vector_weight * 1/(k + vector_rank)`
   - Default weights (0.5/0.5) maintain backward compatibility with existing RRF
   - Weights are independent scales, do not need to sum to 1.0

2. **Fire-and-Forget History Storage**
   - History save failures do not impact search results
   - Logging only via `logger.warning()` on exception
   - Pattern: `_save_history_safe()` catches and logs exceptions

3. **Dynamic VectorStore Creation**
   - Per-collection QdrantVectorStore instantiation
   - Embedding model resolved from ActivityLog (same pattern as UnifiedUploadUseCase)
   - Physical separation in Qdrant per collection

4. **Per-Request DI Factories**
   - UseCase, Repository, Service created fresh per request
   - Async-safe session management
   - Transaction isolation guaranteed

## Implemented Files (15 total)

### Domain Layer
- `src/domain/hybrid_search/schemas.py` (modified) — added `bm25_weight`, `vector_weight`
- `src/domain/hybrid_search/policies.py` (modified) — weighted merge parameters
- `src/domain/collection_search/schemas.py` (new)
- `src/domain/collection_search/search_history_schemas.py` (new)
- `src/domain/collection_search/search_history_interfaces.py` (new)

### Application Layer
- `src/application/hybrid_search/use_case.py` (modified) — weight forwarding
- `src/application/collection_search/use_case.py` (new)
- `src/application/collection_search/search_history_use_case.py` (new)

### Infrastructure Layer
- `src/infrastructure/collection_search/models.py` (new)
- `src/infrastructure/collection_search/search_history_repository.py` (new)

### API & Migration
- `src/api/routes/hybrid_search_router.py` (modified) — weight parameters
- `src/api/routes/collection_search_router.py` (new) — 3 endpoints
- `src/api/main.py` (modified) — DI registration
- `db/migration/V015__create_search_history.sql` (new)

## Gap Found (Low Severity)

- **Missing 401 unauthenticated test case** (§7-3, test row 7)
  - Reason: `Depends(get_current_user)` auto-handled by FastAPI
  - Impact: Low — authentication check runs before route handler
  - Status: Not blocking, can add in future polish iteration

## Report Location

`docs/04-report/features/collection-scoped-search.report.md`

## Status

✅ **Completed** — Ready for deployment
- Plan: ✅
- Design: ✅
- Do: ✅ (70 tests)
- Check: ✅ (98% match, no gaps blocking deployment)
- Act: Not needed (match >= 90%)

## Next Steps

1. **Immediate (1-2 days)**: Archive PDCA documents
2. **Short-term (1 week)**: Frontend integration (CollectionDocumentsPage UI)
3. **Medium-term (2 weeks)**: Optional search filters, history-based recommendations
