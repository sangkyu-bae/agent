# agent-run-observability-m4 Design Document

> **Summary**: M4 — `ai_retrieval_source` 자동 채움(RAG 도구 1지점 wiring) + 운영자 외부 노출 5개 read API + `PATCH /llm-models/{id}/pricing` (M1 G1 carry-over). 신규 테이블/마이그레이션/도메인 엔티티 0건, application 신규 use case 6건, router 신규 1개.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-21
> **Status**: Draft
> **Planning Doc**: [agent-run-observability-m4.plan.md](../../01-plan/features/agent-run-observability-m4.plan.md)
> **Parent (M1) Design**: [agent-run-observability.design.md](../../archive/2026-05/agent-run-observability/agent-run-observability.design.md)
> **Sibling (M2) Design**: [agent-run-observability-m2.design.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.design.md)
> **Sibling (M3) Design**: [agent-run-observability-m3.design.md](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.design.md)

---

## 1. Overview

### 1.1 Design Goals

- M1·M2·M3에서 채워진 4개 테이블(`ai_run / ai_run_step / ai_tool_call / ai_llm_call`)을 **외부 API로 첫 노출** — read 안전성·권한·페이로드 안정성 최우선
- 5번째 테이블 `ai_retrieval_source`도 wiring 완료 → RAG 답변의 근거 chunk를 사후 SQL/UI로 추적 가능
- M1 G1 carry-over 해소: `PATCH /llm-models/{id}/pricing` + `CostCalculator.invalidate()` **의무 호출**을 use case 안에 캡슐화 → router는 호출만, 빼먹기 불가
- 신규 마이그레이션/도메인 엔티티 0건 — M1 데이터 모델이 충분
- 어드민/사용자 화면 PDCA가 백엔드 변경 없이 진행 가능한 안정적 응답 contract

### 1.2 Design Principles

- **Single Interception Point (Tool Body)**: RAG retrieval 영속화는 `InternalDocumentSearchTool._format_results` 한 곳에서만 발생 — `RunContext.get_current_run_context()` 활용으로 ToolFactory/Spec 변경 0
- **Read-Only First Exposure**: M4 read API 5건은 모두 GET — write는 PATCH /pricing 1건만. 응답 contract를 어드민 PDCA가 그대로 소비할 수 있게 충분히 평탄화
- **Capsule Invalidation**: 가격 캐시 무효화 의무를 `UpdateLlmModelPricingUseCase.execute()` 안에 가둔다 → router·테스트가 빼먹어도 단위 테스트 1건이 강제 검증 (`test_calls_cost_calculator_invalidate_with_model_id`)
- **YAGNI**: 페이지네이션·필터(검색어/부서/모델 family)·CSV export는 M4 미포함 — Run list 같은 list API도 미포함 (어드민 PDCA가 list 요구 시 별도)
- **Best-Effort Isolation**: retrieval 영속화 실패가 RAG 답변 흐름을 차단하지 않음 (M2 패턴 일관)
- **Information Leak vs UX**: run 404(not found) vs 403(존재하나 본인 아님)을 **명시 분리** — run_id가 UUID4(unguessable) 이므로 leak 위험 낮음. 어드민이 정확한 디버깅 가능

### 1.3 Plan §11 Open Issues 결정

| Open Issue | 결정 | 근거 |
|-----------|------|------|
| `tavily_search` retrieval 영속화 포함 여부 | **미포함**. M5 후속 PDCA | Tavily 결과는 web URL — `ai_retrieval_source.chunk_id/document_id` 의미론 충돌. 별도 schema 정의 필요. M4 In Scope는 RAG(internal_document_search)만 |
| `LlmModelResponse`에 가격 필드 노출 여부 | **additive 확장** — `input_price_per_1k_usd / output_price_per_1k_usd / pricing_updated_at` optional 3 필드 추가 | 기존 frontend는 옵셔널 필드 무시. 어드민 화면이 가격 확인하려면 별도 API보다 응답에 포함이 자연. List 응답에도 동일 노출 |
| run not-found vs unauthorized 통일 | **분리** — 존재하지 않음 = 404, 존재하나 권한 없음 = 403 | run_id가 UUID4이므로 random guess 실효 없음. 어드민/사용자 UX 디버깅 명확성 우선 |
| NodeUsageRow 배치 | `src/domain/agent_run/interfaces.py` (UserUsageRow/LlmUsageRow와 동급 frozen dataclass) | M1 패턴 일관 — abc method가 반환 타입을 같은 모듈에서 제공 |
| Use case 파일 구조 | **5개 분리** in `src/application/agent_run/use_cases/` 디렉토리 + 1개 in `src/application/llm_model/` | `src/application/llm_model/`이 이미 이 패턴 (`update_llm_model_use_case.py` 등). 단일 책임. Aggregator wrapper 4개는 짧으므로 `usage_query_use_cases.py` 한 파일로 합쳐도 무방 — 본 Design은 5개 분리 채택 |
| 가격 API endpoint shape | `PATCH /api/v1/llm-models/{id}/pricing` body `{input_price_per_1k_usd, output_price_per_1k_usd}` — Decimal as string | JSON Decimal 안전성 (float 부동소수 회피) — Pydantic v2 `Decimal` type이 자동 처리 |

---

## 2. Architecture

