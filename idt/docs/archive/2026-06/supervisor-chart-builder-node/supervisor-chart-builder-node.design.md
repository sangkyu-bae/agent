# SUPERVISOR-CHART-BUILDER-NODE: 설계 문서

> 상태: Design
> Plan 참조: docs/01-plan/features/supervisor-chart-builder-node.plan.md
> 연관 Task: CHART-NODE-001
> 작성일: 2026-06-08

---

## 1. 설계 개요

분석 워커 직후 `chart_router`(viz_decision 기록)와 `quality_gate` 사이에 **`chart_builder` 노드를 신설**하여, `viz_decision="visualize"`일 때 기존 `LangChainChartBuilder`로 Chart.js config를 생성한다. 생성 후 `visualization_done` 플래그로 분석 워커를 **결정적으로 skip** 처리해 supervisor 재라우팅 루프를 차단하고, 차트는 `ANSWER_COMPLETED` 이벤트의 `charts` 페이로드로 전달한다(General Chat 계약 동일). Excel 워크플로우·에이전트 채팅 프론트도 동일 계약으로 연결한다.

### 1-1. 변경 요약

| # | 레이어 | 파일 | 변경 |
|---|--------|------|------|
| D-1 | application | `agent_builder/supervisor_state.py` | state 필드 `charts`, `visualization_done` 추가 |
| D-2 | application | `agent_builder/supervisor_nodes.py::build_initial_state` | 신규 필드 초기화 |
| D-3 | application | `visualization/chart_extract.py` (신규) | `extract_question`/`extract_analysis_text` 공용 헬퍼 분리 |
| D-4 | application | `visualization/chart_router.py` | 헬퍼를 D-3에서 import (중복 제거) |
| D-5 | application | `visualization/chart_builder_node.py` (신규) | `create_chart_builder_node(builder, logger)` |
| D-6 | application | `agent_builder/workflow_compiler.py` | `chart_builder` 노드 등록 + conditional edge 배선, `chart_max_count` 주입 |
| D-7 | application | `agent_builder/supervisor_hooks.py::AttachmentRoutingHooks.skip_workers` | `visualization_done` 가드 |
| D-8 | application | `agent_builder/run_agent_use_case.py` | `_StreamState.charts` 캡처 + `ANSWER_COMPLETED` payload `charts` 추가 |
| D-9 | application | `workflows/excel_analysis_workflow.py` | `chart_builder` 노드 + conditional edge, `ExcelAnalysisState.charts` |
| D-10 | domain | `entities/analysis_result.py` | `AnalysisResult.charts` 필드 추가 |
| D-11 | application | `use_cases/analyze_excel_use_case.py` | 최종 state의 `charts`를 결과에 surface |
| D-12 | interfaces | `api/routes/analysis_router.py` | 응답 스키마에 `charts` 노출 |
| D-13 | infra/DI | `api/main.py` | `WorkflowCompiler`에 `chart_max_count`, `ExcelAnalysisWorkflow`에 `chart_builder` 주입 |
| D-14 | front | `idt_front/src/types/websocket.ts` | `AgentAnswerCompletedData.charts?` 추가 |
| D-15 | front | `idt_front/src/hooks/useAgentRunStream.ts` | `charts` 캡처 |
| D-16 | front | 에이전트 채팅 렌더 컴포넌트 | `ChartRenderer` 연결 |

> **ws_router/ws_adapter 무변경 확정**: `AgentRunEventWsAdapter.to_ws_message`(`infrastructure/agent_run/ws_adapter.py:36`)와 `ChatEventWsAdapter` 모두 `data=dict(event.payload)`로 **payload 전체를 패스스루**한다. 따라서 ANSWER_COMPLETED payload에 `charts`를 추가하면 자동으로 `agent_answer_completed.data.charts`로 직렬화된다. (Plan §3-1 item 7은 코드 변경 없이 "확인"으로 종결.)

### 1-2. Plan 대비 설계 확정 사항 (오픈 이슈 해소)

