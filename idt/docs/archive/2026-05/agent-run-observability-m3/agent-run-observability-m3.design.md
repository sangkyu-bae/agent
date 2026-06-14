# agent-run-observability-m3 Design Document

> **Summary**: M3 — `WorkflowCompiler` 가 `add_node` 호출 시점에 모든 LangGraph 노드를 `track_step(...)` 컨텍스트 매니저로 자동 wrapping. 신규 테이블/도메인 0건, single-point graph build interception.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-21
> **Status**: Draft
> **Planning Doc**: [agent-run-observability-m3.plan.md](../../01-plan/features/agent-run-observability-m3.plan.md)
> **Parent (M1) Design**: [agent-run-observability.design.md](../../archive/2026-05/agent-run-observability/agent-run-observability.design.md)
> **Sibling (M2) Design**: [agent-run-observability-m2.design.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.design.md)

---

## 1. Overview

### 1.1 Design Goals

- M1 "**단일 진입점 인터셉트**" 정신 유지 — 단, 진입점이 callback이 아닌 **graph build 시점** (`WorkflowCompiler.add_node` 직전)
- 모든 LangGraph 노드(supervisor/worker/sub_agent/quality_gate/answer_agent/search) 자동 wrapping — 노드 함수 본문 변경 0
- `ai_run_step` 자동 채움 + `ai_tool_call.step_id` / `ai_llm_call.step_id` FK 자동 채움 (M1·M2 작업의 결실 회수)
- Supervisor `decision.reasoning`을 `output_summary`에 보존 → 사후 추적 가능
- best-effort 격리 — step 기록 실패가 사용자 응답 흐름을 차단하지 않음

### 1.2 Design Principles

- **Single Interception Point (Graph Build)**: 진입점이 callback(M2)이 아닌 `WorkflowCompiler`라는 점만 다르고 정신은 동일 — "노드 함수 6개를 수정하지 말고 6개 add_node 호출 1군데만 손댄다"
- **Domain Closed**: `NodeType` enum 변경 0 — `answer_agent`/`search`는 `NodeType.OTHER`로 매핑 (YAGNI; 명시적 분류는 M4 API 노출 시 별도 PDCA)
- **YAGNI**: 노드 input/output 직렬화는 1KB summary만; stack-based step 중첩은 현 패턴에 없으므로 지원 안 함
- **best-effort isolation**: record_step 실패 시 `step_id=None` → 노드는 정상 실행, `_current_step_id` 미세팅 → 해당 step 범위의 LLM/tool 호출은 step_id=NULL로 기록 (데이터 손실 < 1 step)

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                     RunAgentUseCase.execute()                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  workflow = await compiler.compile(spec, tracker=..., run_id=...)│  │
│  │  graph.ainvoke(state, config={"callbacks": [usage_callback]})  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│              WorkflowCompiler.compile()   ★ M3 wiring 지점             │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ for each (name, fn, node_type) in {supervisor, worker, ...}:    │  │
│  │     wrapped = _with_step_tracking(name, node_type, fn)          │  │
│  │     graph.add_node(name, wrapped)                                │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  graph 실행 (LangChain CallbackManager 자동 전파)
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       LangGraph StateGraph                             │
│                                                                       │
│  supervisor_wrapped ──▶ worker_wrapped ──▶ quality_gate_wrapped ──▶   │
│       │                      │                       │                │
│  ┌────▼──────────────────────▼───────────────────────▼─────────────┐ │
│  │  track_step(name, node_type) 컨텍스트 매니저  ★ M3 신규           │ │
│  │   enter:                                                          │ │
│  │   ├─ step_index = callback._step_index + 1                       │ │
│  │   ├─ step_id = tracker.record_step(STARTED, step_index, name,   │ │
│  │   │                                node_type, input_summary)    │ │
│  │   ├─ callback.enter_step(step_id)  # _step_index += 1            │ │
│  │   └─ ctx = with_step_id(get_ctx(), step_id); set_ctx(ctx)        │ │
│  │   body:                                                          │ │
│  │   ├─ result = await node_fn(state)                               │ │
│  │   │   ↓ (노드 내부 LLM/tool 호출)                                  │ │
│  │   │   ├─ UsageCallback.on_llm_end(...)                          │ │
│  │   │   │    └─ tracker.record_llm_call(step_id=_current_step_id) │ │
│  │   │   └─ UsageCallback.on_tool_start(...)                       │ │
│  │   │        └─ tracker.record_tool_call(step_id=_current_step_id)│ │
│  │   exit (normal):                                                 │ │
│  │   ├─ output_summary = result.pop("_step_output_summary",        │ │
│  │   │                                _summarize_state_output(...))│ │
│  │   ├─ tracker.update_step(SUCCESS, output_summary)                │ │
│  │   ├─ callback.exit_step()  # _current_step_id = None             │ │
│  │   └─ set_ctx(with_step_id(ctx, None))                            │ │
│  │   exit (exception):                                              │ │
│  │   ├─ tracker.update_step(FAILED, error_text=str(e)[:1024])       │ │
│  │   ├─ callback.exit_step()                                        │ │
│  │   ├─ set_ctx(with_step_id(ctx, None))                            │ │
│  │   └─ raise (propagate to fail_run)                               │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│      ai_run_step           ai_tool_call            ai_llm_call        │
│      (M3 채워짐)            (step_id ★ NOT NULL)   (step_id ★ NOT NULL)│
└───────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow (한 run의 4 노드 흐름)

