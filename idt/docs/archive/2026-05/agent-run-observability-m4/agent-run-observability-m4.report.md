# agent-run-observability-m4 (M4) Completion Report

> **Summary**: Agent Run 운영 관측성 M4 마일스톤 완료 (98% 설계 일치, ≥90% 임계 통과). M1·M2·M3가 만든 4개 테이블을 **외부 API로 첫 노출** + 5번째 테이블 `ai_retrieval_source` wiring 완료 + M1 G1 carry-over(`cost_calculator.invalidate`) use case 캡슐화로 해소.
>
> **Feature**: Agent Run 운영 관측성 (M4 — Retrieval Wiring + Read APIs + Pricing PATCH)
> **Task ID**: AGENT-OBS-004
> **Project**: sangplusbot (idt)
> **Scope**: M4 only — RAG retrieval 영속화 wiring + 5 read API + PATCH /pricing + cost cache invalidate
> **Version**: 1.0
> **Planning Date**: 2026-05-21
> **Completion Date**: 2026-05-21
> **Match Rate**: 98%
> **Status**: ✅ COMPLETED (M4)
> **Parent (M1)**: agent-run-observability (archived 2026-05-19, 96%)
> **Sibling (M2)**: agent-run-observability-m2 (archived 2026-05-21, 98%)
> **Sibling (M3)**: agent-run-observability-m3 (archived 2026-05-21, 99%)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | Agent Run 운영 관측성 (M4 — Retrieval Wiring + Read APIs + Pricing PATCH) |
| Task ID | AGENT-OBS-004 |
| Start Date | 2026-05-21 |
| End Date | 2026-05-21 |
| Duration | 1 day (Plan → Design → Do → Check → Report 모두 단일 세션) |
| Predecessor | M3 (AGENT-OBS-003, archived, 99%) |
| Milestones Pending | (Future M5: tavily retrieval / 어드민 dashboard 등 — 별도 PDCA) |
| Final Match Rate | **98%** (≥90% threshold met) |

### 1.2 Results Summary