### 2.1 Component Diagram (M4 추가 컴포넌트)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        HTTP Layer (FastAPI)                               │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ agent_run_router.py   ★ NEW                                       │    │
│  │  GET  /api/v1/agents/runs/{run_id}                                │    │
│  │  GET  /api/v1/admin/usage/users?from=&to=                         │    │
│  │  GET  /api/v1/admin/usage/llm-models?from=&to=                    │    │
│  │  GET  /api/v1/admin/usage/by-node?from=&to=        ★ M3 효과       │    │
│  │  GET  /api/v1/usage/me?from=&to=                                  │    │
│  ├──────────────────────────────────────────────────────────────────┤    │
│  │ llm_model_router.py  (patch)                                      │    │
│  │  PATCH /api/v1/llm-models/{id}/pricing  ★ M1 G1                   │    │
│  └─────────────────────────┬────────────────────────────────────────┘    │
└────────────────────────────┼────────────────────────────────────────────┘
                             │ Depends(use_case)
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       Application Layer                                   │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ application/agent_run/use_cases/                       ★ NEW dir  │    │
│  │  ├─ get_run_detail_use_case.py         (5 repo fetches + join)    │    │
│  │  ├─ get_usage_by_user_use_case.py      (aggregator wrapper)       │    │
│  │  ├─ get_usage_by_llm_use_case.py       (aggregator wrapper)       │    │
│  │  ├─ get_usage_by_node_use_case.py      (aggregator wrapper)       │    │
│  │  └─ get_usage_me_use_case.py           (for_user wrapper)         │    │
│  │                                                                    │    │
│  │ application/llm_model/                                            │    │
│  │  └─ update_llm_model_pricing_use_case.py   ★ NEW                  │    │
│  │      execute(id, req) →                                            │    │
│  │        repo.find_by_id → mutate prices → repo.update              │    │
│  │        → cost_calculator.invalidate(id)  ★ M1 G1 의무              │    │
│  │                                                                    │    │
│  │ application/agent_run/aggregator.py (modified)                    │    │
│  │  + by_node(from, to) -> List[NodeUsageRow]                        │    │
│  │                                                                    │    │
│  │ application/rag_agent/tools.py (modified)                         │    │
│  │  InternalDocumentSearchTool._format_results:                      │    │
│  │   + best-effort record_retrieval loop                             │    │
│  │     (uses RunContext.run_id / tool_call_id auto-set by M2)        │    │
│  └─────────────────────────┬────────────────────────────────────────┘    │
└────────────────────────────┼────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       Infrastructure / Domain                             │
│  domain/agent_run/interfaces.py (modified)                                │
│   + NodeUsageRow dataclass                                                │
│   + LlmCallRepositoryInterface.aggregate_by_node(from, to)                │
│                                                                           │
│  infrastructure/persistence/repositories/llm_call_repository.py (mod)     │
│   + aggregate_by_node SQL — JOIN ai_run_step + GROUP BY node_name         │
│                                                                           │
│  application/agent_run/tracker.py        unchanged (record_retrieval 활용)│
│  application/agent_run/cost_calculator.py unchanged (invalidate 활용)     │
│  application/agent_run/context.py        unchanged (RunContext 활용)      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 RAG Retrieval Wiring Data Flow

```
[LangGraph worker_react node body]
  ↓ tool invocation
[InternalDocumentSearchTool._arun]
  ↓
[BaseTool.ainvoke 표준 hook 발화 (M2 wiring)]
  ↓
[UsageCallback.on_tool_start → tracker.record_tool_call → tool_call_id 발급]
[UsageCallback._current_tool_call_id = tool_call_id]
[RunContext.tool_call_id ★ M2가 set]
  ↓
[InternalDocumentSearchTool._arun 본문 진행]
  ↓ hybrid_search_use_case.execute(...) → HybridSearchResponse(results=[...])
  ↓
[InternalDocumentSearchTool._format_results(results)]  ★ M4 wiring 지점
  │
  ├─ ctx = get_current_run_context()
  │  if ctx is None or ctx.run_id is None:
  │      → 영속화 skip (graph 외 호출용 fallback)
  │
  ├─ for rank_index, hit in enumerate(results, start=1):
  │      collected_sources.append(...)    # 기존 로직 (반환문에 영향)
  │      try:
  │          await tracker.record_retrieval(
  │              run_id=ctx.run_id,
  │              tool_call_id=ctx.tool_call_id,        ★ M2가 채움
  │              collection_name=self.collection_name or hit.metadata.get("collection") or "unknown",
  │              document_id=hit.metadata.get("document_id"),
  │              chunk_id=hit.id,
  │              score=hit.score,
  │              rank_index=rank_index,
  │              content_preview=hit.content[:cfg.retrieval_preview_max_bytes],
  │              metadata=hit.metadata,
  │          )
  │      except Exception as e:
  │          logger.warning("record_retrieval failed (best-effort)", exception=e)
  │          continue  # 다음 hit 계속
  │
  └─ return "\n\n".join(lines)  # 기존 반환

[UsageCallback.on_tool_end → tracker.update_tool_call(SUCCESS) (M2)]
[ai_retrieval_source 테이블에 N row INSERT 완료]
```

**핵심**: ToolFactory/Spec 변경 0 — `InternalDocumentSearchTool`이 tracker DI를 받는 방식이 필요. 두 옵션:

| 옵션 | 방법 | 결정 |
|------|------|------|
| A | `InternalDocumentSearchTool`에 `tracker` 필드 추가 + `tool_factory.py`에서 주입 | **채택** — 명시적 DI |
| B | `RunContext`에 `tracker` 포함 → tool이 ContextVar에서 read | DDD: tracker는 application 책임. ContextVar에 넣으면 책임 영역 모호 |

**채택 (A) + 최소 침습**: `tool_factory.py`에 `tracker` 파라미터 1개 추가, `workflow_compiler.py`가 호출 시 자기 tracker를 전달 (M3가 이미 받음).

### 2.3 Run Detail Tree Assembly Flow

```
GET /api/v1/agents/runs/{run_id}
  ↓ require auth
[agent_run_router.get_run_detail(run_id, current_user)]
  ↓
[GetRunDetailUseCase.execute(run_id, requesting_user)]
  │
  ├─ run = await agent_run_repo.find_run(RunId(run_id))
  │   ├─ if run is None  → raise NotFoundError → 404
  │   └─ if run.user_id != requesting_user.id and requesting_user.role != ADMIN
  │       → raise ForbiddenError → 403
  │
  ├─ # 4개 batch fetch (모두 단일 SQL, run_id 단일 인덱스 활용)
  ├─ steps      = await agent_run_repo.find_steps(RunId(run_id))       # ORDER BY step_index
  ├─ tool_calls = await agent_run_repo.find_tool_calls(RunId(run_id))
  ├─ retrievals = await agent_run_repo.find_retrievals(RunId(run_id))
  └─ llm_calls  = await llm_call_repo.find_by_run(RunId(run_id))
  ↓
[Client-side join in memory]
  ├─ tool_calls_by_step      = { step_id: [tool_call, ...] }
  ├─ llm_calls_by_step       = { step_id: [llm_call, ...] }
  ├─ llm_calls_by_tool_call  = { tool_call_id: [llm_call, ...] }   # tool 내부 LLM
  └─ retrievals_by_tool_call = { tool_call_id: [retrieval, ...] }
  ↓
[tree_dto = RunDetailDto(
   run=RunRow.from_domain(run),
   steps=[
     StepRow(
       ...,
       tool_calls=[
         ToolCallRow(..., retrievals=retrievals_by_tool_call.get(tc.id, []),
                          llm_calls=llm_calls_by_tool_call.get(tc.id, [])
                    ) for tc in tool_calls_by_step.get(step.id, [])
       ],
       llm_calls=llm_calls_by_step.get(step.id, []),  # node-level LLM (step_id 있고 tool_call_id NULL)
     )
     for step in steps
   ],
   orphan_llm_calls=llm_calls with step_id IS NULL  # M2 이전 데이터 또는 graph 외 호출
)]
  ↓
return RunDetailResponse.from_dto(tree_dto)
```

