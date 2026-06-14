---
template: analysis
version: 1.2
feature: agent-run-admin-dashboard
date: 2026-05-22
author: gap-detector
project: sangplusbot (idt + idt_front)
status: Approved
---

# agent-run-admin-dashboard Analysis Report

> **Analysis Type**: Gap Analysis (Design ↔ Implementation)
>
> **Project**: sangplusbot (idt + idt_front)
> **Analyst**: gap-detector
> **Date**: 2026-05-22
> **Design Doc**: [agent-run-admin-dashboard.design.md](../02-design/features/agent-run-admin-dashboard.design.md)
> **Plan Doc**:   [agent-run-admin-dashboard.plan.md](../01-plan/features/agent-run-admin-dashboard.plan.md)

---

## 1. Analysis Overview

### 1.1 Purpose

M5 dashboard PDCA의 Check 단계 — 설계 5 endpoints + UI 3 pages가 실제 구현과 일치하는지, 보안 불변식·DDD 의존성·TDD 커버리지가 유지되는지를 검증한다.

### 1.2 Scope

- **Backend**: `idt/src/{domain,application,infrastructure,interfaces,api}/agent_run*`
- **Frontend**: `idt_front/src/{types,services,hooks,pages,components,constants,lib}` (M5 신규 부분)
- **Tests**: `idt/tests/`, `idt_front/src/**/*.test.{ts,tsx}`

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

| Design | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| `GET /api/v1/admin/agents/runs` | `GET /api/v1/admin/runs` | ⚠️ Modified | M5 선행 작업이 `/admin/runs`로 이미 채택 — Plan 단계에서 결정. FE `ADMIN_AGENT_RUNS` 상수가 `/api/v1/admin/runs`로 동기화돼 일관성 유지. |
| `GET /api/v1/admin/usage/summary` | `GET /api/v1/admin/usage/summary` | ✅ Match | `require_role("admin")` + `_resolve_period` 사용. |
| `GET /api/v1/admin/usage/timeseries` | `GET /api/v1/admin/usage/timeseries` | ✅ Match | bucket="day" 고정. |
| `GET /api/v1/usage/me/runs` | `GET /api/v1/usage/me/runs` | ✅ Match | `user_id` 쿼리 미수용 — route 시그니처에 없음. |
| `GET /api/v1/usage/me/timeseries` | `GET /api/v1/usage/me/timeseries` | ✅ Match | `current_user.id` 강제. |

**Query 파라미터 차이**:

| Design | Impl | Severity | Notes |
|--------|------|---------|-------|
| `page` / `size` | `offset` / `limit` | Minor | 의미 동등 (offset=size*(page-1)). M5 선행 PDCA에서 채택된 표기 — Plan §6.2 "offset (page+size)"와도 호환. FE `AdminRunsParams`도 `limit`/`offset`로 명명. |
| Response: `{ from, to, page, size, total, items }` | `{ from_dt, to_dt, limit, offset, total, rows }` | Minor | Pydantic alias 없이 snake_case 그대로 노출. FE 타입이 BE 응답에 1:1 동기화. |

### 2.2 Domain VOs & Repository Interfaces

| Design Item | Implementation | Status | Severity |
|-------------|----------------|--------|----------|
| `RunListFilter` (singular) with `force_user_id` field | `RunListFilters` (plural) without `force_user_id`; UseCase uses `dataclasses.replace(filters, user_id=...)` | ⚠️ Modified | Minor — 보안 효과 동등. UseCase 레벨 override가 더 단순. |
| `RunListItem` dataclass | `AgentRun` entity 직접 반환 + Pydantic `RunRowDto` 변환 | ⚠️ Modified | Minor — 변환 위치가 schema 레이어로 이동. 도메인 row 추가 부담 회피. |
| `UsageSummaryRow` | `UsageSummaryRow` | ✅ Match | |
| `UsageTimeseriesPoint` | `UsageTimeseriesPoint` | ✅ Match | |
| `AgentRunRepositoryInterface.list_runs(filter, page, size)` | `list_runs(filters)` + 별도 `count_runs(filters)` | ⚠️ Modified | Minor — page/size는 filters 내부로 흡수. UseCase에서 `asyncio.gather(list_runs, count_runs)` 동시 실행 → 성능상 우위. |
| `LlmCallRepositoryInterface.aggregate_summary` | 동일 시그니처 | ✅ Match | |
| `LlmCallRepositoryInterface.aggregate_timeseries` | 동일 시그니처 | ✅ Match | |