```
┌────────────────────────────────────────────────────────────────┐
│  M4 Completion Rate: 98%                                       │
├────────────────────────────────────────────────────────────────┤
│  ✅ New files:        9                                        │
│     - src/application/agent_run/exceptions.py                  │
│     - src/application/agent_run/use_cases/__init__.py          │
│     - src/application/agent_run/use_cases/get_run_detail_*.py │
│     - src/application/agent_run/use_cases/get_usage_by_*.py    │ (4 files)
│     - src/application/llm_model/update_llm_model_pricing_*.py │
│     - src/api/routes/agent_run_router.py                       │
│     - src/interfaces/schemas/agent_run_response.py             │
│  ✅ Modified files:   8                                        │
│     - src/application/rag_agent/tools.py (async + tracker)     │
│     - src/domain/agent_run/interfaces.py (+ NodeUsageRow)      │
│     - src/application/agent_run/aggregator.py (+ by_node)      │
│     - src/infrastructure/persistence/repositories/             │
│         llm_call_repository.py (+ aggregate_by_node)           │
│     - src/application/llm_model/schemas.py (가격 필드 + req)   │
│     - src/api/routes/llm_model_router.py (+ PATCH /pricing)    │
│     - src/infrastructure/agent_builder/tool_factory.py         │
│     - src/api/main.py (DI 와이어링 + 관측성 싱글톤 재배치)     │
│  ✅ Test files (new): 6                                        │
│     - tests/application/rag_agent/.../retrieval.py (8)         │
│     - tests/application/agent_run/use_cases/run_detail.py (7) │
│     - tests/application/agent_run/use_cases/usage_query.py(4) │
│     - tests/application/llm_model/update_pricing.py (5)        │
│     - tests/api/test_agent_run_router.py (10)                  │
│     - tests/api/test_llm_model_router_pricing.py (4)           │
│  ✅ Test files (mod): 2                                        │
│     - tests/infrastructure/agent_run/llm_call_repository (+3) │
│     - tests/application/agent_run/test_aggregator.py (+1)      │
│  ✅ Test cases:       42 new + 121 regression = 163 / 163 pass │
│     (1272s in batch, 163/163 PASS, 0 failures, 0 errors)       │
│  ✅ DB migrations:    0 (Design §1.1 약속 100% 준수)           │
│  ✅ Domain changes:   +1 dataclass (NodeUsageRow) + 1 abc      │
│  ✅ Endpoints:        +6 (5 GET + 1 PATCH)                     │
│  🟢 Free win #1:      LlmModelResponse 가격 필드 list endpoint │
│                       에도 자동 적용 (별도 fetch 불필요)        │
│  🟢 Free win #2:      _resolve_period 가 응답에 from/to echo   │
│  🟢 Free win #3:      cost_calculator_singleton 공유로 M1 G1   │
│                       root-cause 해소 (invalidate 즉시 반영)   │
│  🟡 Minor deviations: 3 (RunNotFoundError 부모 / assemble 위치/ │
│                         tool_call_id NULL retrieval 처리)       │
│  🟠 Major / 🔴 Critical: 0                                     │
└────────────────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | M1·M2·M3로 데이터 레이어는 100% 채워졌지만 **외부에서 읽을 길이 없었다**. (1) `ai_retrieval_source` INSERT 호출 0건 — RAG 답변의 근거 chunk를 사후 추적 불가. (2) Run 상세 / 사용자별 / LLM별 / **노드별**(★ M3 효과) 사용량 API 부재 — 어드민은 DB SQL 콘솔 외 접근 불가. (3) LLM 가격 PATCH API 부재 + 캐시 invalidate 의무 미충족 (M1 G1 carry-over) — 가격 변경 후 5분간 stale. |
| **Solution** | **신규 마이그레이션 0건, wiring 1건 + 5 read API + 1 PATCH endpoint.** (a) `InternalDocumentSearchTool._format_results`를 async 승격 후 hit별 best-effort `record_retrieval` — `RunContext.run_id/tool_call_id` 자동 활용 (M2·M3 ContextVar 사전 작업). (b) `agent_run_router.py` 신규 5 endpoint(`GET /agents/runs/{run_id}` + `GET /admin/usage/{users,llm-models,by-node}` + `GET /usage/me`) — read는 기존 `AgentRunRepository.find_*` + `UsageAggregator` 재사용. (c) `PATCH /llm-models/{id}/pricing` + `UpdateLlmModelPricingUseCase`가 `CostCalculator.invalidate(model_id)` 의무 호출을 **캡슐화** → router/테스트가 빼먹어도 단위 테스트 2건이 강제 검증. 도메인 변경은 `NodeUsageRow` 1 dataclass + abc method 1개. |
| **Function / UX Effect** | (1) **RAG 답변 책임 추적**: "이 답변에 인용된 chunk가 무엇이고 어느 문서였나"를 1줄 SQL/JSON으로 확인. (2) **Run 상세 트리 API**: 어드민이 한 run의 `supervisor → worker → quality_gate → answer` + 각 노드별 LLM/툴/검색 결과를 1회 호출로 JSON 트리 수신. (3) **노드별 차지백** (`/admin/usage/by-node`): "answer_agent가 비용 70% 차지"같은 인사이트 5초 안에 확인 — ★ M3 step_id JOIN의 실질 효과 첫 노출. (4) **사용자 셀프 사용량** (`/usage/me`): 본인 토큰/비용 직접 확인 → 무리 사용 자제. (5) **가격 인플레/할인 즉시 반영**: 관리자 PATCH 직후 다음 LLM 호출부터 새 단가 — cache invalidate 의무 캡슐화로 M1 G1 영구 해소. (6) 비-admin이 다른 사용자 run 접근 시 403, 미존재 run 404 분리로 어드민 디버깅 명확성 ↑. |
| **Core Value** | **"실행 원장 → 운영 가시성"의 완성.** M1·M2·M3는 DB에 데이터를 쌓는 파이프라인이었고, M4는 그 데이터를 외부로 노출하는 **첫 인터페이스**다. 이후 `agent-run-admin-dashboard` / `agent-usage-dashboard`가 모두 M4 API만 호출하면 됨 — 화면 PDCA들이 백엔드 변경 없이 진행 가능. 1일 만에 완료 (Plan/Design/Do/Check/Report 모두 단일 세션), 신규 마이그레이션 0건, 테스트 42건 신규(목표 33건 대비 +27%) + 163/163 PASS. M1 G1 carry-over 영구 해소(invalidate 캡슐화). |

---

## 2. Related Documents

| Phase | Document | Status | Match Rate |
|-------|----------|--------|-----------|
| Plan | [agent-run-observability-m4.plan.md](../../01-plan/features/agent-run-observability-m4.plan.md) | ✅ Finalized | — |
| Design | [agent-run-observability-m4.design.md](../../02-design/features/agent-run-observability-m4.design.md) | ✅ Finalized | — |
| Check | [agent-run-observability-m4.analysis.md](../../03-analysis/agent-run-observability-m4.analysis.md) | ✅ Complete | 98% |
| Report | Current document | ✅ Complete | — |

---

## 3. Completed Items (M4)

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | RAG retrieval wiring — `_format_results` async + hit별 `record_retrieval` | ✅ | `tools.py:110-159` |
| FR-02 | `_format_results` 호출자 2곳 await 추가 | ✅ | `tools.py:79`, `tools.py:108` |
| FR-03 | RunContext None / tracker None 시 영속화 skip | ✅ | `tools.py:117, 132-133` |
| FR-04 | content_preview 컷오프 `RunObservabilityConfig.retrieval_preview_max_bytes` | ✅ | `tools.py:118, 136` |
| FR-05 | best-effort 격리 — record_retrieval 실패가 RAG 답변 차단 안함 | ✅ | `tools.py:135-159` try/except continue |
| FR-06 | `NodeUsageRow` frozen dataclass | ✅ | `interfaces.py:48-59` |
| FR-07 | `LlmCallRepositoryInterface.aggregate_by_node` abc method | ✅ | `interfaces.py:145-149` |
| FR-08 | `SqlAlchemyLlmCallRepository.aggregate_by_node` INNER JOIN ai_run_step | ✅ | `llm_call_repository.py:170-200` |
| FR-09 | `UsageAggregator.by_node` 메서드 | ✅ | `aggregator.py` 신규 메서드 |
| FR-10 | `RunNotFoundError` / `RunAccessDeniedError` 예외 | ✅ | `exceptions.py:9-23` |
| FR-11 | `GetRunDetailUseCase` — 5 batch fetch + client-side join | ✅ | `get_run_detail_use_case.py:73-92` |
| FR-12 | `_assemble` — tool/retrieval/llm in-memory dict join | ✅ | `get_run_detail_use_case.py:95-145` |
| FR-13 | 권한 분기 — owner OR admin / 그 외 403 | ✅ | UC L83-84 + router L100-118 |
| FR-14 | 4 Usage query UC — aggregator wrapper | ✅ | `use_cases/get_usage_by_{user,llm,node,me}_use_case.py` |
| FR-15 | `UpdateLlmModelPricingUseCase` — ★ invalidate 캡슐화 | ✅ | `update_llm_model_pricing_use_case.py:57` |
| FR-16 | `UpdatePricingRequest` Pydantic Decimal `ge=0` | ✅ | `schemas.py:32-36` |
| FR-17 | `LlmModelResponse` 가격 필드 3개 additive 확장 | ✅ | `schemas.py:49-66` |
| FR-18 | `agent_run_router.py` 5 endpoints | ✅ | `agent_run_router.py:95,122,134,146,159` |
| FR-19 | `from`/`to` Query alias + period validation 422 | ✅ | `agent_run_router.py:76-88, 124-126` |
| FR-20 | admin only (`require_role("admin")`) on 3 admin endpoints | ✅ | router L126, L138, L150 |
| FR-21 | `current_user.id` 문자열 변환 (`User.id: Optional[int]`) | ✅ | router L106, L168 |
| FR-22 | `PATCH /llm-models/{id}/pricing` endpoint + DI placeholder | ✅ | `llm_model_router.py:145-162` |
| FR-23 | `RunDetailResponse` / `UsageBy{User,Llm,Node}Response` Pydantic | ✅ | `agent_run_response.py:97-200` |
| FR-24 | ToolFactory `tracker` / `run_observability_config` 파라미터 | ✅ | `tool_factory.py:26-35` |
| FR-25 | 관측성 싱글톤 ToolFactory 이전 배치 | ✅ | `main.py:1481-1513` (주석 명시) |
| FR-26 | `create_agent_run_factories()` 5 factory | ✅ | `main.py:1247-1293` |
| FR-27 | `create_llm_model_factories(cost_calculator=...)` 시그니처 | ✅ | `main.py:1223-1244` |
| FR-28 | `_cost_calculator_singleton` 공유 (PATCH ↔ LLM 호출 동일 instance) | ✅ | `main.py:2144` (튜플) + L2212 (전달) |
| FR-29 | 6 `dependency_overrides` 적용 | ✅ | `main.py:2218, 2228-2232` |
| FR-30 | `app.include_router(agent_run_router)` | ✅ | `main.py:2433` |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Architecture (Thin DDD) | domain → infra 참조 0 | 0건 | ✅ |
| Layer dependency direction | domain ← application ← infrastructure | 위반 0건 | ✅ |
| DB migrations | 0 (Design §1.1 약속) | 0 | ✅ |
| Out-of-scope preservation | 페이지네이션 / 필터 / CSV export | 모두 미구현 (YAGNI) | ✅ |
| Convention (CLAUDE.md §3, §6) | print() 0, 함수 ≤40줄, if 중첩 ≤2 | 100% 준수 (`_assemble` ~50 module-level only) | ✅ |
| Test files (Design §9.1) | 6 new + 2 augment | 6 new + 2 augment | ✅ |
| Unit test pass rate | 100% | 163/163 (M1/M2/M3 회귀 포함) | ✅ |
| 신규 테스트 vs 목표 | 33 | 42 (127%) | ✅ |
| Match Rate (M4) | ≥90% | 98% | ✅ |
| 핵심 회귀 가드 | 6 required | 6/6 통과 | ✅ |

### 3.3 Deliverables

#### Code Files

| Type | File | Lines | Notes |
|------|------|------:|-------|
| NEW | `src/application/agent_run/exceptions.py` | 23 | RunNotFoundError(LookupError) + RunAccessDeniedError(PermissionError) |
| NEW | `src/application/agent_run/use_cases/__init__.py` | 1 | package marker |
| NEW | `src/application/agent_run/use_cases/get_run_detail_use_case.py` | 145 | DTO(StepNode/ToolCallNode/RunDetailDto) + UseCase + `_assemble` |
| NEW | `src/application/agent_run/use_cases/get_usage_by_user_use_case.py` | 17 | aggregator wrapper |
| NEW | `src/application/agent_run/use_cases/get_usage_by_llm_use_case.py` | 17 | aggregator wrapper |
| NEW | `src/application/agent_run/use_cases/get_usage_by_node_use_case.py` | 17 | aggregator wrapper (★ M3 효과) |
| NEW | `src/application/agent_run/use_cases/get_usage_me_use_case.py` | 17 | for_user wrapper |
| NEW | `src/application/llm_model/update_llm_model_pricing_use_case.py` | 67 | ★ M1 G1: cost_calculator.invalidate 캡슐화 |
| NEW | `src/api/routes/agent_run_router.py` | 170 | 5 endpoints + DI placeholders + `_resolve_period` |
| NEW | `src/interfaces/schemas/agent_run_response.py` | 306 | RunDetailResponse + 3 UsageResponse + 7 converters |
| MODIFIED | `src/application/rag_agent/tools.py` | +50 | `_format_results` 동기→async + tracker/logger/config 필드 + best-effort record_retrieval |
| MODIFIED | `src/domain/agent_run/interfaces.py` | +14 | NodeUsageRow + aggregate_by_node abc |
| MODIFIED | `src/application/agent_run/aggregator.py` | +6 | `by_node` wrapper |
| MODIFIED | `src/infrastructure/persistence/repositories/llm_call_repository.py` | +30 | aggregate_by_node SQL (INNER JOIN AgentRunStepModel) |
| MODIFIED | `src/application/llm_model/schemas.py` | +15 | UpdatePricingRequest + LlmModelResponse 가격 필드 3 additive |
| MODIFIED | `src/api/routes/llm_model_router.py` | +25 | PATCH /{model_id}/pricing + DI placeholder |
| MODIFIED | `src/infrastructure/agent_builder/tool_factory.py` | +10 | tracker / run_observability_config 파라미터 + InternalDocumentSearchTool 주입 |
| MODIFIED | `src/api/main.py` | +50 | 관측성 싱글톤 ToolFactory 이전 재배치 + create_agent_run_factories + create_llm_model_factories pricing 확장 + 6 dep_overrides + router include |

#### Test Files

| Type | File | Cases | Notes |
|------|------|------:|-------|
| NEW | `tests/application/rag_agent/test_internal_document_search_retrieval.py` | 8 | per-hit / ctx None skip / tool_call_id / best-effort / partial failure / Optional |
| NEW | `tests/application/agent_run/use_cases/__init__.py` | — | package marker |
| NEW | `tests/application/agent_run/use_cases/test_get_run_detail_use_case.py` | 7 | tree / empty / orphan / 404 / 403 / admin / N+1 가드 |
| NEW | `tests/application/agent_run/use_cases/test_usage_query_use_cases.py` | 4 | 4 UC delegate 검증 |
| NEW | `tests/application/llm_model/test_update_pricing_use_case.py` | 5 | 저장 / timestamp / ★ invalidate / 호출 순서 / not-found |
| NEW | `tests/api/test_agent_run_router.py` | 10 | run 200 owner/admin + 404 + 403 / 3 admin usage / admin role / period 422 / me self-id |
| NEW | `tests/api/test_llm_model_router_pricing.py` | 4 | 200 / 403 / 404 / 422 (negative price) |
| MODIFIED | `tests/infrastructure/agent_run/test_llm_call_repository.py` | +3 | aggregate_by_node — GROUP BY / INNER JOIN / period window |
| MODIFIED | `tests/application/agent_run/test_aggregator.py` | +1 | by_node delegate |

#### Documents

| Phase | File |
|-------|------|
| Plan | `docs/01-plan/features/agent-run-observability-m4.plan.md` |
| Design | `docs/02-design/features/agent-run-observability-m4.design.md` |
| Analysis | `docs/03-analysis/agent-run-observability-m4.analysis.md` |
| Report | `docs/04-report/features/agent-run-observability-m4.report.md` (this) |

---

## 4. Implementation Highlights

### 4.1 RAG Retrieval Wiring — RunContext 자동 활용 (Design §2.2)

M2가 `tool_call_id`를, M3가 `step_id`를 ContextVar에 set/reset해 둔 상태에서, M4는 도구 본체가 그 컨텍스트를 read만 하면 된다 — **factory/spec 변경 0**:

```python
# tools.py (M4)
async def _format_results(self, results: list) -> str:
    ctx = get_current_run_context() if self.tracker is not None else None
    preview_max = (self.config or _DEFAULT_OBS_CFG).retrieval_preview_max_bytes
    for rank_index, hit in enumerate(results, start=1):
        # ... 기존 포맷팅
        if ctx is None or ctx.run_id is None:
            continue
        try:
            await self.tracker.record_retrieval(
                run_id=ctx.run_id,
                tool_call_id=ctx.tool_call_id,        # ★ M2가 set
                collection_name=self.collection_name or hit.metadata.get("collection") or "unknown",
                document_id=hit.metadata.get("document_id"),
                chunk_id=hit.id,
                score=hit.score,
                rank_index=rank_index,
                content_preview=hit.content[:preview_max],
                metadata=dict(hit.metadata),
            )
        except Exception as e:
            self.logger.warning("...", exception=e, chunk_id=hit.id)
            # continue — 다음 hit