**비고**: `llm_calls_by_step`는 `step_id 있고 tool_call_id NULL`인 LLM만 (노드 본문 LLM). `llm_calls_by_tool_call`은 tool 내부 LLM (예: RAG re-rank, query rewrite). 양쪽 모두 step 안에 표시되도록 tool_calls는 step 내부 노드로 그룹화.

### 2.4 Usage Endpoint Flow (3 admin + 1 self)

```
GET /api/v1/admin/usage/users?from=&to=                          [require_role("admin")]
GET /api/v1/admin/usage/llm-models?from=&to=                     [require_role("admin")]
GET /api/v1/admin/usage/by-node?from=&to=    ★ M3 효과            [require_role("admin")]
GET /api/v1/usage/me?from=&to=                                    [get_current_user]
   ↓
[Router parses from/to (default = NOW - 30 days)]
   ↓
[Period validation: to - from <= 366 days, from <= to]
   ↓
[GetUsageByXxxUseCase.execute(from, to[, user_id])]
   ↓
[UsageAggregator.by_user(from, to) | by_llm_model | by_node | for_user]
   ↓
[LlmCallRepository.aggregate_*(...)] — 단일 SQL GROUP BY
   ↓
return UsageByXxxResponse(rows=[...])
```

### 2.5 Pricing PATCH Flow

```
PATCH /api/v1/llm-models/{id}/pricing
  body = { "input_price_per_1k_usd": "0.005", "output_price_per_1k_usd": "0.015" }
  [require_role("admin")]
   ↓
[UpdateLlmModelPricingUseCase.execute(id, req, request_id)]
  ├─ model = await llm_model_repo.find_by_id(id, request_id)
  │   └─ if model is None → raise ValueError("모델을 찾을 수 없습니다") → router maps to 404
  ├─ model.input_price_per_1k_usd  = req.input_price_per_1k_usd
  │  model.output_price_per_1k_usd = req.output_price_per_1k_usd
  │  model.pricing_updated_at      = now_utc()
  │  model.updated_at              = now_utc()
  ├─ updated = await llm_model_repo.update(model, request_id)
  └─ cost_calculator.invalidate(id)   ★ M1 G1 의무 호출 — use case 안에 캡슐화
   ↓
return LlmModelResponse.from_domain(updated)  (★ 가격 필드 포함 확장)
```

---

## 3. Application Layer Design

### 3.1 `GetRunDetailUseCase`

**파일**: `src/application/agent_run/use_cases/get_run_detail_use_case.py`

```python
class GetRunDetailUseCase:
    def __init__(
        self,
        agent_run_repo: AgentRunRepositoryInterface,
        llm_call_repo: LlmCallRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_run_repo = agent_run_repo
        self._llm_call_repo = llm_call_repo
        self._logger = logger

    async def execute(
        self,
        run_id: str,
        requesting_user_id: str,
        is_admin: bool,
    ) -> RunDetailDto:
        """run+steps+tool_calls+retrievals+llm_calls 트리 조립.

        Raises:
            RunNotFoundError: run이 존재하지 않음 (router → 404)
            RunAccessDeniedError: run 존재하나 본인 아님 + non-admin (router → 403)
        """
        rid = RunId(run_id)
        run = await self._agent_run_repo.find_run(rid)
        if run is None:
            raise RunNotFoundError(run_id)
        if run.user_id != requesting_user_id and not is_admin:
            raise RunAccessDeniedError(run_id)

        # 4 batch fetches — 모두 run_id 단일 인덱스, O(1) SQL
        steps = await self._agent_run_repo.find_steps(rid)
        tool_calls = await self._agent_run_repo.find_tool_calls(rid)
        retrievals = await self._agent_run_repo.find_retrievals(rid)
        llm_calls = await self._llm_call_repo.find_by_run(rid)

        return assemble_run_detail(run, steps, tool_calls, retrievals, llm_calls)
```

**assembly 헬퍼**: 같은 파일 또는 `assembler.py` 분리. 함수 ≤40줄 유지.

**예외 클래스** (`src/application/agent_run/exceptions.py` ★ 신규 또는 도메인 errors): `RunNotFoundError(ValueError)`, `RunAccessDeniedError(PermissionError)`. application 레이어 own. domain은 무관.

### 3.2 Usage Query Use Cases (4건)

**파일**: 4개 분리 (단일 책임). 모두 동일 형태 — `UsageAggregator` wrapper:

```python
# get_usage_by_user_use_case.py
class GetUsageByUserUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(self, from_dt: datetime, to_dt: datetime) -> List[UserUsageRow]:
        return await self._aggregator.by_user(from_dt, to_dt)
```

`by_llm` / `by_node` / `me` 동일 패턴. `me`만 `current_user_id: str` 인자 추가 → `for_user(user_id, from, to)` 호출.

> **YAGNI 검토**: 이 4개는 trivial wrapper — 1 파일 `usage_query_use_cases.py`로 합치는 안. 분리 이유: 향후 권한·로깅·캐시 추가 시 단위 분리. **현재 5개 use case 디렉토리 + 5개 파일 명시적 분리 채택** (M3 closure vs method 결정과 같은 류 — 명시성 우선).

### 3.3 `UsageAggregator.by_node`

**파일**: `src/application/agent_run/aggregator.py`

```python
async def by_node(
    self, from_dt: datetime, to_dt: datetime
) -> List[NodeUsageRow]:
    return await self._repo.aggregate_by_node(from_dt, to_dt)
```

3줄 추가.

### 3.4 `UpdateLlmModelPricingUseCase`

**파일**: `src/application/llm_model/update_llm_model_pricing_use_case.py`

```python
class UpdateLlmModelPricingUseCase:
    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        cost_calculator: CostCalculator,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._cost_calc = cost_calculator
        self._logger = logger

    async def execute(
        self,
        model_id: str,
        request: UpdatePricingRequest,
        request_id: str,
    ) -> LlmModelResponse:
        model = await self._repo.find_by_id(model_id, request_id)
        if model is None:
            raise ValueError(f"모델을 찾을 수 없습니다: {model_id}")

        now = datetime.now(timezone.utc)
        model.input_price_per_1k_usd = request.input_price_per_1k_usd
        model.output_price_per_1k_usd = request.output_price_per_1k_usd
        model.pricing_updated_at = now
        model.updated_at = now

        updated = await self._repo.update(model, request_id)

        # ★ M1 G1 의무 — 캡슐화로 빼먹기 불가
        self._cost_calc.invalidate(model_id)

        self._logger.info(
            "LlmModel pricing updated and cache invalidated",
            request_id=request_id,
            model_id=model_id,
            input_price=str(request.input_price_per_1k_usd),
            output_price=str(request.output_price_per_1k_usd),
        )
        return LlmModelResponse.from_domain(updated)
```