| Plan 오픈 이슈 | 설계 확정 |
|----------------|-----------|
| **§6-3 Excel chart_builder LLM** (`claude_client`는 BaseChatModel 아님) | `main.py:1728`이 이미 General Chat용 `viz_llm = _llm_factory.create(_default_llm_model, temperature=0)`를 생성한다. 동일 패턴으로 만든 `LangChainChartBuilder`를 **`ExcelAnalysisWorkflow`에 주입**(claude_client 미사용). → Plan §6-3 옵션 1 채택 |
| **Supervisor chart_builder LLM** | WorkflowCompiler는 `compile()` 내 per-run `llm`(에이전트 설정 모델)을 가진다. 기존 `LangChainVisualizationClassifier(llm)`가 이미 이 `llm`으로 compile 내 생성되므로(`workflow_compiler.py:300`), **chart_builder도 compile 내에서 `llm`으로 생성**(에이전트 모델 일관 사용). `__init__`엔 빌더가 아닌 `chart_max_count: int`만 주입 |

---

## 2. State 설계 (D-1, D-2)

### 2-1. `SupervisorState` 필드 추가 (`supervisor_state.py`)

```python
class SupervisorState(TypedDict):
    # ... 기존 필드 유지 ...

    # analysis-chart-router: 분석 직후 라우터의 판단 결과. "visualize" | "text" | ""
    viz_decision: str

    # supervisor-chart-builder-node: chart_builder가 생성한 Chart.js config 리스트.
    # 각 항목 = ChartConfig.model_dump(exclude_none=True) (= 프론트 ChartPayload).
    charts: list[dict]

    # supervisor-chart-builder-node: 시각화 처리 완료 플래그.
    # True면 skip_workers가 분석 워커를 제외해 supervisor 재라우팅을 결정적으로 차단.
    visualization_done: bool
```

### 2-2. `build_initial_state` 초기화 (`supervisor_nodes.py:53-70`)

```python
    return {
        # ... 기존 필드 ...
        "viz_decision": "",
        "charts": [],               # 추가
        "visualization_done": False, # 추가
    }
```

> **주의**: `SupervisorState`는 TypedDict이며 일부 노드가 `state["charts"]`를 직접 인덱싱할 수 있으므로 초기화 누락 시 KeyError. 단, chart_builder/skip_workers는 모두 `state.get(...)`로 접근해 방어한다.

---

## 3. 공용 추출 헬퍼 분리 (D-3, D-4)

`chart_router.py`의 `_extract_question` / `_extract_analysis_text`를 `chart_builder_node`와 공유하기 위해 신규 모듈로 이동한다.

### 3-1. `src/application/visualization/chart_extract.py` (신규)

```python
"""chart_router / chart_builder 공용 질문·분석텍스트 추출 헬퍼.

Excel(user_query/analysis_text)과 Supervisor(messages) 양쪽 state 형태를 모두 지원.
"""


def extract_question(state: dict) -> str:
    """최근 user 질문 추출. Excel(user_query) / Supervisor(messages) 모두 지원."""
    if state.get("user_query"):
        return state["user_query"]
    for msg in reversed(state.get("messages", [])):
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
        if role in ("user", "human"):
            return (
                msg.get("content", "") if isinstance(msg, dict)
                else getattr(msg, "content", "")
            )
    return ""


def extract_analysis_text(state: dict) -> str:
    """직전 분석 텍스트 추출. Excel(analysis_text) / Supervisor(마지막 AIMessage) 지원."""
    if state.get("analysis_text"):
        return state["analysis_text"]
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, dict):
            continue
        if getattr(msg, "type", "") == "ai":
            return getattr(msg, "content", "")
    return ""
```

### 3-2. `chart_router.py` 리팩토링

기존 모듈 내 `_extract_question`/`_extract_analysis_text` 정의를 제거하고 상단에서 import한다(동작 동일, 호출부 이름만 교체).

```python
from src.application.visualization.chart_extract import (
    extract_analysis_text,
    extract_question,
)
# chart_router 내부: _extract_question(state) → extract_question(state)
```

> 동작 무변경 리팩토링. 기존 `chart_router` 테스트가 GREEN을 유지해야 한다(회귀 가드).

---

