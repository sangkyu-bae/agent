# agent-run-observability (M1) Completion Report

> **Summary**: Agent Run 운영 관측성 M1 마일스톤 완료 (96% 설계 일치, ≥90% 임계 통과)
>
> **Feature**: Agent Run 운영 관측성 (Run/Step/Tool/Retrieval/LlmCall 영속화)
> **Task ID**: AGENT-OBS-001
> **Project**: sangplusbot (idt)
> **Scope**: M1 only — Run lifecycle + `ai_llm_call` + LLM pricing + UsageCallback + LangSmith trace
> **Version**: 1.0
> **Planning Date**: 2026-05-18
> **Completion Date**: 2026-05-19
> **Match Rate**: 96%
> **Status**: ✅ COMPLETED (M1)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | Agent Run 운영 관측성 (M1) |
| Task ID | AGENT-OBS-001 |
| Start Date | 2026-05-18 |
| End Date | 2026-05-19 |
| Duration | 2 days (Plan → Design → Do → Check) |
| Milestones Done | M1 (Run + LlmCall + Pricing + UsageCallback + LangSmith) |
| Milestones Pending | M2 (Tool Call invocation), M3 (Run Step), M4 (Retrieval + Usage API) |
| Final Match Rate | **96%** (≥90% threshold met) |

### 1.2 Results Summary

