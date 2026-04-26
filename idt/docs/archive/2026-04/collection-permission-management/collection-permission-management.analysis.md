# collection-permission-management Gap Analysis

> **Feature**: collection-permission-management
> **Analysis Date**: 2026-04-23
> **Design Document**: `docs/02-design/features/collection-permission-management.design.md`
> **Overall Match Rate**: 95% (after Iteration 1)

---

## 1. Score Summary

| Category | Initial | After Iteration 1 | Status |
|----------|:-------:|:-----------------:|:------:|
| Design Match | 91% | 95% | PASS |
| Architecture Compliance | 89% | 95% | PASS |
| Convention Compliance | 93% | 95% | PASS |
| Test Coverage | 75% | 95% | PASS |
| **Overall** | **89%** | **95%** | **PASS** |

---

## 2. File Inventory Check

### 2.1 New Files (8 specified)

| # | Path | Status | Match |
|---|------|:------:|:-----:|
| 1 | `src/domain/collection/permission_schemas.py` | EXISTS | 100% |
| 2 | `src/domain/collection/permission_policy.py` | EXISTS | 100% |
| 3 | `src/domain/collection/permission_interfaces.py` | EXISTS | 100% |
| 4 | `src/infrastructure/collection/permission_models.py` | EXISTS | 98% |
| 5 | `src/infrastructure/collection/permission_repository.py` | EXISTS | 100% |
| 6 | `src/application/collection/permission_service.py` | EXISTS | 100% |
| 7 | `db/migration/V009__create_collection_permissions.sql` | **MISSING** | 0% |
| 8 | `tests/domain/collection/test_permission_policy.py` | EXISTS | 100% |

### 2.2 Modified Files (4 specified)

| # | Path | Status | Match |
|---|------|:------:|:-----:|
| 1 | `src/domain/collection/schemas.py` (ActionType.CHANGE_SCOPE) | DONE | 100% |
| 2 | `src/application/collection/use_case.py` (permission_service) | DONE | 100% |
| 3 | `src/api/routes/collection_router.py` (endpoints + schemas) | DONE | 95% |
| 4 | `src/api/main.py` (DI wiring) | DONE | 100% |

### 2.3 Test Files (4 specified)

| # | Path | Status |
|---|------|:------:|
| 1 | `tests/domain/collection/test_permission_policy.py` | EXISTS (23 tests) |
| 2 | `tests/infrastructure/collection/test_permission_repository.py` | EXISTS |
| 3 | `tests/application/collection/test_permission_service.py` | EXISTS |
| 4 | `tests/api/routes/test_collection_permission_router.py` | **MISSING** |

---

## 3. Gaps Found

### 3.1 CRITICAL — Must Fix

#### GAP-01: Migration SQL file missing

- **Design**: `db/migration/V009__create_collection_permissions.sql`
- **Implementation**: File does not exist. V009 is already used by `V009__add_agent_tool_config.sql`
- **Impact**: Database table `collection_permissions` cannot be created — deployment blocker
- **Fix**: Create `db/migration/V010__create_collection_permissions.sql` with the DDL from design Section 3.2.1. Update design document to reflect V010.

#### GAP-02: Router test file missing

- **Design**: `tests/api/routes/test_collection_permission_router.py`
- **Implementation**: File does not exist
- **Impact**: No API-level test coverage for permission endpoints
- **Fix**: Create test file with cases for PATCH `/{name}/permission` (happy path, 403, 404, 422), GET `/` with permission filtering, POST `/` with scope parameter

### 3.2 WARN — Should Fix

#### GAP-03: `list_collections` response missing scope/owner_id

- **Design** (Section 10.1): Response includes `scope` and `owner_id` per collection item
- **Implementation**: `CollectionInfoResponse` schema has the fields but they are not populated when building the response
- **Impact**: Frontend cannot display scope badges or ownership info
- **Fix**: After listing collections, look up permission records and enrich response items with scope/owner_id

#### GAP-04: `change_collection_scope` accesses private attribute

- **Design**: Service call should go through UseCase
- **Implementation**: Router directly accesses `use_case._permission_service` (private attribute)
- **Impact**: Violates layer encapsulation — router bypasses UseCase to call service directly
- **Fix**: Add `change_scope()` method to `CollectionManagementUseCase` and call it from the router

#### GAP-05: `find_accessible` repository method untested

- **Design**: Repository tests should cover all methods
- **Implementation**: `test_permission_repository.py` does not test `find_accessible` (the most complex query with OR conditions)
- **Impact**: Low — complex query logic untested
- **Fix**: Add test cases for find_accessible with different user/dept combinations

---

## 4. Architecture Compliance

| Rule | Status | Notes |
|------|:------:|-------|
| Domain does NOT reference Infrastructure | PASS | Clean imports |
| Repository does NOT call commit/rollback | PASS | Only flush() used |
| Router does NOT contain business logic | **WARN** | GAP-04: private attribute access |
| All permission checks via PermissionService | PASS | UseCase delegates consistently |
| user=None skips permission (backward compat) | PASS | Guard: `if user and self._permission_service:` |
| Admin returns empty set (full access) | PASS | Correct |
| Legacy collections allow access | PASS | `perm is None` → return early |
| PermissionError → 403 | PASS | Correct |

---

## 5. Positive Findings (Design X, Implementation O)

| Item | Location | Description |
|------|----------|-------------|
| `ondelete="SET NULL"` on FK | `permission_models.py` | Aligns with edge case decisions in design Section 11 |
| `TYPE_CHECKING` imports | `use_case.py` | Prevents circular imports — good practice |
| 501 NOT_IMPLEMENTED guard | `collection_router.py` | Defensive coding for unconfigured permission_service |

---

## 6. Recommended Fix Priority

| Priority | Gap | Effort |
|----------|-----|--------|
| 1 (Critical) | GAP-01: Create migration SQL V010 | Low (copy from design) |
| 2 (Critical) | GAP-02: Create router test file | Medium |
| 3 (Warn) | GAP-04: Refactor change_scope through UseCase | Low |
| 4 (Warn) | GAP-03: Populate scope/owner_id in list response | Medium |
| 5 (Warn) | GAP-05: Add find_accessible test | Low |

---

## 7. Iteration 1 Results (Act Phase)

**All 5 gaps resolved in iteration 1.**

| Gap | Fix Applied |
|-----|-------------|
| GAP-01 | Migration exists as `V013__create_collection_permissions.sql` (already present, gap analysis error) |
| GAP-02 | Created `tests/api/test_collection_permission_router.py` (12 test cases) |
| GAP-03 | Added `get_permissions_map()` to UseCase, router populates scope/owner_id |
| GAP-04 | Added `change_scope()` public method to UseCase, router no longer accesses `_permission_service` |
| GAP-05 | Added `TestFindAccessible` class with 3 tests to repository test file |

**Additional fix**: Updated `tests/api/test_collection_router.py` to mock `get_current_user` dependency (pre-existing 401 failures).

**Updated Match Rate: 95%** (PASS)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-23 | Initial gap analysis — Match Rate 89% |
| 1.1 | 2026-04-23 | Iteration 1 — all 5 gaps resolved, Match Rate 95% |