### 3.5 `tracker` DI into `InternalDocumentSearchTool`

**파일**: `src/application/rag_agent/tools.py` — `InternalDocumentSearchTool`에 `tracker` 필드 추가.

```python
class InternalDocumentSearchTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    ...
    tracker: Any = None  # RunTracker | None — graph 외 호출 시 None
    logger: Any = None
    config: Any = None   # RunObservabilityConfig

    def _format_results(self, results: list) -> str:
        lines: list[str] = []
        ctx = get_current_run_context() if self.tracker is not None else None
        for rank_index, hit in enumerate(results, start=1):
            source = hit.metadata.get("source", "unknown")
            self.collected_sources.append(
                DocumentSource(content=hit.content, source=source, chunk_id=hit.id, score=hit.score)
            )
            lines.append(f"[출처: {source}]\n{hit.content}")

            if ctx is not None and ctx.run_id is not None:
                # best-effort fire-and-forget — 동기 메서드 안에서 async 호출
                # → 옵션 B: _format_results를 async로 승격. 호출자 _single/_multi_query_search는 이미 async
                # → 또는 옵션 C: asyncio.create_task로 fire-and-forget
                # Design 결정: 옵션 B (await + try/except) — 데이터 일관성 우선, 성능 영향 미미 (이미 await search)
                pass  # 실제 await는 _format_results를 async로 변경 후 (3.5-2 참조)
        return "\n\n".join(lines)
```

**3.5-2 동기/비동기 결정**: 현재 `_format_results`는 동기. 두 옵션:

| 옵션 | 방법 | 결정 |
|------|------|------|
| B | `_format_results`를 `async def`로 변경 + 호출자 `_single_query_search`/`_multi_query_search`에서 `await` | **채택** — 호출자가 이미 async, 한 함수 시그니처 변경 |
| C | `asyncio.create_task(tracker.record_retrieval(...))` fire-and-forget | run lifecycle보다 INSERT가 늦게 끝나면 race. 거부 |

**최종 패턴**:

```python
async def _format_results(self, results: list) -> str:
    lines: list[str] = []
    ctx = get_current_run_context() if self.tracker is not None else None
    for rank_index, hit in enumerate(results, start=1):
        source = hit.metadata.get("source", "unknown")
        self.collected_sources.append(
            DocumentSource(content=hit.content, source=source, chunk_id=hit.id, score=hit.score)
        )
        lines.append(f"[출처: {source}]\n{hit.content}")

        if ctx is None or ctx.run_id is None:
            continue
        try:
            preview_max = (self.config or _DEFAULT_CFG).retrieval_preview_max_bytes
            await self.tracker.record_retrieval(
                run_id=ctx.run_id,
                tool_call_id=ctx.tool_call_id,
                collection_name=self.collection_name or hit.metadata.get("collection") or "unknown",
                document_id=hit.metadata.get("document_id"),
                chunk_id=hit.id,
                score=hit.score,
                rank_index=rank_index,
                content_preview=hit.content[:preview_max] if hit.content else None,
                metadata=hit.metadata,
            )
        except Exception as e:
            if self.logger is not None:
                self.logger.warning(
                    "record_retrieval failed in InternalDocumentSearchTool (best-effort)",
                    exception=e,
                    chunk_id=hit.id,
                )
            # continue — 다음 hit 계속
    return "\n\n".join(lines)
```

호출자 변경 (2 곳):
```python
return self._format_results(result.results)
→
return await self._format_results(result.results)
```

---

## 4. Domain Layer Changes

### 4.1 `NodeUsageRow` dataclass

**파일**: `src/domain/agent_run/interfaces.py` (UserUsageRow/LlmUsageRow와 동일 위치).

```python
@dataclass(frozen=True)
class NodeUsageRow:
    """노드별 기간 집계 결과 (★ M3 step_id JOIN 효과).

    step_id가 NULL인 LLM 호출은 자연 제외 (M2 이전 데이터 / graph 외 호출).
    """
    node_name: str
    call_count: int
    total_tokens: int
    total_cost_usd: Decimal
```

### 4.2 `LlmCallRepositoryInterface.aggregate_by_node`

```python
class LlmCallRepositoryInterface(ABC):
    ...
    @abstractmethod
    async def aggregate_by_node(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[NodeUsageRow]: ...
```

### 4.3 Domain 변경 없음 항목

- `AgentRunStep` / `LlmCall` / `RetrievalSource` 엔티티: 그대로
- `NodeType` enum: 그대로 (M3에서 OTHER 재활용 결정 유지 — M4가 UI 노출 시 enum 추가 검토는 후속 PDCA)
- value_objects.py: 그대로
- policies.py: 그대로

---

## 5. Infrastructure Layer Design

### 5.1 `SqlAlchemyLlmCallRepository.aggregate_by_node`

**파일**: `src/infrastructure/persistence/repositories/llm_call_repository.py`

```python
async def aggregate_by_node(
    self, from_dt: datetime, to_dt: datetime
) -> List[NodeUsageRow]:
    """JOIN ai_run_step → GROUP BY node_name.

    SELECT s.node_name,
           COALESCE(SUM(l.total_tokens), 0)     AS tokens,
           COALESCE(SUM(l.total_cost_usd), 0)   AS cost,
           COUNT(*)                              AS calls
      FROM ai_llm_call l
      INNER JOIN ai_run_step s ON s.id = l.step_id
     WHERE l.created_at BETWEEN :from AND :to
     GROUP BY s.node_name
    """
    stmt = (
        select(
            AgentRunStepModel.node_name.label("node_name"),
            func.coalesce(func.sum(LlmCallModel.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(LlmCallModel.total_cost_usd), 0).label("cost"),
            func.count().label("calls"),
        )
        .join(AgentRunStepModel, AgentRunStepModel.id == LlmCallModel.step_id)  # INNER JOIN
        .where(LlmCallModel.created_at.between(from_dt, to_dt))
        .group_by(AgentRunStepModel.node_name)
    )
    rows = (await self._session.execute(stmt)).all()
    return [
        NodeUsageRow(
            node_name=r.node_name,
            call_count=int(r.calls),
            total_tokens=int(r.tokens),
            total_cost_usd=Decimal(r.cost),
        )
        for r in rows
    ]
```

**Note**: `INNER JOIN`이라 `step_id IS NULL`인 행은 자연 제외 — Plan §5-2 정책과 일관.

### 5.2 `RetrievalSource.metadata_json` 직렬화