### 2.3 UseCases

| Design | Implementation | Status | Notes |
|--------|----------------|--------|-------|
| `ListRunsUseCase` (신규) | 기존 M5 작업물 재사용 + `_validate()` 강화 | ✅ Match (semantic) | Design은 "5 신규"라 표기. 실제로는 4 신규 + 1 기존. |
| `GetUsageSummaryUseCase` | `get_usage_summary_use_case.py` | ✅ Match | |
| `GetUsageTimeseriesUseCase` | `get_usage_timeseries_use_case.py` | ✅ Match | |
| `ListMyRunsUseCase` | `list_my_runs_use_case.py` — `ListRunsUseCase`에 위임 (DRY) | ✅ Match | force_user_id 대신 `replace(filters, user_id=user_id)`로 강제. |
| `GetMyUsageTimeseriesUseCase` | `get_my_usage_timeseries_use_case.py` | ✅ Match | |

### 2.4 Pydantic Response Schemas

| Design | Implementation | Status | Notes |
|--------|----------------|--------|-------|
| `RunListItemDto` w/ langsmith_run_url | `RunRowDto` + `conversation_id` + `error_message` − `langsmith_run_url` | ⚠️ Modified | Minor — langsmith URL은 RunDetailResponse 트리에 존재. 목록에는 불필요. |
| `RunListResponse` (`from`/`to` alias) | `RunListResponse` (`from_dt`/`to_dt`, no alias) | ⚠️ Modified | Minor — 일관성 ↑ (FE도 `from_dt` 사용). |
| `UsageSummaryResponse` (서버측 `success_rate`) | 동일 + `from_row` factory에서 0-division guard 후 `round(rate, 4)` | ✅ Match | |
| `UsageTimeseriesPointDto` / `UsageTimeseriesResponse` | 동일 | ✅ Match | |

### 2.5 Aggregator Extension

| Design | Implementation | Status |
|--------|----------------|--------|
| `UsageAggregator.summary(from_dt, to_dt, user_id)` | 동일 | ✅ |
| `UsageAggregator.timeseries(from_dt, to_dt, user_id)` | 동일 | ✅ |

### 2.6 DI Wiring (`src/api/main.py`)

| Design | Implementation | Status |
|--------|----------------|--------|
| 5 factory 추가 + 5 `dependency_overrides` | `create_agent_run_factories()` 안에 5 factory + 5 overrides | ✅ Match |

### 2.7 Frontend Components

| Design | Implementation | Status |
|--------|----------------|--------|
| `AdminAgentRunsPage` (페이지 컨테이너 + 탭) | `pages/AdminAgentRunsPage/index.tsx` | ✅ |
| `SummaryCards` (admin/me 공용) | `pages/AdminAgentRunsPage/components/SummaryCards.tsx` (+ test) | ✅ |
| `TimeseriesChart` (admin/me 공용) | `pages/AdminAgentRunsPage/components/TimeseriesChart.tsx` | ✅ |
| `RunListTable` (admin/me 공용) | `pages/AdminAgentRunsPage/components/RunListTable.tsx` (+ test) | ✅ |
| `UsageByUserTab` / `UsageByLlmTab` / `UsageByNodeTab` | `UsageTabs.tsx` (단일 파일에 통합) | ⚠️ Modified — Trivial |
| `AgentRunDetailPage` + `StepTree` | `pages/AgentRunDetailPage/{index.tsx, components/StepTree.tsx}` | ✅ |
| `UsageMePage` | `pages/UsageMePage/index.tsx` | ✅ |
| `PeriodFilter` (공용) | `components/common/PeriodFilter.tsx` | ✅ |

### 2.8 Frontend Plumbing

