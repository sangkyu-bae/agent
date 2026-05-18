# multi-agent-composition Design Document

> **Summary**: 복수의 에이전트를 워커로 조합하여 상위 에이전트를 구성하는 멀티 에이전트 조합 기능의 상세 설계
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-11
> **Status**: Draft
> **Planning Doc**: [multi-agent-composition.plan.md](../../01-plan/features/multi-agent-composition.plan.md)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 에이전트 빌더는 Tool만 워커로 조합 가능하여, 복수 에이전트를 엮은 멀티스텝 워크플로우를 구성할 수 없음 |
| **Solution** | WorkerDefinition에 `worker_type`(`tool`/`sub_agent`) 필드를 추가하고, WorkflowCompiler가 sub_agent 워커를 재귀 컴파일하여 StateGraph 노드로 삽입 |
| **Function/UX Effect** | 기존 에이전트를 레고 블록처럼 조합하여 복합 에이전트 생성, Task 위임 방식으로 독립 실행 후 결과 반환 |
| **Core Value** | 에이전트 재사용성 극대화, 금융/정책 도메인의 전문 에이전트 조합 멀티스텝 분석 자동화 |

---

## 1. Design Overview

### 1.1 Design Goals

- WorkerDefinition을 `tool` / `sub_agent` 두 유형으로 확장 (하위 호환 유지)
- WorkflowCompiler에서 sub_agent 워커를 재귀적으로 컴파일하여 StateGraph에 삽입
- 순환참조 방지, 중첩 깊이 제한(MAX=2), 접근 권한 검증을 도메인 정책으로 분리
- Tool과 Sub-Agent를 혼합하여 하나의 에이전트에 동시 사용 가능

### 1.2 Design Principles

- **하위 호환성**: `worker_type` 기본값 `"tool"`, 기존 에이전트는 변경 없이 동작
- **도메인 규칙 분리**: 순환참조/중첩깊이/접근권한 정책을 `domain/` 레이어에 배치
- **관심사 분리**: 서브 에이전트 컴파일은 WorkflowCompiler 내부, 권한 검증은 Policy, DB 조회는 Repository
- **확장 가능**: MAX_NESTING_DEPTH를 상수로 관리하여 추후 설정 변경 용이

### 1.3 Design Constraints

- `domain/` → `infrastructure/` 참조 금지 (DDD 레이어 규칙)
- WorkflowCompiler가 Repository를 직접 사용 (application 레이어이므로 허용)
- 서브 에이전트는 순차 실행 (병렬 실행은 Phase 2)

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────┐     ┌────────────────────────┐     ┌──────────────────────────────────┐
│   Client     │────▶│  agent_builder_router   │────▶│       CreateAgentUseCase          │
│  (Frontend)  │     │  POST /api/v1/agents    │     │                                  │
└──────────────┘     └────────────────────────┘     │  1. sub_agent_configs 처리         │
                                                     │  2. SubAgentAccessPolicy 검증     │
                                                     │  3. CircularReferencePolicy 검증  │
                                                     │  4. NestingDepthPolicy 검증       │
                                                     │  5. WorkerDefinition 생성 (혼합)  │
                                                     │  6. AgentDefinition 저장          │
                                                     └──────────────────────────────────┘

┌──────────────┐     ┌────────────────────────┐     ┌──────────────────────────────────┐
│   Client     │────▶│  agent_builder_router   │────▶│       RunAgentUseCase             │
│  (Frontend)  │     │  POST /{id}/run         │     │                                  │
└──────────────┘     └────────────────────────┘     │  1. Load AgentDefinition          │
                                                     │  2. compiler.compile(workflow)    │
                                                     │  3. graph.ainvoke(initial_state)  │
                                                     └───────────────┬──────────────────┘
                                                                     │
                                     ┌───────────────────────────────▼──────────────────────────────┐
                                     │           WorkflowCompiler.compile()                          │
                                     │                                                              │
                                     │   workers 순회:                                              │
                                     │   ┌────────────────────────┬────────────────────────────┐    │
                                     │   │ worker_type == "tool"  │ worker_type == "sub_agent"  │    │
                                     │   │                        │                             │    │
                                     │   │ ToolFactory.create()   │ repository.find_by_id()     │    │
                                     │   │    ↓                   │    ↓                        │    │
                                     │   │ create_react_agent()   │ self.compile(sub_workflow,  │    │
                                     │   │    ↓                   │   depth=depth+1)            │    │
                                     │   │ _wrap_worker()         │    ↓                        │    │
                                     │   │                        │ _wrap_sub_agent()            │    │
                                     │   └────────────────────────┴────────────────────────────┘    │
                                     │                                                              │
                                     │   StateGraph(SupervisorState):                               │
                                     │   supervisor → tool_worker / sub_agent_worker → quality_gate │
                                     └──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow: 에이전트 생성