V021 schema: `metadata_json JSON NULL` — MySQL JSON 컬럼. SQLAlchemy `JSON` type 자동 처리. M1이 이미 `metadata_json: Optional[dict]`로 처리 — M4 변경 0.

크기 안전 장치: `len(json.dumps(hit.metadata))` 가 비정상적으로 큰 (>8KB) 경우 worker LLM의 hit.metadata가 이상한 — Risk §10에서 다룸. 1차 컷오프 없이 진행, 운영 모니터링.

### 5.3 LlmModelRepository — 변경 없음

기존 `update()` 메서드가 `input_price_per_1k_usd / output_price_per_1k_usd / pricing_updated_at` 컬럼을 이미 갱신. M4가 호출만.

### 5.4 ToolFactory — `tracker` 주입

**파일**: `src/infrastructure/agent_builder/tool_factory.py`

```python
class ToolFactory:
    def __init__(
        self,
        logger: LoggerInterface,
        hybrid_search_use_case=None,
        hybrid_search_use_case_getter=None,
        tavily_api_key=None,
        mcp_tool_loader=None,
        tracker=None,                     # ★ NEW
        run_observability_config=None,    # ★ NEW (optional — RunObservabilityConfig)
    ) -> None:
        ...
        self._tracker = tracker
        self._cfg = run_observability_config

    def create(...) -> BaseTool:
        match tool_id:
            case "internal_document_search":
                ...
                return InternalDocumentSearchTool(
                    hybrid_search_use_case=...,
                    ...,
                    tracker=self._tracker,         # ★ NEW
                    logger=self._logger,            # ★ NEW (warning log용)
                    config=self._cfg,               # ★ NEW
                )
```

호출자 (`workflow_compiler.py`): ToolFactory 생성 시 `tracker=self._tracker` 전달 — `WorkflowCompiler.compile`이 M3에서 이미 `tracker` 인자 수신.

---

## 6. Interfaces (HTTP) Layer Design

### 6.1 `agent_run_router.py` ★ 신규

**파일**: `src/api/routes/agent_run_router.py`

```python
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.application.agent_run.exceptions import RunAccessDeniedError, RunNotFoundError
from src.application.agent_run.use_cases.get_run_detail_use_case import GetRunDetailUseCase
from src.application.agent_run.use_cases.get_usage_by_user_use_case import GetUsageByUserUseCase
from src.application.agent_run.use_cases.get_usage_by_llm_use_case import GetUsageByLlmUseCase
from src.application.agent_run.use_cases.get_usage_by_node_use_case import GetUsageByNodeUseCase
from src.application.agent_run.use_cases.get_usage_me_use_case import GetUsageMeUseCase
from src.domain.auth.entities import User, UserRole
from src.interfaces.dependencies.auth import get_current_user, require_role
from src.interfaces.schemas.agent_run_response import (
    RunDetailResponse,
    UsageByUserResponse,
    UsageByLlmResponse,
    UsageByNodeResponse,
)

router = APIRouter(prefix="/api/v1", tags=["agent-run-observability"])


# -------- DI placeholders --------

def get_run_detail_use_case() -> GetRunDetailUseCase:
    raise NotImplementedError

def get_usage_by_user_use_case() -> GetUsageByUserUseCase:
    raise NotImplementedError

def get_usage_by_llm_use_case() -> GetUsageByLlmUseCase:
    raise NotImplementedError

def get_usage_by_node_use_case() -> GetUsageByNodeUseCase:
    raise NotImplementedError

def get_usage_me_use_case() -> GetUsageMeUseCase:
    raise NotImplementedError


# -------- Helper --------

def _resolve_period(
    from_: Optional[datetime], to: Optional[datetime]
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    to_dt = to or now
    from_dt = from_ or (to_dt - timedelta(days=30))
    if from_dt > to_dt:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "from must be <= to")
    if (to_dt - from_dt).days > 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "period must be <= 366 days")
    return from_dt, to_dt


# -------- Endpoints --------

@router.get("/agents/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(
    run_id: str,
    current_user: User = Depends(get_current_user),
    use_case: GetRunDetailUseCase = Depends(get_run_detail_use_case),
) -> RunDetailResponse:
    """Run 상세 트리: run + steps + tool_calls + retrievals + llm_calls."""
    is_admin = current_user.role == UserRole.ADMIN
    try:
        dto = await use_case.execute(
            run_id=run_id,
            requesting_user_id=str(current_user.id),
            is_admin=is_admin,
        )
        return RunDetailResponse.from_dto(dto)
    except RunNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run not found: {run_id}")
    except RunAccessDeniedError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


@router.get("/admin/usage/users", response_model=UsageByUserResponse)
async def get_admin_usage_by_user(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageByUserUseCase = Depends(get_usage_by_user_use_case),
) -> UsageByUserResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    rows = await use_case.execute(from_dt, to_dt)
    return UsageByUserResponse.from_rows(rows, from_dt=from_dt, to_dt=to_dt)


@router.get("/admin/usage/llm-models", response_model=UsageByLlmResponse)
async def get_admin_usage_by_llm(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageByLlmUseCase = Depends(get_usage_by_llm_use_case),
) -> UsageByLlmResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    rows = await use_case.execute(from_dt, to_dt)
    return UsageByLlmResponse.from_rows(rows, from_dt=from_dt, to_dt=to_dt)


@router.get("/admin/usage/by-node", response_model=UsageByNodeResponse)
async def get_admin_usage_by_node(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageByNodeUseCase = Depends(get_usage_by_node_use_case),
) -> UsageByNodeResponse:
    """★ M3 효과 — 노드별 토큰/비용 GROUP BY."""
    from_dt, to_dt = _resolve_period(from_, to)
    rows = await use_case.execute(from_dt, to_dt)
    return UsageByNodeResponse.from_rows(rows, from_dt=from_dt, to_dt=to_dt)


@router.get("/usage/me", response_model=UsageByLlmResponse)
async def get_usage_me(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    use_case: GetUsageMeUseCase = Depends(get_usage_me_use_case),
) -> UsageByLlmResponse:
    """현재 사용자 본인의 LLM 모델별 사용량."""
    from_dt, to_dt = _resolve_period(from_, to)
    rows = await use_case.execute(str(current_user.id), from_dt, to_dt)
    return UsageByLlmResponse.from_rows(rows, from_dt=from_dt, to_dt=to_dt)
```

### 6.2 `llm_model_router.py` 패치 — PATCH /pricing

