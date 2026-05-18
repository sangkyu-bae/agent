# supervisor-custom-loop Design Document

> **Summary**: WorkflowCompiler를 Custom StateGraph 기반 Supervisor로 전면 재작성하여 품질게이트, 조건부 워커 라우팅, 반복/토큰 제한 지원
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-11
> **Status**: Draft
> **Planning Doc**: [supervisor-custom-loop.plan.md](../../01-plan/features/supervisor-custom-loop.plan.md)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `create_supervisor()` 블랙박스 사용으로 워커 응답 검증, 조건부 라우팅, 반복 제한 등 내부루프 제어 불가 |
| **Solution** | `StateGraph(SupervisorState)`로 supervisor → worker → quality_gate 루프를 직접 구성하고, Hook 함수로 확장 지점 제공 |
| **Function/UX Effect** | 에이전트가 워커 응답을 검증·재시도하여 답변 품질 향상, 무한루프 방지로 안정성 확보 |
| **Core Value** | 금융/정책 도메인의 보수적 응답 품질을 Supervisor 내부 루프에서 보장하면서 확장 가능한 구조 |

---

## 1. Overview

### 1.1 Design Goals

- `langgraph_supervisor.create_supervisor`를 제거하고 `StateGraph`로 동일 기능 + 확장 기능 구현
- Supervisor → Worker → QualityGate → Supervisor 루프를 명시적 노드/엣지로 표현
- Hook 함수 주입으로 코드 레벨 워커 강제/스킵/품질검증 커스터마이즈
- 기존 에이전트(DB 저장)가 새 컴파일러에서 동일하게 동작 (전체 마이그레이션)

### 1.2 Design Principles

- **명시적 제어**: 모든 루프 동작이 StateGraph 노드/엣지로 가시화
- **관심사 분리**: Supervisor 판단 / Worker 실행 / 품질검증 / Hook 로직 각각 독립 모듈
- **도메인 규칙 분리**: `SupervisorConfig`, `QualityGatePolicy`는 domain 레이어에 위치
- **확장 용이**: Phase 2 기능(데이터 파이프라인, 스트리밍)을 노드 추가만으로 대응

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────┐     ┌──────────────────────┐     ┌─────────────────────────────────┐
│   Client     │────▶│ agent_builder_router  │────▶│       RunAgentUseCase           │
│  (Frontend)  │     │ POST /{id}/run        │     │                                 │
└──────────────┘     └──────────────────────┘     │  1. Load Agent + Config          │
                                                   │  2. Build messages (multi-turn)  │
                                                   │  3. compiler.compile(...)        │
                                                   │  4. graph.ainvoke(initial_state) │
                                                   │  5. Parse result + Save turn     │
                                                   └──────────────┬──────────────────┘
                                                                  │
                                          ┌───────────────────────▼──────────────────────┐
                                          │          WorkflowCompiler.compile()           │
                                          │                                               │
                                          │  ┌─────────────────────────────────────────┐  │
                                          │  │        StateGraph(SupervisorState)       │  │
                                          │  │                                         │  │
                                          │  │  ┌─────────────┐   ┌──────────────┐     │  │
                                          │  │  │ supervisor   │──▶│  worker_{N}   │    │  │
                                          │  │  │  (LLM 판단) │   │(ReAct Agent) │    │  │
                                          │  │  └──────▲──────┘   └──────┬───────┘    │  │
                                          │  │         │                  │             │  │
                                          │  │    "pass"│           ┌─────▼──────┐     │  │
                                          │  │         │           │quality_gate │     │  │
                                          │  │         └───────────│ (검증 노드) │     │  │
                                          │  │                     └────────────┘     │  │
                                          │  └─────────────────────────────────────────┘  │
                                          │                                               │
                                          │  Injected:                                    │
                                          │  - ToolFactory (worker 도구 생성)             │
                                          │  - LLMFactory (LLM 인스턴스 생성)             │
                                          │  - SupervisorHooks (확장 로직)                │
                                          └───────────────────────────────────────────────┘