## 4. chart_builder 노드 (D-5)

### 4-1. `src/application/visualization/chart_builder_node.py` (신규)

```python
"""viz_decision="visualize"일 때만 Chart.js config를 생성하는 노드.

차트 생성과 그래프 흐름 제어를 분리한다: 이 노드는 state["charts"]만 채우고
visualization_done=True를 세팅하며, messages/last_worker_id는 건드리지 않는다.
→ 직후 quality_gate가 분석 텍스트(직전 AIMessage)를 평가하므로 차트 노드가
  품질검증 재시도(루프)를 유발하지 않는다.

모든 실패는 빈 결과로 graceful degrade — 텍스트 답변 본 흐름을 절대 막지 않는다.
"""
from src.application.visualization.chart_extract import (
    extract_analysis_text,
    extract_question,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.interfaces import ChartBuilderInterface
from src.domain.visualization.schemas import VizDecision


def create_chart_builder_node(
    builder: ChartBuilderInterface,
    logger: LoggerInterface,
):
    async def chart_builder(state: dict) -> dict:
        if state.get("viz_decision") != VizDecision.VISUALIZE.value:
            # 텍스트 분기는 이 노드를 타지 않는 것이 정상이나(라우팅), 방어적으로 처리.
            return {"visualization_done": True}

        question = extract_question(state)
        analysis_text = extract_analysis_text(state)

        try:
            configs = await builder.build(question, analysis_text, context="")
            charts = [c.model_dump(exclude_none=True) for c in configs]
        except Exception as e:
            logger.error("chart_builder failed, fallback []", exception=e)
            charts = []

        logger.info("chart_builder done", chart_count=len(charts))
        return {"charts": charts, "visualization_done": True}

    return chart_builder
```

**불변식**:
- 반환 dict는 `charts`, `visualization_done`만 포함 → `add_messages` reducer 영향 없음, `last_worker_id` 불변.
- `builder.build`는 `LangChainChartBuilder`로 내부에서 이미 예외→`[]` graceful. 본 노드의 try/except는 2차 안전망.

---

## 5. workflow_compiler 배선 (D-6)

### 5-1. `__init__` 시그니처

```python
def __init__(
    self,
    tool_factory: ToolFactory,
    llm_factory: LLMFactoryInterface,
    logger: LoggerInterface,
    hooks: SupervisorHooks | None = None,
    agent_repository: AgentDefinitionRepositoryInterface | None = None,
    llm_model_repository: LlmModelRepositoryInterface | None = None,
    excel_analysis_workflow_getter: Callable[[], Any] | None = None,
    chart_max_count: int = 0,   # 추가: 0이면 차트 비활성(하위호환)
) -> None:
    ...
    self._chart_max_count = chart_max_count
```

> 빌더 인스턴스가 아닌 `chart_max_count: int`만 주입한다. 차트 빌더는 `compile()` 내 per-run `llm`으로 생성(에이전트 모델 일관). `0`이면 차트 노드 미등록 = 기존 동작.

### 5-2. `compile()` 노드 등록 + 배선

**현재** (`workflow_compiler.py:295-327`):

```python
if analysis_worker_ids:
    chart_router_fn = create_chart_router_node(...)
    graph.add_node("chart_router", _wrap_step("chart_router", NodeType.OTHER, chart_router_fn))

# ... 워커 edge ...
for worker_id in worker_map:
    if worker_id in analysis_worker_ids:
        graph.add_edge(worker_id, "chart_router")
    else:
        graph.add_edge(worker_id, "quality_gate")

if analysis_worker_ids:
    graph.add_edge("chart_router", "quality_gate")
```

**수정 후**:

```python
if analysis_worker_ids:
    chart_router_fn = create_chart_router_node(
        policy=VisualizationRoutingPolicy(),
        logger=self._logger,
        classifier=LangChainVisualizationClassifier(llm),
    )
    graph.add_node(
        "chart_router",
        _wrap_step("chart_router", NodeType.OTHER, chart_router_fn),
    )
    # supervisor-chart-builder-node: chart_max_count>0일 때만 빌더 노드 등록.
    if self._chart_max_count > 0:
        chart_builder = LangChainChartBuilder(
            llm=llm,
            logger=self._logger,
            style_policy=ChartStylePolicy(),
            max_count=self._chart_max_count,
        )
        graph.add_node(
            "chart_builder",
            _wrap_step(
                "chart_builder",
                NodeType.OTHER,
                create_chart_builder_node(chart_builder, self._logger),
            ),
        )

# 워커 edge (기존 유지)
for worker_id in worker_map:
    if worker_id in analysis_worker_ids:
        graph.add_edge(worker_id, "chart_router")
    else:
        graph.add_edge(worker_id, "quality_gate")

if analysis_worker_ids:
    if self._chart_max_count > 0:
        # visualize → chart_builder → quality_gate, text → quality_gate
        graph.add_conditional_edges(
            "chart_router",
            route_after_chart_router,
            {"visualize": "chart_builder", "text": "quality_gate"},
        )
        graph.add_edge("chart_builder", "quality_gate")
    else:
        graph.add_edge("chart_router", "quality_gate")  # 하위호환
```

**추가 import** (`workflow_compiler.py` 상단):

```python
from src.application.visualization.chart_router import (
    create_chart_router_node,
    route_after_chart_router,   # 추가
)
from src.application.visualization.chart_builder_node import create_chart_builder_node
from src.domain.visualization.chart_policy import ChartStylePolicy
from src.infrastructure.visualization.llm_chart_builder import LangChainChartBuilder
```

> `route_after_chart_router`는 이미 `chart_router.py:66-74`에 구현돼 있어 그대로 재사용. (`viz_decision=="visualize"` → `"visualize"`, else `"text"`)

### 5-3. 흐름도

```
supervisor ─route_to_worker→ analysis_worker
analysis_worker ─edge→ chart_router        (viz_decision 기록)
chart_router ─route_after_chart_router┬ "visualize" → chart_builder ─edge→ quality_gate
                                      └ "text"                      ─edge→ quality_gate
quality_gate ─route_after_quality→ supervisor
supervisor: visualization_done=True → skip_workers(analysis ids) → 분석워커 선택 불가 → FINISH
```

---

## 6. skip_workers 결정적 가드 (D-7)

### 6-1. `AttachmentRoutingHooks.skip_workers` (`supervisor_hooks.py:49-50`)

**현재**:

```python
def skip_workers(self, state: SupervisorState) -> list[str]:
    return []
```

**수정 후**:

```python
def skip_workers(self, state: SupervisorState) -> list[str]:
    # supervisor-chart-builder-node: 시각화 처리가 끝나면 분석 워커를 skip 처리해
    # supervisor LLM의 분석워커 재선택(무한루프)을 결정적으로 차단한다.
    if state.get("visualization_done"):
        return list(self._analysis_worker_ids)
    return []
```

### 6-2. 동작 보장

- `supervisor_node`는 `next_worker in skipped` 시 `__end__` 처리(`supervisor_nodes.py:159-160`). 또한 decision_prompt에 "스킵된 워커(사용 불가)"로 명시돼 LLM이 애초에 선택하지 않도록 유도.
- 분석 워커가 유일 워커인 에이전트: supervisor는 다른 선택지가 없으므로 FINISH → 최종 답변 = 직전 분석 텍스트(AIMessage). 차트는 `state["charts"]`로 별도 전달.
- 다중 워커 에이전트: 이미 실행된 분석 워커만 skip, 나머지 워커는 정상 동작.

> **DefaultHooks 비대상**: skip 가드는 분석 워커가 있을 때만 활성화되는 `AttachmentRoutingHooks`에만 추가한다. `workflow_compiler.py:209-211`에서 `analysis_worker_ids`가 있고 외부 주입 훅이 없으면 자동으로 `AttachmentRoutingHooks`로 대체되므로 기본 경로가 보장된다.

---

## 7. 차트 surface — run_agent_use_case (D-8)

### 7-1. `_StreamState`에 charts 추가 (`run_agent_use_case.py:102-108`)