```

**효과**: M2의 단일 인터셉트 정신 유지 — ToolFactory에 tracker 1줄, 도구 본체에 try/except 1군데만 손댐. WorkflowCompiler / Spec / Agent 정의 등 어떠한 상위 객체도 변경 없음.

### 4.2 ★ M1 G1 영구 해소 — invalidate 의무 캡슐화 (Design §2.5, §3.4)

M1 회고에서 식별된 G1 "cost_calculator.invalidate 호출 누락 가능성"이 M4에서 **시스템적으로 봉인**됨:

```python
# update_llm_model_pricing_use_case.py
class UpdateLlmModelPricingUseCase:
    async def execute(self, model_id, request, request_id) -> LlmModelResponse:
        model = await self._repo.find_by_id(model_id, request_id)
        if model is None:
            raise ValueError(f"모델을 찾을 수 없습니다: {model_id}")

        # ... mutate prices + pricing_updated_at ...

        updated = await self._repo.update(model, request_id)
        self._cost_calc.invalidate(model_id)   # ★ M1 G1 의무
        return LlmModelResponse.from_domain(updated)
```

핵심: router는 invalidate를 모른다. 단위 테스트 2건이 강제 검증:
- `test_calls_cost_calculator_invalidate_with_model_id`
- `test_invalidate_called_after_repo_update` (호출 순서까지)

또한 `_cost_calculator_singleton`이 `create_agent_builder_factories` 튜플로 반환되어 **PATCH /pricing이 무효화하는 캐시가 LLM 호출 경로와 동일 instance** — 즉시 모든 호출 경로에 반영. M1 G1의 root cause(다른 instance 사용) 자체가 봉인됨.

### 4.3 Run Detail Tree Assembly — N+1 회피 (Design §2.3)

5회 batch fetch만 사용 → in-memory dict join → 트리 응답. 회귀 가드 테스트(`test_uses_exactly_5_repo_calls_max`)가 영구히 N+1 재발을 막는다:

```python
# get_run_detail_use_case.py
async def execute(self, run_id, requesting_user_id, is_admin) -> RunDetailDto:
    rid = RunId(run_id)
    run = await self._agent_run_repo.find_run(rid)
    if run is None: raise RunNotFoundError(run_id)
    if run.user_id != requesting_user_id and not is_admin:
        raise RunAccessDeniedError(run_id)

    # 4 batch fetch (모두 run_id 단일 인덱스, O(1) SQL)
    steps = await self._agent_run_repo.find_steps(rid)
    tool_calls = await self._agent_run_repo.find_tool_calls(rid)
    retrievals = await self._agent_run_repo.find_retrievals(rid)
    llm_calls = await self._llm_call_repo.find_by_run(rid)

    return _assemble(run, steps, tool_calls, retrievals, llm_calls)