```

### 2.2 Graph Flow (StateGraph)

```
                        ┌───────────┐
                        │   START   │
                        └─────┬─────┘
                              │
                              ▼
                    ┌──────────────────┐
            ┌──────│    supervisor     │◄─────────────────────────┐
            │      │  (LLM + Hooks)   │                          │
            │      └──────────────────┘                          │
            │               │                                     │
            │      route_to_worker()                              │
            │        ┌──────┼──────┬───── ... ──┐                │
            │        │      │      │             │                │
            │        ▼      ▼      ▼             ▼                │
     "__end__"  ┌────────┐┌────────┐       ┌────────┐            │
            │   │worker_0││worker_1│  ...  │worker_N│            │
            │   └───┬────┘└───┬────┘       └───┬────┘            │
            │       │         │                 │                 │
            │       └─────────┼─────────────────┘                │
            │                 │                                   │
            │                 ▼                                   │
            │       ┌──────────────────┐                         │
            │       │   quality_gate   │                         │
            │       └──────────────────┘                         │
            │                 │                                   │
            │        route_after_quality()                        │
            │          ┌──────┼──────────┐                       │
            │          │      │          │                        │
            │       "pass" "retry"  "force_end"                  │
            │          │      │          │                        │
            │          │      ▼          │                        │
            │          │  (해당 worker   │                        │
            │          │   재호출)       │                        │
            │          │                 │                        │
            │          └────────┬────────┘                       │
            │                   │                                 │
            ▼                   └─────────────────────────────────┘
        ┌───────┐
        │  END  │
        └───────┘
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `WorkflowCompiler` | `ToolFactory` | 워커 도구 인스턴스 생성 |
| `WorkflowCompiler` | `LLMFactoryInterface` | LLM 인스턴스 생성 |
| `WorkflowCompiler` | `SupervisorHooks` | 확장 로직 주입 |
| `supervisor_node` | `SupervisorState` | 루프 상태 읽기/쓰기 |
| `quality_gate_node` | `QualityGatePolicy` | 품질검증 규칙 (domain) |
| `RunAgentUseCase` | `WorkflowCompiler` | 그래프 컴파일 (기존과 동일) |

---

## 3. Data Model

### 3.1 SupervisorState (신규)

**위치**: `src/application/agent_builder/supervisor_state.py`

```python
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class SupervisorState(TypedDict):
    """Custom Supervisor 그래프의 상태 정의."""

    # ── 메시지 (LangGraph 표준) ──
    messages: Annotated[list, add_messages]

    # ── 루프 제어 ──
    iteration_count: int           # 현재 supervisor 루프 반복 횟수
    max_iterations: int            # 최대 반복 (기본 10)
    token_usage: int               # 누적 토큰 추정치
    token_limit: int               # 토큰 상한 (기본 8000)

    # ── 워커 라우팅 ──
    next_worker: str               # supervisor가 선택한 다음 워커 ("__end__" = 종료)
    last_worker_id: str            # 마지막 실행 워커 ID
    available_workers: list[str]   # 워커 ID 목록

    # ── 품질 게이트 ──
    quality_gate_enabled: bool     # 품질검증 활성 여부
    retry_counts: dict[str, int]   # 워커별 재시도 횟수
    max_retries_per_worker: int    # 워커당 최대 재시도 (기본 2)

    # ── Hook 오버라이드 ──
    forced_worker: str             # Hook에 의한 강제 워커 ("" = 없음)
    skipped_workers: list[str]     # Hook에 의한 스킵 워커 목록
```

### 3.2 SupervisorConfig (신규 — Domain)

**위치**: `src/domain/agent_builder/schemas.py` (기존 파일에 추가)

```python
@dataclass(frozen=True)
class SupervisorConfig:
    """Supervisor 루프 실행 설정. WorkflowCompiler에 전달."""

    max_iterations: int = 10
    token_limit: int = 8000
    quality_gate_enabled: bool = False    # 기본 비활성 (점진적 활성화)
    max_retries_per_worker: int = 2
```

### 3.3 기존 스키마 변경 없음

- `AgentDefinition`, `WorkflowDefinition`, `WorkerDefinition` — 변경 없음
- `RunAgentRequest`, `RunAgentResponse` — 변경 없음
- DB 테이블 — 변경 없음

---

## 4. API Specification

### 4.1 외부 API 변경 없음

`POST /api/v1/agents/{agent_id}/run` 의 Request/Response 스키마는 변경하지 않는다. Supervisor 내부 구조 변경은 API 사용자에게 투명하다.

### 4.2 내부 인터페이스 변경

#### WorkflowCompiler.compile() 시그니처 변경

