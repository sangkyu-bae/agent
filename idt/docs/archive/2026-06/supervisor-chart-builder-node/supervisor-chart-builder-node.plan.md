# SUPERVISOR-CHART-BUILDER-NODE: 분석 노드 직후 chart_router가 실제 차트를 생성하지 못하고 supervisor 무한루프를 도는 버그 수정

> 상태: Plan
> 연관 Task: CHART-NODE-001
> 작성일: 2026-06-08
> 우선순위: Critical

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Agent Builder(Supervisor) 그래프에서 데이터 분석 워커 실행 후 `chart_router`를 타지만, `chart_router`는 `viz_decision`만 기록할 뿐 **실제 Chart.js 데이터를 생성하는 노드로 매핑되지 않는다.** 차트가 만들어지지 않으니 supervisor LLM은 "그래프 그려줘" 요청이 미완료라 판단하고 분석 워커로 계속 재라우팅 → `max_iterations(10)`까지 회전하며 토큰을 소진(사실상 무한루프). |
| **Solution** | 이미 존재하지만 General Chat 경로에만 연결돼 있던 `LangChainChartBuilder`/`ChartStylePolicy`/`ChartConfig`를 재사용해 **`chart_builder` 노드를 신규 도입**. `chart_router`를 conditional edge로 바꿔 `visualize → chart_builder → quality_gate → supervisor` 흐름을 만들고, 차트 생성 후 `visualization_done` 플래그로 분석 워커를 **결정적(deterministic)으로 skip** 처리해 supervisor 재라우팅 루프를 차단. 생성된 차트는 `ANSWER_COMPLETED` 이벤트의 `charts` 페이로드로 전달(General Chat 계약 재사용). Excel 워크플로우도 동일 노드를 연결. 프론트 에이전트 채팅 UI도 `charts`를 받아 General Chat과 동일하게 렌더링. |
| **Function UX Effect** | "그래프 그려줘 / 차트로 보여줘" 같은 요청이 분석 워커가 있는 에이전트와 엑셀 분석 모두에서 실제 Chart.js 차트로 렌더링된다. 무한 회전·응답 지연·토큰 낭비가 사라진다. |
| **Core Value** | 분석 결과의 **시각화 완결성** 확보. 데이터 분석 에이전트의 핵심 가치(숫자→직관적 그래프)를 General Chat에 이어 Supervisor·Excel 경로까지 일관되게 제공. |

---

## 1. 문제 정의 (Problem Statement)

분석 워커(`category == "analysis"`)를 가진 에이전트에게 "데이터 그래프로 그려줘"를 요청하는 시나리오:

```
user: "이 데이터 추이를 그래프로 보여줘"
supervisor → analysis_worker (분석 텍스트 생성)
analysis_worker → chart_router (viz_decision="visualize" 기록만 함)
chart_router → quality_gate → supervisor   ← 복귀
supervisor: 차트가 안 보임 → analysis_worker 재호출
... max_iterations(10)까지 반복 ...
```

사용자 관점 증상:
- 응답이 한참 지연되다가(10회 회전) 결국 차트 없이 텍스트만 나오거나 빈 응답.
- 토큰이 비정상적으로 많이 소모됨.
- "차트를 그려달라고 했는데 그래프가 안 그려진다 / 멈춘 것 같다(무한루프)".

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. [Critical] `chart_router`는 판단만 하고 차트 생성 노드로 매핑되지 않음

**파일**: `src/application/agent_builder/workflow_compiler.py:295-327`

현재 배선:

```python
# analysis-chart-router: analysis 워커가 있을 때만 라우터 노드 등록.
if analysis_worker_ids:
    chart_router_fn = create_chart_router_node(...)
    graph.add_node("chart_router", _wrap_step("chart_router", NodeType.OTHER, chart_router_fn))

# analysis 워커 직후 라우터 경유
graph.add_edge(worker_id, "chart_router")

if analysis_worker_ids:
    # 현재: 라우터는 viz_decision만 기록하고 quality_gate로 그대로 진행.
    # 후속 차트 처리 노드 도입 시 아래를 conditional edge로 교체:
    #   graph.add_conditional_edges("chart_router", route_after_chart_router,
    #       {"visualize": "chart_builder", "text": "quality_gate"})
    graph.add_edge("chart_router", "quality_gate")
```