```
┌───────────────────────────────────────────────────────────┐
│  M1 Completion Rate: 96%                                  │
├───────────────────────────────────────────────────────────┤
│  ✅ Migrations:       2 / 2  (V021 + V022)               │
│  ✅ Domain modules:   4 / 4  (entities/VOs/policies/IF)  │
│  ✅ Application:      6 / 6  (tracker/cost/ctx/agg/...)  │
│  ✅ Infrastructure:   4 / 4  (ORM + 2 repos + callback)  │
│  ✅ Test files:      13 / 13 (118/118 agent_run tests)   │
│  ✅ UseCase wiring:   RunAgentUseCase fully integrated   │
│  ✅ DI wiring:        main.py singletons + factories     │
│  🟠 Major gap:        1 (PATCH /llm-models/{id}/pricing) │
│  🟡 Minor gaps:       2 (status enum doc, DTO location)  │
│  ✅ Free wins:        M2/M3/M4 data layer pre-built      │
└───────────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 사용자 질문 1회의 응답에 supervisor/worker/summarizer/내부 툴 LLM이 여러 번 호출되지만 우리 DB는 `conversation_message` 텍스트만 갖고 있어 (1) 사용자별 토큰·비용 추적 불가, (2) LLM별 비용 비교 불가, (3) RAG 근거 chunk 미저장, (4) LangSmith 외부 SaaS 의존. 감사·과금·디버깅의 단일 진실 공급원이 부재. |
| **Solution** | 5개 신규 테이블(`ai_run`/`ai_run_step`/`ai_tool_call`/`ai_retrieval_source`/`ai_llm_call`) + `llm_model` 가격 컬럼. **LangChain `UsageCallback` 단일 인터셉트**로 supervisor/worker/summarizer/tool 내부 LLM을 일관 수집 — 노드 코드에 trace 로직을 흩뿌리지 않는다. 가격 변동 보존을 위해 호출 시점 가격 스냅샷을 `ai_llm_call`에 저장. 집계 성능을 위해 `user_id`/`agent_id`/`model_name`/`provider`를 `ai_llm_call`에 비정규화. |
| **Function / UX Effect** | **데이터 레이어 100% 완성** — (1) Run 단위 상태/소요시간/토큰/비용 영속화, (2) **사용자×LLM 매트릭스 SQL 1줄 집계** (`SELECT user_id, model_name, SUM(total_tokens) FROM ai_llm_call ...`), (3) `langsmith_trace_id`/`langsmith_run_url` 저장으로 어드민→LangSmith 점프 가능, (4) `RunAgentResponse.run_id` 노출로 프론트엔드 "이 답변의 trace 보기" 준비, (5) 5분 TTL 가격 캐시로 비용 계산 성능 확보. 118개 테스트 100% 통과. |
| **Core Value** | **운영 책임이 LangSmith에서 우리 DB로 이전 완료**. SaaS화·부서 차지백·이상 호출 탐지의 토대인 "**사용자별·LLM별 토큰/비용 원장**"이 SQL 단일 테이블 스캔으로 동작. M1만으로 즉시 가치 발생하며, M2/M3/M4 데이터 레이어가 무상으로 함께 구축됨 — 후속 마일스톤은 "wiring + API 노출"만 남음. |

---

## 2. Related Documents

| Phase | Document | Status | Match Rate |
|-------|----------|--------|-----------|
| Plan | [agent-run-observability.plan.md](../../01-plan/features/agent-run-observability.plan.md) | ✅ Finalized | — |
| Design | [agent-run-observability.design.md](../../02-design/features/agent-run-observability.design.md) | ✅ Finalized | — |
| Check | [agent-run-observability.analysis.md](../../03-analysis/agent-run-observability.analysis.md) | ✅ Complete | 96% |
| Act | Current document | ✅ Complete | — |

---

## 3. Completed Items (M1)

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | V021 migration — 5 tables (`ai_run`/`ai_run_step`/`ai_tool_call`/`ai_retrieval_source`/`ai_llm_call`) | ✅ Complete | All FKs + 16 indexes per design; `user_message_id` FK fixed to INT (MySQL 3780) |
| FR-02 | V022 migration — `llm_model` pricing columns + seed for gpt-4o / gpt-4o-mini / claude-3.5-sonnet | ✅ Complete | DECIMAL(10,6) input/output 1k USD + `pricing_updated_at` |
| FR-03 | Domain layer — `AgentRun`/`AgentRunStep`/`ToolCall`/`RetrievalSource`/`LlmCall` entities | ✅ Complete | 5 dataclasses + 6 VOs + 2 policies |
| FR-04 | `RunStatusTransitionPolicy` (RUNNING → SUCCESS/FAILED/CANCELLED) | ✅ Complete | Validated by `test_policies.py` |
| FR-05 | `CostCalculationPolicy` (Decimal quantize 6dp, price-snapshot semantics) | ✅ Complete | `policies.py:35-58` |
| FR-06 | Repository interfaces (`AgentRunRepositoryInterface` + `LlmCallRepositoryInterface`) | ✅ Complete | Adds `apply_completion_totals` + `mark_failed` beyond design |
| FR-07 | ORM models for 5 tables | ✅ Complete | `models/agent_run.py` |
| FR-08 | `AgentRunRepository.apply_completion_totals` — single SUM UPDATE with idempotency guard | ✅ Complete | `WHERE status='RUNNING'` makes retryable |
| FR-09 | `LlmCallRepository` 3 aggregate queries (by_user / by_llm_model / for_user) | ✅ Complete | `func.sum/count` based |
| FR-10 | `SessionScopedLlmModelRepository` — singleton-friendly DB adapter | ✅ Complete | Solves long-lived singleton DI |
| FR-11 | `RunTracker` — `start_run` (immediate commit, raise on fail) | ✅ Complete | Failed start = degraded mode trigger |
| FR-12 | `RunTracker.complete_run` / `fail_run` — best-effort, warning log on failure | ✅ Complete | Message[:1024], stack[:4096] |
| FR-13 | `RunTracker.record_step/tool/retrieval/llm_call` — all best-effort | ✅ Complete | Per-call session, no flow block |
| FR-14 | `CostCalculator` — TTL=300s cache, `invalidate()`, injectable clock | ✅ Complete | Per-model TTL with snapshot pricing |
| FR-15 | `ModelNameResolver` — LangChain `model_name` → `llm_model.id` mapping (hit + miss caching) | ✅ Complete | Prevents DB flood for unmapped models |
| FR-16 | `RunContext` ContextVar — propagate `run_id`/`step_id`/`tool_call_id` | ✅ Complete | `with_step_id` / `with_tool_call_id` helpers |
| FR-17 | `UsageCallback` — `AsyncCallbackHandler.on_llm_start/end/error` | ✅ Complete | Latency timing + error tracking |
| FR-18 | Provider-specific token normalization (OpenAI / Anthropic / Ollama) | ✅ Complete | `_normalize_to_token_usage` single point |
| FR-19 | LLMFactory `stream_usage=True` for OpenAI streaming | ✅ Complete | Solves last-chunk gotcha |
| FR-20 | `TraceExtractor` — lazy `langsmith` import, returns (None,None) on failure | ✅ Complete | Test envs without langsmith don't blow up |
| FR-21 | `RunAgentUseCase` integration — optional Tracker injection, degraded mode | ✅ Complete | `tracker=None` or `start_run RuntimeError` graceful |
| FR-22 | LangGraph metadata injection (`run_id`/`conversation_id`/`user_id`/`agent_id`) | ✅ Complete | + callback registration |
| FR-23 | LangSmith `trace_id` + `run_url` persistence on `complete_run` | ✅ Complete | Admin → LangSmith jump enabled |
| FR-24 | `RunAgentResponse.run_id` exposure | ✅ Complete | Frontend trace-jump ready |
| FR-25 | Supervisor node `set_purpose(SUPERVISOR)` at entry | ✅ Complete | `supervisor_nodes.py:72` |
| FR-26 | DI wiring in `main.py` (Tracker/CostCalc/Resolver singletons) | ✅ Complete | `run_uc_factory` receives tracker |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Architecture Compliance (Thin DDD) | 100% | 100% | ✅ |
| Convention Compliance (CLAUDE.md §6) | 100% | 98% | ✅ |
| Test Files Coverage | 13 spec'd | 13 / 13 | ✅ |
| Test Suite Pass Rate | 100% | 118 / 118 (agent_run) | ✅ |
| Best-effort isolation (no flow block) | Required | All record_* methods isolated | ✅ |
| Session-per-operation (DB-001 §10.3) | Required | All Tracker methods compliant | ✅ |
| Match Rate (M1) | ≥90% | 96% | ✅ |
| Degraded mode safety | Required | tracker=None + start RuntimeError handled | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| Migrations (V021, V022) | `db/migration/` | ✅ 2 files |
| Domain layer | `src/domain/agent_run/` | ✅ 4 files |
| Application layer | `src/application/agent_run/` | ✅ 6 files |
| ORM models | `src/infrastructure/persistence/models/agent_run.py` | ✅ 1 file |
| Repositories | `src/infrastructure/persistence/repositories/{agent_run,llm_call}_repository.py` | ✅ 2 files |
| LLM factory updates | `src/infrastructure/llm/{llm_factory.py,usage_callback.py}` | ✅ 2 files (1 modified, 1 new) |
| LangSmith extractor | `src/infrastructure/langsmith/trace_extractor.py` | ✅ 1 file |
| LLM model extensions | `src/domain/llm_model/entity.py` + `src/infrastructure/llm_model/*` | ✅ 3 files modified |
| UseCase integration | `src/application/agent_builder/run_agent_use_case.py` + `supervisor_nodes.py` + `schemas.py` | ✅ 3 files modified |
| DI wiring | `src/api/main.py` | ✅ Modified |
| Tests | `tests/{domain,application,infrastructure}/agent_run/` + `tests/infrastructure/llm/` + `tests/application/agent_builder/test_run_agent_use_case_observability.py` | ✅ 13 files |
| Documentation | `docs/01-plan` + `docs/02-design` + `docs/03-analysis` + this report | ✅ 4 PDCA docs |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| M2 — Tool Call invocation from LangGraph tool layer | Plan milestone split; data layer is M1-complete | High | ~1 week (wiring only) |
| M3 — Run Step recording (LangGraph callback / `astream(updates)` hook) | Plan milestone split; data layer is M1-complete | High | ~1 week (wiring only) |
| M4 — Retrieval source recording from RAG adapters | Plan milestone split; data layer is M1-complete | High | ~1 week |
| M4 — Usage API routes (`/admin/usage/users`, `/admin/usage/llm-models`, `/usage/me`, `GET /agents/runs/{run_id}`) | Plan milestone split; aggregator queries are M1-complete | High | ~3 days (API exposure) |
| `PATCH /llm-models/{id}/pricing` + `CostCalculator.invalidate()` hook (G1) | Pricing UI not yet landed; 5-min TTL covers eventual consistency | Medium | 30 min when needed |
| `SupervisorState` add `run_id`/`supervisor_llm_model_id`/`worker_llm_model_ids` fields | Wrong milestone for M1; collected in M3 | Low | 1 hour at M3 |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| All-token-level persistence | Out of scope per Plan §1-3 (non-goal) | SSE streaming unchanged; only `on_llm_end` aggregates |
| LangGraph state replication to our DB | LangGraph checkpointer responsibility per Plan §1-3 | Postgres checkpointer in separate PDCA (`langgraph-postgres-checkpointer`) |
| Full LangSmith trace replication | Cost + redundancy per Plan §1-3 | Only `trace_id` + `run_url` persisted; deep dive stays in LangSmith |
| Real-time alerts / cost-anomaly UI | Out of scope per Plan §1-3 | Future PDCA `agent-cost-anomaly-detection` |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Notes |
|--------|--------|-------|-------|
| Design Match Rate (M1) | ≥90% | **96%** | ≥threshold; M2-M4 explicitly out of scope |
| Architecture Compliance (Thin DDD) | 100% | **100%** | domain → no external deps; infra-only ORM |
| Convention Compliance (CLAUDE.md) | 100% | **98%** | Cosmetic: status enum doc lag, DTO placement (impl is cleaner) |
| Agent-run tests | All pass | **118 / 118** | TDD discipline maintained |
| Spec'd test files | 13 | **13** | One per Design §9 entry |
| Major gaps | 0 | **1** | G1 — pricing PATCH endpoint (deferred to M4) |
| Minor gaps | ≤3 | **2** | G3 status enum doc, G4 DTO placement |
| Cosmetic gaps | informational | **1** | G5 lazy langsmith import (improvement, not regression) |

### 5.2 Resolved Issues During Implementation

| Issue | Resolution | Result |
|-------|------------|--------|
| MySQL Error 3780 — FK type mismatch on `ai_run.user_message_id` (BIGINT vs INT) | Changed V021 from BIGINT → INT (matches `conversation_message.id` actual type) | ✅ Resolved during Check |
| OpenAI streaming usage_metadata missing | Set `stream_usage=True` once in `LLMFactory` | ✅ Single source of truth |
| Long-lived `CostCalculator`/`ModelNameResolver` singletons need per-call DB access | Created `SessionScopedLlmModelRepository` adapter | ✅ Elegant DI |
| Unmapped LangChain `model_name` flooding DB | `ModelNameResolver` caches misses with `None` | ✅ Single DB query per missed model |
| `complete_run` retry safety | Added `WHERE id = :rid AND status='RUNNING'` idempotency guard | ✅ Safe to retry |
| Observability failure can take down agent service | Best-effort wrappers + degraded mode on `start_run RuntimeError` | ✅ Cannot block user flow |
| `langsmith` SDK absence in test envs | Lazy import inside `TraceExtractor.extract()` | ✅ Tests run without optional dep |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **Single-point LLM interception** via LangChain `BaseCallbackHandler` proved correct — supervisor/worker/summarizer/tool-internal LLMs all captured without spreading record code across nodes.
- **Best-effort + degraded mode discipline** — both `tracker=None` and `start_run RuntimeError` paths gracefully degrade; observability outage cannot break agent service.
- **Price snapshot in `ai_llm_call`** — when llm_model pricing changes, historical cost data stays intact. This is non-obvious until you face a price-change audit.
- **Denormalization for aggregate performance** — `user_id`/`agent_id`/`model_name`/`provider` copied into `ai_llm_call` makes "user × LLM × month" queries single-table scans.
- **TDD-first** — All 13 spec'd test files written; 118 tests passing kept refactors confident.
- **Free M2/M3/M4 data layer** — building the full ORM/repo/tracker/callback infra in M1 means future milestones are pure wiring/API work, not new persistence design.

### 6.2 What Needs Improvement (Problem)

- **FK type assumption** — assumed migration's `BIGINT` was canonical; reality was `conversation_message.id INT`. Discovered only by MySQL Error 3780 at runtime. Should have grepped actual FK target type before drafting migration.
- **Status enum drift** — Plan §5-3 listed `SUCCESS/FAILED` for `ai_tool_call.status` but impl correctly used `STARTED/SUCCESS/FAILED`. Plan doc lagged.
- **DTO placement decision was made during impl**, not Design — `UserUsageRow`/`LlmUsageRow` ended up in `domain/agent_run/interfaces.py` (return-type-with-interface) instead of design's `application/aggregator.py`. Cleaner outcome, but should have been Design-phase decision.
- **Pricing PATCH endpoint absent** — Design §3-2 / §14-6 required it; impl relied solely on 5-min TTL. Acceptable for M1 but should have been carved out as explicit M1 vs M4 split in Plan.

### 6.3 What to Try Next (Try)

- For schema work, **grep FK target types into Plan** before drafting migrations.
- Treat "M1 ships X, M4 ships Y" splits as **explicit decisions** in Plan §6 milestones — not implicit.
- When implementation cleanly improves on design (e.g., DTO placement), **write the design update inline** during Check so Plan/Design/Analysis stay in sync.
- For best-effort wrappers, **add structured `warning` log + counter metric** so we can dashboard "observability drop rate" in M4.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | Milestone split was good, but "what M1 ships" vs "what M2-M4 ship" had ambiguous overlap (e.g., pricing PATCH) | Add a "M1-only items" list inside §13 DoD that excludes items deferred to later milestones |
| Design | Strong; only DTO placement choice flowed wrong direction | Add a "DTO placement rationale" sub-section when interfaces return aggregated DTOs |
| Do | TDD held; FK type mismatch surfaced via MySQL error | Add a "verify FK target type" line to schema implementation checklist |
| Check | Strong; gap-detector caught all 5 gaps with correct severity | Keep using analyst severity tiering (Major/Minor/Cosmetic) for clearer prioritization |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| Migration linting | Add pre-commit check that compares FK column types against target table | Catch MySQL 3780 before runtime |
| Observability dashboarding | Surface `ai_llm_call` aggregates in Grafana (after M4) | Real-time user/LLM cost visibility |
| Cost calibration | Cron job to sync `llm_model` pricing from provider docs (future `llm-pricing-sync` PDCA) | Avoid manual ops drift; reduce stale-cost windows |

---

## 8. Next Steps

### 8.1 Immediate (post-M1 archive)

- [ ] `/pdca archive agent-run-observability --summary` after report review
- [ ] Sync Plan §5-3 doc: add `STARTED` to `ai_tool_call.status` enum description (G3, 1 min)
- [ ] Sync Design §3-4 doc: move `UserUsageRow`/`LlmUsageRow` placement to `domain/agent_run/interfaces.py` (G4, 1 min)
- [ ] Verify production deployment of V021 + V022 migrations (Flyway forward-only)
- [ ] Tail-check `ai_run` rows after first prod traffic to confirm degraded-mode path is not triggered

### 8.2 Next PDCA Cycle

| Item | Priority | Expected Start | Notes |
|------|----------|----------------|-------|
| M2 — `agent-run-observability-tool-call` (tool invocation wiring) | High | After M1 prod stable | Data layer ready; pure wiring |
| M3 — `agent-run-observability-step` (LangGraph node hook) | High | After M2 | Data layer ready; supervisor purpose-tagging in place |
| M4 — `agent-run-observability-api` (Usage APIs + pricing PATCH) | High | After M3 | Aggregator queries ready; just need routers |
| `agent-run-admin-dashboard` (UI) | Medium | After M4 | Frontend Plan separate |
| `agent-usage-dashboard` (user/LLM/department) | Medium | After M4 | SQL views + Recharts panels |
| `agent-pii-masking` (LangSmith anonymizer) | Low | After dashboards | Compliance prep |

---

## 9. Changelog

### v1.0.0 (2026-05-19)

**Added:**
- 5 new tables: `ai_run`, `ai_run_step`, `ai_tool_call`, `ai_retrieval_source`, `ai_llm_call`
- `llm_model` pricing columns: `input_price_per_1k_usd`, `output_price_per_1k_usd`, `pricing_updated_at` (V022)
- Domain layer: `src/domain/agent_run/` (entities, value_objects, interfaces, policies)
- Application layer: `src/application/agent_run/` (tracker, cost_calculator, context, aggregator, model_name_resolver, schemas)
- Infrastructure: ORM (`agent_run.py`), repos (`agent_run_repository.py`, `llm_call_repository.py`), LangChain callback (`usage_callback.py`), LangSmith trace extractor
- 13 test files (118 tests, all passing)
- `RunAgentResponse.run_id` exposure for frontend trace jump

**Changed:**
- `RunAgentUseCase`: optional `RunTracker` injection + LangGraph callback/metadata wiring + `start_run`/`complete_run`/`fail_run` lifecycle + degraded mode on tracker failure
- `supervisor_nodes.py`: `set_purpose(SUPERVISOR)` on node entry
- `LlmModel` entity + repository: pricing fields + `find_by_provider_and_name`
- `LLMFactory`: `stream_usage=True` for OpenAI (streaming token-usage gotcha fix)
- `main.py` DI: Tracker/CostCalculator/ModelNameResolver singletons via `SessionScopedLlmModelRepository`

**Fixed:**
- V021 migration `ai_run.user_message_id` type changed BIGINT → INT to match `conversation_message.id` (MySQL Error 3780)

**Deferred (M2-M4):**
- Tool call invocation wiring from LangGraph tool layer
- LangGraph node step recording
- RAG retrieval source recording from RAG adapters
- Usage API routes (`/admin/usage/users`, `/admin/usage/llm-models`, `/usage/me`, `GET /agents/runs/{run_id}`)
- `PATCH /llm-models/{id}/pricing` admin endpoint with `CostCalculator.invalidate()` hook

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-19 | M1 completion report — Match Rate 96%, ≥90% threshold met | 배상규 |