```python
# Before
def compile(
    self,
    workflow: WorkflowDefinition,
    llm_model: LlmModel,
    request_id: str,
    temperature: float = 0.0,
) -> CompiledGraph:

# After
def compile(
    self,
    workflow: WorkflowDefinition,
    llm_model: LlmModel,
    request_id: str,
    temperature: float = 0.0,
    supervisor_config: SupervisorConfig | None = None,  # 신규
) -> CompiledGraph:
```

#### RunAgentUseCase.execute() 변경

```python
# 추가되는 로직 (compile 호출 시)
config = SupervisorConfig()   # 기본값 사용 (향후 agent_definition에서 로드 가능)
graph = self._compiler.compile(
    workflow=workflow,
    llm_model=llm_model,
    temperature=agent.temperature,
    request_id=request_id,
    supervisor_config=config,
)

# ainvoke 시 초기 상태 구성 변경
initial_state = build_initial_state(
    messages=messages,
    config=config,
    available_workers=[w.worker_id for w in workflow.workers],
)
result = await graph.ainvoke(initial_state)
```

---

## 5. Detailed Design

### 5.1 supervisor_nodes.py — 노드 함수 상세

**위치**: `src/application/agent_builder/supervisor_nodes.py`

#### 5.1.1 build_initial_state()

```python
def build_initial_state(
    messages: list[dict],
    config: SupervisorConfig,
    available_workers: list[str],
) -> SupervisorState:
    """초기 SupervisorState 생성."""
    return {
        "messages": messages,
        "iteration_count": 0,
        "max_iterations": config.max_iterations,
        "token_usage": 0,
        "token_limit": config.token_limit,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": available_workers,
        "quality_gate_enabled": config.quality_gate_enabled,
        "retry_counts": {},
        "max_retries_per_worker": config.max_retries_per_worker,
        "forced_worker": "",
        "skipped_workers": [],
    }
```

#### 5.1.2 create_supervisor_node()

Supervisor 노드 팩토리 — LLM과 워커 목록을 클로저로 캡처.

```python
def create_supervisor_node(
    llm: BaseChatModel,
    workers: list[WorkerDefinition],
    supervisor_prompt: str,
    hooks: SupervisorHooks,
    logger: LoggerInterface,
):
    """supervisor 노드 함수를 생성하는 팩토리."""

    worker_descriptions = "\n".join(
        f"- {w.worker_id}: {w.description}" for w in workers
    )

    # Supervisor용 structured output 스키마
    class SupervisorDecision(BaseModel):
        next: str = Field(description="다음 호출할 worker_id 또는 'FINISH'")
        reasoning: str = Field(description="선택 이유")

    async def supervisor_node(state: SupervisorState) -> dict:
        """Supervisor LLM이 다음 워커를 결정하거나 종료를 판단."""

        # 1. 루프 가드 체크
        if state["iteration_count"] >= state["max_iterations"]:
            logger.warning("max_iterations reached", ...)
            return {"next_worker": "__end__"}

        if state["token_usage"] >= state["token_limit"]:
            logger.warning("token_limit reached", ...)
            return {"next_worker": "__end__"}

        # 2. Hook: force_worker 체크
        forced = hooks.force_worker(state)
        if forced:
            return {
                "next_worker": forced,
                "forced_worker": forced,
                "iteration_count": state["iteration_count"] + 1,
            }

        # 3. Hook: skip_workers 수집
        skipped = hooks.skip_workers(state)

        # 4. LLM 호출 — 다음 워커 결정
        decision_prompt = f"""당신은 Supervisor입니다. 사용 가능한 워커:
{worker_descriptions}

다음 중 선택하세요:
- 워커 호출이 필요하면 해당 worker_id를 선택
- 모든 작업이 완료되었으면 'FINISH'를 선택
스킵된 워커(사용 불가): {skipped}"""

        messages = state["messages"] + [
            {"role": "system", "content": decision_prompt}
        ]

        llm_with_structure = llm.with_structured_output(SupervisorDecision)
        decision = await llm_with_structure.ainvoke(messages)

        next_worker = decision.next
        if next_worker == "FINISH":
            next_worker = "__end__"
        elif next_worker in skipped:
            # 스킵된 워커를 선택한 경우 → FINISH로 폴백
            next_worker = "__end__"

        return {
            "next_worker": next_worker,
            "skipped_workers": skipped,
            "iteration_count": state["iteration_count"] + 1,
        }

    return supervisor_node
```