```
1. RunAgentUseCase.execute()
       │
       ├─ tracker.start_run(run_id) → ai_run row 생성 (M1)
       ├─ callback = UsageCallback(tracker, run_id, ...)   # _step_index=0 (M3 신규 필드)
       └─ workflow = compiler.compile(spec, tracker=tracker, callback=callback, ...)
              │
              │  M3: 각 add_node를 _with_step_tracking로 감쌈
              ▼
       graph.ainvoke(state, config={callbacks: [callback]})
              │
              ▼
2. [Step 1] supervisor 진입
       │
       ├─ track_step.__aenter__("supervisor", SUPERVISOR):
       │   ├─ step_index = 1 (callback._step_index → 1)
       │   ├─ step_id_1 = record_step(STARTED, step_index=1, ...) → uuid
       │   ├─ callback.enter_step(step_id_1)  → _current_step_id=step_id_1, _step_index=1
       │   └─ RunContext.step_id = step_id_1
       │
       ├─ supervisor_node body:
       │   ├─ llm.with_structured_output(SupervisorDecision).ainvoke(msgs)
       │   │    └─ on_llm_end → record_llm_call(step_id=step_id_1, purpose=SUPERVISOR) ★
       │   └─ return {"next_worker": "worker_finance", "_step_output_summary": decision.reasoning[:1024]}
       │
       └─ track_step.__aexit__:
           ├─ output_summary = result.pop("_step_output_summary")
           ├─ update_step(step_id_1, SUCCESS, output_summary)
           └─ callback.exit_step()  → _current_step_id=None
              RunContext.step_id = None
              
3. [Step 2] worker_finance 진입 (_wrap_worker가 _with_step_tracking 안에 위치)
       │
       ├─ track_step.__aenter__("worker_finance", WORKER):
       │   ├─ step_index = 2
       │   ├─ step_id_2 = record_step(STARTED, step_index=2, ...)
       │   ├─ callback.enter_step(step_id_2)
       │   └─ RunContext.step_id = step_id_2
       │
       ├─ worker body (react agent):
       │   ├─ llm.ainvoke (worker LLM) → record_llm_call(step_id=step_id_2, purpose=WORKER) ★
       │   ├─ tool.ainvoke (rag_search)
       │   │    └─ on_tool_start → record_tool_call(step_id=step_id_2, ...) ★ M3 효과
       │   │        ├─ purpose=WORKER (M2가 자동 설정)
       │   │        └─ 툴 내부 LLM 호출 → record_llm_call(step_id=step_id_2, tool_call_id=tcid)
       │   └─ return AIMessage
       │
       └─ track_step.__aexit__ → update_step(SUCCESS, output_summary=last_ai_msg_content[:1024])

4. [Step 3] quality_gate 진입 → record_step(GATE) → update_step(SUCCESS, output_summary="passed")

5. [Step 4] answer_agent 진입 → record_step(OTHER) → update_step(SUCCESS, output_summary=answer[:1024])

6. graph 종료
       │
       └─ tracker.complete_run(run_id, ...)
              ├─ SUM(ai_llm_call.* WHERE run_id=?) → ai_run 총합 갱신 (M1)
              └─ status=SUCCESS

7. 어드민 조회:
   SELECT step_index, node_name, node_type, status, latency_ms, output_summary
     FROM ai_run_step WHERE run_id=? ORDER BY step_index;
   → 4 row, step_index = 1,2,3,4
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `track_step` (신규) | `RunTracker.record_step/update_step` (M1) | step lifecycle 영속화 |
| `track_step` (신규) | `UsageCallback.enter_step/exit_step` (M1) | `_current_step_id` set/reset (M1·M2가 이미 tool_call/llm_call에 전달) |
| `track_step` (신규) | `RunContext.with_step_id` (M1) | ContextVar 동기화 (M4 retrieval 사전 작업) |
| `track_step` (신규) | `NodeType` enum (M1 도메인) | record_step의 인자 타입 |
| `_with_step_tracking` (신규) | `track_step` | decorator factory |
| `WorkflowCompiler.compile` (수정) | `_with_step_tracking` | 6개 add_node wrapping |
| `UsageCallback` (수정) | M1 인스턴스 필드 패턴 | `_step_index` 카운터 추가 |
| `supervisor_node` (1줄 수정) | M1 dict return | `_step_output_summary` key 노출 |
| (변경 없음) `RunAgentUseCase` | tracker/callback DI | M1·M2가 이미 callback을 graph에 등록 |
| (변경 없음) `_wrap_worker` / `_wrap_sub_agent` | — | step_tracking이 그 바깥 — token_usage 누적은 step 범위 안에서 자연 동작 |

신규 외부 라이브러리: **없음** (M2와 동일).

---

## 3. Data Model

### 3.1 변경 없음

M1 V021의 `ai_run_step` 컬럼을 그대로 사용. **DB 마이그레이션 0건.**

### 3.2 `ai_run_step` 컬럼별 채움 정책 (M3)

| 컬럼 | 채움 시점 | 값 |
|------|----------|-----|
| `id` | `track_step.__aenter__` | `record_step` 내부 `uuid.uuid4()` |
| `run_id` | 〃 | callback이 보유한 `self._run_id` (M1) |
| `step_index` | 〃 | `callback._step_index` (M3 신규, enter_step에서 monotonic increment, 1부터 시작) |
| `node_name` | 〃 | decorator 인자 (`"supervisor"`, `"worker_finance"`, `"quality_gate"`, `"answer_agent"`, search worker_id) |
| `node_type` | 〃 | decorator 인자 (`NodeType.SUPERVISOR` / `WORKER` / `GATE` / `OTHER`) |
| `llm_model_id` | 〃 | **NULL** — 노드 자체는 LLM 아님; 노드 *내부* LLM은 `ai_llm_call.step_id` JOIN으로 추적 |
| `status` | enter → exit | `STARTED` → `SUCCESS` / `FAILED` |
| `input_summary` | enter | `_summarize_state_input(state)[:1024]` — 마지막 user 메시지 + iteration_count |
| `output_summary` | exit | supervisor: `decision.reasoning[:1024]` (via `_step_output_summary` key) / worker·answer: `last_ai_message.content[:1024]` / quality_gate: `quality_gate_result + retry_counts` 요약 |
| `started_at` | enter | `record_step` 내부 `_utcnow()` |
| `ended_at` | exit | `update_step` 내부 `_utcnow()` (M1 update_step이 자동 set + latency 계산) |
| `latency_ms` | exit | M1 `update_step`이 자동 계산 (`ended_at - started_at`) |
| `error_text` | exit (FAILED) | `str(error)[:1024]` |

### 3.3 NodeType 매핑 결정 (Plan §4-4 해결)

**결정: `NodeType` 도메인 enum 변경 0건. `answer_agent`/`search` → `NodeType.OTHER`.**

| 노드 | M3 매핑 | 근거 |
|------|---------|------|
| `supervisor` | `NodeType.SUPERVISOR` | 명백 |
| 일반 worker (react agent) | `NodeType.WORKER` | 명백 |
| sub_agent (재귀 graph) | `NodeType.WORKER` | "worker처럼 동작하는 컨테이너" — 외부 관점 동일 |
| `quality_gate` | `NodeType.GATE` | M1 enum 정의 그대로 |
| `answer_agent` (search 워커 후 종합) | **`NodeType.OTHER`** | YAGNI — 명시 분류는 M4 API에서 별도 분류 필요해질 때 enum 확장 검토 |
| `search` worker (lambda-like) | `NodeType.WORKER` | 사용자 의도 처리 노드 — worker 의미적 동급 |

**확장 시기**: M4 어드민 API/대시보드가 "answer_agent를 따로 보여달라"고 요구하면 그때 enum에 ANSWER 추가 (1줄 + 마이그레이션 0건 — VARCHAR 컬럼). 현 시점 YAGNI.

### 3.4 ai_run_step status 전이

```
        [INSERT record_step]
                │
                ▼
            ┌────────┐
            │STARTED │
            └────┬───┘
       ┌─────────┼─────────┐
       │         │         │
   [normal exit] [exception] [process kill]
       │         │           │
       ▼         ▼           ▼
   ┌────────┐ ┌────────┐  (orphan: STARTED 잔존)
   │SUCCESS │ │FAILED  │   └─ M4 dashboard에서 detection
   └────────┘ └────────┘     별도 PDCA로 sweep 검토
