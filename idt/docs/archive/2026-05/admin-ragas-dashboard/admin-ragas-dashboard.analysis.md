# admin-ragas-dashboard Gap Analysis Report

> **Feature**: admin-ragas-dashboard
> **Design Document**: `docs/02-design/features/admin-ragas-dashboard.design.md`
> **Analysis Date**: 2026-05-18
> **Overall Match Rate**: **95%**

---

## Score Summary

| Category | Score | Status |
|----------|:-----:|:------:|
| API Specification | 100% | PASS |
| Backend Layer Design | 100% | PASS |
| Application DTO | 100% | PASS |
| Frontend Layer Design | 100% | PASS |
| UI Components | 100% | PASS |
| Security | 100% | PASS |
| Test Coverage | 63% | WARN |
| Minor Deviations | 67% | INFO |
| **Weighted Overall** | **95%** | **PASS** |

---

## Matched Items (37/40)

- 4/4 API endpoints: paths, methods, params, defaults, auth
- 13/13 Backend components: domain interface, UseCase, repository, router, DI
- 16/16 Application DTO fields
- 19/19 Frontend items: constants, types, service, query keys, sidebar, route
- 8/8 UI components: StatCard, RunsFilter, RunsTable, RunDetailPanel, score colors
- 4/4 Security: require_role, AdminRoute, authApiClient, 404 handling

---

## Gaps Found

### Gap 1 (P0): `contexts=[]` Hardcoded in Run Detail Response

- **Location**: `src/api/routes/admin_ragas_router.py:173`
- **Issue**: Design specifies `contexts` in result items. Router hardcodes `contexts=[]` instead of passing actual context data from domain entity.
- **Root Cause**: Application-level `EvalResultItem` in `schemas.py` lacks `contexts` field.
- **Fix**: Pass contexts through UseCase → Router.

### Gap 2 (P1): Missing Router Integration Tests

- `tests/api/test_admin_ragas_router.py` does not exist
- Missing: 403 non-admin test, 401 unauthenticated test, happy-path tests

### Gap 3 (P1): Missing Repository Admin Tests

- `tests/infrastructure/ragas/test_repository_admin.py` does not exist

### Gap 4 (P1): Missing Pagination Test

- `test_list_runs_pagination` not implemented in UseCase tests

### Gap 5 (P2): Response Type Naming

- Design: `AdminDashboardResponseBody`, `AdminRunDetailResponseBody`
- Implementation: `DashboardResponseBody`, `RunDetailResponseBody`
- Impact: Low (naming only)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-05-18 | Initial gap analysis |