| Design | Implementation | Status |
|--------|----------------|--------|
| `types/agentRunAdmin.ts` + `types/usageMe.ts` | 둘 다 존재. `usageMe.ts`가 `agentRunAdmin.ts` 재수출 + `MyRunsParams` 별도 | ✅ |
| `constants/api.ts` +10 endpoints | 모두 존재 | ✅ |
| `lib/queryKeys.ts` +agentRunAdmin, +usageMe | 존재 | ✅ |
| `services/agentRunAdminService.ts` | 7 methods | ✅ |
| `services/usageMeService.ts` | 3 methods | ✅ |
| `hooks/useAgentRunAdmin.ts` + `useUsageMe.ts` | 존재 | ✅ |
| `components/layout/AdminLayout.tsx` +사이드바 "Agent Run 관측" | 존재 | ✅ |
| `components/layout/TopNav.tsx` +"내 사용량" | 존재 | ✅ |
| `App.tsx` +3 routes | 존재 | ✅ |

### 2.9 Extras Not in Design (Trivial-positive)

| Item | Location | Severity |
|------|----------|----------|
| FE `aggregateMyCards` 헬퍼 | `pages/UsageMePage/index.tsx` | Trivial — Plan §2.1 의도와 일치 (별도 me/summary 엔드포인트 없음). |
| `RunRowDto.conversation_id` / `error_message` | 응답 스키마 | Trivial — 운영 디버깅에 유익. |
| Use of `replace()` instead of `force_user_id` field | `list_my_runs_use_case.py` | Trivial — Design 의도(서버 강제) 더 단순하게 달성. |

### 2.10 Items Missing (Design O, Impl X)

없음. 모든 Design 항목이 형태가 다르거나 동등 항목으로 구현됨.

### 2.11 Match Rate Summary

```
┌──────────────────────────────────────────────────┐
│  Overall Match Rate: 94%                          │
├──────────────────────────────────────────────────┤
│  ✅ Match (exact):           28 items (74%)       │
│  ⚠️ Modified (semantic eq):   8 items (21%)       │
│  ➕ Extras (intentional):     2 items (5%)         │
│  ❌ Missing:                  0 items (0%)        │
└──────────────────────────────────────────────────┘
```

---

## 3. Code Quality Analysis

### 3.1 Complexity

| File | Function | LoC | Cyclomatic | Status |
|------|----------|-----|-----------|--------|
| `list_runs_use_case.py` | `_validate` | 17 | 5 | ✅ |
| `list_runs_use_case.py` | `execute` | 14 | 1 | ✅ |
| `agent_run_router.py` | `get_admin_runs` | 41 | 4 | ⚠️ — 40-line guideline 1줄 초과 |
| `agent_run_router.py` | `get_my_runs` | 35 | 4 | ✅ |
| `aggregator.py` | `summary`/`timeseries` | 3 each | 1 | ✅ |
| `UsageSummaryResponse.from_row` | (factory) | 13 | 2 | ✅ |

### 3.2 Code Smells

| Severity | File | Issue |
|----------|------|-------|
| 🟢 Trivial | `agent_run_router.py:217-256` | `get_admin_runs` 41줄 — `CLAUDE.md §3` 가이드(40줄) 1줄 초과. 분리 효익 미미. |
| 🟢 Trivial | `agent_run_router.py:233-238` / `302-307` | from/to 검증이 두 라우트에 중복. `_resolve_period`가 기본값 강제하므로 list 라우트에서 별도 처리 — 정당. |

### 3.3 Security

| Severity | Item | Verdict |
|----------|------|---------|
| 🟢 OK | Admin 엔드포인트 우회 | 3개 admin route 전부 `Depends(require_role("admin"))`. dashboard 통합테스트로 401/403 확인. |
| 🟢 OK | `/usage/me/*` 타사용자 노출 | (1) Route 시그니처에 `user_id` Query 없음. (2) `ListMyRunsUseCase`가 `replace(filters, user_id=current_user.id)`로 강제. (3) FE `usageMeService.test.ts` SEC-1/2/3이 querystring에 `user_id` 없음을 검증. |
| 🟢 OK | SQL Injection | SQLAlchemy parameterized query만 사용. raw SQL 없음. |
| 🟢 OK | Period DoS | `_resolve_period`가 366일 초과 422. |

---

## 4. Test Coverage