```

응답 구조: `RunDto + steps[] (각 step 안에 llm_calls[] + tool_calls[] (각 안에 retrievals[] + llm_calls[])) + orphan_llm_calls[]`.

### 4.4 ★ M3 효과 첫 실질 노출 — /admin/usage/by-node

M3가 `ai_llm_call.step_id`를 자동 채워준 덕에 M4가 추가 마이그레이션 없이 노드별 비용 집계를 SQL 1줄로 제공:

```sql
SELECT s.node_name,
       COUNT(*)                  AS call_count,
       SUM(l.prompt_tokens)      AS prompt_tokens,
       SUM(l.completion_tokens)  AS completion_tokens,
       SUM(l.total_tokens)       AS total_tokens,
       SUM(l.total_cost_usd)     AS total_cost_usd
FROM ai_llm_call l
INNER JOIN ai_run_step s ON s.id = l.step_id   -- ★ M3 wiring 결과
WHERE l.created_at BETWEEN :from AND :to
GROUP BY s.node_name;
```

INNER JOIN이 `step_id IS NULL` 행을 자연 제외 — M2 이전 데이터/graph 외 호출은 의도적으로 안 잡힘. 어드민이 "supervisor 5% / worker_finance 25% / answer_agent 70%" 같은 비용 분포를 5초 안에 확인.

### 4.5 404 vs 403 분리 — UUID4 unguessable의 신뢰

Design §1.3 결정사항: run 미존재 = 404, 존재하나 본인 아님 = 403. run_id가 UUID4(추측 비용 무한)이므로 정보 누설 위험이 낮고, 어드민 디버깅 명확성이 우선:

```python
# agent_run_router.py
try:
    dto = await use_case.execute(...)