#### 5.1.3 create_quality_gate_node()

```python
def create_quality_gate_node(
    policy: QualityGatePolicy,
    logger: LoggerInterface,
):
    """품질 게이트 노드 함수 팩토리."""

    async def quality_gate_node(state: SupervisorState) -> dict:
        """워커 응답 품질 검증. 비활성 시 바이패스."""

        if not state["quality_gate_enabled"]:
            return {}   # 바이패스 — 상태 변경 없음

        last_worker = state["last_worker_id"]
        messages = state["messages"]

        # 마지막 AI 메시지 추출
        last_ai_msg = None
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                last_ai_msg = msg
                break

        if last_ai_msg is None:
            return {}

        # 도메인 정책으로 품질 검증
        is_acceptable = policy.check_response(last_ai_msg.content)

        if is_acceptable:
            logger.info("quality_gate passed", worker_id=last_worker)
            return {}

        # 재시도 횟수 체크
        retry_counts = dict(state["retry_counts"])
        current_retries = retry_counts.get(last_worker, 0)

        if current_retries >= state["max_retries_per_worker"]:
            logger.warning(
                "quality_gate max_retries reached, forcing pass",
                worker_id=last_worker,
                retries=current_retries,
            )
            return {}

        # 재시도: retry_count 증가 + 피드백 메시지 추가
        retry_counts[last_worker] = current_retries + 1
        feedback_msg = {
            "role": "user",
            "content": f"[품질검증 실패] 응답이 기준에 미달합니다. "
                       f"더 정확하고 구체적인 답변을 다시 생성해주세요. "
                       f"(재시도 {current_retries + 1}/{state['max_retries_per_worker']})",
        }

        return {
            "messages": [feedback_msg],
            "retry_counts": retry_counts,
            "next_worker": last_worker,   # 재시도 시 동일 워커 재호출
        }

    return quality_gate_node
```

#### 5.1.4 라우팅 함수

```python
def route_to_worker(state: SupervisorState) -> str:
    """supervisor 노드 후 라우팅: 워커 이름 또는 __end__."""
    return state["next_worker"]


def route_after_quality(state: SupervisorState) -> str:
    """quality_gate 노드 후 라우팅."""
    next_worker = state.get("next_worker", "")

    # quality_gate에서 next_worker를 재설정했으면 → 해당 워커 재호출
    if next_worker and next_worker != "__end__":
        return next_worker

    # 그 외 → supervisor로 복귀
    return "supervisor"
```

### 5.2 supervisor_hooks.py — Hook 프로토콜

**위치**: `src/application/agent_builder/supervisor_hooks.py`

```python
from typing import Protocol

from src.application.agent_builder.supervisor_state import SupervisorState


class SupervisorHooks(Protocol):
    """Supervisor 루프 확장을 위한 Hook 프로토콜.

    WorkflowCompiler에 주입하여 코드 레벨 워커 제어를 가능하게 한다.
    Phase 2에서 transform_result 등 추가 Hook 확장 예정.
    """

    def force_worker(self, state: SupervisorState) -> str | None:
        """특정 워커를 강제 호출. None이면 LLM 판단에 위임."""
        ...

    def skip_workers(self, state: SupervisorState) -> list[str]:
        """이번 iteration에서 스킵할 워커 목록."""
        ...


class DefaultHooks:
    """기본 Hook 구현 — 모든 결정을 LLM에 위임."""

    def force_worker(self, state: SupervisorState) -> str | None:
        return None

    def skip_workers(self, state: SupervisorState) -> list[str]:
        return []
```

### 5.3 QualityGatePolicy — 도메인 규칙

**위치**: `src/domain/agent_builder/policies.py` (기존 파일에 추가)

```python
class QualityGatePolicy:
    """워커 응답 품질 검증 도메인 규칙."""

    MIN_RESPONSE_LENGTH = 10
    EMPTY_INDICATORS = ["모르겠습니다", "답변할 수 없습니다", "정보를 찾을 수 없"]

    @classmethod
    def check_response(cls, content: str) -> bool:
        """응답이 최소 품질 기준을 충족하는지 검사."""
        if not content or len(content.strip()) < cls.MIN_RESPONSE_LENGTH:
            return False

        stripped = content.strip().lower()
        for indicator in cls.EMPTY_INDICATORS:
            if stripped.startswith(indicator):
                return False

        return True
```