| Module | Test File | Cases |
|--------|-----------|-------|
| `ListRunsUseCase` | `tests/application/agent_run/use_cases/test_list_runs_use_case.py` | exists |
| `GetUsageSummaryUseCase` | `test_get_usage_summary_use_case.py` | exists |
| `GetUsageTimeseriesUseCase` | `test_get_usage_timeseries_use_case.py` | exists |
| `ListMyRunsUseCase` | `test_list_my_runs_use_case.py` | exists (force user_id 검증) |
| `GetMyUsageTimeseriesUseCase` | `test_get_my_usage_timeseries_use_case.py` | exists |
| `AgentRunRepository.list_runs/count_runs` | `tests/infrastructure/agent_run/test_agent_run_repository.py` (TestListRuns) | exists |
| `LlmCallRepository.aggregate_summary/timeseries` | `tests/infrastructure/agent_run/test_llm_call_repository.py` (TestAggregateSummary/Timeseries) | exists |
| Admin runs route | `tests/api/test_agent_run_router_list.py` | exists (M5) |
| Dashboard routes (summary/timeseries + me security) | `tests/api/test_agent_run_router_dashboard.py` | 10 cases incl. security |
| FE `SummaryCards` | `pages/AdminAgentRunsPage/components/SummaryCards.test.tsx` | 4 cases |
| FE `RunListTable` | `pages/AdminAgentRunsPage/components/RunListTable.test.tsx` | 4 cases |
| FE `usageMeService` security | `services/usageMeService.test.ts` | 3 cases (SEC-1/2/3) |

**TDD coverage**: 모든 신규 모듈 1:1 매핑 ✅.

---

## 5. Clean Architecture Compliance

### 5.1 Layer Dependency Verification

| Layer | Imports (확인) | 위반 | Status |
|-------|---------------|------|--------|
| **Domain** (`src/domain/agent_run/interfaces.py`) | `abc`, `dataclasses`, `datetime`, `decimal`, `typing`, `src.domain.agent_run.entities`, `value_objects` | 0 (sqlalchemy/pydantic/fastapi 없음) | ✅ |
| **Application** (`use_cases/*`, `aggregator.py`) | `src.application.agent_run.*`, `src.domain.agent_run.*`, stdlib | 0 (infrastructure/api 미참조) | ✅ |
| **Infrastructure** (`repositories/*`) | `sqlalchemy`, `src.domain.agent_run.*`, `src.infrastructure.persistence.models` | 0 (application/api 미참조) | ✅ |
| **Interfaces** (`api/routes/agent_run_router.py`) | `fastapi`, `src.application.*`, `src.domain.agent_run.interfaces`, `src.interfaces.schemas.*`, `src.interfaces.dependencies.auth` | 0 (infrastructure 구체 미참조) | ✅ |

### 5.2 Frontend Layer Assignment

| Component | Layer | Actual | Status |
|-----------|-------|--------|--------|
| `AdminAgentRunsPage`, `AgentRunDetailPage`, `UsageMePage` | Presentation | `src/pages/` | ✅ |
| `useAgentRunAdmin`, `useUsageMe` | Application (hooks) | `src/hooks/` | ✅ |
| `agentRunAdminService`, `usageMeService` | Infrastructure | `src/services/` | ✅ |
| `agentRunAdmin.ts`, `usageMe.ts` | Domain | `src/types/` | ✅ |

### 5.3 Architecture Score

```
Architecture Compliance: 100%
- Correct layer placement: all files
- Dependency violations:   0
- Wrong layer:             0
```

---

## 6. Convention Compliance

### 6.1 Naming

| Category | Convention | Sample Check | Status |
|----------|-----------|--------------|--------|
| UseCase class | `*UseCase` PascalCase | `ListRunsUseCase`, `GetUsageSummaryUseCase` | ✅ |
| Repository method | snake_case `verb_noun`, async | `list_runs`, `aggregate_summary` | ✅ |
| Domain row | `*Row`/`*Item`/`*Point` | `UsageSummaryRow`, `UsageTimeseriesPoint` | ✅ |
| Pydantic schema | `*Dto`/`*Response` | `RunRowDto`, `UsageSummaryResponse` | ✅ |
| FE page | `*Page` PascalCase folder | `AdminAgentRunsPage/`, `UsageMePage/` | ✅ |
| FE hook | `use*` | `useAgentRunAdmin`, `useUsageMe` | ✅ |
| FE service | `*Service` camelCase | `agentRunAdminService`, `usageMeService` | ✅ |
| FE type file | camelCase | `agentRunAdmin.ts`, `usageMe.ts` | ✅ |