```
CreateAgentRequest
  ├── tool_configs: {"internal_document_search": {...}}
  └── sub_agent_configs: [{"ref_agent_id": "uuid-1", "description": "문서 분석"}]
         │
         ▼
  CreateAgentUseCase.execute()
         │
         ├── (1) _build_sub_agent_workers(sub_agent_configs, user_id, request_id)
         │     ├── repository.find_by_id(ref_agent_id) → AgentDefinition 존재 확인
         │     ├── SubAgentAccessPolicy.can_use_as_sub_agent() → 본인 소유 or 구독 확인
         │     ├── CircularReferencePolicy.validate_no_cycle() → 재귀 순환참조 검사
         │     ├── NestingDepthPolicy.validate_depth() → 현재+서브 깊이 합산 검증
         │     └── WorkerDefinition(worker_type="sub_agent", ref_agent_id=...) 생성
         │
         ├── (2) _build_skeleton_from_configs(tool_configs) → 기존 tool WorkerDefinition
         │
         ├── (3) workers = tool_workers + sub_agent_workers
         │     └── AgentBuilderPolicy.validate_worker_count(len(workers))
         │
         └── (4) AgentDefinition 저장 (workers에 tool + sub_agent 혼합)
```

### 2.3 Data Flow: 에이전트 실행

```
RunAgentUseCase.execute(agent_id, query)
         │
         ▼
  agent = repository.find_by_id(agent_id)
  workflow = agent.to_workflow_definition()
         │
         ▼
  WorkflowCompiler.compile(workflow, depth=0, visited={agent_id})
         │
         ├── worker: tool_id="tavily_search", worker_type="tool"
         │     → ToolFactory.create("tavily_search") → create_react_agent() → _wrap_worker()
         │
         └── worker: ref_agent_id="uuid-1", worker_type="sub_agent"
               │
               ├── (1) SubAgentAccessPolicy.can_use_as_sub_agent() → 실행 시점 재검증
               ├── (2) visited.add("uuid-1") → 순환참조 체크
               ├── (3) depth + 1 <= MAX_NESTING_DEPTH → 깊이 체크
               ├── (4) sub_agent = repository.find_by_id("uuid-1")
               ├── (5) sub_workflow = sub_agent.to_workflow_definition()
               ├── (6) sub_graph = self.compile(sub_workflow, depth=1, visited={agent_id, uuid-1})
               └── (7) _wrap_sub_agent(worker_id, sub_graph) → StateGraph 노드로 등록
                         │
                         └── 실행 시: task_message만 전달 → sub_graph.ainvoke() → 결과만 반환
```

---

## 3. Detailed Design

### 3.1 Domain Layer

#### 3.1.1 WorkerDefinition 확장 (`domain/agent_builder/schemas.py`)

```python
@dataclass
class WorkerDefinition:
    """에이전트가 사용할 단일 워커 정의."""

    tool_id: str
    worker_id: str
    description: str
    sort_order: int = 0
    tool_config: dict | None = None
    worker_type: str = "tool"         # "tool" | "sub_agent"
    ref_agent_id: str | None = None   # worker_type="sub_agent"일 때 필수

    def __post_init__(self) -> None:
        if self.worker_type not in ("tool", "sub_agent"):
            raise ValueError(f"worker_type must be 'tool' or 'sub_agent', got '{self.worker_type}'")
        if self.worker_type == "sub_agent" and not self.ref_agent_id:
            raise ValueError("ref_agent_id is required when worker_type='sub_agent'")
        if self.worker_type == "tool" and not self.tool_id:
            raise ValueError("tool_id is required when worker_type='tool'")
```

**변경 포인트:**
- `worker_type` 필드 추가 (기본값 `"tool"` — 하위 호환)
- `ref_agent_id` 필드 추가 (sub_agent 전용)
- `__post_init__` 검증: worker_type에 따른 필수 필드 확인
- `tool_id`는 sub_agent일 때 빈 문자열 허용 (FK 컬럼이 NOT NULL이므로 placeholder 사용)

#### 3.1.2 CircularReferencePolicy (`domain/agent_builder/policies.py`)

```python
class CircularReferenceError(ValueError):
    """에이전트 참조 순환 발생."""

    def __init__(self, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        path_str = " → ".join(cycle_path)
        super().__init__(f"순환참조가 감지되었습니다: {path_str}")


class CircularReferencePolicy:
    """에이전트 간 순환참조 방지 정책."""

    @staticmethod
    def validate_no_cycle(
        current_agent_id: str,
        visited: set[str],
    ) -> None:
        """현재 에이전트가 이미 방문 경로에 있으면 순환."""
        if current_agent_id in visited:
            cycle = list(visited) + [current_agent_id]
            raise CircularReferenceError(cycle)
```

**설계 의도:**
- 컴파일 시점에 `visited: set[str]`를 전파하여 O(N) 검사
- 에이전트 생성 시점에도 `_collect_sub_agent_refs()`로 재귀 탐색하여 사전 검증
- 에러 메시지에 순환 경로를 포함하여 디버깅 용이

#### 3.1.3 NestingDepthPolicy (`domain/agent_builder/policies.py`)