### 5.4 WorkflowCompiler.compile() — 그래프 조립

**위치**: `src/application/agent_builder/workflow_compiler.py` (전면 재작성)

```python
class WorkflowCompiler:

    def __init__(
        self,
        tool_factory: ToolFactory,
        llm_factory: LLMFactoryInterface,
        logger: LoggerInterface,
        hooks: SupervisorHooks | None = None,
    ) -> None:
        self._tool_factory = tool_factory
        self._llm_factory = llm_factory
        self._logger = logger
        self._hooks = hooks or DefaultHooks()

    def compile(
        self,
        workflow: WorkflowDefinition,
        llm_model: LlmModel,
        request_id: str,
        temperature: float = 0.0,
        supervisor_config: SupervisorConfig | None = None,
    ):
        config = supervisor_config or SupervisorConfig()
        llm = self._llm_factory.create(llm_model, temperature)
        policy = QualityGatePolicy()

        # 1. Worker 에이전트 생성 (create_react_agent)
        worker_map: dict[str, CompiledGraph] = {}
        for worker_def in workflow.workers:
            tool = self._tool_factory.create(
                worker_def.tool_id, request_id,
                tool_config=worker_def.tool_config,
            )
            worker_agent = create_react_agent(
                llm, tools=[tool], name=worker_def.worker_id,
            )
            worker_map[worker_def.worker_id] = worker_agent

        # 2. 노드 함수 생성
        supervisor_fn = create_supervisor_node(
            llm=llm,
            workers=workflow.workers,
            supervisor_prompt=workflow.supervisor_prompt,
            hooks=self._hooks,
            logger=self._logger,
        )
        quality_gate_fn = create_quality_gate_node(
            policy=policy, logger=self._logger,
        )

        # 3. StateGraph 조립
        graph = StateGraph(SupervisorState)
        graph.add_node("supervisor", supervisor_fn)
        graph.add_node("quality_gate", quality_gate_fn)

        for worker_id, worker_agent in worker_map.items():
            # 워커 노드: subgraph를 래핑하여 last_worker_id 갱신
            graph.add_node(
                worker_id,
                self._wrap_worker(worker_id, worker_agent),
            )

        # 4. 엣지 설정
        graph.set_entry_point("supervisor")

        # supervisor → 워커 or END
        route_map = {wid: wid for wid in worker_map}
        route_map["__end__"] = END
        graph.add_conditional_edges("supervisor", route_to_worker, route_map)

        # 각 워커 → quality_gate
        for worker_id in worker_map:
            graph.add_edge(worker_id, "quality_gate")

        # quality_gate → supervisor or 워커 재호출
        qg_route_map = {"supervisor": "supervisor"}
        for wid in worker_map:
            qg_route_map[wid] = wid
        graph.add_conditional_edges("quality_gate", route_after_quality, qg_route_map)

        return graph.compile()

    def _wrap_worker(self, worker_id: str, worker_agent):
        """워커 실행 후 last_worker_id, token_usage 갱신하는 래퍼."""

        async def wrapped(state: SupervisorState) -> dict:
            result = await worker_agent.ainvoke(
                {"messages": state["messages"]}
            )
            new_messages = result.get("messages", [])

            # 토큰 사용량 추정 (응답 문자열 길이 기반 근사)
            token_delta = sum(
                len(getattr(m, "content", "")) // 4
                for m in new_messages
                if hasattr(m, "content")
            )

            return {
                "messages": new_messages,
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + token_delta,
            }

        return wrapped
```

### 5.5 route_after_quality 라우팅 로직 상세

```
quality_gate_node 실행 후 state 상태에 따른 분기:

Case 1: quality_gate 비활성 또는 통과
  → quality_gate_node가 빈 dict 반환
  → state["next_worker"] 변경 없음 (이전 supervisor가 설정한 값 유지)
  → route_after_quality는 "supervisor" 반환
  → supervisor 노드로 복귀 → 다음 워커 선택 or FINISH

Case 2: quality_gate 실패 + 재시도 가능
  → quality_gate_node가 {next_worker: last_worker, retry_counts: +1} 반환
  → route_after_quality는 해당 worker_id 반환
  → 동일 워커 재호출

Case 3: quality_gate 실패 + max_retries 도달
  → quality_gate_node가 빈 dict 반환 (강제 통과)
  → route_after_quality는 "supervisor" 반환
  → supervisor 노드로 복귀
```

