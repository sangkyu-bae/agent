---
name: fix-es-index-not-found Completion
description: Elasticsearch index-not-found fix with graceful degradation (100% match rate, zero gaps)
type: project
---

**Feature**: fix-es-index-not-found

**Completion Date**: 2026-04-29

**Match Rate**: 100% (72/72 items) — zero gaps found

**Key Achievement**: Eliminated critical ES index-not-found errors affecting hybrid search by implementing:
1. Graceful degradation in ES Repository (`search()` catches NotFoundError → empty list)
2. Independent ES/Vector search paths in HybridSearchUseCase with fallback
3. Index auto-creation at app startup via `ensure_index_exists()`

**Iterations**: 1 (first pass achieved 100% match rate, no rework needed)

**Test Coverage**: 8 new tests, 2886 total passing, 0 new failures

**Files Changed**: 5 (4 modified, 1 new)
- `src/infrastructure/elasticsearch/es_repository.py` — NotFoundError handling + ensure_index_exists()
- `src/domain/elasticsearch/interfaces.py` — ensure_index_exists() abstract method
- `src/application/hybrid_search/use_case.py` — _fetch_bm25() / _fetch_vector() refactor + fallback
- `src/infrastructure/elasticsearch/es_index_mappings.py` (new) — DOCUMENTS_INDEX_MAPPINGS definition
- `src/api/main.py` — _ensure_es_index() in lifespan

**Design Approach**: Defense in depth (graceful degradation + prevention)
- Phase 1: Soft failures for ES/Vector search failures (empty results instead of 500)
- Phase 2: App startup guarantees index existence via auto-creation

**Report Location**: `docs/04-report/features/fix-es-index-not-found.report.md`
