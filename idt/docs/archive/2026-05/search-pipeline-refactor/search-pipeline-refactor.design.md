# search-pipeline-refactor Design Document

> **Summary**: 도구 카테고리 기반 워커 자동 분기 + Answer Agent 자동 할당 상세 설계
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-11
> **Status**: Draft
> **Planning Doc**: [search-pipeline-refactor.plan.md](../../01-plan/features/search-pipeline-refactor.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. 검색 도구 워커에서 LLM 추론을 **구조적으로 제거**하여 역할 일탈 원천 차단
2. 기존 액션 도구 에이전트의 동작을 **100% 하위 호환** 유지
3. Answer Agent를 시스템 내부 노드로 자동 주입 — 사용자 추가 설정 불필요
4. 새 도구 추가 시 `category` 값만 지정하면 자동 분기 — 확장 비용 최소화

### 1.2 Design Principles

- **Structural Enforcement**: LLM 행동을 프롬프트로 제어하지 않고 파이프라인 구조로 강제
- **Open-Closed**: `ToolMeta.category` 확장으로 새 분기 추가 가능, 기존 코드 수정 불필요
- **Backward Compatibility**: `category` 기본값 `"action"` → 기존 도구는 코드 변경 없이 동일 동작

---

## 2. Architecture

### 2.1 현행 그래프 구조 (Before)

```
┌──────────────────────────────────────────────────┐
│  entry                                           │
│    ↓                                             │
│  [supervisor] ──→ [worker_0 (LLM+tool)] ──→ [quality_gate]
│       ↑               ReAct Agent                  │
│       │                                            │
│       ←────────────────────────────────────────────┘
│       │
│       ↓ (FINISH)
│     END
└──────────────────────────────────────────────────┘

문제: 모든 워커가 create_react_agent → LLM이 자유 추론
      검색 도구 워커도 판단/추천/결론을 포함할 수 있음
```

### 2.2 신규 그래프 구조 (After)

```
┌────────────────────────────────────────────────────────────┐
│  entry                                                     │
│    ↓                                                       │
│  [supervisor]                                              │
│    │         │            │                                │
│    ↓         ↓            ↓                                │
│  [search_0] [search_1] [action_0]                          │
│  (tool 직접) (tool 직접) (LLM+tool)                        │
│    │         │            │                                │
│    ↓         ↓            ↓                                │
│  [quality_gate] ←─────────┘                                │
│    │                                                       │
│    ↓                                                       │
│  [supervisor] ──→ ... ──→ [answer_agent] ──→ END           │
│                           (LLM, 검색결과 종합)              │
└────────────────────────────────────────────────────────────┘

핵심: search 워커는 LLM 없이 tool 직접 호출
      answer_agent만 LLM 추론 (수집된 데이터 기반 답변)
```

### 2.3 시나리오별 그래프 변형

#### Case A: 검색 도구만 있는 에이전트 (e.g. 리서처)

```
supervisor → search_worker_0 → quality_gate → supervisor
           → search_worker_1 → quality_gate → supervisor
           → answer_agent → END
```
- LLM 호출: Supervisor 라우팅 + Answer Agent 답변 = **2회만**
- 검색 단계에서 LLM 개입 **0회**

#### Case B: 액션 도구만 있는 에이전트 (e.g. 코드 실행기)

```
supervisor → action_worker_0 → quality_gate → supervisor
           → action_worker_1 → quality_gate → supervisor → END
```
- **기존과 100% 동일** — answer_agent 미주입
- `create_react_agent` 그대로 사용

#### Case C: 혼합 에이전트 (검색 + 액션)

```
supervisor → search_worker → quality_gate → supervisor
           → action_worker → quality_gate → supervisor
           → answer_agent → END
```
- 검색은 직접 실행, 액션은 ReAct
- Answer Agent가 모든 결과를 종합하여 최종 답변

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `WorkflowCompiler` | `ToolMeta.category` | 워커 타입 분기 결정 |
| `WorkflowCompiler` | `ToolFactory` | tool 인스턴스 생성 (기존과 동일) |
| Search Node | `BaseTool.ainvoke()` | LLM 없이 tool 직접 호출 |
| Answer Agent Node | `BaseChatModel` | 검색 결과 종합 답변 |
| `supervisor_nodes` | `SupervisorState` | answer_agent 라우팅 조건 |

---

## 3. Data Model

### 3.1 ToolMeta 확장

```python
# src/domain/agent_builder/schemas.py

ToolCategory = Literal["search", "action"]

@dataclass(frozen=True)
class ToolMeta:
    tool_id: str
    name: str
    description: str
    requires_env: list[str] = field(default_factory=list)
    category: ToolCategory = "action"   # NEW: 기본값 "action" → 하위 호환
```

**카테고리 분류 기준**:

| category | 정의 | 예시 |
|----------|------|------|
| `search` | 외부 데이터를 가져오기만 하는 도구. 입력→결과가 deterministic. | `internal_document_search`, `tavily_search` |
| `action` | LLM 추론이 필요한 도구. 입력 해석/코드 생성/파일 생성 등. | `python_code_executor`, `excel_export` |

### 3.2 TOOL_REGISTRY 카테고리 할당

```python
# src/domain/agent_builder/tool_registry.py

TOOL_REGISTRY = {
    "internal_document_search": ToolMeta(
        tool_id="internal_document_search",
        name="내부 문서 검색",
        description="...",
        category="search",          # ← search
    ),
    "tavily_search": ToolMeta(
        tool_id="tavily_search",
        name="Tavily 웹 검색",
        description="...",
        requires_env=["TAVILY_API_KEY"],
        category="search",          # ← search
    ),
    "excel_export": ToolMeta(
        tool_id="excel_export",
        name="Excel 파일 생성",
        description="...",
        category="action",          # ← action (기본값)
    ),
    "python_code_executor": ToolMeta(
        tool_id="python_code_executor",
        name="Python 코드 실행",
        description="...",
        category="action",          # ← action (기본값)
    ),
}
```

### 3.3 DB 스키마 변경: `agent_tool.category` 컬럼 추가

카테고리는 TOOL_REGISTRY(내부 도구)와 DB(MCP·외부 도구) **양쪽에서** 결정된다.

- 내부 도구: `TOOL_REGISTRY`에 기본 카테고리가 정의되어 있으므로 DB에 저장하지 않아도 동작
- MCP 도구: `TOOL_REGISTRY`에 없으므로 **DB에 카테고리를 저장해야** 컴파일 시점에 분기 가능
- 에이전트별 오버라이드: 같은 도구라도 에이전트 설계 의도에 따라 카테고리를 다르게 쓸 수 있음

#### agent_tool 테이블 변경

```sql
-- 마이그레이션: V__add_agent_tool_category.sql
ALTER TABLE agent_tool
    ADD COLUMN category VARCHAR(20) NULL DEFAULT NULL;
```

| 컬럼 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `category` | VARCHAR(20) | NULL | `"search"` / `"action"` / NULL (NULL이면 TOOL_REGISTRY fallback) |

#### AgentToolModel 변경

```python
# src/infrastructure/agent_builder/models.py

class AgentToolModel(Base):
    __tablename__ = "agent_tool"
    # ... 기존 컬럼 ...
    category: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None,
    )
```

#### WorkerDefinition 확장

```python
# src/domain/agent_builder/schemas.py

@dataclass
class WorkerDefinition:
    tool_id: str
    worker_id: str
    description: str
    sort_order: int = 0
    tool_config: dict | None = None
    worker_type: str = "tool"
    ref_agent_id: str | None = None
    category: str | None = None  # NEW: DB에서 로드된 카테고리 (None이면 TOOL_REGISTRY fallback)
```

#### 카테고리 결정 우선순위 (3-tier fallback)

```
1. WorkerDefinition.category (DB 값, 에이전트별 오버라이드)
       ↓ None이면
2. TOOL_REGISTRY[tool_id].category (내부 도구 기본값)
       ↓ TOOL_REGISTRY에 없으면 (MCP 등)
3. "action" (최종 기본값)
```

```python
# WorkflowCompiler 내부 헬퍼
def _resolve_category(self, worker_def: WorkerDefinition) -> str:
    """카테고리 결정: DB 오버라이드 → TOOL_REGISTRY → 기본값 "action"."""
    if worker_def.category is not None:
        return worker_def.category
    try:
        meta = get_tool_meta(worker_def.tool_id)
        return meta.category
    except ValueError:
        return "action"
```

### 3.4 MCP 도구 카테고리 처리

MCP 도구는 `TOOL_REGISTRY`에 등록되지 않으므로 DB의 `agent_tool.category`로 관리한다.

| 시나리오 | category 값 | 동작 |
|----------|------------|------|
| MCP 웹 검색 도구 등록 시 | `"search"` 저장 | Search Node (tool 직접 실행) |
| MCP 코드 실행 도구 등록 시 | `"action"` 저장 | Action Node (LLM ReAct) |
| MCP 도구 category 미지정 | NULL → fallback `"action"` | Action Node (안전한 기본값) |

MCP 도구 등록 흐름:
```
MCP 서버 연결 → 도구 목록 로드 → 사용자가 에이전트에 도구 추가
→ 이 시점에 category를 선택하거나, 도구 description 기반 자동 분류
→ agent_tool 테이블에 category 값과 함께 저장
```

---

## 4. Component Specification

### 4.1 WorkflowCompiler.compile() 변경

```python
# src/application/agent_builder/workflow_compiler.py

async def compile(self, workflow, llm_model, request_id, ...):
    llm = self._llm_factory.create(llm_model, temperature)
    policy = QualityGatePolicy()

    worker_map: dict[str, object] = {}
    has_search_workers = False

    for worker_def in workflow.workers:
        if worker_def.worker_type == "sub_agent":
            sub_node = await self._compile_sub_agent(...)
            worker_map[worker_def.worker_id] = sub_node
        else:
            tool = self._tool_factory.create(
                worker_def.tool_id, request_id,
                tool_config=worker_def.tool_config,
            )
            category = self._resolve_category(worker_def)

            if category == "search":
                # Search Node: LLM 없이 tool 직접 호출
                worker_map[worker_def.worker_id] = self._create_search_node(
                    worker_def.worker_id, tool,
                )
                has_search_workers = True
            else:
                # Action Node: 기존 create_react_agent
                worker_agent = create_react_agent(
                    llm, tools=[tool], name=worker_def.worker_id,
                )
                worker_map[worker_def.worker_id] = self._wrap_worker(
                    worker_def.worker_id, worker_agent,
                )

    # --- 그래프 구성 ---
    graph = StateGraph(SupervisorState)
    graph.add_node("supervisor", supervisor_fn)
    graph.add_node("quality_gate", quality_gate_fn)

    for worker_id, node in worker_map.items():
        graph.add_node(worker_id, node)

    # 검색 워커가 있으면 Answer Agent 자동 주입
    if has_search_workers:
        graph.add_node(
            "answer_agent",
            self._create_answer_node(llm, workflow.supervisor_prompt),
        )

    # 라우팅 설정
    graph.set_entry_point("supervisor")
    route_map = {wid: wid for wid in worker_map}
    if has_search_workers:
        route_map["answer_agent"] = "answer_agent"
    route_map["__end__"] = END
    graph.add_conditional_edges("supervisor", route_to_worker, route_map)

    # 워커 → quality_gate
    for worker_id in worker_map:
        graph.add_edge(worker_id, "quality_gate")

    # quality_gate 라우팅
    qg_route_map = {"supervisor": "supervisor"}
    for wid in worker_map:
        qg_route_map[wid] = wid
    graph.add_conditional_edges("quality_gate", route_after_quality, qg_route_map)

    # answer_agent → END
    if has_search_workers:
        graph.add_edge("answer_agent", END)

    return graph.compile()
```

**분기 판단 로직**:
- `get_tool_meta(tool_id).category == "search"` → `_create_search_node()`
- 그 외 → 기존 `create_react_agent` + `_wrap_worker()`
- `mcp_` prefix → TOOL_REGISTRY에 없으므로 `get_tool_meta()` 호출 안 함 → 기존 로직 유지 필요

**MCP 도구 처리**:
`_resolve_category()`가 3-tier fallback을 처리하므로 MCP 전용 분기가 불필요하다.
```python
# MCP든 내부 도구든 동일한 흐름:
category = self._resolve_category(worker_def)
# → worker_def.category가 DB에 있으면 그 값 사용 (MCP 등록 시 저장)
# → 없으면 TOOL_REGISTRY fallback
# → TOOL_REGISTRY에도 없으면 "action" (MCP 기본값)
```
단, MCP 도구는 `tool_factory.create_async()`로 비동기 생성해야 하므로 tool 생성 부분만 분기:
```python
if worker_def.tool_id.startswith("mcp_"):
    tool = await self._tool_factory.create_async(worker_def.tool_id, request_id, ...)
else:
    tool = self._tool_factory.create(worker_def.tool_id, request_id, ...)

# 카테고리 분기는 MCP/내부 구분 없이 동일
category = self._resolve_category(worker_def)
if category == "search":
    ...
```

### 4.2 Search Node 상세

```python
def _create_search_node(self, worker_id: str, tool: BaseTool):
    """검색 도구를 LLM 없이 직접 실행하는 노드."""
    logger = self._logger

    async def search_node(state: SupervisorState) -> dict:
        last_msg = state["messages"][-1]
        query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        logger.info("search_node executing", worker_id=worker_id, query_length=len(query))

        try:
            result = await tool.ainvoke({"query": query})
        except Exception as e:
            logger.error("search_node tool failed", worker_id=worker_id, exception=e)
            result = f"검색 실패: {e}"

        result_str = result if isinstance(result, str) else str(result)

        from langchain_core.messages import AIMessage
        result_msg = AIMessage(
            content=f"[{worker_id} 검색결과]\n{result_str}",
            name=worker_id,
        )

        token_delta = len(result_str) // 4

        return {
            "messages": [result_msg],
            "last_worker_id": worker_id,
            "token_usage": state["token_usage"] + token_delta,
        }

    return search_node
```

**설계 결정**:
- 쿼리 추출: `state["messages"][-1].content` — Supervisor가 라우팅 시 마지막 메시지가 사용자 질문 또는 Supervisor 지시
- 결과 포맷: `[{worker_id} 검색결과]\n{원본}` — Answer Agent가 출처별로 구분 가능
- 에러 처리: tool 호출 실패 시 예외를 메시지로 변환 (그래프 중단 방지)
- `token_usage`: 검색 결과 길이 기반 근사 계산 (기존 `_wrap_worker`와 동일 방식)

### 4.3 Answer Agent Node 상세

```python
def _create_answer_node(self, llm: BaseChatModel, system_prompt: str):
    """수집된 검색 결과를 종합하여 최종 답변을 생성하는 노드."""
    logger = self._logger

    async def answer_node(state: SupervisorState) -> dict:
        # 검색 결과 메시지 수집 (name 속성이 있는 AI 메시지 중 검색결과 태그 포함)
        search_results = []
        for msg in state["messages"]:
            content = msg.content if hasattr(msg, "content") else ""
            if hasattr(msg, "name") and msg.name and "검색결과" in content:
                search_results.append(content)

        if not search_results:
            logger.warning("answer_node: no search results found")
            # 검색 결과 없이도 답변 시도
            context = "(검색 결과 없음)"
        else:
            context = "\n\n---\n\n".join(search_results)

        # 원본 사용자 질문 추출 (첫 번째 user 메시지)
        user_query = ""
        for msg in state["messages"]:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
            if role in ("user", "human"):
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                user_query = content
                break

        answer_prompt = (
            f"{system_prompt}\n\n"
            f"아래 검색 결과를 바탕으로 사용자의 질문에 정확하게 답변하세요.\n"
            f"검색 결과에 없는 내용은 추측하지 마세요.\n\n"
            f"[수집된 검색 결과]\n{context}"
        )

        messages = [
            {"role": "system", "content": answer_prompt},
            {"role": "user", "content": user_query},
        ]

        logger.info("answer_node executing", search_result_count=len(search_results))

        response = await llm.ainvoke(messages)

        token_delta = len(response.content) // 4 if hasattr(response, "content") else 0

        return {
            "messages": [response],
            "last_worker_id": "answer_agent",
            "token_usage": state["token_usage"] + token_delta,
        }

    return answer_node
```

**설계 결정**:
- 검색 결과 식별: `"검색결과"` 태그로 필터 (Search Node가 `[{worker_id} 검색결과]` 형식으로 출력)
- 사용자 질문 추출: `state["messages"]`에서 첫 번째 user 메시지 탐색
- System Prompt: 에이전트의 원래 `system_prompt` + 검색 결과 컨텍스트 주입
- "검색 결과에 없는 내용은 추측하지 마세요" — Answer Agent의 hallucination 최소화 가이드

### 4.4 Supervisor 라우팅 수정

`supervisor_nodes.py`의 `create_supervisor_node`에서 `answer_agent`를 인식해야 합니다.

```python
# supervisor_nodes.py — SupervisorDecision 변경 없음
# answer_agent는 available_workers에 포함되어 Supervisor가 자연스럽게 라우팅

# workflow_compiler.py에서 available_workers 구성 시:
available_workers = [w.worker_id for w in workflow.workers]
if has_search_workers:
    available_workers.append("answer_agent")
```

Supervisor는 기존 LLM 기반 라우팅을 유지합니다.
`worker_descriptions`에 answer_agent를 추가하여 Supervisor가 "검색 완료 후 answer_agent로 보내라"를 판단:

```python
# WorkflowCompiler.compile() 내부에서 workers에 가상 워커 추가
if has_search_workers:
    answer_worker_desc = WorkerDefinition(
        tool_id="__answer_agent__",
        worker_id="answer_agent",
        description="모든 검색 결과를 종합하여 사용자에게 최종 답변을 생성합니다. 검색이 모두 완료된 후 호출하세요.",
        sort_order=999,
    )
    workers_for_supervisor = list(workflow.workers) + [answer_worker_desc]
```

---

## 5. Error Handling

### 5.1 Search Node 에러

| 상황 | 처리 |
|------|------|
| tool.ainvoke() 예외 | 에러 메시지를 AIMessage로 변환, 그래프 계속 진행 |
| 빈 결과 반환 | 빈 문자열 그대로 전달 → QualityGate에서 재시도 판단 |
| timeout | tool 자체의 timeout 처리에 의존 (변경 불필요) |

### 5.2 Answer Agent 에러

| 상황 | 처리 |
|------|------|
| 검색 결과 없음 | `"(검색 결과 없음)"` 컨텍스트로 LLM 호출 — 최소한의 답변 시도 |
| LLM 호출 실패 | 기존 `supervisor_nodes`의 에러 처리 패턴과 동일 — `__end__` 라우팅 |
| 사용자 질문 추출 실패 | 빈 문자열로 fallback |

### 5.3 하위 호환 에러

| 상황 | 처리 |
|------|------|
| 기존 에이전트 (category 미설정) | `ToolMeta.category` 기본값 `"action"` → 기존 ReAct 로직 |
| MCP 도구 | `mcp_` prefix 체크 → 항상 action 처리 |
| `get_tool_meta()` 실패 | 기존 ValueError 그대로 (TOOL_REGISTRY에 없는 도구) |

---

## 6. Test Plan

### 6.1 Test Scope

| Type | Target | Tool | 파일 |
|------|--------|------|------|
| Unit | ToolMeta.category | pytest | `tests/domain/agent_builder/test_schemas.py` |
| Unit | TOOL_REGISTRY 카테고리 | pytest | `tests/domain/agent_builder/test_tool_registry.py` |
| Unit | Search Node | pytest | `tests/application/agent_builder/test_search_node.py` (신규) |
| Unit | Answer Agent Node | pytest | `tests/application/agent_builder/test_answer_node.py` (신규) |
| Unit | WorkflowCompiler 분기 | pytest | `tests/application/agent_builder/test_workflow_compiler.py` (확장) |
| Integration | 전체 그래프 실행 | pytest | `tests/application/agent_builder/test_workflow_compiler.py` (확장) |

### 6.2 Test Cases

#### Domain (ToolMeta, TOOL_REGISTRY)

- [x] TC-D01: `ToolMeta` 기본 category는 `"action"`
- [x] TC-D02: `ToolMeta(category="search")` 정상 생성
- [x] TC-D03: `ToolMeta(category="invalid")` → ValueError (Literal 검증)
- [x] TC-D04: `TOOL_REGISTRY["internal_document_search"].category == "search"`
- [x] TC-D05: `TOOL_REGISTRY["tavily_search"].category == "search"`
- [x] TC-D06: `TOOL_REGISTRY["excel_export"].category == "action"`
- [x] TC-D07: `TOOL_REGISTRY["python_code_executor"].category == "action"`

#### Search Node

- [x] TC-S01: Search Node가 `tool.ainvoke()` 결과를 `[worker_id 검색결과]` 형식으로 반환
- [x] TC-S02: Search Node가 `last_worker_id`를 올바르게 설정
- [x] TC-S03: Search Node가 `token_usage`를 증가시킴
- [x] TC-S04: tool 예외 시 에러 메시지로 변환 (그래프 중단 없음)
- [x] TC-S05: Search Node가 LLM을 호출하지 않음 (mock 검증)

#### Answer Agent Node

- [x] TC-A01: 검색 결과 메시지를 정확히 수집 (`"검색결과"` 태그 필터)
- [x] TC-A02: system_prompt + 검색 결과 컨텍스트로 LLM 호출
- [x] TC-A03: 원본 사용자 질문을 정확히 추출
- [x] TC-A04: 검색 결과 없을 때 `"(검색 결과 없음)"` 컨텍스트
- [x] TC-A05: `last_worker_id == "answer_agent"`

#### _resolve_category (3-tier fallback)

- [x] TC-R01: `worker_def.category="search"` → DB 오버라이드 우선 반환
- [x] TC-R02: `worker_def.category=None`, TOOL_REGISTRY에 있음 → REGISTRY 값 반환
- [x] TC-R03: `worker_def.category=None`, TOOL_REGISTRY에 없음 (MCP) → `"action"` 반환
- [x] TC-R04: `worker_def.category="action"` (DB 명시) → REGISTRY 값 무시하고 `"action"` 반환

#### WorkflowCompiler 분기

- [x] TC-W01: search 도구만 → 그래프에 `answer_agent` 노드 존재
- [x] TC-W02: action 도구만 → 그래프에 `answer_agent` 노드 없음 (기존 동작)
- [x] TC-W03: 혼합 → search는 `_create_search_node`, action은 `create_react_agent`
- [x] TC-W04: `create_react_agent` 호출 횟수 == action 도구 수 (search 도구는 호출 안 함)
- [x] TC-W05: DB category 오버라이드로 내부 search 도구를 action으로 사용 가능
- [x] TC-W06: 기존 테스트 전부 통과 (회귀)

---

## 7. Clean Architecture Layer Assignment

### 7.1 Dependency Rules 준수

```
domain/ (변경)
  └── schemas.py: ToolMeta.category 필드 추가
  └── tool_registry.py: 카테고리 값 할당
  ※ 외부 의존성 없음 — dataclass + Literal만 사용

application/ (변경)
  └── workflow_compiler.py: 분기 로직 + search_node + answer_node
  └── supervisor_nodes.py: answer_agent 라우팅 (최소 변경)
  ※ domain.schemas.get_tool_meta() 참조 — 정당한 의존 방향

infrastructure/ (변경 없음)
  └── tool_factory.py: 기존 그대로
```

### 7.2 Layer 위반 없음 확인

| 변경 | From → To | 위반 여부 |
|------|-----------|----------|
| `workflow_compiler.py` → `get_tool_meta()` | application → domain | **정당** |
| `workflow_compiler.py` → `BaseTool.ainvoke()` | application → langchain_core | **정당** (프레임워크) |
| `workflow_compiler.py` → `BaseChatModel.ainvoke()` | application → langchain_core | **정당** (기존과 동일) |

---

## 8. Implementation Order

### Step 1: Domain 스키마 + DB 마이그레이션 (TDD)

```
Red:   test_schemas.py — ToolMeta(category="search") 테스트
Green: schemas.py — ToolMeta.category + WorkerDefinition.category 추가
Red:   test_tool_registry.py — 카테고리 검증 테스트
Green: tool_registry.py — 4개 도구 카테고리 할당
Green: models.py — AgentToolModel.category 컬럼 추가
Green: V__add_agent_tool_category.sql 마이그레이션 작성
```

변경 파일:
- `src/domain/agent_builder/schemas.py` (ToolMeta.category + WorkerDefinition.category)
- `src/domain/agent_builder/tool_registry.py`
- `src/infrastructure/agent_builder/models.py` (AgentToolModel.category)
- `db/migration/V__add_agent_tool_category.sql` (신규)
- `tests/domain/agent_builder/test_schemas.py` (신규 또는 확장)
- `tests/domain/agent_builder/test_tool_registry.py` (확장)

### Step 2: Search Node 구현 (TDD)

```
Red:   test_search_node.py — TC-S01~S05
Green: workflow_compiler.py — _create_search_node() 메서드 추가
```

변경 파일:
- `src/application/agent_builder/workflow_compiler.py` (`_create_search_node` 추가)
- `tests/application/agent_builder/test_search_node.py` (신규)

### Step 3: Answer Agent Node 구현 (TDD)

```
Red:   test_answer_node.py — TC-A01~A05
Green: workflow_compiler.py — _create_answer_node() 메서드 추가
```

변경 파일:
- `src/application/agent_builder/workflow_compiler.py` (`_create_answer_node` 추가)
- `tests/application/agent_builder/test_answer_node.py` (신규)

### Step 4: WorkflowCompiler.compile() 분기 통합 (TDD)

```
Red:   test_workflow_compiler.py — TC-W01~W05
Green: workflow_compiler.py — compile() 내부 분기 로직
       supervisor_nodes.py — answer_agent 라우팅 지원
```

변경 파일:
- `src/application/agent_builder/workflow_compiler.py` (`compile` 메서드 수정)
- `src/application/agent_builder/supervisor_nodes.py` (최소 수정)
- `tests/application/agent_builder/test_workflow_compiler.py` (확장)

### Step 5: 회귀 테스트 + MCP 처리

```
기존 테스트 전부 실행 → 통과 확인
MCP 도구 분기 처리 확인
```

변경 파일:
- `src/application/agent_builder/workflow_compiler.py` (mcp_ prefix 분기 확인)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-11 | Initial draft | 배상규 |