`chart_router`(`src/application/visualization/chart_router.py`)는 `{"viz_decision": ...}`만 반환한다. **`viz_decision="visualize"`를 소비해 실제 차트를 만드는 노드(`chart_builder`)가 그래프에 존재하지 않는다.** 코드 주석이 이미 "후속 차트 처리 노드 도입 시 conditional edge로 교체"라고 미구현임을 명시.

### 2-2. [Critical] 차트 미생성 → supervisor가 완료를 인지 못해 재라우팅 루프

`chart_router → quality_gate → route_after_quality → supervisor` 로 복귀한다(`supervisor_nodes.py:240-244`). 차트는 메시지 스트림이 아닌 별도 채널(state)에 있어야 하는데 아예 생성되지 않으므로, supervisor LLM 입장에서는 시각화 요청이 충족된 흔적이 없다. 따라서 분석 워커를 다시 선택 → 루프. `supervisor_node`의 `iteration_count >= max_iterations(10)` 가드(`supervisor_nodes.py:96-99`)로만 종료되어 **체감상 무한루프 + 토큰 낭비**.

`AttachmentRoutingHooks.force_worker`에는 "이미 실행됐으면 재강제 금지" 가드가 있으나(`supervisor_hooks.py:44-47`), 이는 **force 라우팅만 막을 뿐 supervisor LLM의 자율 재선택은 막지 못한다.** `skip_workers`는 현재 항상 `[]` 반환.

### 2-3. [동일 패턴] Excel 워크플로우도 chart_builder 미연결

**파일**: `src/application/workflows/excel_analysis_workflow.py:114-118`

```python
# 후속 차트 처리 노드 도입 시 conditional edge로 교체:
#   workflow.add_conditional_edges("chart_router", route_after_chart_router,
#       {"visualize": "chart_builder", "text": END})
workflow.add_edge("chart_router", END)
```

Excel도 `chart_router`에서 바로 END. 차트 생성 노드 없음(루프는 없지만 차트 미생성은 동일).

### 2-4. [자산 확인] 차트 생성 컴포넌트는 이미 존재하며 General Chat에만 연결됨

- `src/infrastructure/visualization/llm_chart_builder.py` — `LangChainChartBuilder(ChartBuilderInterface)` (LLM 수치 추출 → graceful degrade)
- `src/domain/visualization/chart_policy.py` — `ChartStylePolicy` (색상/options 결정론적 조립)
- `src/domain/visualization/chart_schemas.py` — `ChartConfig` (= 프론트 `ChartPayload` 1:1)
- DI: `src/api/main.py:1729-1748` 에서 `LangChainChartBuilder(... max_count=settings.chart_max_count)` 생성 후 **General Chat UseCase에만 주입**.
- 소비: `src/application/general_chat/use_case.py:286-311` `_maybe_build_charts` → `ANSWER_COMPLETED` payload `charts`.

→ **새 차트 생성 로직을 만들 필요 없이, 기존 빌더를 Supervisor·Excel 노드에 연결하는 것이 핵심.**

---

## 3. 수정 범위 (Scope)

> 결정사항(사용자 확인): **① 대상 경로 = Supervisor + Excel 둘 다, ② 루프 차단 = quality_gate 거쳐 supervisor 복귀(결정적 skip 가드 병행), ③ 프론트 = 백엔드 + 에이전트 채팅 UI 둘 다.**

### 3-1. 백엔드 (idt/)

| # | 수정 위치 | 내용 | 우선순위 |
|---|-----------|------|----------|
| 1 | `src/application/agent_builder/supervisor_state.py` | `charts: list[dict]`, `visualization_done: bool` state 필드 추가 | Critical |
| 2 | `src/application/agent_builder/supervisor_nodes.py::build_initial_state` | 신규 필드 초기화(`charts=[]`, `visualization_done=False`) | Critical |
| 3 | `src/application/visualization/chart_builder_node.py` (신규) | `create_chart_builder_node(builder, logger)` — `viz_decision=="visualize"`일 때 `ChartBuilderInterface.build()` 호출, `{"charts": [...], "visualization_done": True}` 반환. **messages/last_worker_id는 건드리지 않음**(quality_gate 오판·재시도 방지) | Critical |
| 4 | `src/application/agent_builder/workflow_compiler.py` | `chart_router` 다음을 conditional edge로 교체: `visualize → chart_builder`, `text → quality_gate`. `chart_builder → quality_gate`. `chart_builder` 노드 등록(빌더 주입). | Critical |
| 5 | `src/application/agent_builder/supervisor_hooks.py::AttachmentRoutingHooks.skip_workers` | `state.get("visualization_done")`가 True면 분석 워커 id 목록 반환 → supervisor 재라우팅 결정적 차단 | Critical |
| 6 | `src/application/agent_builder/run_agent_use_case.py` | `_StreamState`가 `chart_builder` on_chain_end output의 `charts`를 캡처 → `ANSWER_COMPLETED` payload에 `charts` 추가(General Chat 계약 동일) | High |
| 7 | `src/api/routes/ws_router.py` | `ANSWER_COMPLETED` payload의 `charts`가 WS `agent_answer_completed` 메시지로 직렬화되는지 확인/보정(payload 패스스루면 무변경) | High |
| 8 | `src/application/workflows/excel_analysis_workflow.py` | `chart_router` 다음 conditional edge: `visualize → chart_builder → END`, `text → END`. chart_builder에 LLM 빌더 주입(§6-3 의존성 참조) | High |
| 9 | `src/application/use_cases/analyze_excel_use_case.py` | 최종 결과 dict의 `charts`(또는 `state["charts"]`)를 응답에 surface | High |
| 10 | `src/api/main.py` | `chart_builder`를 `WorkflowCompiler`(및 Excel 워크플로우)에 주입하도록 DI 배선 추가 | High |