### 5.6 RunAgentUseCase 변경 최소화

```python
# run_agent_use_case.py 변경 부분 (execute 메서드 내)

# Before:
graph = self._compiler.compile(
    workflow=workflow, llm_model=llm_model,
    temperature=agent.temperature, request_id=request_id,
)
result = await graph.ainvoke({"messages": messages})

# After:
config = SupervisorConfig()
graph = self._compiler.compile(
    workflow=workflow, llm_model=llm_model,
    temperature=agent.temperature, request_id=request_id,
    supervisor_config=config,
)
initial_state = build_initial_state(
    messages=messages, config=config,
    available_workers=[w.worker_id for w in workflow.workers],
)
result = await graph.ainvoke(initial_state)
```

`_parse_result()`는 기존과 동일하게 `result["messages"]`에서 마지막 AI 메시지를 추출.

---

## 6. DI 변경 (main.py)

### 6.1 WorkflowCompiler 생성 변경

```python
# Before:
workflow_compiler = WorkflowCompiler(
    tool_factory=tool_factory,
    llm_factory=llm_factory,
    logger=app_logger,
)

# After:
from src.application.agent_builder.supervisor_hooks import DefaultHooks

workflow_compiler = WorkflowCompiler(
    tool_factory=tool_factory,
    llm_factory=llm_factory,
    logger=app_logger,
    hooks=DefaultHooks(),   # 기본 Hook (확장 시 커스텀 Hook 주입)
)
```

`RunAgentUseCase` DI — 변경 없음 (compiler 인터페이스 유지).

---

## 7. Security Considerations

- [x] 기존 `VisibilityPolicy.can_access` 체크 유지 (변경 없음)
- [x] `max_iterations` 상한으로 무한루프 방지 — DoS 공격 표면 축소
- [x] `token_limit` 상한으로 과도한 LLM 호출 비용 방지
- [x] Supervisor LLM 호출 시 사용자 입력이 아닌 시스템 프롬프트로 워커 목록 전달 — injection 방지
- [x] Hook 함수는 서버 코드에서만 주입 가능 — 클라이언트 제어 불가

---

## 8. Error Handling

| Code | Condition | Cause | Handling |
|------|-----------|-------|----------|
| 500 | Supervisor LLM structured output 파싱 실패 | LLM이 예상 외 응답 | `__end__`로 폴백, 에러 로그 기록 |
| 500 | 워커 실행 중 예외 | 도구 API 실패 등 | 예외 전파 (기존과 동일), 에러 로그 |
| - | max_iterations 초과 | 루프 수렴 실패 | graceful 종료, 현재까지 결과 반환 |
| - | token_limit 초과 | 과도한 토큰 소비 | graceful 종료, 경고 로그 |
| - | 존재하지 않는 worker_id 선택 | LLM 환각 | 유효 워커 목록 검증 → `__end__` 폴백 |

### 8.1 Supervisor LLM 폴백 전략

```python
# supervisor_node 내부
try:
    decision = await llm_with_structure.ainvoke(messages)
    next_worker = decision.next
except Exception:
    logger.error("supervisor LLM decision failed, falling back to __end__")
    next_worker = "__end__"

# 유효성 검증
if next_worker not in available_workers and next_worker not in ("FINISH", "__end__"):
    logger.warning("invalid worker selected", selected=next_worker)
    next_worker = "__end__"
```

---

## 9. Test Plan

### 9.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `SupervisorState` 초기화 | pytest |
| Unit Test | `supervisor_node` 로직 (LLM mock) | pytest + AsyncMock |
| Unit Test | `quality_gate_node` 로직 | pytest + AsyncMock |
| Unit Test | `route_to_worker`, `route_after_quality` | pytest |
| Unit Test | `QualityGatePolicy` | pytest |
| Unit Test | `DefaultHooks`, 커스텀 Hook | pytest |
| Unit Test | `WorkflowCompiler.compile()` 그래프 구조 | pytest + Mock |
| Integration Test | `RunAgentUseCase` → 전체 파이프라인 | pytest + AsyncMock |

### 9.2 Test Cases

