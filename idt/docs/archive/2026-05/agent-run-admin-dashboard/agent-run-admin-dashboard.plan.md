---
template: plan
version: 1.2
feature: agent-run-admin-dashboard
date: 2026-05-21
author: AI Assistant
project: sangplusbot (idt + idt_front)
status: Draft
---

# agent-run-admin-dashboard Planning Document

> **Summary**: Agent Run 관측성(M1–M4)이 적재한 5개 테이블 + 6개 read API 위에 **관리자 통합 대시보드**와 **사용자 My Usage 페이지**를 풀스택으로 구현. Run 목록·필터·페이지네이션·상세 트리·시계열 차트를 한 곳에서 제공.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: AI Assistant
> **Date**: 2026-05-21
> **Status**: Draft
> **Predecessor**: agent-run-observability-m4 (archived 2026-05-21, 98%)
> **Sibling Reference**: admin-ragas-dashboard (archived 2026-05-18)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | M1–M4가 `ai_run / ai_run_step / ai_tool_call / ai_llm_call / ai_retrieval_source` 5개 테이블에 풍부한 관측 데이터를 축적하고 6개 read API(`/agents/runs/{id}`, `/admin/usage/*`, `/usage/me`)도 노출했지만, 이를 **시각적으로 한눈에 보는 화면이 없다**. 관리자는 매번 SQL로 확인하고, 사용자는 본인 비용·토큰 사용량을 볼 수 없다. |
| **Solution** | (a) Admin 전용 통합 대시보드 `/admin/agent-runs`: 통계 카드 + 시계열 라인/바 차트 + 4개 탭(사용자별·LLM별·노드별·Run 목록) + Run 상세 드릴다운. (b) 사용자용 `/usage` 페이지: 본인 토큰/비용 카드 + 최근 30일 시계열 + 본인 Run 목록. (c) 부족한 백엔드 엔드포인트 3종(run list with filter+pagination, summary cards, timeseries) 신설. |
| **Function/UX Effect** | 관리자는 1초 안에 "오늘 LLM 비용 / 가장 많이 쓴 사용자 / 비싼 노드 / 실패한 run"을 식별하고, Run 상세에서 step→tool→llm_call→retrieval 트리를 드릴다운하여 비용 폭증·실패 원인을 추적. 일반 사용자는 본인 사용량을 자율적으로 모니터링. |
| **Core Value** | LLM 비용·품질 거버넌스의 운영 도구화. 데이터가 있어도 보이지 않으면 의사결정에 못 쓴다 — 이번 PDCA는 그 격차를 풀스택으로 메워 *관측성 → 거버넌스*로 전환한다. |

---

## 1. Overview

### 1.1 Purpose

`agent-run-observability` M1–M4 마일스톤이 누적한 데이터·API를 **사람이 쓰는 화면**으로 마무리한다. 백엔드는 이미 90%, 이번 PDCA는 (1) UI 풀-구현 + (2) UI가 필요로 하는 보조 엔드포인트 3종 추가 + (3) admin/user 역할별 접근 통제.

### 1.2 Background

- **선행 작업** (전부 archived):
  - M1 (`agent-run-observability`, 96%): 5개 테이블·로깅 인프라
  - M2 (`agent-run-observability-m2`, 98%): step/tool 추적
  - M3 (`agent-run-observability-m3`, 99%): node 집계
  - M4 (`agent-run-observability-m4`, 98%): retrieval wiring + 5 read API + pricing PATCH
- **현재 노출 API** (M4):
  | Method | Path | 권한 | 비고 |
  |--------|------|------|------|
  | GET | `/api/v1/agents/runs/{run_id}` | user (self) / admin (all) | Run 상세 트리 (이미 완성) |
  | GET | `/api/v1/admin/usage/users` | admin | 사용자별 집계 |
  | GET | `/api/v1/admin/usage/llm-models` | admin | LLM 모델별 집계 |
  | GET | `/api/v1/admin/usage/by-node` | admin | 노드별 집계 |
  | GET | `/api/v1/usage/me` | user (self) | 본인 LLM 사용량 |
  | PATCH | `/api/v1/llm-models/{id}/pricing` | admin | (M4) 가격 수정 |