### 3-2. 프론트엔드 (idt_front/)

| # | 수정 위치 | 내용 | 우선순위 |
|---|-----------|------|----------|
| 11 | `src/types/websocket.ts::AgentAnswerCompletedData` | `charts?: ChartPayload[]` 필드 추가 (`ChatAnswerCompletedData`와 동일 패턴, line 149 참조) | High |
| 12 | `src/hooks/useAgentRunStream.ts` (`case 'agent_answer_completed'`) | `msg.data.charts`를 상태로 캡처 | High |
| 13 | 에이전트 채팅 렌더 컴포넌트 (`MessageBubble.tsx` 또는 Agent run 결과 뷰) | 캡처한 `charts`를 기존 `ChartRenderer`로 전달해 렌더(General Chat과 동일 컴포넌트 재사용) | High |
| 14 | `src/hooks/useAgentRunStream.test.ts` | `agent_answer_completed`에 `charts` 포함 시 상태 반영 테스트 | Medium |

### 3-3. 범위 외 (별도 처리)

- `text` 분기(시각화 아님)에서 발생할 수 있는 일반 supervisor 재라우팅은 기존 동작이며 본 plan 범위 아님(차트 무한루프만 대상).
- `chart_router`의 휴리스틱/LLM 분류 정확도 개선(`VisualizationRoutingPolicy` 튜닝)은 별도.
- 차트의 DB 영속화(대화 재진입 시 차트 복원)는 후속 — 현재는 ephemeral.

---

## 4. 수정 방향 (Solution Design)

### 4-1. 그래프 흐름 (Supervisor)

```
supervisor ─(route_to_worker)→ analysis_worker
analysis_worker ─→ chart_router            (viz_decision 기록)
chart_router ─(route_after_chart_router)→ ┬ visualize → chart_builder ─→ quality_gate
                                          └ text                      ─→ quality_gate
quality_gate ─(route_after_quality)→ supervisor
supervisor: visualization_done=True → skip_workers가 분석 워커 제외 → FINISH
```

핵심: **차트 생성과 루프 차단을 분리**한다.
- `chart_builder`: 차트를 만들어 `state["charts"]`에 적재 + `visualization_done=True`. **메시지/last_worker_id 불변** → quality_gate는 직전 분석 텍스트(이미 양질)를 평가해 통과.
- `skip_workers`: `visualization_done`이면 분석 워커를 skip 목록에 넣어 supervisor가 재선택 불가 → 결정적으로 FINISH 유도. (LLM 판단에 의존하지 않음 = 루프 원천 차단)

### 4-2. `chart_builder` 노드 (신규)