```python
class NestingDepthExceededError(ValueError):
    """중첩 깊이 초과."""

    def __init__(self, current_depth: int, max_depth: int) -> None:
        super().__init__(
            f"중첩 깊이 {current_depth}이(가) 최대 허용 깊이 {max_depth}을(를) 초과합니다"
        )


class NestingDepthPolicy:
    """에이전트 중첩 깊이 제한 정책."""

    MAX_NESTING_DEPTH = 2

    @classmethod
    def validate_depth(cls, current_depth: int) -> None:
        if current_depth > cls.MAX_NESTING_DEPTH:
            raise NestingDepthExceededError(current_depth, cls.MAX_NESTING_DEPTH)
```

**설계 의도:**
- `MAX_NESTING_DEPTH = 2`: 최상위(0) → 서브(1) → 서브서브(2)까지 허용
- 상수를 클래스 변수로 관리하여 추후 config 기반 변경 가능
- `validate_depth()`는 컴파일 시 `depth` 파라미터로 호출

#### 3.1.4 SubAgentAccessPolicy (`domain/agent_builder/policies.py`)

```python
class SubAgentAccessPolicy:
    """서브 에이전트 사용 권한 정책. 본인 소유 + 구독 에이전트만 허용."""

    @staticmethod
    def can_use_as_sub_agent(
        parent_owner_id: str,
        sub_agent_owner_id: str,
        is_subscribed: bool,
    ) -> bool:
        """서브 에이전트로 사용 가능 여부."""
        if parent_owner_id == sub_agent_owner_id:
            return True
        return is_subscribed
```

**설계 의도:**
- Plan에서 결정된 범위: 본인 소유 + 구독 에이전트
- `is_subscribed` 여부는 application 레이어에서 SubscriptionRepository로 조회 후 전달
- 순수 도메인 로직으로 외부 의존 없음

#### 3.1.5 AgentBuilderPolicy 확장 (`domain/agent_builder/policies.py`)

기존 `AgentBuilderPolicy`에 워커 수 검증 메서드 업데이트:

```python
class AgentBuilderPolicy:
    MAX_TOOLS = 5
    MAX_SUB_AGENTS = 3
    MAX_WORKERS_TOTAL = 6   # tool + sub_agent 합산 최대
    MIN_TOOLS = 0           # 변경: sub_agent만으로도 구성 가능
    MIN_WORKERS = 1         # 신규: 최소 1개 워커 필수

    @classmethod
    def validate_worker_count(cls, workers: list) -> None:
        """tool + sub_agent 혼합 워커 수 검증."""
        if len(workers) < cls.MIN_WORKERS:
            raise ValueError(f"최소 {cls.MIN_WORKERS}개 이상의 워커가 필요합니다.")
        if len(workers) > cls.MAX_WORKERS_TOTAL:
            raise ValueError(f"워커는 최대 {cls.MAX_WORKERS_TOTAL}개까지 선택할 수 있습니다.")

        tool_count = sum(1 for w in workers if w.worker_type == "tool")
        sub_agent_count = sum(1 for w in workers if w.worker_type == "sub_agent")

        if tool_count > cls.MAX_TOOLS:
            raise ValueError(f"도구는 최대 {cls.MAX_TOOLS}개까지 선택할 수 있습니다.")
        if sub_agent_count > cls.MAX_SUB_AGENTS:
            raise ValueError(f"서브 에이전트는 최대 {cls.MAX_SUB_AGENTS}개까지 선택할 수 있습니다.")
```

**변경 포인트:**
- 기존 `validate_tool_count(count: int)` → `validate_worker_count(workers: list)` 로 확장
- `MIN_TOOLS` 0으로 변경 (sub_agent만으로 구성 가능)
- `MIN_WORKERS = 1` 추가 (최소 1개 워커 필수)
- 하위 호환: 기존 `validate_tool_count()`는 유지하되 내부에서 `validate_worker_count()` 호출

---

### 3.2 Infrastructure Layer

#### 3.2.1 DB Migration (`db/migration/V014__add_worker_type_to_agent_tool.sql`)

```sql
ALTER TABLE agent_tool
  ADD COLUMN worker_type VARCHAR(20) NOT NULL DEFAULT 'tool'
    AFTER tool_config,
  ADD COLUMN ref_agent_id VARCHAR(36) NULL
    AFTER worker_type;

ALTER TABLE agent_tool
  ADD CONSTRAINT fk_agent_tool_ref_agent
    FOREIGN KEY (ref_agent_id) REFERENCES agent_definition(id)
    ON DELETE SET NULL;

CREATE INDEX idx_agent_tool_ref_agent ON agent_tool(ref_agent_id);
```

**설계 결정:**
- `worker_type DEFAULT 'tool'`: 기존 데이터 무변경
- `ref_agent_id ON DELETE SET NULL`: 서브 에이전트 삭제 시 참조만 null 처리 (상위 에이전트 보존)
- `idx_agent_tool_ref_agent`: 역참조 조회 성능 (이 에이전트를 서브로 사용하는 상위 에이전트 찾기)