- **부족한 부분**:
  - Run **목록**(필터/페이지네이션) 엔드포인트가 없음
  - 통계 카드용 단일 요약 엔드포인트 없음 (총 비용/총 토큰/run 수/성공률)
  - 시계열(일자별 추이) 엔드포인트 없음
  - 사용자 자신의 Run 목록 조회 경로 없음
  - 모든 화면이 부재 (백엔드 only)

### 1.3 Related Documents

- M4 Report: `docs/archive/2026-05/agent-run-observability-m4/agent-run-observability-m4.report.md`
- M1 Plan (스키마 정의): `docs/archive/2026-05/agent-run-observability/`
- 패턴 레퍼런스: `docs/archive/2026-05/admin-ragas-dashboard/` (구조·라우팅·서비스/타입 분리)
- Backend 라우터: `src/api/routes/agent_run_router.py`
- Frontend 레이아웃: `idt_front/src/components/layout/AdminLayout.tsx`
- DB 스키마: `db/migration/V021__create_agent_run_tables.sql`

---

## 2. Scope

### 2.1 In Scope

#### Backend (idt/)

- [ ] **신규 엔드포인트 3종** (전부 `/api/v1` 하위):
  - `GET /api/v1/admin/agents/runs` — Run 목록 조회 (admin 전용, 필터·페이지네이션)
  - `GET /api/v1/admin/usage/summary` — 통계 카드용 단일 요약 (admin)
  - `GET /api/v1/admin/usage/timeseries` — 일자별 비용·토큰·run 수 시계열 (admin)
- [ ] **사용자용 신규 엔드포인트 2종**:
  - `GET /api/v1/usage/me/runs` — 본인 Run 목록 (필터·페이지네이션)
  - `GET /api/v1/usage/me/timeseries` — 본인 일자별 시계열
- [ ] **새 UseCase 5개** (application layer, 단일 책임):
  - `ListRunsUseCase` — admin 전용, 필터 파라미터 지원
  - `GetUsageSummaryUseCase` — 카드 4종(total_cost, total_tokens, run_count, success_rate)
  - `GetUsageTimeseriesUseCase` — daily bucket aggregation
  - `ListMyRunsUseCase` — user 자기 자신 필터 강제
  - `GetMyUsageTimeseriesUseCase` — user 자기 자신 시계열
- [ ] **Repository 메서드 확장** (`AiRunRepository`, `LlmCallRepository`):
  - `list_runs(filters, page, size) -> Page[Run]`
  - `aggregate_summary(from_dt, to_dt, user_id?) -> SummaryRow`
  - `aggregate_timeseries(from_dt, to_dt, bucket='day', user_id?) -> List[TimeseriesRow]`
- [ ] **응답 스키마 추가** (`agent_run_response.py`):
  - `RunListItemDto`, `RunListResponse` (cursor 또는 offset)
  - `UsageSummaryResponse`
  - `UsageTimeseriesPoint`, `UsageTimeseriesResponse`
- [ ] **TDD**: 5개 UseCase + 3개 admin route + 2개 me route 테스트 선작성 (Red → Green)

#### Frontend (idt_front/)

- [ ] **Admin 통합 대시보드 페이지** `/admin/agent-runs` (`AdminAgentRunsPage.tsx`):
  - 기간 필터 (오늘/7일/30일/커스텀)
  - 통계 카드 4개 (총 비용·총 토큰·Run 수·성공률)
  - 시계열 차트 1개 (Line: 일자별 비용 + Bar: 일자별 run 수, recharts)
  - 탭 4개: 사용자별 / LLM별 / 노드별 / Run 목록
  - Run 목록 테이블: 필터(user/agent/status), 페이지네이션, 행 클릭 시 상세 드릴다운
- [ ] **Run 상세 모달 또는 별도 페이지** (`AgentRunDetailModal.tsx` 또는 `/admin/agent-runs/:runId`):
  - Run 헤더 (status/duration/cost/tokens/agent/user)
  - Steps 트리 (StepDto → ToolCalls → LlmCalls + Retrievals)
  - LangSmith trace URL 링크