| ID | Category | Description | Expected |
|----|----------|-------------|----------|
| TC-01 | 하위호환 | 기존 agent 실행 (quality_gate off) | 기존과 동일 응답 형태 |
| TC-02 | supervisor | LLM이 FINISH 선택 | next_worker = "__end__", 루프 종료 |
| TC-03 | supervisor | LLM이 유효 워커 선택 | 해당 워커 노드 실행 |
| TC-04 | supervisor | LLM이 잘못된 워커 선택 | `__end__` 폴백 |
| TC-05 | supervisor | max_iterations 도달 | 즉시 `__end__` |
| TC-06 | supervisor | token_limit 초과 | 즉시 `__end__` |
| TC-07 | quality_gate | 비활성 상태 | 바이패스, 빈 dict 반환 |
| TC-08 | quality_gate | 활성 + 통과 | 빈 dict 반환 |
| TC-09 | quality_gate | 활성 + 실패 + 재시도 가능 | next_worker = last_worker, retry +1 |
| TC-10 | quality_gate | 활성 + 실패 + max_retries 도달 | 강제 통과 (빈 dict) |
| TC-11 | hooks | force_worker 반환 시 | LLM 호출 스킵, 해당 워커 직행 |
| TC-12 | hooks | skip_workers에 포함된 워커 선택 | `__end__` 폴백 |
| TC-13 | policy | 빈 응답 | check_response → False |
| TC-14 | policy | 정상 응답 | check_response → True |
| TC-15 | policy | "모르겠습니다" 시작 응답 | check_response → False |
| TC-16 | compiler | 워커 1개 그래프 | 노드: supervisor, worker_0, quality_gate |
| TC-17 | compiler | 워커 3개 그래프 | 노드 5개 + 올바른 엣지 구조 |
| TC-18 | wrap_worker | 워커 실행 후 | last_worker_id 갱신, token_usage 증가 |
| TC-19 | integration | multi-turn + supervisor | session_id 유지 + 커스텀 루프 동작 |

### 9.3 Mock 전략

```python
# supervisor_node 테스트: LLM mock
mock_llm = AsyncMock()
mock_llm.with_structured_output.return_value.ainvoke.return_value = (
    SupervisorDecision(next="worker_0", reasoning="test")
)

# quality_gate 테스트: 정책은 실제 사용 (단순 로직)
policy = QualityGatePolicy()

# WorkflowCompiler 테스트: tool_factory, llm_factory mock
mock_tool_factory = Mock(spec=ToolFactory)
mock_tool_factory.create.return_value = Mock(spec=BaseTool)

# worker_agent mock
mock_worker_agent = AsyncMock()
mock_worker_agent.ainvoke.return_value = {
    "messages": [AIMessage(content="검색 결과입니다...")]
}
```

---

## 10. Clean Architecture

### 10.1 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `SupervisorConfig` | **Domain** | `src/domain/agent_builder/schemas.py` |
| `QualityGatePolicy` | **Domain** | `src/domain/agent_builder/policies.py` |
| `SupervisorState` | **Application** | `src/application/agent_builder/supervisor_state.py` |
| `supervisor_node`, `quality_gate_node` | **Application** | `src/application/agent_builder/supervisor_nodes.py` |
| `SupervisorHooks`, `DefaultHooks` | **Application** | `src/application/agent_builder/supervisor_hooks.py` |
| `WorkflowCompiler` | **Application** | `src/application/agent_builder/workflow_compiler.py` |
| `RunAgentUseCase` | **Application** | `src/application/agent_builder/run_agent_use_case.py` |
| DI wiring | **Infrastructure** | `src/api/main.py` |

### 10.2 Dependency Rules 준수

```
domain/agent_builder/
  ├── schemas.py (SupervisorConfig)     → 의존 없음 ✅
  └── policies.py (QualityGatePolicy)   → 의존 없음 ✅

application/agent_builder/
  ├── supervisor_state.py               → langgraph (framework) ✅
  ├── supervisor_nodes.py               → SupervisorState, QualityGatePolicy (domain) ✅
  ├── supervisor_hooks.py               → SupervisorState ✅
  ├── workflow_compiler.py              → 위 모듈 + ToolFactory + LLMFactory ✅
  └── run_agent_use_case.py             → WorkflowCompiler, SupervisorConfig ✅

  ✗ domain → infrastructure 참조 없음 ✅
  ✗ application → infrastructure 직접 참조 없음 ✅
```

---

## 11. Implementation Guide

### 11.1 변경 파일 목록