#### 3.2.2 ORM Model 확장 (`infrastructure/agent_builder/models.py`)

```python
class AgentToolModel(Base):
    __tablename__ = "agent_tool"
    __table_args__ = (
        UniqueConstraint("agent_id", "worker_id", name="uq_agent_worker"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    worker_type: Mapped[str] = mapped_column(              # 신규
        String(20), nullable=False, default="tool"
    )
    ref_agent_id: Mapped[str | None] = mapped_column(      # 신규
        String(36),
        ForeignKey("agent_definition.id", ondelete="SET NULL"),
        nullable=True,
    )

    agent: Mapped["AgentDefinitionModel"] = relationship(
        "AgentDefinitionModel", back_populates="tools",
        foreign_keys=[agent_id],
    )
```

**변경 포인트:**
- `worker_type` 컬럼 추가 (기본값 `"tool"`)
- `ref_agent_id` 컬럼 추가 (FK → agent_definition)
- `relationship`에 `foreign_keys=[agent_id]` 명시 (ambiguous FK 방지)

#### 3.2.3 Repository 매핑 업데이트 (`infrastructure/agent_builder/agent_definition_repository.py`)

**`save()` 변경:**

```python
# 기존
tools=[
    AgentToolModel(
        id=str(uuid.uuid4()),
        agent_id=agent.id,
        tool_id=w.tool_id,
        worker_id=w.worker_id,
        description=w.description,
        sort_order=w.sort_order,
        tool_config=w.tool_config,
    )
    for w in agent.workers
],

# 변경
tools=[
    AgentToolModel(
        id=str(uuid.uuid4()),
        agent_id=agent.id,
        tool_id=w.tool_id,
        worker_id=w.worker_id,
        description=w.description,
        sort_order=w.sort_order,
        tool_config=w.tool_config,
        worker_type=w.worker_type,           # 추가
        ref_agent_id=w.ref_agent_id,         # 추가
    )
    for w in agent.workers
],
```

**`_to_domain()` 변경:**

```python
def _to_domain(self, model: AgentDefinitionModel) -> AgentDefinition:
    return AgentDefinition(
        # ... 기존 필드 동일 ...
        workers=[
            WorkerDefinition(
                tool_id=t.tool_id,
                worker_id=t.worker_id,
                description=t.description or "",
                sort_order=t.sort_order,
                tool_config=t.tool_config,
                worker_type=t.worker_type,         # 추가
                ref_agent_id=t.ref_agent_id,       # 추가
            )
            for t in sorted(model.tools, key=lambda x: x.sort_order)
        ],
        # ... 나머지 필드 동일 ...
    )
```

---

### 3.3 Application Layer

#### 3.3.1 Application Schema 확장 (`application/agent_builder/schemas.py`)

```python
class SubAgentConfigRequest(BaseModel):
    """서브 에이전트 설정 요청 스키마."""
    ref_agent_id: str = Field(..., description="서브 에이전트로 사용할 에이전트 ID")
    description: str = Field("", max_length=500, description="상위 에이전트에서의 역할 설명")


class CreateAgentRequest(BaseModel):
    user_request: str = Field(..., max_length=1000)
    name: str = Field(..., max_length=200)
    user_id: str = ""
    llm_model_id: str | None = None
    visibility: str = Field("private", pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float = Field(0.70, ge=0.0, le=2.0)
    tool_configs: dict[str, RagToolConfigRequest] | None = None
    sub_agent_configs: list[SubAgentConfigRequest] | None = None  # 신규


class WorkerInfo(BaseModel):
    tool_id: str
    worker_id: str
    description: str
    sort_order: int
    tool_config: dict | None = None
    worker_type: str = "tool"               # 신규
    ref_agent_id: str | None = None         # 신규
    ref_agent_name: str | None = None       # 신규 (응답 전용, 표시용)


class CreateAgentResponse(BaseModel):
    # ... 기존 필드 동일 ...
    has_sub_agents: bool = False             # 신규 (빠른 판별용)
```

#### 3.3.2 WorkflowCompiler 확장 (`application/agent_builder/workflow_compiler.py`)

**핵심 변경: `compile()` 시그니처 및 로직**