```python
from src.application.llm_model.update_llm_model_pricing_use_case import (
    UpdateLlmModelPricingUseCase,
)
from src.application.llm_model.schemas import UpdatePricingRequest

def get_update_llm_model_pricing_use_case() -> UpdateLlmModelPricingUseCase:
    raise NotImplementedError


@router.patch("/{model_id}/pricing", response_model=LlmModelResponse)
async def update_llm_model_pricing(
    model_id: str,
    body: UpdatePricingRequest,
    _: User = Depends(require_role("admin")),
    use_case: UpdateLlmModelPricingUseCase = Depends(
        get_update_llm_model_pricing_use_case
    ),
) -> LlmModelResponse:
    """LLM 모델 가격 변경 + 캐시 무효화 (관리자 전용, ★ M1 G1)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(model_id, body, request_id=request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
```

### 6.3 Pydantic Schemas — Response DTOs

**파일**: `src/interfaces/schemas/agent_run_response.py` ★ 신규

`RunDetailResponse` (요약 — 핵심 필드):

```python
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

class TokenUsageDto(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class CostUsdDto(BaseModel):
    input_usd: Decimal = Decimal("0")
    output_usd: Decimal = Decimal("0")
    total_usd: Decimal = Decimal("0")

class RetrievalDto(BaseModel):
    id: str
    collection_name: str
    document_id: Optional[str]
    chunk_id: Optional[str]
    score: Optional[float]
    rank_index: Optional[int]
    content_preview: Optional[str]
    created_at: datetime

class LlmCallDto(BaseModel):
    id: str
    purpose: Optional[str]
    provider: str
    model_name: str
    llm_model_id: Optional[str]
    token_usage: TokenUsageDto
    cost_usd: CostUsdDto
    latency_ms: Optional[int]
    status: str
    created_at: datetime

class ToolCallDto(BaseModel):
    id: str
    tool_name: str
    arguments: Optional[dict]
    result_summary: Optional[str]
    latency_ms: Optional[int]
    status: str
    retrievals: list[RetrievalDto] = []
    llm_calls: list[LlmCallDto] = []  # tool 내부 LLM (re-rank, multi-query 등)

class StepDto(BaseModel):
    id: str
    step_index: int
    node_name: str
    node_type: str
    status: str
    input_summary: Optional[str]
    output_summary: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    latency_ms: Optional[int]
    error_text: Optional[str]
    llm_calls: list[LlmCallDto] = []   # 노드 본문 LLM (tool_call_id NULL, step_id 있음)
    tool_calls: list[ToolCallDto] = []

class RunDto(BaseModel):
    id: str
    status: str
    user_id: str
    agent_id: str
    conversation_id: str
    llm_model_id: Optional[str]
    langgraph_thread_id: str
    langsmith_trace_id: Optional[str]
    langsmith_run_url: Optional[str]
    token_usage: TokenUsageDto
    cost_usd: CostUsdDto
    llm_call_count: int
    started_at: datetime
    ended_at: Optional[datetime]
    latency_ms: Optional[int]
    error_message: Optional[str]
    # error_stack은 응답 미포함 (디버깅 별도 API)

class RunDetailResponse(BaseModel):
    run: RunDto
    steps: list[StepDto] = []
    orphan_llm_calls: list[LlmCallDto] = []   # step_id IS NULL (M2 이전 또는 graph 외)

    @classmethod
    def from_dto(cls, dto) -> "RunDetailResponse": ...
```

`UsageByUserResponse`:

```python
class UsageByUserRow(BaseModel):
    user_id: str
    total_tokens: int
    total_cost_usd: Decimal
    call_count: int

class UsageByUserResponse(BaseModel):
    from_dt: datetime
    to_dt: datetime
    rows: list[UsageByUserRow]
```

`UsageByLlmResponse` / `UsageByNodeResponse` 동일 형태.

`UpdatePricingRequest`:

```python
class UpdatePricingRequest(BaseModel):
    input_price_per_1k_usd: Decimal = Field(..., ge=0)
    output_price_per_1k_usd: Decimal = Field(..., ge=0)
```

`LlmModelResponse` 확장 (`src/application/llm_model/schemas.py`):

```python
class LlmModelResponse(BaseModel):
    id: str
    provider: str
    model_name: str
    display_name: str
    description: str | None
    max_tokens: int | None
    is_active: bool
    is_default: bool
    # ★ M4 additive
    input_price_per_1k_usd: Decimal | None = None
    output_price_per_1k_usd: Decimal | None = None
    pricing_updated_at: datetime | None = None

    @classmethod
    def from_domain(cls, model: LlmModel) -> "LlmModelResponse":
        return cls(
            ...,
            input_price_per_1k_usd=model.input_price_per_1k_usd,
            output_price_per_1k_usd=model.output_price_per_1k_usd,
            pricing_updated_at=model.pricing_updated_at,
        )
```

기존 frontend 영향 0 (옵셔널 필드).

---

## 7. Wiring (api/main.py)

### 7.1 신규 DI factory

```python
# imports
from src.application.agent_run.use_cases.get_run_detail_use_case import GetRunDetailUseCase
from src.application.agent_run.use_cases.get_usage_by_user_use_case import GetUsageByUserUseCase
from src.application.agent_run.use_cases.get_usage_by_llm_use_case import GetUsageByLlmUseCase
from src.application.agent_run.use_cases.get_usage_by_node_use_case import GetUsageByNodeUseCase
from src.application.agent_run.use_cases.get_usage_me_use_case import GetUsageMeUseCase
from src.application.llm_model.update_llm_model_pricing_use_case import UpdateLlmModelPricingUseCase
from src.api.routes import agent_run_router

# DI factories (이미 생성된 cost_calculator / agent_run_repo / llm_call_repo / usage_aggregator 재사용)

def get_run_detail_use_case_factory(
    session: AsyncSession = Depends(get_session),
) -> GetRunDetailUseCase:
    return GetRunDetailUseCase(
        agent_run_repo=SqlAlchemyAgentRunRepository(session),
        llm_call_repo=SqlAlchemyLlmCallRepository(session),
        logger=app_logger,
    )

# Usage 4건: aggregator는 read-only이므로 app-level singleton 가능
# 단, repository session은 request scope이므로 use case도 request scope으로 유지

def get_usage_by_user_factory(...) -> GetUsageByUserUseCase: ...
# 동일 패턴

def get_update_pricing_factory(
    session: AsyncSession = Depends(get_session),
) -> UpdateLlmModelPricingUseCase:
    return UpdateLlmModelPricingUseCase(
        repository=LlmModelRepository(session, logger=app_logger),
        cost_calculator=app_cost_calculator,  # ★ 앱 시작 시 만든 싱글톤 (M1 인스턴스 재사용)
        logger=app_logger,
    )

# Router include + override
app.include_router(agent_run_router.router)
app.dependency_overrides[agent_run_router.get_run_detail_use_case] = get_run_detail_use_case_factory
app.dependency_overrides[agent_run_router.get_usage_by_user_use_case] = get_usage_by_user_factory
app.dependency_overrides[agent_run_router.get_usage_by_llm_use_case] = get_usage_by_llm_factory
app.dependency_overrides[agent_run_router.get_usage_by_node_use_case] = get_usage_by_node_factory
app.dependency_overrides[agent_run_router.get_usage_me_use_case] = get_usage_me_factory
app.dependency_overrides[llm_model_router.get_update_llm_model_pricing_use_case] = get_update_pricing_factory
```