```python
@dataclass
class _StreamState:
    token_acc: dict[str, list[str]] = field(default_factory=dict)
    final_messages: list = field(default_factory=list)
    charts: list[dict] = field(default_factory=list)   # 추가
```

### 7-2. on_chain_end에서 charts 캡처 (`run_agent_use_case.py:570-575` 인근)

**현재**:

```python
output = (raw.get("data", {}) or {}).get("output")
# 어떤 chain_end이든 messages가 있으면 final_messages 갱신 (top-level이 마지막)
if isinstance(output, dict) and "messages" in output:
    state.final_messages = list(output["messages"])
```

**수정 후 (추가)**:

```python
output = (raw.get("data", {}) or {}).get("output")
if isinstance(output, dict) and "messages" in output:
    state.final_messages = list(output["messages"])
# supervisor-chart-builder-node: chart_builder 노드 output의 charts 캡처.
if isinstance(output, dict) and output.get("charts"):
    state.charts = list(output["charts"])
```

> top-level 그래프 output에도 `charts`가 누적되어 내려올 수 있으나(state 병합), `output.get("charts")` truthy일 때만 갱신하므로 빈 배열이 유효 charts를 덮어쓰지 않는다.

### 7-3. ANSWER_COMPLETED payload 확장 (`run_agent_use_case.py:243-246`)

**현재**:

```python
yield self._build_event(
    seq, AgentRunEventType.ANSWER_COMPLETED, run_id,
    {"answer": answer, "tools_used": tools_used},
)
```

**수정 후**:

```python
answer_payload = {"answer": answer, "tools_used": tools_used}
if state.charts:
    answer_payload["charts"] = state.charts
yield self._build_event(
    seq, AgentRunEventType.ANSWER_COMPLETED, run_id, answer_payload,
)
```

> `charts`가 비면 키 자체를 생략 → 프론트 하위호환(필드 부재 = 차트 미표시). General Chat의 `_maybe_build_charts` 계약(`use_case.py:286-311`)과 동일한 `list[dict]` 형태.

---

## 8. Excel 경로 (D-9 ~ D-12)

### 8-1. `ExcelAnalysisState.charts` + 노드 배선 (`excel_analysis_workflow.py`)

State TypedDict에 `charts: list[dict]` 추가. `__init__`에 `chart_builder: ChartBuilderInterface | None = None` 주입.

**`_build_graph()` 수정** (`excel_analysis_workflow.py:88-118`):

```python
workflow.add_node(
    "chart_router",
    create_chart_router_node(
        VisualizationRoutingPolicy(), self._logger, classifier=None
    ),
)
if self._chart_builder is not None:
    workflow.add_node(
        "chart_builder",
        create_chart_builder_node(self._chart_builder, self._logger),
    )

# ... evaluate → {"retry": "web_search", "complete": "chart_router"} (기존) ...

if self._chart_builder is not None:
    workflow.add_conditional_edges(
        "chart_router",
        route_after_chart_router,
        {"visualize": "chart_builder", "text": END},
    )
    workflow.add_edge("chart_builder", END)
else:
    workflow.add_edge("chart_router", END)  # 하위호환
```

`run()`의 initial state에 `"charts": []` 추가(`analyze_excel_use_case.py:80-89` initial dict와 `excel_analysis_workflow` 초기화 양쪽).

### 8-2. `AnalysisResult.charts` (D-10, `analysis_result.py`)

```python
@dataclass
class AnalysisResult:
    request_id: str
    user_query: str
    excel_summary: Dict[str, Any]
    final_answer: str
    is_successful: bool
    attempts: List[AnalysisAttempt]
    created_at: Optional[datetime] = None
    charts: List[Dict[str, Any]] = field(default_factory=list)  # 추가
```

> `field` import 추가(`from dataclasses import dataclass, field`). 기본값이라 기존 생성자 호출 하위호환.

### 8-3. `_build_result` surface (D-11, `analyze_excel_use_case.py:112-138`)

```python
return AnalysisResult(
    ...
    final_answer=state["analysis_text"],
    charts=state.get("charts", []),   # 추가
)
```

### 8-4. API 응답 스키마 (D-12, `analysis_router.py`)