- [ ] **사용자 My Usage 페이지** `/usage` (`UsageMePage.tsx`):
  - 본인 카드 4개 + 시계열 차트 + 본인 Run 목록 (간이)
  - 일반 사용자 권한으로 접근 가능 (admin/department/etc. 무관)
- [ ] **AdminLayout 사이드바**에 메뉴 1개 추가: `Agent Run 관측성` (icon: chart)
- [ ] **TopNav/계정 메뉴**에 `내 사용량` 링크 추가
- [ ] **타입 모듈** `src/types/agentRunAdmin.ts` 신설 (백엔드 응답 1:1 매핑)
- [ ] **서비스 모듈** `src/services/agentRunAdminService.ts`, `usageMeService.ts` 신설
- [ ] **TanStack Query 훅** `src/hooks/useAgentRunAdmin.ts`, `useUsageMe.ts` 신설 (queryKeys 등록)
- [ ] **constants/api.ts**에 신규 엔드포인트 상수 추가 (`ADMIN_AGENT_RUNS`, `ADMIN_USAGE_SUMMARY`, etc.)

#### Cross-cutting

- [ ] **권한 통제**: admin 엔드포인트 = `require_role(UserRole.ADMIN)`, me 엔드포인트 = `get_current_user`만, run 상세는 self/admin 분기 (M4 기존 로직 유지)
- [ ] **API 계약 동기화**: 백엔드 스키마 → 프론트 타입 1:1 동기화 (CLAUDE.md §4-1 준수)
- [ ] **로깅**: 신규 UseCase·Route는 LOG-001 준수, 새 `verify-logging` skill로 검증

### 2.2 Out of Scope

- **DB 스키마 변경 금지** (M1–M4가 정의한 5개 테이블만 사용. 마이그레이션 0건)
- **실시간 스트리밍·WebSocket 푸시** (이번 PDCA는 polling 기반 read-only)
- **Run 재실행·취소·삭제 기능** (M5/M6 별도 PDCA)
- **Tavily 등 외부 retrieval wiring** (M4 carry-over, 별도 PDCA)
- **알람·임계치(threshold) 설정 UI** (대시보드만, 알람은 별도)
- **CSV·Excel 내보내기** (필요 시 v1.1)
- **사용자 비용 한도(quota) 적용** (관측만, 통제는 별도)
- **모바일 반응형 최적화** (PC 우선, 모바일은 best-effort)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Admin이 `/admin/agent-runs` 진입 시 4개 통계 카드(총 비용/토큰/run 수/성공률)가 1초 내 표시 | High | Pending |
| FR-02 | Admin이 기간(오늘/7d/30d/커스텀)을 바꾸면 카드·차트·탭 데이터가 모두 동기화 | High | Pending |
| FR-03 | Admin이 시계열 차트에서 일자별 비용 추이를 라인으로, run 수를 바로 동시 확인 | High | Pending |
| FR-04 | Admin이 Run 목록 탭에서 user/agent/status 필터 + 페이지네이션으로 검색 | High | Pending |
| FR-05 | Run 행 클릭 시 step → tool_call → llm_call → retrieval 트리가 상세 화면에 표시 | High | Pending |
| FR-06 | 일반 사용자가 `/usage`에서 본인 토큰/비용/run 수를 카드로 확인 | High | Pending |
| FR-07 | 사용자는 본인 외 다른 사용자의 데이터에 절대 접근 불가 (403) | High | Pending |
| FR-08 | 사용자/LLM/노드별 집계 탭이 모두 admin-ragas-dashboard와 동일한 룩앤필 (테이블 + 정렬) | Medium | Pending |
| FR-09 | 빈 데이터 상태(0 run) 시 빈 상태 일러스트/문구 표시 | Medium | Pending |
| FR-10 | LangSmith trace URL이 있는 run은 외부 링크 버튼 노출 | Medium | Pending |
| FR-11 | Admin 사이드바 / 사용자 TopNav에 진입 메뉴 추가 | Medium | Pending |
| FR-12 | 모든 신규 API 응답에 `from`/`to` echo (M4 컨벤션 유지) | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | Summary 카드 API < 300ms (30일, 1만 run 기준) | 인덱스 활용 + EXPLAIN 확인 |
| Performance | Timeseries API < 500ms (30일 daily bucket) | `GROUP BY DATE(started_at)` + `idx_run_started_at` |
| Performance | Run 목록 페이지네이션 1페이지 < 400ms | offset-pagination + 기존 인덱스 (`idx_run_user_started`, `idx_run_status`) |
| Security | admin 엔드포인트는 `require_role(ADMIN)` 통과해야만 호출 | pytest로 401/403 검증 |
| Security | `/usage/me/*` 는 `user_id = current_user.id` 강제 (서버측 필터) | UseCase 인자에 user_id 명시, 테스트로 보장 |
| Architecture | DDD 레이어 의존성 규칙 준수 (`verify-architecture` 통과) | skill 실행 |
| Logging | LOG-001 준수 (`verify-logging` 통과) | skill 실행 |
| TDD | 모든 신규 모듈에 테스트 선존재 (`verify-tdd` 통과) | skill 실행 |
| Accessibility | 키보드 탭 이동·테이블 스크린리더 가능 | manual check |
| API Contract | 백엔드 schema 변경 시 프론트 type 동기화 (`api-contract` skill) | skill 실행 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-12 전부 구현
- [ ] 신규 UseCase 5개 + Route 5개 단위 테스트 작성 및 통과
- [ ] 프론트 컴포넌트 핵심 단위 테스트 (Vitest + RTL + MSW) 작성
- [ ] M4의 기존 6개 API에 회귀 없음 (전체 테스트 PASS)
- [ ] Gap Analysis Match Rate ≥ 90%
- [ ] 4개 verify-* skill (architecture / logging / tdd / api-contract) 전부 통과