| # | File | Type | Description |
|---|------|------|-------------|
| 1 | `src/application/agent_builder/supervisor_state.py` | **New** | SupervisorState TypedDict 정의 |
| 2 | `src/domain/agent_builder/schemas.py` | Modify | SupervisorConfig dataclass 추가 |
| 3 | `src/domain/agent_builder/policies.py` | Modify | QualityGatePolicy 클래스 추가 |
| 4 | `src/application/agent_builder/supervisor_hooks.py` | **New** | Hook Protocol + DefaultHooks |
| 5 | `src/application/agent_builder/supervisor_nodes.py` | **New** | supervisor_node, quality_gate_node, routing 함수, build_initial_state |
| 6 | `src/application/agent_builder/workflow_compiler.py` | Modify | compile() 전면 재작성 — StateGraph 기반 |
| 7 | `src/application/agent_builder/run_agent_use_case.py` | Modify | SupervisorConfig 생성 + initial_state 구성 |
| 8 | `src/api/main.py` | Modify | WorkflowCompiler DI에 hooks 추가 |
| 9 | `pyproject.toml` | Modify | `langgraph-supervisor` 의존성 제거 |
| 10 | `tests/domain/agent_builder/test_quality_gate_policy.py` | **New** | QualityGatePolicy 단위 테스트 |
| 11 | `tests/application/agent_builder/test_supervisor_nodes.py` | **New** | 노드 함수 단위 테스트 |
| 12 | `tests/application/agent_builder/test_supervisor_hooks.py` | **New** | Hook 로직 테스트 |
| 13 | `tests/application/agent_builder/test_workflow_compiler.py` | Modify | Custom StateGraph 검증 테스트로 전환 |
| 14 | `tests/application/agent_builder/test_run_agent_use_case.py` | Modify | SupervisorConfig 전달 테스트 추가 |

### 11.2 Implementation Order (TDD)

```
Phase 1: Domain 레이어
  [Test] QualityGatePolicy (TC-13~15)
  [Impl] QualityGatePolicy
  [Test] SupervisorConfig 검증
  [Impl] SupervisorConfig

Phase 2: Application 레이어 — State + Hooks
  [Impl] SupervisorState (TypedDict — 테스트 불필요)
  [Test] DefaultHooks (TC-11~12)
  [Impl] SupervisorHooks Protocol + DefaultHooks

Phase 3: Application 레이어 — Nodes
  [Test] build_initial_state
  [Impl] build_initial_state
  [Test] supervisor_node (TC-02~06)
  [Impl] supervisor_node
  [Test] quality_gate_node (TC-07~10)
  [Impl] quality_gate_node
  [Test] route_to_worker, route_after_quality
  [Impl] routing 함수

Phase 4: Application 레이어 — Compiler
  [Test] WorkflowCompiler.compile() 그래프 구조 (TC-16~18)
  [Impl] WorkflowCompiler 재작성
  [Test] _wrap_worker (TC-18)
  [Impl] _wrap_worker

Phase 5: Integration
  [Test] RunAgentUseCase + SupervisorConfig (TC-01, TC-19)
  [Impl] RunAgentUseCase 변경 + main.py DI
  [Cleanup] pyproject.toml에서 langgraph-supervisor 제거
```

---

## 12. Phase 2 확장 설계 가이드

| 확장 | 변경 위치 | 구체적 방법 |
|------|----------|------------|
| 워커 간 데이터 파이프라인 | `supervisor_hooks.py` | `transform_result(state, worker_output) -> dict` Hook 추가. `_wrap_worker` 내부에서 워커 실행 후 Hook 호출 |
| 워커별 개별 프롬프트 | `WorkerDefinition` + `_wrap_worker` | `worker_prompt: str | None` 필드 추가, create_react_agent에 `prompt=` 전달 |
| 실행 중간 결과 스트리밍 | `run_agent_use_case.py` | `graph.astream()` 전환 + SSE 응답 |
| Human-in-the-Loop | `supervisor_hooks.py` + graph | `require_approval(state) -> bool` Hook + `langgraph.types.interrupt` 노드 |
| 워커 타임아웃 | `_wrap_worker` | `asyncio.wait_for(worker_agent.ainvoke(...), timeout=30)` |
| 동적 워커 추가 | `compile()` | 런타임에 `worker_map`에 워커 추가, 그래프 재컴파일 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-11 | Initial design document | 배상규 |