```python
# src/application/visualization/chart_builder_node.py
from src.domain.visualization.interfaces import ChartBuilderInterface
from src.domain.visualization.schemas import VizDecision
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def create_chart_builder_node(
    builder: ChartBuilderInterface,
    logger: LoggerInterface,
):
    """viz_decision=="visualize"일 때만 Chart.js config 생성.

    실패/비대상은 빈 결과로 graceful degrade. 본 흐름(텍스트 답변)은 절대 막지 않는다.
    messages/last_worker_id는 수정하지 않아 quality_gate 오판·재시도를 유발하지 않는다.
    """
    async def chart_builder(state: dict) -> dict:
        if state.get("viz_decision") != VizDecision.VISUALIZE.value:
            return {"visualization_done": True}

        question = _extract_question(state)       # chart_router와 동일 추출 로직 재사용
        analysis_text = _extract_analysis_text(state)
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

> `_extract_question` / `_extract_analysis_text`는 `chart_router.py`의 동일 헬퍼를 공용 모듈로 추출해 재사용한다(중복 방지).

### 4-3. `workflow_compiler.py` 배선 변경

```python
if analysis_worker_ids:
    graph.add_node("chart_router", _wrap_step("chart_router", NodeType.OTHER, chart_router_fn))
    chart_builder_fn = create_chart_builder_node(self._chart_builder, self._logger)
    graph.add_node("chart_builder", _wrap_step("chart_builder", NodeType.OTHER, chart_builder_fn))

# analysis 워커 직후 라우터
graph.add_edge(worker_id, "chart_router")          # (기존)

if analysis_worker_ids:
    graph.add_conditional_edges(
        "chart_router", route_after_chart_router,
        {"visualize": "chart_builder", "text": "quality_gate"},
    )
    graph.add_edge("chart_builder", "quality_gate")
```

`WorkflowCompiler.__init__`에 `chart_builder: ChartBuilderInterface | None = None` 주입(미주입 시 차트 비활성 = 하위호환). 미주입이면 `chart_router → quality_gate` 직결(현행 유지).

### 4-4. `skip_workers` 결정적 가드

```python
# AttachmentRoutingHooks
def skip_workers(self, state: SupervisorState) -> list[str]:
    if state.get("visualization_done"):
        return list(self._analysis_worker_ids)   # 분석 워커 재라우팅 차단 → FINISH 유도
    return []