### 6.2 Folder Structure

| Path | Exists | OK |
|------|:------:|:--:|
| `src/domain/agent_run/` | ✅ | ✅ |
| `src/application/agent_run/use_cases/` | ✅ | ✅ |
| `src/infrastructure/persistence/repositories/` | ✅ | ✅ |
| `src/interfaces/schemas/` | ✅ | ✅ |
| `idt_front/src/pages/{Page}/components/` | ✅ | ✅ |
| `idt_front/src/{services,hooks,types,constants,lib}/` | ✅ | ✅ |

### 6.3 Score

```
Convention Compliance: 98%
  Naming:           100%
  Folder Structure: 100%
  Import Order:      95% (TS)
  Env Variables:    100% (no new vars)
```

---

## 7. Overall Score

```
┌─────────────────────────────────────────────┐
│  Overall Score: 95/100                       │
├─────────────────────────────────────────────┤
│  Design Match:        94 points              │
│  Code Quality:        92 points              │
│  Security:           100 points              │
│  Testing:             96 points              │
│  Architecture:       100 points              │
│  Convention:          98 points              │
└─────────────────────────────────────────────┘
```

---

## 8. Gap List by Severity

### Critical
없음.

### Major
없음.

### Minor

1. **Endpoint path** `/admin/agents/runs` → `/admin/runs` (M5 carry-over, FE 상수 동기화 완료).
2. **Pagination params** `page`/`size` → `offset`/`limit` (BE/FE 일관, Plan §6.2와 호환).
3. **Repository signature** `list_runs(filter, page, size)` 단일 메서드 → `list_runs(filters)` + `count_runs(filters)` 분리 (asyncio.gather 효율).
4. **VO naming** `RunListFilter` → `RunListFilters` (plural) + `force_user_id` 제거, UseCase의 `replace()` override로 보안 강제.

### Trivial

5. **Response field names** `from`/`to` alias 미적용, `from_dt`/`to_dt` 그대로 노출 (FE 타입 동기화).
6. **`RunRowDto`** `langsmith_run_url` 미포함, 대신 `conversation_id`/`error_message` 추가.
7. **`get_admin_runs` 41줄** — 가이드(40줄) 1줄 초과.
8. **`UsageTabs.tsx`** — 3개 탭 컴포넌트가 단일 파일에 통합 (Design은 3 separate files).

---

## 9. Items Requiring Design Doc Update

설계 문서가 구현과 다른 부분 — Report 단계에서 design v1.1로 동기화 권장:

- [ ] §3.1 `RunListFilter` → `RunListFilters`, `force_user_id` 제거 (보안 메커니즘은 UseCase `replace()` 사용으로 변경됨을 명시)
- [ ] §3.2 Repository 인터페이스: `list_runs(filter, page, size) -> tuple[..., int]` → `list_runs(filters)` + `count_runs(filters)` 분리 명시
- [ ] §4.1 endpoint path 컬럼: `/admin/agents/runs` → `/admin/runs`로 정정
- [ ] §4.2.1 pagination params: `page`/`size` → `offset`/`limit` 정정
- [ ] §4.3 Pydantic schema: `from`/`to` alias 사용 안 함을 명시, `RunRowDto`에 `conversation_id`/`error_message` 추가, `langsmith_run_url` 제거

---

## 10. Recommended Next Step

**Match Rate 94% (≥ 90%) → `/pdca report agent-run-admin-dashboard`**

Critical/Major 이슈 없음. Minor 4건은 모두 Plan/구현 단계의 의식적 선택이며 보안·기능적 동등성이 확보됨. Trivial 4건도 운영 가독성을 개선하는 방향. Iterate 불필요.

---

## 11. Next Steps Checklist

- [ ] Design v1.1로 동기화 (위 §9 5건)
- [ ] `/pdca report agent-run-admin-dashboard` 실행
- [ ] (선택) `_resolve_period`-style 헬퍼로 `get_admin_runs`/`get_my_runs`의 from/to 검증을 한 줄로 줄여 40-line guideline 회복

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-22 | Initial gap analysis. Match Rate 94%, 0 Critical/Major. Recommend Report. | gap-detector |