```

M2와 동일한 best-effort 정책 — orphan STARTED는 운영 모니터링 대상.

### 3.5 Entity Relationships (M3 완료 후)

```
ai_run (M1) 1
  ├─ N ai_run_step (★ M3 채워짐)
  │      ├─ N ai_tool_call (★ step_id 자동 채워짐 — M2가 _current_step_id 사용)
  │      │      └─ N ai_retrieval_source (M4 예정)
  │      └─ N ai_llm_call (★ step_id 자동 채워짐 — M1이 _current_step_id 사용)
  │             └─ tool_call_id FK (M2 채워짐)
  └─ N ai_llm_call (step_id NULL 가능 — graph 외부 LLM 호출)
```

---

## 4. Interface Specification

### 4.1 `track_step` Async Context Manager — `src/application/agent_run/step_tracking.py` (신규)

```python
"""LangGraph 노드 실행 lifecycle을 ai_run_step 테이블에 영속화.

AGENT-OBS-003 §4.1 — async context manager 패턴.
WorkflowCompiler가 모든 add_node 호출을 _with_step_tracking으로 wrapping할 때 사용.
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from src.application.agent_run.context import (
    get_current_run_context,
    set_current_run_context,
    with_step_id,
)
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.domain.logging.interfaces.logger_interface import LoggerInterface


_INPUT_SUMMARY_MAX_CHARS: Final[int] = 1024
_OUTPUT_SUMMARY_MAX_CHARS: Final[int] = 1024
_ERROR_TEXT_MAX_CHARS: Final[int] = 1024


@dataclass
class _StepContext:
    """track_step 컨텍스트 내부에서 노드 본문이 output_summary를 갱신할 수 있도록 노출."""
    step_id: Optional[str]
    output_summary: Optional[str] = None


@asynccontextmanager
async def track_step(
    *,
    tracker: RunTracker,
    callback: "UsageCallback",       # 순환 import 회피 위해 forward ref
    run_id: RunId,
    node_name: str,
    node_type: NodeType,
    input_summary: Optional[str] = None,
    logger: LoggerInterface,
) -> AsyncIterator[_StepContext]:
    """노드 실행 1회의 lifecycle 인터셉트.

    - enter: record_step(STARTED) + callback.enter_step + RunContext.step_id 갱신
    - exit (normal): update_step(SUCCESS, output_summary) + callback.exit_step + 복원
    - exit (exception): update_step(FAILED, error_text) + callback.exit_step + 복원 + re-raise
    - best-effort: record_step 실패 → step_id=None, callback.enter_step skip, update_step skip
    """
    next_index = callback._step_index + 1   # M3: monotonic counter
    step_id = await _record_step_best_effort(
        tracker=tracker, run_id=run_id,
        step_index=next_index, node_name=node_name, node_type=node_type,
        input_summary=_truncate(input_summary, _INPUT_SUMMARY_MAX_CHARS),
        logger=logger,
    )

    prev_step_id = callback._current_step_id
    prev_ctx = get_current_run_context()

    if step_id is not None:
        callback.enter_step(step_id)   # _step_index 자동 increment (4.4 참조)
        if prev_ctx is not None:
            set_current_run_context(with_step_id(prev_ctx, step_id))

    ctx = _StepContext(step_id=step_id)
    try:
        yield ctx
    except BaseException as e:
        await _update_step_best_effort(
            tracker=tracker, run_id=run_id, step_id=step_id,
            status=StepStatus.FAILED,
            output_summary=None,
            error_text=_truncate(str(e), _ERROR_TEXT_MAX_CHARS),
            logger=logger, node_name=node_name,
        )
        _restore_context(callback, prev_step_id, prev_ctx)
        raise
    else:
        await _update_step_best_effort(
            tracker=tracker, run_id=run_id, step_id=step_id,
            status=StepStatus.SUCCESS,
            output_summary=_truncate(ctx.output_summary, _OUTPUT_SUMMARY_MAX_CHARS),
            error_text=None,
            logger=logger, node_name=node_name,
        )
        _restore_context(callback, prev_step_id, prev_ctx)
```

**핵심 보장**:
- `step_id=None` (record_step 실패) 케이스는 `enter_step` 호출 skip → `_current_step_id`/RunContext 미오염
- 예외 경로에서도 `update_step(FAILED)` + 컨텍스트 복원 100% 보장 (try/except/else 패턴 — `finally`를 쓰지 않는 이유는 update_step의 status를 try/except에서 분기해야 하기 때문)

### 4.2 `_with_step_tracking` Decorator Factory — `workflow_compiler.py` 내부

```python
def _with_step_tracking(
    self,
    node_name: str,
    node_type: NodeType,
    fn: Callable[[SupervisorState], Awaitable[dict]],
) -> Callable[[SupervisorState], Awaitable[dict]]:
    """add_node에 등록할 노드 함수를 track_step으로 감싸 반환.

    - tracker / callback / run_id 가 None이면 wrapping 없이 원본 fn 반환 (관측성 비활성)
    - 노드 fn의 return dict에 '_step_output_summary' 키가 있으면 그 값을 output_summary로 사용
    - 위 키가 없으면 dict의 messages 마지막 AIMessage content[:1024]를 사용 (fallback)
    """
    tracker = self._tracker
    callback = self._callback
    run_id = self._run_id

    if tracker is None or callback is None or run_id is None:
        return fn  # 관측성 비활성 — 원본 그대로

    async def wrapped(state: SupervisorState) -> dict:
        input_summary = _summarize_state_input(state)
        async with track_step(
            tracker=tracker, callback=callback, run_id=run_id,
            node_name=node_name, node_type=node_type,
            input_summary=input_summary, logger=self._logger,
        ) as step_ctx:
            result = await fn(state)
            # supervisor가 노출한 reasoning이 있으면 우선
            forced_summary = result.pop("_step_output_summary", None) \
                if isinstance(result, dict) else None
            step_ctx.output_summary = forced_summary or _summarize_state_output(result)
            return result
    return wrapped
```

### 4.3 `WorkflowCompiler.compile()` 변경 — add_node 6 지점

| Before (line ~135) | After (M3) |
|--------------------|------------|
| `graph.add_node("supervisor", supervisor_fn)` | `graph.add_node("supervisor", self._with_step_tracking("supervisor", NodeType.SUPERVISOR, supervisor_fn))` |
| `graph.add_node("quality_gate", quality_gate_fn)` | `graph.add_node("quality_gate", self._with_step_tracking("quality_gate", NodeType.GATE, quality_gate_fn))` |
| `graph.add_node(worker_id, worker_agent)` (lambda branch) | `graph.add_node(worker_id, self._with_step_tracking(worker_id, NodeType.WORKER, worker_agent))` |
| `graph.add_node(worker_id, self._wrap_worker(worker_id, worker_agent))` | `graph.add_node(worker_id, self._with_step_tracking(worker_id, NodeType.WORKER, self._wrap_worker(worker_id, worker_agent)))` |
| `graph.add_node("answer_agent", self._create_answer_node(...))` | `graph.add_node("answer_agent", self._with_step_tracking("answer_agent", NodeType.OTHER, self._create_answer_node(...)))` |
| (sub_agent via `_wrap_sub_agent`) | sub_agent도 동일 — `_wrap_sub_agent` 결과를 `_with_step_tracking` 으로 한번 더 감쌈 |

**wrapping order**: `step_tracking` (outermost) → `_wrap_worker`/`_wrap_sub_agent` (token_usage 누적) → 원본 노드 함수. step 범위가 token_usage 누적 범위를 포함하므로 `ai_run.total_tokens` 와 `ai_run_step` 데이터 모순 없음.

### 4.4 `UsageCallback` 변경 — `_step_index` 카운터 1 필드

```python
class UsageCallback(AsyncCallbackHandler):
    def __init__(self, tracker, run_id, ...):
        # ... M1·M2 기존 필드 ...
        self._current_step_id: Optional[str] = None   # M1
        self._step_index: int = 0                      # M3 신규 — monotonic counter

    def enter_step(self, step_id: str) -> None:        # M1 기존 메서드 보강
        self._current_step_id = step_id
        self._step_index += 1                          # M3: increment

    def exit_step(self) -> None:                       # M1 기존 메서드 (변경 없음)
        self._current_step_id = None
        # _step_index는 reset하지 않음 — run 내 monotonic 보장
```

**이유**: `step_index`는 한 run 안에서 단조 증가하는 시퀀스. `exit_step` 에서 reset하면 retry로 인한 quality_gate→worker 재방문 시 step_index 1,2,3,2,3,4 같은 충돌 발생.

### 4.5 `supervisor_node` 변경 — reasoning 노출 1줄

```python
# src/application/agent_builder/supervisor_nodes.py — line ~110
try:
    llm_with_structure = llm.with_structured_output(SupervisorDecision)
    decision = await llm_with_structure.ainvoke(messages)
    next_worker = decision.next
except Exception:
    logger.error("supervisor LLM decision failed, falling back to __end__")
    return {"next_worker": "__end__"}

# ... (라우팅 로직 그대로) ...

reasoning = getattr(decision, "reasoning", None) or f"next={next_worker}"
return {
    "next_worker": next_worker,
    "skipped_workers": skipped,
    "iteration_count": state["iteration_count"] + 1,
    "_step_output_summary": reasoning[:1024],    # M3 신규 — wrapper가 사용
}
```

**Note**: `SupervisorDecision` Pydantic 모델은 현재 `next` / `answer` 2 필드만 존재. `reasoning` 필드는 schema 검증 필요 — 없으면 next_worker 텍스트로 fallback. Design Phase 시 sup_decision schema 확인 후 reasoning 필드 추가 여부 결정 (Open Issue §12 참조).

### 4.6 헬퍼 함수 — `step_tracking.py` 내부

```python
from langchain_core.messages import BaseMessage, AIMessage


def _summarize_state_input(state: Mapping[str, Any]) -> Optional[str]:
    """LangGraph state → input_summary 1KB.

    - 마지막 user 메시지 content + iteration_count + last_worker_id
    - state 키 누락에 안전 (best-effort)
    """
    try:
        messages = state.get("messages") or []
        last_user = _find_last_message(messages, role="user") or _find_last_message(messages, role="human")
        user_text = _extract_content(last_user) if last_user else "(no user message)"
        parts = [
            f"iter={state.get('iteration_count', 0)}",
            f"last_worker={state.get('last_worker_id', '')}",
            f"user={user_text[:600]}",
        ]
        return " | ".join(parts)[:_INPUT_SUMMARY_MAX_CHARS]
    except Exception:
        return None


def _summarize_state_output(result: Any) -> Optional[str]:
    """노드 return dict → output_summary 1KB.

    - dict["messages"] 중 마지막 AIMessage content
    - 없으면 next_worker / quality_gate_result 같은 dict 키 요약
    - 그 외 → str(result)[:1024]
    """
    try:
        if not isinstance(result, dict):
            return str(result)[:_OUTPUT_SUMMARY_MAX_CHARS]
        new_messages = result.get("messages") or []
        last_ai = _find_last_message(new_messages, kind=AIMessage)
        if last_ai is not None:
            return _extract_content(last_ai)[:_OUTPUT_SUMMARY_MAX_CHARS]
        # routing-only result
        keys = ["next_worker", "quality_gate_result", "retry_counts"]
        snippet = {k: result.get(k) for k in keys if k in result}
        if snippet:
            return json.dumps(snippet, ensure_ascii=False, default=str)[:_OUTPUT_SUMMARY_MAX_CHARS]
        return None
    except Exception:
        return None
```

`_find_last_message` / `_extract_content` 는 dict 형태와 BaseMessage 인스턴스 양쪽을 안전하게 처리 — answer_node 의 `_is_search_result` 패턴과 동일한 dict-or-instance 분기.

---

## 5. State Machine

### 5.1 `ai_run_step.status` 전이 (재정리)

```
       [enter] record_step → STARTED row INSERT
                │
       ┌────────┼────────┐
       │        │        │
   normal exit  exception kill -9
       │        │        │
       ▼        ▼        ▼
   ┌────────┐ ┌────────┐ STARTED 잔존 (orphan)
   │SUCCESS │ │FAILED  │
   └────────┘ └────────┘
```

### 5.2 `UsageCallback` 내부 상태 전이

```
초기:
  _current_step_id = None
  _step_index = 0
  _current_tool_call_id = None (M2 동일)

Step 1 (supervisor) enter:
  step_id_1 = record_step → uuid (만약 None이면 모든 이하 skip)
  enter_step(step_id_1) → _current_step_id = step_id_1, _step_index = 1
  RunContext.step_id = step_id_1

  [Step 1 안에서 LLM call]
  on_llm_end → record_llm_call(step_id=step_id_1) ★

Step 1 exit:
  update_step(step_id_1, SUCCESS, output_summary)
  exit_step() → _current_step_id = None
  RunContext.step_id = None
  (note: _step_index는 1 유지 — monotonic)

Step 2 (worker) enter:
  step_id_2 = record_step(step_index=2, ...)
  enter_step(step_id_2) → _current_step_id = step_id_2, _step_index = 2
  ...
```

---

## 6. Error Handling

### 6.1 Failure Modes & Responses (M2와 일관)

| 시나리오 | 영향 | 처리 |
|---------|------|------|
| `record_step` 실패 (DB 다운 등) | `step_id=None` 반환 | `enter_step` skip, `_current_step_id` 유지(None) → 해당 step 범위 LLM/tool은 step_id=NULL로 기록 (데이터 손실 < 1 step). 노드 본문은 정상 실행 |
| `update_step` 실패 | STARTED row 잔존 (orphan) | warning log. M4 sweep 대상 |
| 노드 함수 본문 예외 (RuntimeError 등) | step row가 FAILED로 정상 기록 + 예외 re-raise → fail_run에 전파 | `__aexit__`에서 status=FAILED + error_text 기록 후 raise |
| `_summarize_state_input/output` 직렬화 실패 | summary = None | 내부 try/except (best-effort) |
| LangGraph 비정상 종료 (프로세스 kill) | STARTED row 잔존 | M4 sweep 검토 |
| `prev_ctx is None` (RunContext 미설정) | RunContext 동기화 skip | 정상 — M4 retrieval은 RunContext 없으면 그냥 step_id를 못 받음 (best-effort) |
| `decision.reasoning` 필드 부재 (Open Issue §12-1) | `_step_output_summary` 누락 | wrapper가 `_summarize_state_output` fallback 사용 → quality_gate routing key 등으로 요약 |

### 6.2 Logging Conventions (LOG-001)

| Level | 시나리오 |
|-------|---------|
| `info` | (없음 — RunTracker가 이미 기록) |
| `warning` | record_step 실패, update_step 실패, summary 직렬화 실패 |
| `error` | (해당 없음 — M3는 best-effort) |

모든 warning은 `run_id` + `node_name` context 포함.

---

## 7. Security Considerations

- [x] **PII / 민감정보**: `input_summary`에 user 메시지가 1KB 컷되어 포함 — anonymization은 별도 PDCA(`agent-pii-masking`). M3는 1KB 컷이 1차 방어선
- [x] **로그 노출**: warning log에 `node_name` + `run_id`만 — `state` 원문은 노출하지 않음
- [x] **권한**: M3는 데이터 영속화만 — 조회 API(M4)에서 admin/self 권한 분리
- [x] **state 직렬화 안전성**: `_summarize_state_input/output` 둘 다 try/except 안 — 어떤 state 형태에도 crash 안 함
- [x] **Repository 격리**: M1·M2와 동일 — tracker가 session-per-operation 적용 (DB-001)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `track_step` 컨텍스트 매니저 | pytest + AsyncMock |
| Unit | `_summarize_state_input/output` | pytest |
| Unit | `_with_step_tracking` decorator | pytest |
| Unit | `UsageCallback._step_index` 단조 증가 | pytest |
| Integration | RunAgentUseCase + real MySQL + DummyLLM + 4 노드 흐름 | pytest + testcontainers (M1·M2 conftest 재활용) |
| Manual | 실 LLM + RAG 1회 + SQL 조회 | mycli / psql |

### 8.2 Key Test Cases

#### `tests/application/agent_run/test_step_tracking.py` (~10 cases)

```python
@pytest.mark.asyncio
async def test_track_step_records_started_with_index_1(tracker_mock, callback, run_id):
    tracker_mock.record_step.return_value = "step-001"
    async with track_step(
        tracker=tracker_mock, callback=callback, run_id=run_id,
        node_name="supervisor", node_type=NodeType.SUPERVISOR,
        input_summary="user=hi", logger=logger_mock,
    ):
        pass
    args = tracker_mock.record_step.await_args.kwargs
    assert args["step_index"] == 1
    assert args["status"] == StepStatus.STARTED
    assert args["node_type"] == NodeType.SUPERVISOR


@pytest.mark.asyncio
async def test_track_step_calls_enter_step_and_restores_on_exit(...):
    tracker_mock.record_step.return_value = "step-001"
    async with track_step(...) as step:
        assert callback._current_step_id == "step-001"
        assert callback._step_index == 1
    assert callback._current_step_id is None  # 복원
    assert callback._step_index == 1          # monotonic 유지


@pytest.mark.asyncio
async def test_track_step_updates_run_context_step_id(...):
    set_current_run_context(RunContext(run_id=run_id, ...))
    tracker_mock.record_step.return_value = "step-001"
    async with track_step(...) as step:
        ctx = get_current_run_context()
        assert ctx.step_id == "step-001"
    ctx_after = get_current_run_context()
    assert ctx_after.step_id is None


@pytest.mark.asyncio
async def test_track_step_records_success_with_output_summary(...):
    tracker_mock.record_step.return_value = "step-001"
    async with track_step(...) as step:
        step.output_summary = "supervisor chose worker_finance"
    upd = tracker_mock.update_step.await_args.kwargs
    assert upd["status"] == StepStatus.SUCCESS
    assert "worker_finance" in upd["output_summary"]


@pytest.mark.asyncio
async def test_track_step_records_failed_on_exception_and_reraises(...):
    tracker_mock.record_step.return_value = "step-001"
    with pytest.raises(RuntimeError, match="node failed"):
        async with track_step(...):
            raise RuntimeError("node failed")
    upd = tracker_mock.update_step.await_args.kwargs
    assert upd["status"] == StepStatus.FAILED
    assert "node failed" in upd["error_text"]


@pytest.mark.asyncio
async def test_track_step_record_step_failure_degrades_gracefully(...):
    tracker_mock.record_step.return_value = None  # best-effort 실패
    async with track_step(...) as step:
        # _current_step_id는 갱신되지 않음 (None 유지)
        assert callback._current_step_id is None
    # update_step도 skip
    tracker_mock.update_step.assert_not_called()


@pytest.mark.asyncio
async def test_track_step_input_summary_truncated_at_1024(...):
    big = "x" * 5000
    tracker_mock.record_step.return_value = "step-001"
    async with track_step(..., input_summary=big):
        pass
    args = tracker_mock.record_step.await_args.kwargs
    assert len(args["input_summary"]) <= 1024


@pytest.mark.asyncio
async def test_track_step_isolated_per_callback_instance(...):
    cb1 = UsageCallback(...)
    cb2 = UsageCallback(...)
    async with track_step(callback=cb1, ...):
        async with track_step(callback=cb2, ...):
            assert cb1._step_index == 1
            assert cb2._step_index == 1  # 격리됨


def test_summarize_state_input_no_messages_returns_safe():
    assert _summarize_state_input({}) is not None  # crash 안 함


def test_summarize_state_output_last_ai_message_extracted():
    msg = AIMessage(content="final answer")
    assert "final answer" in _summarize_state_output({"messages": [msg]})
```

#### `tests/application/agent_builder/test_workflow_compiler_step_wrapping.py` (~6 cases)

```python
@pytest.mark.asyncio
async def test_supervisor_wrapped_with_node_type_SUPERVISOR(compiler_with_tracker):
    graph = await compiler_with_tracker.compile(workflow_spec)
    # supervisor 노드 실행 시 record_step의 node_type=SUPERVISOR 호출 검증
    ...

@pytest.mark.asyncio
async def test_worker_wrapped_with_node_type_WORKER(...):
    ...

@pytest.mark.asyncio
async def test_quality_gate_wrapped_with_node_type_GATE(...):
    ...

@pytest.mark.asyncio
async def test_answer_agent_wrapped_with_node_type_OTHER(...):
    ...

@pytest.mark.asyncio
async def test_sub_agent_wrapped_with_node_type_WORKER(...):
    ...

@pytest.mark.asyncio
async def test_no_wrapping_when_tracker_none(compiler_without_tracker):
    """tracker=None → 원본 fn 그대로 (관측성 비활성)."""
    graph = await compiler_without_tracker.compile(workflow_spec)
    # record_step 호출 0건
    ...
```

#### `tests/application/agent_builder/test_run_agent_use_case_observability.py` 보강 (~4 cases — `TestRunStepWiringM3`)

```python
@pytest.mark.asyncio
async def test_one_run_creates_one_step_row_per_node(use_case, db_session):
    """supervisor + worker + quality_gate + answer → ai_run_step 4 row."""
    resp = await use_case.execute(conversation_with_rag)
    rows = await db_session.execute(
        select(RunStepModel).where(RunStepModel.run_id == resp.run_id)
        .order_by(RunStepModel.step_index)
    )
    rows = rows.scalars().all()
    assert len(rows) >= 4
    names = [r.node_name for r in rows]
    assert "supervisor" in names
    assert any("worker_" in n for n in names)
    assert "quality_gate" in names


@pytest.mark.asyncio
async def test_llm_call_inside_node_attaches_step_id(  # ★ 핵심 회귀 가드
    use_case, db_session,
):
    """ai_llm_call.step_id NOT NULL — M1·M2의 데이터 레이어 회수."""
    resp = await use_case.execute(conversation_simple)
    rows = await db_session.execute(text("""
        SELECT l.purpose, l.step_id, s.node_name
          FROM ai_llm_call l JOIN ai_run_step s ON s.id = l.step_id
         WHERE l.run_id = :rid
    """), {"rid": resp.run_id})
    matched = rows.all()
    assert any(r.step_id is not None for r in matched)


@pytest.mark.asyncio
async def test_node_failure_records_step_status_failed(use_case_with_failing_worker, db_session):
    with pytest.raises(...):
        await use_case_with_failing_worker.execute(...)
    rows = await db_session.execute(
        select(RunStepModel).where(RunStepModel.status == "FAILED")
    )
    failed = rows.scalars().all()
    assert len(failed) >= 1
    assert failed[0].error_text is not None


@pytest.mark.asyncio
async def test_supervisor_step_records_decision_reasoning(use_case, db_session):
    resp = await use_case.execute(conversation_simple)
    rows = await db_session.execute(
        select(RunStepModel).where(
            RunStepModel.run_id == resp.run_id,
            RunStepModel.node_name == "supervisor",
        )
    )
    sup = rows.scalars().first()
    assert sup is not None
    assert sup.output_summary is not None
    assert len(sup.output_summary) <= 1024
```

#### `tests/infrastructure/llm/test_usage_callback_*.py` 보강 (~2 cases)

```python
def test_step_index_monotonic_increment():
    cb = UsageCallback(tracker, run_id, ...)
    assert cb._step_index == 0
    cb.enter_step("s1")
    assert cb._step_index == 1
    cb.exit_step()
    assert cb._step_index == 1  # exit는 reset 안 함
    cb.enter_step("s2")
    assert cb._step_index == 2


def test_step_index_isolated_per_instance():
    cb1 = UsageCallback(...)
    cb2 = UsageCallback(...)
    cb1.enter_step("a")
    cb2.enter_step("b")
    cb1.enter_step("c")
    assert cb1._step_index == 2
    assert cb2._step_index == 1
```

### 8.3 테스트 우선순위

1. **핵심 회귀 가드**: `test_llm_call_inside_node_attaches_step_id` — M3의 가치 보장
2. **State machine**: `test_track_step_calls_enter_step_and_restores_on_exit` + `test_track_step_records_failed_on_exception_and_reraises`
3. **Best-effort**: `test_track_step_record_step_failure_degrades_gracefully`
4. 나머지 단위 테스트

---

## 9. Clean Architecture

### 9.1 Layer Structure (CLAUDE.md §2 준수)

| Layer | Responsibility | M3 변경 |
|-------|---------------|---------|
| **domain/agent_run/** | `NodeType` / `StepStatus` (M1) | **변경 없음** (`ANSWER` 미추가, §3.3 결정) |
| **application/agent_run/** | `step_tracking.py` (신규) — `track_step` + helpers | 1 신규 파일 |
| **application/agent_builder/** | `workflow_compiler.py` — `_with_step_tracking` 메서드 + 6 add_node 수정 | 동일 파일 내 |
| **application/agent_builder/** | `supervisor_nodes.py` — return dict 1 키 추가 | 동일 파일 내 1줄 |
| **infrastructure/llm/** | `usage_callback.py` — `_step_index` 필드 + enter_step 1줄 | 동일 파일 내 |
| **infrastructure/persistence/** | M1 ORM/Repo | **변경 없음** |
| **interfaces/** (FastAPI router) | | **변경 없음** (M4 범위) |

### 9.2 Dependency Direction

```
application/agent_builder/workflow_compiler.py
    ├──> application/agent_run/step_tracking.py      ★ M3 신규
    ├──> application/agent_run/tracker.py            (M1 — 변경 없음)
    ├──> domain/agent_run/value_objects.py           (NodeType import)
    └──> infrastructure/llm/usage_callback.py        ← already imported (M1)

application/agent_run/step_tracking.py               ★ M3 신규
    ├──> application/agent_run/context.py            (M1 — get/set ContextVar)
    ├──> application/agent_run/tracker.py            (RunTracker type hint)
    ├──> domain/agent_run/value_objects.py           (NodeType, StepStatus, RunId)
    └──> domain/logging/interfaces/logger_interface.py

infrastructure/llm/usage_callback.py
    └──> (M1·M2 의존성 그대로, _step_index 1 필드 추가)
```

**역방향 의존성 0건** — application/agent_builder는 application/agent_run을 import (정방향).

### 9.3 Forbidden Action 체크 (CLAUDE.md §6)

- [x] domain → infrastructure 참조: **없음**
- [x] controller/router에 비즈니스 로직: **N/A** (M3 라우터 변경 없음)
- [x] 대화 기록을 vector db에 저장: **N/A**
- [x] `print()` 사용: **금지** — `self._logger.warning` 사용
- [x] 스택 트레이스 없는 에러 처리: warning log에 `exception=e` 전달
- [x] Repository 내부 commit/rollback: M3에서 Repository 변경 없음
- [x] 한 UseCase 안에서 repository 별 다른 세션: N/A
- [x] config 하드코딩 금지: 1024자 상수는 M2와 일관 (`_INPUT_SUMMARY_MAX_CHARS` 등 모듈 상수)

---

## 10. Coding Convention Reference

### 10.1 Naming (Python — CLAUDE.md §3)

| Target | Rule | M3 예 |
|--------|------|-------|
| Module | snake_case.py | `step_tracking.py` |
| Function | snake_case | `track_step`, `_with_step_tracking`, `_summarize_state_input` |
| Class | PascalCase | `_StepContext` |
| Constant | UPPER_SNAKE_CASE | `_INPUT_SUMMARY_MAX_CHARS`, `_OUTPUT_SUMMARY_MAX_CHARS` |
| Private | `_` prefix | `_step_index`, `_with_step_tracking`, `_StepContext` |
| Async | `async def` / `@asynccontextmanager` | `track_step` |

### 10.2 Import Order (step_tracking.py 예시)

```python
# 1. Standard library
from __future__ import annotations
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Final, Mapping, Optional

# 2. Third-party
from langchain_core.messages import AIMessage, BaseMessage

# 3. First-party (src)
from src.application.agent_run.context import (
    get_current_run_context, set_current_run_context, with_step_id,
)
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.domain.logging.interfaces.logger_interface import LoggerInterface
```

순환 import 회피: `step_tracking` → `usage_callback` 직접 import 금지. 대신 callback 인자를 typing.TYPE_CHECKING으로 forward ref (또는 `Any` 사용 — best-effort).

### 10.3 함수 길이 / if 중첩

- `track_step` 본체 ~30줄 (try/except/else 패턴) ≤ 40줄 ✅
- `_with_step_tracking.wrapped` ~15줄 ✅
- if 중첩 모두 1~2단계 ✅

### 10.4 LOG-001 Logger (warning 예시)

```python
self._logger.warning(
    "track_step record_step failed (best-effort)",
    exception=e,
    run_id=run_id.value,
    node_name=node_name,
    node_type=node_type.value,
)
```

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── src/
│   ├── application/
│   │   ├── agent_run/
│   │   │   ├── tracker.py                       # M1 (변경 없음)
│   │   │   ├── context.py                       # M1 (변경 없음)
│   │   │   ├── purpose_inference.py             # M2 (변경 없음)
│   │   │   └── step_tracking.py                 ★ M3 신규
│   │   └── agent_builder/
│   │       ├── workflow_compiler.py             ★ M3 수정 (_with_step_tracking + 6 add_node 변경)
│   │       └── supervisor_nodes.py              ★ M3 수정 (1줄 — _step_output_summary 노출)
│   └── infrastructure/
│       └── llm/
│           └── usage_callback.py                 ★ M3 수정 (_step_index 필드 + enter_step 1줄)
└── tests/
    ├── application/
    │   ├── agent_run/
    │   │   └── test_step_tracking.py             ★ M3 신규 (~10 cases)
    │   └── agent_builder/
    │       ├── test_workflow_compiler_step_wrapping.py  ★ M3 신규 (~6 cases)
    │       └── test_run_agent_use_case_observability.py # M3 보강 (+4 cases)
    └── infrastructure/
        └── llm/
            └── test_usage_callback_*.py          # M3 보강 (+2 cases)
```

### 11.2 Implementation Order (TDD)

```
Step 1: UsageCallback._step_index (가장 작은 변경)
  1.1 test_usage_callback_*.py에 _step_index 2 cases 추가 (Red)
  1.2 usage_callback.py에 _step_index 필드 + enter_step 1줄 (Green)

Step 2: step_tracking 모듈 (의존성 최소)
  2.1 test_step_tracking.py 10 cases 작성 (Red)
  2.2 step_tracking.py 구현 (Green)
  2.3 ruff/mypy 통과

Step 3: WorkflowCompiler._with_step_tracking
  3.1 test_workflow_compiler_step_wrapping.py 6 cases 작성 (Red)
  3.2 workflow_compiler.py에 헬퍼 + 6 add_node wrapping (Green)

Step 4: supervisor_node reasoning 노출
  4.1 supervisor_nodes.py test가 있다면 _step_output_summary 키 검증 추가
  4.2 supervisor_node return dict 1줄 추가

Step 5: 통합 테스트
  5.1 test_run_agent_use_case_observability.py에 4 cases 추가 (Red)
  5.2 (구현 변경 없음 — 위 4 step의 결과)
  5.3 통합 테스트 통과 확인 (Green)

Step 6: 수동 검증
  6.1 RAG 1회 실 호출 → ai_run_step + ai_llm_call.step_id JOIN SQL
  6.2 verify-logging skill 실행
  6.3 verify-architecture skill 실행

Step 7: 문서
  7.1 docs/03-analysis/agent-run-observability-m3.analysis.md 준비 (Check phase)
```

### 11.3 Dependencies / Setup

신규 패키지 0건. LangChain `asynccontextmanager` 표준 stdlib.

---

## 12. Open Issues / M2 Sync Notes

### 12.1 `SupervisorDecision.reasoning` 필드 존재 여부

현재 `SupervisorDecision` Pydantic 모델은:
```python
class SupervisorDecision(BaseModel):
    next: str
    answer: Optional[str] = None
```

`reasoning` 필드가 없음. M3 Do phase 시 두 가지 옵션:

| 옵션 | Pros | Cons |
|------|------|------|
| **A: reasoning 필드 추가 (1줄)** + supervisor_prompt에 "reasoning도 함께 출력하라" 명시 | output_summary가 풍부 — "왜 이 워커를 골랐는지"가 의미 있음 | LLM 토큰 약간 증가, supervisor prompt 변경 |
| B: reasoning 미추가, fallback (next_worker 텍스트만) 사용 | 변경 0 | output_summary 의미 빈약 ("next=worker_finance"만 기록) |

**권장**: A. supervisor 노드 LLM에 reasoning 필드를 요구하는 것이 비용 대비 가치 큼. Do phase 시 결정. 만약 A 선택 시 supervisor_nodes.py 변경 +2줄(model 정의 1 + supervisor_prompt 보강 1).

### 12.2 M2 sync — Tool call `step_id` 자동 채움 검증

M2는 `record_tool_call(step_id=self._current_step_id)` 호출함. M3이 `_current_step_id`를 노드 진입 시 set하면 **추가 코드 0줄**로 `ai_tool_call.step_id`가 자동 채워진다. M3 Check phase의 회귀 검증 항목.

### 12.3 LangGraph 공식 노드 hook (장기 모니터링)

LangGraph 0.4+가 공식 노드-level `on_node_start/end` hook을 출시하면 M3의 decorator wrapping을 callback-driven으로 마이그레이션 가능. 현 시점 (LangGraph 0.3.x) 공식 API 부재 — Decorator가 최선.

### 12.4 M2 status enum 표기 갱신 (carry-over)

M2 Plan §5-3 status enum 동기화 (G3 follow-up) — M1 Plan은 이미 archive됨. 별도 작업으로 진행하거나 무시 (Plan은 historical record).

---

## 13. Acceptance Criteria

M3 Design은 다음 조건 충족 시 "Approved" — Do phase 진입 가능:

- [x] 신규 테이블/마이그레이션 0건
- [x] 도메인 enum 변경 0건 (`NodeType.ANSWER` 미추가)
- [x] 노드 함수 본문 변경 ≤ 1줄 (supervisor reasoning 1줄만)
- [x] WorkflowCompiler `add_node` 6 지점 wrapping
- [x] best-effort 격리 — 단위 테스트로 검증
- [x] step_tracking.py가 application layer 의존성 규칙 준수
- [x] CLAUDE.md §3 함수 길이 / if 중첩 / print() 금지 준수
- [x] M2 패턴 (`_ToolStartInfo` style + best-effort sentinel) 일관 유지

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-21 | M3 초안 — track_step 컨텍스트 매니저 + WorkflowCompiler decorator wrapping. NodeType enum 변경 없음 (OTHER 재활용), step_index = UsageCallback monotonic counter | 배상규 |