```

`supervisor_node`는 이미 `skipped` 워커 선택 시 `__end__` 처리(`supervisor_nodes.py:159-160`). 분석 워커가 유일 워커면 supervisor는 분석 텍스트를 최종 답변으로 FINISH, 차트는 `state["charts"]`로 별도 전달.

### 4-5. 차트 surface (run_agent_use_case)

`ANSWER_COMPLETED` payload를 `{answer, tools_used}` → `{answer, tools_used, charts}`로 확장(`run_agent_use_case.py:243-246`). `_StreamState`가 `chart_builder` on_chain_end output(`data.output.charts`)을 캡처하도록 `_map_event`/on_chain_end 처리부에 누적(General Chat의 `_maybe_build_charts` 결과 전달과 동일 효과). `charts`가 비면 키 생략 또는 빈 배열 → 프론트 하위호환.

### 4-6. Excel 경로

```python
workflow.add_node("chart_builder", create_chart_builder_node(excel_chart_builder, self._logger))
workflow.add_conditional_edges(
    "chart_router", route_after_chart_router,
    {"visualize": "chart_builder", "text": END},
)
workflow.add_edge("chart_builder", END)
```

`ExcelAnalysisState`에 `charts: list[dict]` 추가, `analyze_excel_use_case`가 최종 `charts`를 응답에 포함.

---

## 5. 테스트 계획 (TDD)

> 백엔드 pytest는 Windows 이벤트 루프 teardown 산발 실패 이슈가 있어 **격리 실행**으로 검증한다(메모리: backend-test-eventloop-flakiness). 프론트 vitest는 `--pool=threads`(메모리: frontend-vitest-forks-timeout).

### 5-1. `chart_builder_node` 단위 테스트 (신규)
- `viz_decision="visualize"` + 수치 분석텍스트 → `charts` 비어있지 않음, `visualization_done=True`.
- `viz_decision="text"` → `charts` 미생성(또는 빈), `visualization_done=True`, **빌더 호출 안 함**.
- `builder.build` 예외 → `charts=[]`로 graceful degrade(예외 전파 X).
- **messages/last_worker_id 불변** 단언(quality_gate 오판 방지 회귀).

### 5-2. `workflow_compiler` 라우팅 테스트
- 분석 워커 + `chart_builder` 주입 시: `visualize` 분기에서 `chart_builder` 노드를 거쳐 `state["charts"]`가 채워지고 그래프가 **유한 횟수**(≤ max_iterations 훨씬 이전)에 종료됨(루프 회귀 방지).
- `chart_builder` 미주입(None) 시: `chart_router → quality_gate` 직결, 기존 동작 보존.

### 5-3. `skip_workers` 가드 테스트
- `visualization_done=True` → 분석 워커 id가 skip에 포함.
- supervisor가 skip된 분석 워커 선택 시 `__end__`로 귀결(재라우팅 차단).

### 5-4. `run_agent_use_case` ANSWER_COMPLETED 테스트
- `chart_builder`가 charts를 만든 run → `ANSWER_COMPLETED` payload에 `charts` 포함.
- charts 없는 run → 기존과 동일(키 없음/빈 배열), 하위호환.

### 5-5. Excel 워크플로우 테스트
- `visualize` 분기 → `charts` 채워짐, END 도달.
- `text` 분기 → charts 없이 END.

### 5-6. 프론트 테스트
- `useAgentRunStream.test.ts`: `agent_answer_completed`에 `charts` 포함 시 상태에 반영.
- (가능 시) 에이전트 채팅 뷰에서 `charts` 전달 시 `ChartRenderer` 렌더 스냅샷/존재 검증.

---

## 6. 영향 범위 / 리스크 / 의존성

| 항목 | 영향 | 비고 |
|------|------|------|
| `SupervisorState` 필드 추가 | 낮음 | `build_initial_state` 초기화 동반 — 누락 시 KeyError 주의 |
| `chart_builder` 미주입 경로 | 없음 | None이면 현행 `chart_router → quality_gate` 유지(하위호환) |
| quality_gate 재시도 | 회피 설계 | chart_builder가 messages 불변 → 직전 분석텍스트 평가 그대로 |
| 토큰 사용량 | 소폭 증가 | 차트 생성용 LLM structured output 1회. 단, **무한루프 제거로 순감소** 기대 |
| `ANSWER_COMPLETED` 계약 | 추가 필드 | `charts` optional → 프론트/백 하위호환 |
| 차트 렌더 경로 | General Chat과 동일 컴포넌트 재사용 | 신규 차트 컴포넌트 불필요 |

### 6-3. [의존성/오픈 이슈] Excel chart_builder용 LLM

`LangChainChartBuilder`는 `langchain_core` `BaseChatModel`을 요구한다. Excel 워크플로우는 `claude_client`(커스텀 어댑터)를 사용하므로 그대로 주입 불가할 수 있다. 옵션:
1. Excel용 `chart_builder`에 별도 `BaseChatModel`(General Chat과 동일 LLM 팩토리 산출물) 주입 — **권장**.
2. `claude_client`를 감싸는 어댑터로 `ChartBuilderInterface.build` 구현.
→ Design 단계에서 main.py DI 자원 확인 후 확정. (Supervisor 경로는 `compile()` 내 `llm`이 이미 `BaseChatModel`이라 문제 없음.)

---

## 7. 구현 순서

1. **TDD RED**: `chart_builder_node` 단위 테스트(5-1) 작성 → 실패 확인.
2. `supervisor_state.py` 필드 추가 + `build_initial_state` 초기화.
3. `chart_builder_node.py` 신규 구현 + `_extract_question/_extract_analysis_text` 공용화.
4. `workflow_compiler.py` conditional edge 배선 + `chart_builder` 주입(§4-3).
5. `AttachmentRoutingHooks.skip_workers` 가드(§4-4) + 테스트(5-3).
6. `run_agent_use_case.py` charts 캡처 + `ANSWER_COMPLETED` 확장 + 테스트(5-4).
7. `ws_router.py` charts 직렬화 확인.
8. `main.py` DI: `WorkflowCompiler`에 `chart_builder` 주입.
9. Excel 경로(§4-6) + DI(§6-3) + 테스트(5-5).
10. 프론트: `websocket.ts` 타입 → `useAgentRunStream.ts` 캡처 → 채팅 뷰 `ChartRenderer` 연결 + 테스트(5-6).
11. 로컬 수동 검증: 분석 워커 에이전트에 "그래프 그려줘" → 차트 렌더 + 루프 없음 확인 / 엑셀 업로드 분석 → 차트 확인.
12. `/pdca analyze supervisor-chart-builder-node` → Gap 분석 → Report.

---

## 8. 미해결 / 후속 이슈

- **차트 영속화**: 대화 재진입 시 차트 복원(현재 ephemeral). 별도 plan.
- **text 분기 일반 재라우팅**: 차트와 무관한 supervisor 회전 최적화는 별도.
- **`chart_router` 분류 정확도**: 휴리스틱/LLM 분류 튜닝 별도.
- **검색결과/분석텍스트 추출 휴리스틱**: `"검색결과" in content` 한국어 고정 문자열 의존 — 구조화 메타데이터로 개선 검토.