### 4.2 Quality Criteria

- [ ] 백엔드 신규 함수 단위 ≤ 40줄, 중첩 ≤ 2단 (CLAUDE.md §3)
- [ ] 프론트 컴포넌트 단일 책임 (페이지 ≠ 비즈니스 로직, 훅에 분리)
- [ ] 신규 코드 100% 타입 명시 (pydantic / TypeScript strict)
- [ ] DB 마이그레이션 0건 (이번 PDCA의 강제 조건)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 대용량 ai_llm_call(>10만 row) 시 timeseries 쿼리 지연 | High | Medium | `started_at` 인덱스 + 1일 단위 GROUP BY + Plan §3.2에 성능 기준 명시. 필요 시 application-level cache (5분 TTL) |
| Run 목록 필터 조합 폭발 → 인덱스 미스 | Medium | Medium | 1차는 `user_id + status + started_at` 인덱스로 커버. 측정 후 부족하면 covering index 추가 (마이그레이션 1건 허용 — 별도 결재) |
| `/usage/me` 권한 누락으로 타사용자 데이터 노출 | Critical | Low | UseCase 시그니처에 `user_id: str` 필수화 + Route에서 `current_user.id` 강제 주입 + 보안 테스트 케이스 명시 |
| 프론트 차트 라이브러리 신규 도입(번들 사이즈) | Low | Medium | admin-ragas-dashboard에서 이미 사용 중인 차트 라이브러리 재사용 (확인 필요, 없으면 recharts 채택) |
| Step/Tool/LLM_call 트리 데이터가 깊어 렌더링 느림 | Medium | Low | RunDetail은 이미 M4에서 완성된 응답 구조 그대로 사용. virtual scroll 불필요(평균 step < 20) |
| Admin/User 역할 분기 누락 → 사용자에게 admin 메뉴 노출 | Medium | Low | `AdminRoute` 래퍼 재사용 (`AdminUsersPage`와 동일 패턴), 사이드바도 AdminLayout 안에만 추가 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| Starter | 단순 정적 사이트 | 포트폴리오 | ☐ |
| Dynamic | feature 모듈, BaaS | 일반 풀스택 | ☐ |
| **Enterprise** | **Thin DDD 4-layer (domain/application/infrastructure/interfaces)** | **현재 프로젝트** | **☑** |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Backend 패턴 | Service / UseCase | **UseCase per endpoint** | 기존 M4 컨벤션 100% 유지 (`Get*UseCase` 단일 책임) |
| Run List 페이지네이션 | offset / cursor | **offset (page+size)** | admin-ragas-dashboard와 동일. 1만 row까지 충분, UX 단순 |
| Timeseries bucket | client-side / SQL group | **SQL `GROUP BY DATE(started_at)`** | DB 인덱스 활용, 네트워크 페이로드 최소화 |
| 차트 라이브러리 | recharts / chart.js / D3 | **recharts** | React 친화, admin-ragas와 동일 컨벤션, 트리 셰이킹 |
| Run 상세 표시 방식 | Modal / Page | **Page (`/admin/agent-runs/:runId`)** | 딥링크 공유·뒤로가기 UX, 트리가 깊어 모달이 답답 |
| State 관리 | TanStack Query / Zustand | **TanStack Query (서버 상태) + Zustand (UI 필터)** | 기존 프로젝트 컨벤션 동일 (`idt_front/CLAUDE.md` §) |
| Form 처리 | RHF / native | **native (필터만, 폼 없음)** | 입력 폼이 없고 select/datepicker만 |