Excel 분석 응답 모델에 `charts: list[dict] = []` 추가하여 `result.charts`를 노출. (프론트 Excel 분석 화면 연동은 본 plan의 에이전트 채팅 프론트와 동일 `ChartRenderer` 재사용 — Excel UI 연결 세부는 프론트 구현 시 결정.)

---

## 9. DI 배선 (D-13, `main.py`)

### 9-1. WorkflowCompiler (`main.py:1802-1806`)

```python
workflow_compiler = WorkflowCompiler(
    tool_factory=tool_factory, llm_factory=_llm_factory, logger=app_logger,
    agent_repository=...,
    excel_analysis_workflow_getter=get_configured_excel_analysis_workflow,
    chart_max_count=settings.chart_max_count,   # 추가
)
```

### 9-2. ExcelAnalysisWorkflow (`main.py:678` 인근, `get_configured_excel_analysis_workflow`)

```python
# main.py:1728의 viz_llm 패턴 재사용 (claude_client 미사용)
excel_viz_llm = _llm_factory.create(_default_llm_model, temperature=0)
excel_chart_builder = LangChainChartBuilder(
    llm=excel_viz_llm,
    logger=app_logger,
    style_policy=ChartStylePolicy(),
    max_count=settings.chart_max_count,
)
workflow = ExcelAnalysisWorkflow(
    ...,
    chart_builder=excel_chart_builder,   # 추가
)
```

> `_default_llm_model` / `ChartStylePolicy` / `LangChainChartBuilder` 는 main.py에 이미 import·정의됨(`main.py:320,322,1728`). 추가 import 불필요.

---

## 10. 프론트엔드 (D-14 ~ D-16, idt_front/)

### 10-1. 타입 (`src/types/websocket.ts:62`)

```typescript
export interface AgentAnswerCompletedData {
  answer: string;
  tools_used: string[];
  /** 차트 페이로드 (Chart.js config 패스스루). 필드 부재 시 미표시(하위호환). */
  charts?: ChartPayload[];   // 추가 (ChatAnswerCompletedData와 동일 패턴)
}
```

`ChartPayload`는 이미 `./chart`에서 import됨(line 10).

### 10-2. 훅 (`src/hooks/useAgentRunStream.ts` `case 'agent_answer_completed'`)

```typescript
case 'agent_answer_completed':
  setState((s) => ({
    ...s,
    answer: msg.data.answer,
    charts: msg.data.charts ?? [],   // 추가
  }));
  break;
```

훅 state 타입에 `charts: ChartPayload[]` 필드 추가(초기값 `[]`).

### 10-3. 렌더 컴포넌트

에이전트 채팅 결과를 렌더하는 컴포넌트(`MessageBubble.tsx` 또는 Agent run 결과 뷰)에서, General Chat과 동일하게 `charts`를 `ChartRenderer`로 전달:

```tsx
{charts?.map((cfg, i) => <ChartRenderer key={i} config={cfg} />)}
```

> `ChartRenderer`/`chartValidator`/`chartSetup`은 이미 존재(`src/components/chat/ChartRenderer.tsx` 등). 신규 컴포넌트 불필요 — 데이터 전달만 연결.

---

## 11. 테스트 설계 (TDD)

> 백엔드 pytest: Windows 이벤트 루프 이슈로 **격리 실행** 검증(메모리: backend-test-eventloop-flakiness). 프론트 vitest: `--pool=threads`(메모리: frontend-vitest-forks-timeout).

### 11-1. `chart_builder_node` 단위 (신규 `tests/application/visualization/test_chart_builder_node.py`)

| 케이스 | 입력 | 기대 |
|--------|------|------|
| visualize+데이터 | `viz_decision="visualize"`, 수치 분석텍스트, FakeBuilder→[config] | `charts` 1+개, `visualization_done=True` |
| text 분기 방어 | `viz_decision="text"` | `visualization_done=True`, builder **미호출**, charts 없음 |
| 빌더 예외 | builder.build raises | `charts=[]`, 예외 전파 X |
| 불변식 | 반환 dict 키 | `{"charts","visualization_done"}`만 — messages/last_worker_id 키 없음 |