```python
class WorkflowCompiler:
    def __init__(
        self,
        tool_factory: ToolFactory,
        llm_factory: LLMFactoryInterface,
        logger: LoggerInterface,
        hooks: SupervisorHooks | None = None,
        agent_repository: AgentDefinitionRepositoryInterface | None = None,  # 신규
    ) -> None:
        self._tool_factory = tool_factory
        self._llm_factory = llm_factory
        self._logger = logger
        self._hooks = hooks or DefaultHooks()
        self._agent_repository = agent_repository  # 서브 에이전트 조회용

    async def compile(                    # 변경: sync → async
        self,
        workflow: WorkflowDefinition,
        llm_model: LlmModel,
        request_id: str,
        temperature: float = 0.0,
        supervisor_config: SupervisorConfig | None = None,
        depth: int = 0,                   # 신규: 현재 중첩 깊이
        visited: set[str] | None = None,  # 신규: 순환참조 추적
        owner_user_id: str | None = None, # 신규: 접근 권한 검증용
    ):
        NestingDepthPolicy.validate_depth(depth)

        config = supervisor_config or SupervisorConfig()
        # ... 기존 LLM/Policy 초기화 동일 ...

        worker_map: dict[str, object] = {}
        for worker_def in workflow.workers:
            if worker_def.worker_type == "sub_agent":
                sub_node = await self._compile_sub_agent(
                    worker_def=worker_def,
                    llm_model=llm_model,
                    request_id=request_id,
                    temperature=temperature,
                    supervisor_config=config,
                    depth=depth + 1,
                    visited=visited or set(),
                    owner_user_id=owner_user_id,
                )
                worker_map[worker_def.worker_id] = sub_node
            else:
                tool = self._tool_factory.create(
                    worker_def.tool_id, request_id,
                    tool_config=worker_def.tool_config,
                )
                worker_agent = create_react_agent(
                    llm, tools=[tool], name=worker_def.worker_id,
                )
                worker_map[worker_def.worker_id] = worker_agent

        # ... 이하 기존 StateGraph 조립 동일 ...
```

**신규 메서드: `_compile_sub_agent()`**

```python
    async def _compile_sub_agent(
        self,
        worker_def: WorkerDefinition,
        llm_model: LlmModel,
        request_id: str,
        temperature: float,
        supervisor_config: SupervisorConfig,
        depth: int,
        visited: set[str],
        owner_user_id: str | None,
    ):
        """서브 에이전트를 재귀 컴파일하여 래핑된 노드 함수 반환."""
        if self._agent_repository is None:
            raise ValueError("agent_repository is required for sub_agent compilation")

        ref_id = worker_def.ref_agent_id
        CircularReferencePolicy.validate_no_cycle(ref_id, visited)

        sub_agent = await self._agent_repository.find_by_id(ref_id, request_id)
        if sub_agent is None or sub_agent.status == "deleted":
            raise ValueError(f"서브 에이전트를 찾을 수 없습니다: {ref_id}")

        sub_llm_model = await self._resolve_sub_agent_llm(sub_agent, request_id)

        new_visited = visited | {ref_id}
        sub_workflow = sub_agent.to_workflow_definition()
        sub_graph = await self.compile(
            workflow=sub_workflow,
            llm_model=sub_llm_model,
            request_id=request_id,
            temperature=sub_agent.temperature,
            supervisor_config=supervisor_config,
            depth=depth,
            visited=new_visited,
            owner_user_id=owner_user_id,
        )

        return self._wrap_sub_agent(worker_def.worker_id, sub_graph)
```

**신규 메서드: `_wrap_sub_agent()`**

```python
    def _wrap_sub_agent(self, worker_id: str, sub_graph):
        """서브 에이전트 그래프를 상위 StateGraph 노드로 래핑. Task 위임 방식."""

        async def wrapped(state: SupervisorState) -> dict:
            last_msg = state["messages"][-1]
            task_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            sub_initial = build_initial_state(
                messages=[{"role": "user", "content": task_content}],
                config=SupervisorConfig(
                    token_limit=state["token_limit"] // 2,
                ),
                available_workers=[],  # 서브 그래프 내부에서 자체 관리
            )

            result = await sub_graph.ainvoke(sub_initial)
            sub_messages = result.get("messages", [])

            answer_content = ""
            if sub_messages:
                last = sub_messages[-1]
                answer_content = last.content if hasattr(last, "content") else str(last)

            from langchain_core.messages import AIMessage
            answer_msg = AIMessage(
                content=answer_content,
                name=worker_id,
            )

            sub_token_usage = result.get("token_usage", 0)

            return {
                "messages": [answer_msg],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + sub_token_usage,
            }

        return wrapped
```

**`compile()` sync → async 전환 영향:**

| 호출처 | 변경 |
|--------|------|
| `RunAgentUseCase.execute()` | `self._compiler.compile()` → `await self._compiler.compile()` |
| 테스트 | `compiler.compile()` → `await compiler.compile()` |

#### 3.3.3 CreateAgentUseCase 확장 (`application/agent_builder/create_agent_use_case.py`)

**생성자 변경:**

```python
class CreateAgentUseCase:
    def __init__(
        self,
        tool_selector: ToolSelector,
        prompt_generator: PromptGenerator,
        repository: AgentDefinitionRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        perm_repo: CollectionPermissionRepositoryInterface,
        subscription_repo: SubscriptionRepositoryInterface,  # 신규
        logger: LoggerInterface,
    ) -> None:
        # ... 기존 + subscription_repo 추가 ...
        self._subscription_repo = subscription_repo
```

**`execute()` 내 sub_agent 처리 추가:**