### 6.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

신규 파일 구조 (Backend):

  src/
   ├─ domain/agent_run/
   │   └─ interfaces.py                 [M] +RunListFilter VO, +SummaryRow, +TimeseriesRow
   ├─ application/agent_run/
   │   ├─ use_cases/
   │   │   ├─ list_runs_use_case.py          [N]
   │   │   ├─ get_usage_summary_use_case.py  [N]
   │   │   ├─ get_usage_timeseries_use_case.py [N]
   │   │   ├─ list_my_runs_use_case.py       [N]
   │   │   └─ get_my_usage_timeseries_use_case.py [N]
   │   └─ aggregator.py                  [M] +summary, +timeseries 메서드
   ├─ infrastructure/persistence/repositories/
   │   ├─ ai_run_repository.py           [M] +list_runs, +aggregate_summary
   │   └─ llm_call_repository.py         [M] +aggregate_timeseries
   ├─ interfaces/schemas/
   │   └─ agent_run_response.py          [M] +RunListResponse, +UsageSummary, +UsageTimeseries
   └─ api/routes/
       └─ agent_run_router.py            [M] +5 endpoints

신규 파일 구조 (Frontend):

  idt_front/src/
   ├─ pages/
   │   ├─ AdminAgentRunsPage/                [N]
   │   │   ├─ index.tsx                       (페이지 컨테이너 + 탭 라우팅)
   │   │   ├─ components/
   │   │   │   ├─ SummaryCards.tsx
   │   │   │   ├─ TimeseriesChart.tsx
   │   │   │   ├─ RunListTable.tsx
   │   │   │   ├─ UsageByUserTab.tsx
   │   │   │   ├─ UsageByLlmTab.tsx
   │   │   │   └─ UsageByNodeTab.tsx
   │   │   └─ store.ts                        (Zustand: 필터 상태)
   │   ├─ AgentRunDetailPage/                [N]
   │   │   ├─ index.tsx
   │   │   └─ components/StepTree.tsx
   │   └─ UsageMePage/                       [N]
   │       └─ index.tsx
   ├─ services/
   │   ├─ agentRunAdminService.ts            [N]
   │   └─ usageMeService.ts                  [N]
   ├─ hooks/
   │   ├─ useAgentRunAdmin.ts                [N]
   │   └─ useUsageMe.ts                      [N]
   ├─ types/
   │   ├─ agentRunAdmin.ts                   [N]
   │   └─ usageMe.ts                         [N]
   ├─ constants/api.ts                       [M] +ADMIN_AGENT_RUNS, +ADMIN_USAGE_SUMMARY, ...
   ├─ lib/queryKeys.ts                       [M] +agentRunAdmin, +usageMe
   ├─ components/layout/AdminLayout.tsx      [M] +사이드바 항목
   ├─ components/layout/TopNav.tsx           [M] +"내 사용량" 링크
   └─ App.tsx                                [M] +3 routes