### 11-2. `workflow_compiler` 라우팅 (`tests/application/agent_builder/test_workflow_compiler.py` 추가)

- `chart_max_count>0` + 분석워커 + visualize: 컴파일된 그래프 invoke 시 `state["charts"]` 채워지고 **유한 종료**(iteration_count ≪ max_iterations). → 루프 회귀 가드.
- `chart_max_count=0`: `chart_router → quality_gate` 직결, `chart_builder` 노드 부재(기존 동작 보존).

### 11-3. `skip_workers` 가드 (`tests/application/agent_builder/test_supervisor_hooks.py`)

- `visualization_done=True` → 반환에 분석 워커 id 포함.
- `visualization_done=False/미설정` → `[]`.

### 11-4. `run_agent_use_case` ANSWER_COMPLETED (`tests/.../test_run_agent_use_case.py`)

- chart_builder on_chain_end output에 charts 포함 시 → ANSWER_COMPLETED payload `charts` 존재.
- charts 없음 → payload에 `charts` 키 부재(하위호환).

### 11-5. Excel (`tests/application/workflows/test_excel_analysis_workflow.py`)

- chart_builder 주입 + visualize → `state["charts"]` 채워지고 END.
- chart_builder=None → 기존 `chart_router→END` 동작.

### 11-6. chart_router 회귀 (`test_chart_router.py`)

- 헬퍼 모듈 분리 후에도 기존 라우팅 테스트 GREEN 유지.

### 11-7. 프론트 (`useAgentRunStream.test.ts`)

- `agent_answer_completed` + charts → 훅 state.charts 반영.
- charts 없음 → state.charts = `[]`.

---

## 12. 영향 범위 / 리스크

| 항목 | 영향 | 완화 |
|------|------|------|
| `chart_max_count=0` 경로 | 없음 | conditional edge 미배선, 노드 미등록 = 기존 그래프 |
| quality_gate 재시도 | 회피 | chart_builder가 messages 불변 → 직전 분석텍스트 평가 그대로 |
| 토큰 사용량 | 차트당 structured output 1회 | 무한루프(최대 10회 분석 재실행) 제거로 **순감소** |
| ANSWER_COMPLETED 계약 | optional `charts` 추가 | 프론트/백 하위호환 |
| `AnalysisResult` 생성자 | default 필드 | 기존 호출 하위호환 |
| 헬퍼 모듈 분리 | chart_router import 경로 변경 | 동작 무변경, 기존 테스트로 가드 |

---

## 13. 구현 순서 (Do 단계 체크리스트)

1. **RED**: `test_chart_builder_node.py`(11-1) 작성 → 실패.
2. `chart_extract.py`(D-3) 생성 + `chart_router.py`(D-4) 리팩토링 → chart_router 기존 테스트 GREEN 확인.
3. `supervisor_state.py`(D-1) + `build_initial_state`(D-2).
4. `chart_builder_node.py`(D-5) 구현 → 11-1 GREEN.
5. `supervisor_hooks.py`(D-7) + 11-3.
6. `workflow_compiler.py`(D-6) 배선 + 11-2.
7. `run_agent_use_case.py`(D-8) + 11-4.
8. `main.py`(D-13) DI: WorkflowCompiler `chart_max_count`.
9. Excel: `excel_analysis_workflow.py`(D-9) + `analysis_result.py`(D-10) + `analyze_excel_use_case.py`(D-11) + `analysis_router.py`(D-12) + main.py(D-13) Excel DI + 11-5.
10. 프론트(D-14~16) + 11-7.
11. 로컬 수동 검증: 분석워커 에이전트 "그래프 그려줘" → 차트 렌더 + 루프 없음 / 엑셀 분석 → 차트.
12. `/pdca analyze supervisor-chart-builder-node`.

---

## 14. 미해결 / 후속

- 차트 영속화(대화 재진입 복원) — 현재 ephemeral, 별도 plan.
- Excel UI의 `ChartRenderer` 연결 세부(분석 결과 화면) — 프론트 구현 시 확정.
- `chart_router` 분류 정확도 튜닝 — 별도.