### 7.2 ToolFactory tracker 주입

`workflow_compiler.py`가 이미 tracker DI 받음 (M3). ToolFactory 생성 지점에 tracker 전달 1줄 추가:

```python
self._tool_factory = ToolFactory(
    logger=self._logger,
    hybrid_search_use_case_getter=...,
    tavily_api_key=...,
    mcp_tool_loader=...,
    tracker=tracker,                                # ★ M4 추가
    run_observability_config=RunObservabilityConfig(),  # ★ M4 추가
)
```

**ToolFactory 위치**: `WorkflowCompiler.compile()`이 내부에서 ToolFactory 생성하는지 / 외부 주입인지 확인 필요. Design 시점 가정: compile() 호출자가 tool_factory를 주입 → main.py에서 tracker 함께 전달. 또는 compile()이 받은 tracker를 ToolFactory에 forward (M3가 이미 받음).

---

## 8. Permission Matrix

| Endpoint | 인증 | 권한 | 추가 검증 |
|----------|------|------|----------|
| `GET /api/v1/agents/runs/{run_id}` | Required | run.user_id == current_user **OR** admin | 외 → 403; 미존재 → 404 |
| `GET /api/v1/admin/usage/users` | Required | admin only | period validation |
| `GET /api/v1/admin/usage/llm-models` | Required | admin only | period validation |
| `GET /api/v1/admin/usage/by-node` | Required | admin only | period validation |
| `GET /api/v1/usage/me` | Required | 본인 (current_user) | period validation |
| `PATCH /api/v1/llm-models/{id}/pricing` | Required | admin only | body Decimal validation (≥0) |

**`current_user.id` 타입 주의**: `User.id: Optional[int]`. `ai_llm_call.user_id`는 `str(VARCHAR)` — M1·M2가 이미 `str(user_id)` 처리. M4 use case에서도 `requesting_user_id=str(current_user.id)` 일관.

---

## 9. Test Strategy

### 9.1 단위 테스트 매트릭스

| 모듈 | 파일 | 케이스 수 | 핵심 검증 |
|------|------|----------|----------|
| `InternalDocumentSearchTool` retrieval | `tests/application/rag_agent/test_internal_document_search_retrieval.py` | 4 | per-hit record_retrieval / ctx None skip / tool_call_id 전달 / best-effort 격리 |
| `aggregate_by_node` repository | `tests/infrastructure/persistence/test_llm_call_aggregate_by_node.py` | 3 | GROUP BY / NULL step_id 제외 / from-to window |
| `GetRunDetailUseCase` | `tests/application/agent_run/test_get_run_detail_use_case.py` | 6 | 트리 조립 / 404 / 403 / orphan / empty branch / N+1 (≤5 repo call) |
| `UsageAggregator.by_node` | `tests/application/agent_run/test_aggregator_by_node.py` | 1 | delegate |
| 4 usage query use case | `tests/application/agent_run/use_cases/test_usage_query_use_cases.py` | 4 | delegate to aggregator |
| `UpdateLlmModelPricingUseCase` | `tests/application/llm_model/test_update_pricing_use_case.py` | 4 | 가격 저장 / pricing_updated_at NOW / **invalidate 호출** / not found |
| `agent_run_router` | `tests/api/test_agent_run_router.py` | 8 | 200 owner / 200 admin / 403 / 404 / admin role / period 422 / orphan / `/usage/me` self only |
| `llm_model_router` PATCH | `tests/api/test_llm_model_router_pricing.py` | 3 | 200 + body / 403 non-admin / 404 not found |

**총**: ~33 new test cases. M1·M2·M3 회귀 가드 ~200 case + workspace 통합 테스트는 별도.

### 9.2 핵심 회귀 가드 (3건)

1. **`test_record_retrieval_failure_does_not_break_tool_output`** — RAG 답변이 retrieval 실패로 끊기지 않음 (best-effort)
2. **`test_calls_cost_calculator_invalidate_with_model_id`** — M1 G1 의무 (mock `cost_calculator.invalidate(model_id)` 호출 검증)
3. **`test_get_run_detail_returns_403_for_other_user_non_admin`** — 권한 안전성

### 9.3 통합 검증 (수동)

Plan §12.3 항목 8건. 핵심 SQL 3건:
```sql
-- (1) RAG retrieval row 채워짐
SELECT rs.rank_index, rs.score, rs.chunk_id, tc.tool_name, s.node_name
  FROM ai_retrieval_source rs
  JOIN ai_tool_call tc ON tc.id = rs.tool_call_id
  JOIN ai_run_step  s  ON s.id  = tc.step_id
 WHERE rs.run_id = ? ORDER BY rs.rank_index;
-- 결과: top_k row, tool_call_id NOT NULL, node_name = 'worker_*'

-- (2) by-node 집계
SELECT node_name, total_tokens, total_cost_usd, call_count
  FROM (
    SELECT s.node_name,
           SUM(l.total_tokens) AS total_tokens,
           SUM(l.total_cost_usd) AS total_cost_usd,
           COUNT(*) AS call_count
      FROM ai_llm_call l
      JOIN ai_run_step s ON s.id = l.step_id
     WHERE l.created_at >= ? AND l.created_at < ?
     GROUP BY s.node_name
  ) t
 ORDER BY total_cost_usd DESC;
-- 결과: supervisor / worker_* / quality_gate / answer_agent 분리

-- (3) 가격 PATCH 후 캐시 영향
-- PATCH 직후 같은 model_id로 LLM 호출 → ai_llm_call.input_price_per_1k_usd / output_price_per_1k_usd가 새 값
```

---

## 10. Risk Mitigation