[N] = New, [M] = Modified
```

### 6.4 Endpoint Inventory (전·후 비교)

| Path | Before | After | Notes |
|------|:------:|:-----:|------|
| `GET /api/v1/agents/runs/{run_id}` | ✅ | ✅ | M4 그대로 사용 |
| `GET /api/v1/admin/usage/users` | ✅ | ✅ | 그대로 사용 (대시보드 탭 1) |
| `GET /api/v1/admin/usage/llm-models` | ✅ | ✅ | 그대로 사용 (대시보드 탭 2) |
| `GET /api/v1/admin/usage/by-node` | ✅ | ✅ | 그대로 사용 (대시보드 탭 3) |
| `GET /api/v1/usage/me` | ✅ | ✅ | UsageMePage 카드 |
| `GET /api/v1/admin/agents/runs` | ❌ | ✅ | **신규** — Run 목록 (탭 4) |
| `GET /api/v1/admin/usage/summary` | ❌ | ✅ | **신규** — 카드 4개 |
| `GET /api/v1/admin/usage/timeseries` | ❌ | ✅ | **신규** — 시계열 |
| `GET /api/v1/usage/me/runs` | ❌ | ✅ | **신규** — 본인 Run 목록 |
| `GET /api/v1/usage/me/timeseries` | ❌ | ✅ | **신규** — 본인 시계열 |

총: 신규 5건 / 변경 0건 / 삭제 0건.

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md`(루트 + idt + idt_front) 컨벤션 정의됨
- [x] `docs/rules/db-session.md`, `logging.md`, `testing.md` 존재
- [x] ESLint + Prettier + TypeScript strict 설정됨
- [x] pytest + Vitest + RTL + MSW 설정됨
- [x] verify-architecture / verify-logging / verify-tdd / api-contract skill 존재

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Naming** | exists | UseCase = `*UseCase` 접미, 페이지 = `Admin*Page` / `UsageMePage` | High |
| **Folder structure** | exists | 페이지는 폴더 + index.tsx + components/ 분리 (admin-ragas 패턴) | High |
| **Import order** | exists (eslint) | 표준/외부/내부(@/) 순 | Medium |
| **Environment variables** | exists | 신규 없음 | — |
| **Error handling** | exists | 401/403/404 → toast + ErrorBoundary, 500 → fallback | Medium |
| **TanStack Query keys** | exists | `['agentRunAdmin', ...]`, `['usageMe', ...]` | High |

### 7.3 Environment Variables Needed

신규 환경변수 없음. 기존 `VITE_API_BASE_URL` (FE), `MYSQL_*` (BE) 그대로 사용.

### 7.4 Pipeline Integration

이번 PDCA는 9-phase 파이프라인을 따로 거치지 않는다. Phase 1 (Schema)·Phase 2 (Convention)는 선행 PDCA에서 확정. 본 작업은 PDCA 단일 사이클 (Plan → Design → Do → Check → Report → Archive).

---

## 8. Implementation Order (참고)

설계 문서에서 상세화하지만 큰 흐름은 다음과 같다:

1. **Backend Phase A** — 신규 admin 3 endpoints (테스트 우선)
   - `ListRunsUseCase` → `GetUsageSummaryUseCase` → `GetUsageTimeseriesUseCase`
2. **Backend Phase B** — 신규 me 2 endpoints
   - `ListMyRunsUseCase` → `GetMyUsageTimeseriesUseCase`
3. **Frontend Phase A** — 타입·서비스·훅 골격 (백엔드 응답에 맞춰)
4. **Frontend Phase B** — `AdminAgentRunsPage` 구현 (카드 → 차트 → 탭 4개)
5. **Frontend Phase C** — `AgentRunDetailPage` 구현 (M4 응답 그대로)
6. **Frontend Phase D** — `UsageMePage` 구현 + TopNav 링크
7. **검증** — verify-architecture / verify-logging / verify-tdd / api-contract / gap-detector

---

## 9. Next Steps

1. [ ] `/pdca design agent-run-admin-dashboard` — 설계 문서 작성 (응답 JSON 형상, 쿼리 SQL, 컴포넌트 props)
2. [ ] 설계 리뷰 후 `/pdca do agent-run-admin-dashboard` — TDD 사이클 시작 (Backend Phase A부터)
3. [ ] 구현 완료 후 `/pdca analyze` — gap-detector로 설계-구현 일치도 측정

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-21 | Initial draft. M4 후속으로 풀스택 dashboard + my-usage 정의 | AI Assistant |