```python
    async def execute(self, request: CreateAgentRequest, request_id: str):
        # ... Step 0~1: 기존 LLM 모델, tool 선택 동일 ...

        # Step 1.5: 서브 에이전트 워커 빌드 (신규)
        sub_agent_workers = []
        if request.sub_agent_configs:
            sub_agent_workers = await self._build_sub_agent_workers(
                configs=request.sub_agent_configs,
                user_id=request.user_id,
                request_id=request_id,
                existing_tool_count=len(skeleton.workers) if not request.tool_configs else len(request.tool_configs),
            )

        # Step 2: 모든 워커 합산 검증
        all_workers = list(skeleton.workers) + sub_agent_workers
        AgentBuilderPolicy.validate_worker_count(all_workers)

        # ... Step 3~4: 프롬프트 생성, 저장 (workers=all_workers) ...
```

**신규 메서드: `_build_sub_agent_workers()`**

```python
    async def _build_sub_agent_workers(
        self,
        configs: list[SubAgentConfigRequest],
        user_id: str,
        request_id: str,
        existing_tool_count: int,
    ) -> list[WorkerDefinition]:
        workers: list[WorkerDefinition] = []

        for i, config in enumerate(configs):
            # 1. 서브 에이전트 존재 확인
            sub_agent = await self._repository.find_by_id(config.ref_agent_id, request_id)
            if sub_agent is None or sub_agent.status == "deleted":
                raise ValueError(f"서브 에이전트를 찾을 수 없습니다: {config.ref_agent_id}")

            # 2. 접근 권한 검증 (본인 소유 or 구독)
            is_subscribed = await self._check_subscription(
                user_id, config.ref_agent_id, request_id
            )
            if not SubAgentAccessPolicy.can_use_as_sub_agent(
                parent_owner_id=user_id,
                sub_agent_owner_id=sub_agent.user_id,
                is_subscribed=is_subscribed,
            ):
                raise PermissionError(
                    f"서브 에이전트 '{sub_agent.name}'에 대한 사용 권한이 없습니다"
                )

            # 3. 순환참조 검증 (서브 에이전트의 하위 참조 재귀 탐색)
            visited = set()
            self._check_circular_refs(sub_agent, visited, request_id)

            # 4. 중첩 깊이 검증
            sub_depth = self._calculate_max_depth(sub_agent)
            NestingDepthPolicy.validate_depth(sub_depth + 1)

            # 5. WorkerDefinition 생성
            description = config.description or sub_agent.description
            workers.append(WorkerDefinition(
                tool_id=f"sub_agent_{config.ref_agent_id[:8]}",  # placeholder
                worker_id=f"sub_agent_{sub_agent.name}_{i}",
                description=description,
                sort_order=existing_tool_count + i,
                worker_type="sub_agent",
                ref_agent_id=config.ref_agent_id,
            ))

        return workers

    async def _check_subscription(
        self, user_id: str, agent_id: str, request_id: str
    ) -> bool:
        sub = await self._subscription_repo.find_by_user_and_agent(
            user_id, agent_id, request_id
        )
        return sub is not None
```

#### 3.3.4 RunAgentUseCase 변경 (`application/agent_builder/run_agent_use_case.py`)

**compile 호출 변경 (async + 파라미터 추가):**

```python
    # 기존
    graph = self._compiler.compile(
        workflow=workflow,
        llm_model=llm_model,
        temperature=agent.temperature,
        request_id=request_id,
        supervisor_config=config,
    )

    # 변경
    graph = await self._compiler.compile(
        workflow=workflow,
        llm_model=llm_model,
        temperature=agent.temperature,
        request_id=request_id,
        supervisor_config=config,
        depth=0,
        visited={agent_id},
        owner_user_id=viewer_user_id or agent.user_id,
    )
```

---

### 3.4 API Layer

#### 3.4.1 사용 가능한 서브 에이전트 목록 API (신규)

```
GET /api/v1/agents/available-sub-agents
```

**역할:** 현재 사용자가 서브 에이전트로 사용 가능한 에이전트 목록 반환 (본인 소유 + 구독)

**응답:**

```python
class AvailableSubAgentsResponse(BaseModel):
    agents: list[SubAgentCandidate]

class SubAgentCandidate(BaseModel):
    agent_id: str
    name: str
    description: str
    source_type: str       # "owned" | "subscribed"
    tool_ids: list[str]    # 포함된 도구 목록 (UI 표시용)
    has_sub_agents: bool   # 이미 서브 에이전트를 포함하는지 (깊이 경고용)
```

#### 3.4.2 CreateAgent API 변경 (기존 엔드포인트)

요청 body에 `sub_agent_configs` 필드 추가만으로 동작 (Pydantic 자동 처리).
별도 라우터 코드 변경 불필요.

#### 3.4.3 GetAgent 응답 확장

`GetAgentResponse.workers`의 `WorkerInfo`에 이미 추가된 `worker_type`, `ref_agent_id`, `ref_agent_name`이 자동 포함.

`ref_agent_name`은 GetAgentUseCase에서 `ref_agent_id`로 에이전트명을 조회하여 채움:

```python
# GetAgentUseCase 내
for worker in workers:
    if worker.worker_type == "sub_agent" and worker.ref_agent_id:
        sub = await self._repository.find_by_id(worker.ref_agent_id, request_id)
        worker.ref_agent_name = sub.name if sub else "(삭제됨)"
```

---

## 4. Implementation Order

TDD 원칙: 각 단계에서 테스트 먼저 작성 → Red → Green → Refactor.

### Phase 1: Domain Layer (테스트 14개)

| # | 파일 | 변경 | 테스트 |
|---|------|------|--------|
| 1-1 | `domain/agent_builder/schemas.py` | WorkerDefinition에 `worker_type`, `ref_agent_id` 추가, `__post_init__` 검증 | `test_worker_definition_sub_agent_type` |
| 1-2 | `domain/agent_builder/schemas.py` | WorkerDefinition sub_agent일 때 ref_agent_id 필수 검증 | `test_worker_definition_sub_agent_requires_ref_id` |
| 1-3 | `domain/agent_builder/schemas.py` | WorkerDefinition 기본값 tool 하위 호환 | `test_worker_definition_default_tool_type` |
| 1-4 | `domain/agent_builder/policies.py` | `CircularReferencePolicy.validate_no_cycle()` | `test_circular_ref_detects_cycle` |
| 1-5 | `domain/agent_builder/policies.py` | CircularReferencePolicy 정상 경로 (순환 없음) | `test_circular_ref_allows_valid_chain` |
| 1-6 | `domain/agent_builder/policies.py` | `CircularReferenceError` 에러 메시지에 경로 포함 | `test_circular_ref_error_includes_path` |
| 1-7 | `domain/agent_builder/policies.py` | `NestingDepthPolicy.validate_depth()` depth=2 허용 | `test_nesting_depth_allows_max` |
| 1-8 | `domain/agent_builder/policies.py` | NestingDepthPolicy depth=3 거부 | `test_nesting_depth_rejects_over_max` |
| 1-9 | `domain/agent_builder/policies.py` | NestingDepthPolicy depth=0 허용 | `test_nesting_depth_allows_zero` |
| 1-10 | `domain/agent_builder/policies.py` | `SubAgentAccessPolicy.can_use_as_sub_agent()` 본인 소유 → True | `test_sub_agent_access_owner` |
| 1-11 | `domain/agent_builder/policies.py` | SubAgentAccessPolicy 구독 → True | `test_sub_agent_access_subscribed` |
| 1-12 | `domain/agent_builder/policies.py` | SubAgentAccessPolicy 비접근 → False | `test_sub_agent_access_denied` |
| 1-13 | `domain/agent_builder/policies.py` | `AgentBuilderPolicy.validate_worker_count()` 혼합 워커 | `test_validate_worker_count_mixed` |
| 1-14 | `domain/agent_builder/policies.py` | validate_worker_count sub_agent 초과 | `test_validate_worker_count_exceeds_sub_agent_max` |

### Phase 2: Infrastructure Layer (테스트 4개)

| # | 파일 | 변경 | 테스트 |
|---|------|------|--------|
| 2-1 | `db/migration/V014__*.sql` | DDL 작성 | (마이그레이션 자체) |
| 2-2 | `infrastructure/agent_builder/models.py` | `worker_type`, `ref_agent_id` 컬럼 추가 | `test_agent_tool_model_columns` |
| 2-3 | `infrastructure/agent_builder/agent_definition_repository.py` | `save()` 매핑 | `test_repository_save_sub_agent_worker` |
| 2-4 | `infrastructure/agent_builder/agent_definition_repository.py` | `_to_domain()` 매핑 | `test_repository_to_domain_sub_agent` |

### Phase 3: Application Layer (테스트 8개)

| # | 파일 | 변경 | 테스트 |
|---|------|------|--------|
| 3-1 | `application/agent_builder/schemas.py` | `SubAgentConfigRequest`, `WorkerInfo` 확장 | `test_sub_agent_config_schema` |
| 3-2 | `application/agent_builder/workflow_compiler.py` | `compile()` async 전환 + depth/visited 파라미터 | `test_compiler_async_basic` |
| 3-3 | `application/agent_builder/workflow_compiler.py` | `_compile_sub_agent()` 재귀 컴파일 | `test_compiler_sub_agent_compile` |
| 3-4 | `application/agent_builder/workflow_compiler.py` | `_wrap_sub_agent()` Task 위임 래핑 | `test_compiler_wrap_sub_agent_task_delegation` |
| 3-5 | `application/agent_builder/workflow_compiler.py` | 순환참조 시 에러 | `test_compiler_circular_ref_error` |
| 3-6 | `application/agent_builder/workflow_compiler.py` | 깊이 초과 시 에러 | `test_compiler_depth_exceeded_error` |
| 3-7 | `application/agent_builder/create_agent_use_case.py` | sub_agent_configs 처리 | `test_create_agent_with_sub_agents` |
| 3-8 | `application/agent_builder/create_agent_use_case.py` | Tool + Sub-Agent 혼합 생성 | `test_create_agent_mixed_workers` |