| 위험 | 영향 | 가능성 | M4 대응 |
|------|------|--------|---------|
| `_format_results` 동기 → 비동기 변경 시 호출자 누락 | RAG 도구 깨짐 | Low | 호출자 2곳(`_single_query_search`, `_multi_query_search`) 명시 + grep 가드 + integration test |
| `record_retrieval` 가 hit 5개에 대해 5회 commit → 트랜잭션 부하 | DB 부하 ↑ | Medium | M1 tracker가 이미 메서드별 session-per-operation 패턴. 1회 INSERT → 1 commit. 운영 환경에서는 INSERT 5건 << LLM 호출 latency. 향후 bulk insert 최적화 별도 PDCA |
| Run 상세 응답이 step/tool/retrieval 많을 시 페이로드 폭증 | 네트워크 부하 | Low | 한 run의 step ≤ 20, tool_call ≤ 30, retrieval ≤ 50 가정. 1 run ≤ 200KB. 초과 시 pagination 별도 |
| `current_user.id` int → 문자열 변환 일관성 | user_id 불일치로 권한 분기 오동작 | Medium | M1·M2가 이미 `str(user_id)` 일관 — `tracker.start_run` 시점부터 string. M4 use case에서도 `str(current_user.id)` 명시 |
| 가격 캐시 invalidate 누락 (M1 G1 재발) | 가격 변경 후 5분간 stale | High (원인) | use case 안에 캡슐화 + 단위 테스트로 검증. router는 호출 의무 없음 (use case가 책임) |
| Decimal JSON 직렬화 | float 부동소수 오차 | Low | Pydantic v2가 Decimal → JSON string 직렬화. 클라이언트는 string으로 받아 BigDecimal 처리 가능 |
| `JOIN ai_run_step` 슬로우 — 큰 데이터셋 | by-node API latency ↑ | Medium | `ai_llm_call.step_id` 컬럼에 인덱스 추가 필요 여부 확인 — V021 schema 점검 |
| `ai_retrieval_source.metadata_json` 큰 메타데이터 | TEXT JSON column 폭증 | Low | hit.metadata 평균 ~1KB. 비정상 케이스는 1차 운영 모니터링 — 별도 컷오프 PDCA |
| RetrievalSource `score` Decimal(10,6) overflow | INSERT 실패 | Very Low | RRF score는 0~1 normalized 또는 작은 양수. 안전 |
| `_resolve_period` default = 최근 30일이 일부 케이스에 부족 | UX 혼선 | Low | from/to 미지정 시 응답 헤더에 실효 from_dt/to_dt 포함 — `UsageByXxxResponse.from_dt/to_dt` 필드로 명시 |
| 다중 동시 PATCH /pricing | DB 마지막 wins / 캐시 race | Low | use case 트랜잭션 안 갱신 + invalidate 후 새 호출이 다시 fetch. race window는 ms 단위 (캐시 inconsistency 5분 → ms로 축소된 셈) |
| `RunAccessDeniedError` → 403 vs leak 우려 | 사용자가 다른 run id를 시도 | Low | run_id UUID4 — 추측 비용 무한. 분리 정책 안전 |
| step.input_summary / output_summary 안에 PII | 응답 leak | Medium | M3 wrapping이 이미 1KB 컷 + supervisor/worker만 사용 — 사용자 질문 원문은 conversation_history 별도. 보안 검토 후 별도 redaction PDCA |

---

## 11. Implementation Order

Plan §6 단계와 정합. 빠진 항목 없음.

1. **M4-1**: `_format_results` async 변경 + `tracker` 필드 추가 + best-effort record_retrieval + 단위 4건 (test-first)
2. **M4-2**: `NodeUsageRow` + `LlmCallRepositoryInterface.aggregate_by_node` (interface 추가) — abc method 실패하는 단위 1건
3. **M4-3**: `SqlAlchemyLlmCallRepository.aggregate_by_node` SQL + 통합 3건 (testcontainer or in-memory MySQL)
4. **M4-4**: `UsageAggregator.by_node` + 단위 1건
5. **M4-5**: `GetRunDetailUseCase` + 단위 6건 (트리 조립 / 404 / 403 / orphan / empty / N+1 가드)
6. **M4-6**: 4 usage query use case + 단위 4건
7. **M4-7**: `UpdateLlmModelPricingUseCase` + 단위 4건 (★ invalidate 호출 가드)
8. **M4-8**: `agent_run_router.py` 신규 + Pydantic schemas + 통합 8건
9. **M4-9**: `llm_model_router.py` PATCH 추가 + 통합 3건
10. **M4-10**: `api/main.py` DI wiring (6 factory)
11. **M4-11**: ToolFactory tracker 주입 + WorkflowCompiler 패스스루
12. **M4-12**: 수동 검증 (실 LLM 1회 + 5 endpoint curl + PATCH 1회)

**핵심 의존성**:
- M4-1 → M4-11 (tracker 주입은 마지막)
- M4-2 → M4-3 → M4-4 → M4-6 (chain)
- M4-3 → M4-5 → M4-8 (chain)
- M4-7 → M4-9 (chain)
- M4-10 은 마지막 wire-up

---

## 12. Open Issues (Design 종료 후 처리)

| Open Issue | 처리 시점 |
|-----------|----------|
| ToolFactory tracker 주입 위치(`__init__` vs `create_async` 시점) — 본 Design은 `__init__` 채택 | Do phase 초반 검증 |
| `_format_results` 위치의 ContextVar read가 cross-thread 우려 (asyncio task별 격리지만 fire-and-forget이 아니므로 안전) | 통합 테스트로 검증 |
| Run 상세에서 `error_stack`을 응답에 포함할지 (현재 미포함) | 어드민 PDCA에서 별도 endpoint(`GET /admin/runs/{id}/error-stack`) 결정 |
| `/admin/runs` list API 부재 → 어드민이 run_id를 어떻게 발견하는가? | 어드민 PDCA에서 별도 list endpoint 추가 |
| 부서별 집계 | 별도 PDCA (`user → department` mapping 도입) |
| `ai_llm_call.step_id`에 인덱스 추가 SQL 마이그레이션 (성능 가드) | by-node API 슬로우 발견 시 별도 마이그레이션 PDCA |

---

## 13. Design 변경 이력

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-05-21 | M4 초안 — Retrieval wiring + 5 read API + Pricing PATCH. Open Issues 6건 모두 결정 완료 (§1.3) |

---

## 14. 참고 자료

- Plan: [agent-run-observability-m4.plan.md](../../01-plan/features/agent-run-observability-m4.plan.md)
- M1 Design (전체 데이터 모델): [agent-run-observability.design.md](../../archive/2026-05/agent-run-observability/agent-run-observability.design.md)
- M2 Design (tool_call_id ContextVar 사전 작업): [agent-run-observability-m2.design.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.design.md)
- M3 Design (step_id ContextVar 사전 작업): [agent-run-observability-m3.design.md](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.design.md)
- V021 schema: `db/migration/V021__create_agent_run_tables.sql`
- 권한 dependency: `src/interfaces/dependencies/auth.py` (`get_current_user`, `require_role`)
- LLM 모델 가격 entity: `src/domain/llm_model/entity.py` (input_price_per_1k_usd / output_price_per_1k_usd / pricing_updated_at)