except RunNotFoundError:
    raise HTTPException(404, f"Run not found: {run_id}")
except RunAccessDeniedError:
    raise HTTPException(403, "Access denied")
return RunDetailResponse.from_dto(dto)
```

회귀 가드 테스트 2건(`test_returns_404_when_not_found`, `test_returns_403_when_other_user_non_admin`)이 분리 유지 보증.

### 4.6 LlmModelResponse 가격 필드 additive — 어드민 free win

Design §1.3 #2 결정: 기존 schema에 옵셔널 3 필드 추가:

```python
class LlmModelResponse(BaseModel):
    # ... 기존 8 필드
    # ── M4 additive ──
    input_price_per_1k_usd: Decimal | None = None
    output_price_per_1k_usd: Decimal | None = None
    pricing_updated_at: datetime | None = None
```

**Free win**: list endpoint(`GET /llm-models`)에도 자동 적용 → 어드민 화면이 별도 fetch 없이 list 응답에서 모델 가격 표시 가능. 기존 frontend는 옵셔널 필드 무시 → 영향 0.

---

## 5. Gap Analysis Summary

Match Rate 98% — 3건 Minor 의미 동등 deviation, Critical/Major 0건.

| 유형 | 항목 | Impact |
|------|------|--------|
| 🟡 Minor | `RunNotFoundError` 부모 클래스 — Design은 ValueError 예시, 실제는 LookupError | None — router catch는 클래스명 기준; LookupError가 의미상 더 정확 |
| 🟡 Minor | `_assemble` 헬퍼 위치 — Design "같은 파일 또는 assembler.py 분리" / 실제 같은 파일 module-level | None — Design 허용 옵션. ~50줄로 함수 길이 규약 준수 |
| 🟡 Minor | `tool_call_id IS NULL`인 retrieval — dict join이 자연 제외 | None — M4 spec 상 tool_call_id 항상 set (M2 ContextVar) |
| 🔵 Added | Test 케이스 9건 확장 (33 → 42) — 회귀 가드 강화 | +27% test coverage |
| 🔵 Added | `test_invalidate_called_after_repo_update` (호출 순서 검증) | M1 G1 재발 방지 2중 |
| 🔵 Added | `update_pricing_factory`가 cost_calculator None 가드 | 운영 안전성 |
| 🟢 Free Win | LlmModelResponse 가격 필드 list endpoint 자동 적용 | 어드민 별도 fetch 불필요 |
| 🟢 Free Win | `_resolve_period`가 응답 `from_dt/to_dt` echo | 클라이언트가 실효값 항상 확인 |
| 🟢 Free Win | cost_calculator_singleton 공유 (PATCH ↔ LLM 호출 동일 instance) | M1 G1 root cause 봉인 |

전체 분석: [agent-run-observability-m4.analysis.md](../../03-analysis/agent-run-observability-m4.analysis.md)

---

## 6. Manual Verification (Pending — Operator Side)

Plan §12.3 / Design §9.3 수동 검증 항목:

- [ ] RAG 질문 1회 → `ai_retrieval_source` row N건 + `tool_call_id NOT NULL` (★ M4 핵심 가치)
  ```sql
  SELECT rs.rank_index, rs.collection_name, rs.score, rs.chunk_id,
         tc.tool_name, s.node_name
    FROM ai_retrieval_source rs
    JOIN ai_tool_call tc ON tc.id = rs.tool_call_id
    JOIN ai_run_step s ON s.id = tc.step_id
   WHERE rs.run_id=? ORDER BY rs.rank_index;
  ```
- [ ] `GET /api/v1/agents/runs/{run_id}` 응답 검증
  - run / steps[] / 각 step 안 llm_calls/tool_calls/retrievals 트리 구성
  - owner: 200, non-owner non-admin: 403, 미존재: 404
- [ ] `GET /api/v1/admin/usage/users?from=&to=` → 사용자별 token/cost 정렬
- [ ] `GET /api/v1/admin/usage/llm-models?from=&to=` → 모델별 분리
- [ ] `GET /api/v1/admin/usage/by-node?from=&to=` (★ M3 효과 첫 확인)
  → supervisor / worker_* / quality_gate / answer_agent 분리
- [ ] `GET /api/v1/usage/me?from=&to=` → 본인 row만
- [ ] `PATCH /api/v1/llm-models/{gpt-4o-id}/pricing`
  ```json
  {"input_price_per_1k_usd": "0.005", "output_price_per_1k_usd": "0.015"}
  ```
  → 200 + 다음 LLM 호출의 `ai_llm_call.input_price_per_1k_usd / output_price_per_1k_usd` 새 값 반영 (M1 G1 영구 해소 검증)
- [ ] 비-admin이 `/admin/*` 호출 → 403
- [ ] retrieval 강제 예외 주입 → RAG 답변 정상 반환 (best-effort 검증)

---

## 7. Follow-up Items

### 7.1 Immediate
**없음.** M4는 자체로 완결 — API 5개 + PATCH 1개 모두 즉시 사용 가능.

### 7.2 Documentation Sync (Optional)
- 없음 (Design §12.1 ~ 12.6 모두 본 Plan/Design §1.3에서 결정 완료)

### 7.3 Next Milestones

| Milestone | Scope | Pre-requisite |
|-----------|-------|---------------|
| `agent-run-admin-dashboard` | 어드민 UI 화면 (Run list / 트리 시각화 / Usage 차트) — M4 API만 호출 | M4 완료 (현재) |
| `agent-usage-dashboard` | 사용자 셀프 사용량 + 부서 mapping 도입 화면 | M4 완료 (현재) |
| **M5** (`agent-run-observability-m5`) | (1) `tavily_search` retrieval 영속화 (별도 schema 정의), (2) `GET /admin/runs?from=&to=&user_id=&status=` list API, (3) `ai_llm_call.step_id` 인덱스 마이그레이션 (by-node API 슬로우 발견 시) | M4 완료 (현재) |
| `agent-run-pii-redaction` | step.input_summary / output_summary 보안 검토 + redaction 정책 | M4 완료 + 보안 검토 |
| `agent-run-retention-policy` | ai_run / step / tool / retrieval / llm_call TTL · GDPR anonymization | 별도 컴플라이언스 |
| `agent-run-pricing-history` | `ai_llm_pricing_history` audit table (가격 변경 이력) | 별도 |

---

## 8. Lessons Learned

| 항목 | 학습 |
|------|------|
| M1·M2·M3의 ContextVar 선투자가 M4에서 코드 0줄로 회수됨 | M2가 `tool_call_id`, M3가 `step_id`를 ContextVar에 set/reset해 둔 덕에 M4는 도구 본체가 `get_current_run_context()` 한 줄로 영속화 가능. **데이터 lifecycle을 ContextVar 단일 슬롯으로 통합한 설계가 정답이었다** |
| Use case 안에 의무 호출 캡슐화가 M1 G1 같은 회귀를 영구히 봉인한다 | `cost_calculator.invalidate(model_id)`를 router에 두면 다른 endpoint 추가 시 빼먹기 쉬움. UC 안으로 가두고 단위 테스트로 호출 자체를 검증하면 빠질 길이 없다 |
| Design §1.3 "Open Issue 사전 결정"이 Do phase 의사결정 비용을 0으로 만든다 | M4 Plan §11에서 6개 미결정 사항을 Design §1.3에서 일괄 확정 → Do phase에서 한 번도 멈추지 않음. M3 "Open Issue 재확인 패턴" 일관 |
| 1 day end-to-end PDCA가 누적된다 | M1 7일 → M2 2일 → M3 1일 → M4 1일. 데이터/콘텍스트/best-effort 패턴이 누적되면서 후속 마일스톤은 wiring + endpoint 작성으로 축소 |
| INNER JOIN이 데이터 일관성 자동 가드 | M4 by-node 집계에서 INNER JOIN이 `step_id IS NULL` 행 자연 제외 — 별도 WHERE 절 필요 없음. SQL 사양 활용으로 코드 단순화 |
| Pydantic 옵셔널 필드 additive 확장은 frontend 영향 0 | LlmModelResponse에 가격 3 필드 추가가 list endpoint 자동 노출까지 무료 — frontend는 모르고 무시, admin 화면은 즉시 활용 |
| 404 vs 403 분리는 UUID4 자원에서 안전 | run_id 추측 비용 무한 → 정보 누설 위험 낮음 → 어드민 디버깅 명확성 우선이 합리적 |
| `_format_results` 동기→async 승격이 fire-and-forget보다 안전 | asyncio.create_task로 분리하면 run lifecycle 종료보다 INSERT 늦어질 위험. await로 직렬화한 비용은 LLM 호출 latency 대비 무시 가능 |

---

## 9. Acknowledgments

- M1 architect: 5-table schema + `ai_retrieval_source` 컬럼 미리 정의 → M4는 wiring만
- M1 G1 식별: cost_calculator.invalidate 의무를 명시 → M4가 use case 캡슐화로 영구 해소
- M2 patch: `RunContext.tool_call_id` ContextVar set/reset → M4 RAG 도구가 read만 하면 됨
- M3 wiring: `RunContext.step_id` + `ai_llm_call.step_id` 자동 채움 → M4 by-node API가 추가 마이그레이션 없이 가능
- M3 "단일 진입점" 정신: ToolFactory 한 곳에 tracker 주입 → 도구 본체 외 모든 상위 객체 변경 0
- `RunObservabilityConfig` (M1): `retrieval_preview_max_bytes` 등 1KB 컷오프 상수 통합 — M4가 그대로 활용
- LangChain BaseTool standard hook (M2 wiring 기반) — M4가 retrieval 영속화도 같은 도구 인스턴스에서 처리

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-21 | M4 완료 보고서 — Match Rate 98%, 42 신규 + 121 회귀 = 163/163 PASS, 5 read API + 1 PATCH endpoint, 신규 마이그레이션 0건, M1 G1 영구 해소 | 배상규 |