### Phase 4: API Layer (테스트 3개)

| # | 파일 | 변경 | 테스트 |
|---|------|------|--------|
| 4-1 | `api/routes/agent_builder_router.py` | available-sub-agents 엔드포인트 | `test_list_available_sub_agents_api` |
| 4-2 | `api/routes/agent_builder_router.py` | CreateAgent body 확장 (자동) | `test_create_agent_api_with_sub_agents` |
| 4-3 | `application/agent_builder/get_agent_use_case.py` | ref_agent_name 조회 | `test_get_agent_includes_sub_agent_name` |

---

## 5. Error Handling

| 상황 | 에러 | HTTP 코드 | 메시지 |
|------|------|-----------|--------|
| 존재하지 않는 서브 에이전트 참조 | `ValueError` | 400 | "서브 에이전트를 찾을 수 없습니다: {id}" |
| 삭제된 서브 에이전트 참조 | `ValueError` | 400 | "서브 에이전트를 찾을 수 없습니다: {id}" |
| 서브 에이전트 접근 권한 없음 | `PermissionError` | 403 | "서브 에이전트 '{name}'에 대한 사용 권한이 없습니다" |
| 순환참조 감지 | `CircularReferenceError` | 400 | "순환참조가 감지되었습니다: A → B → A" |
| 중첩 깊이 초과 | `NestingDepthExceededError` | 400 | "중첩 깊이 3이(가) 최대 허용 깊이 2을(를) 초과합니다" |
| 워커 수 초과 | `ValueError` | 400 | "워커는 최대 6개까지 선택할 수 있습니다" |
| 서브 에이전트 수 초과 | `ValueError` | 400 | "서브 에이전트는 최대 3개까지 선택할 수 있습니다" |
| 실행 시 삭제된 서브 에이전트 | `ValueError` | 400 | "서브 에이전트를 찾을 수 없습니다: {id}" |

---

## 6. Migration & Backward Compatibility

### 6.1 DB Migration

- `ALTER TABLE` 단일 마이그레이션으로 처리
- `worker_type DEFAULT 'tool'` — 기존 행 무변경
- `ref_agent_id NULL` — 기존 행에 영향 없음

### 6.2 Code Compatibility

| 변경 | 영향 | 호환 전략 |
|------|------|----------|
| WorkerDefinition 필드 추가 | 기존 생성 코드 | 기본값 설정으로 영향 없음 |
| `compile()` sync → async | 호출처 2곳 | `await` 추가 필요 (RunAgentUseCase, 테스트) |
| `validate_tool_count()` → `validate_worker_count()` | CreateAgentUseCase | 기존 메서드는 유지, 내부 위임 |
| Repository 매핑 | 기존 데이터 | 새 필드 기본값이므로 역방향 호환 |

### 6.3 Rollback Plan

1. 마이그레이션 롤백: `ALTER TABLE agent_tool DROP COLUMN worker_type, DROP COLUMN ref_agent_id`
2. 코드 롤백: git revert (기존 코드 변경 최소화 설계)

---

## 7. File Change Matrix

| 파일 | 변경 유형 | 주요 변경 |
|------|----------|----------|
| `domain/agent_builder/schemas.py` | 수정 | WorkerDefinition 필드 추가, `__post_init__` |
| `domain/agent_builder/policies.py` | 수정 | 3개 Policy 클래스 + 2개 Error 클래스 추가, AgentBuilderPolicy 확장 |
| `infrastructure/agent_builder/models.py` | 수정 | AgentToolModel 컬럼 2개 추가 |
| `infrastructure/agent_builder/agent_definition_repository.py` | 수정 | save(), _to_domain() 매핑 |
| `application/agent_builder/schemas.py` | 수정 | SubAgentConfigRequest, WorkerInfo, CreateAgentRequest 확장 |
| `application/agent_builder/workflow_compiler.py` | 수정 | compile() async화, _compile_sub_agent(), _wrap_sub_agent() |
| `application/agent_builder/create_agent_use_case.py` | 수정 | _build_sub_agent_workers(), subscription_repo 주입 |
| `application/agent_builder/run_agent_use_case.py` | 수정 | compile() await 추가 |
| `application/agent_builder/get_agent_use_case.py` | 수정 | ref_agent_name 조회 |
| `api/routes/agent_builder_router.py` | 수정 | available-sub-agents 엔드포인트 추가 |
| `db/migration/V014__add_worker_type_to_agent_tool.sql` | 신규 | DDL |
| `tests/domain/agent_builder/test_multi_agent_policies.py` | 신규 | 도메인 정책 테스트 14개 |
| `tests/application/agent_builder/test_workflow_compiler_sub_agent.py` | 신규 | 컴파일러 테스트 6개 |
| `tests/application/agent_builder/test_create_agent_sub_agent.py` | 신규 | 생성 테스트 2개 |
