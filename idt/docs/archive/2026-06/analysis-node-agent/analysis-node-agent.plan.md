# ANALYSIS-NODE-AGENT: Supervisor 그래프에 분석 전용 노드 에이전트 추가 (엑셀분석 1차 연동)

> 상태: Plan
> 연관 Task: ANALYSIS-NODE-001
> 작성일: 2026-06-04
> 우선순위: High

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 현재 supervisor 그래프(`WorkflowCompiler`)에서 `category="search"` 워커만 LLM 없는 전용 노드(`_create_search_node`)로 동작하고, 나머지 워커는 모두 `create_react_agent`로 동작한다. "수집된 데이터를 질문 기준으로 분석"하는 책임이 별도 노드로 분리되어 있지 않아, 엑셀 등 정형 데이터 분석을 supervisor 흐름 안에서 일관되게 처리할 수 없다. 이미 만들어진 `ExcelAnalysisWorkflow`(자가교정·할루시네이션 검증·재시도·코드실행)는 standalone API에만 묶여 있어 에이전트 빌더 워크플로우에서 재사용되지 못한다. |
| **Solution** | `category="analysis"` 신규 워커 타입을 도입하고, `WorkflowCompiler`에 전용 노드 `_create_analysis_node`를 추가한다. 이 노드는 **(a) 엑셀 파일이 있으면** 기존 `ExcelAnalysisWorkflow`를 래핑 호출하고, **(b) 없으면** 직전 search 결과(있으면) 또는 전체 대화 문맥을 대상으로 LLM 분석을 수행한다. 분석 결과만 `AIMessage`로 반환하고 `quality_gate → supervisor`로 복귀한다. |
| **Function UX Effect** | 사용자가 엑셀을 첨부하면 supervisor가 분석 워커로 라우팅 → 질문 기준으로 데이터를 분석한 결과를 받는다. 엑셀이 없을 때는 검색 결과/대화 맥락을 종합 분석하는 "분석가" 역할을 한 노드가 담당한다. search → analysis → answer 의 다단 협업이 가능해진다. |
| **Core Value** | RAG/Agent 플랫폼에 **"검색"과 분리된 "분석" 역량**을 1급 노드로 추가. 금융/정책 정형 데이터(엑셀) 분석을 예측 가능한 노드 구조로 확장하면서, 기존 자가교정 워크플로우 자산을 재사용해 중복 구현을 피한다. |

---

## 1. 문제 정의 (Problem Statement)

### 1-1. 현재 동작

`src/application/agent_builder/workflow_compiler.py::compile()` (lines 109~152)는 워커별 카테고리에 따라 노드를 생성한다:

```python
category = self._resolve_category(worker_def)
if category == "search":
    worker_map[wid] = self._create_search_node(wid, tool)   # LLM 없는 전용 노드
    has_search_workers = True
else:                                                       # category == "action"
    worker_agent = create_react_agent(llm, tools=[tool], name=wid)
    worker_map[wid] = worker_agent
```

- **search 워커**: `_create_search_node` — 도구를 직접 실행, 결과를 `AIMessage(name=worker_id, content="[... 검색결과]\n...")`로 추가.
- **그 외(action) 워커**: `create_react_agent` 표준 ReAct 루프.
- search 워커가 1개 이상이면 가상 `answer_agent` 노드가 추가되어 검색결과를 종합해 최종 답변 생성(END).

### 1-2. 문제점

1. "데이터를 질문 기준으로 **분석**하고 결과만 반환"하는 책임을 가진 전용 노드가 없다. action 워커(`create_react_agent`)는 도구 호출 중심이라 "분석가" 역할에 부적합하고 토큰·동작이 예측 어렵다.
2. 엑셀 분석 자산(`src/application/workflows/excel_analysis_workflow.py` + `src/application/use_cases/analyze_excel_use_case.py`)이 **standalone `/api/v1/analysis/excel` 라우터에만** 연결되어 있고, 에이전트 빌더 supervisor 흐름에서는 재사용 불가.
3. `ToolCategory = Literal["search", "action"]` (`schemas.py:8`)에 분석 개념이 없어 라우팅 분기가 불가능.

---

## 2. 결정된 설계 방향 (확정된 답변 반영)

사용자 확인 결과 다음으로 확정:

| 결정 항목 | 선택 | 의미 |
|-----------|------|------|
| 기존 코드 관계 | **기존 워크플로우 래핑** | 엑셀 분기는 `ExcelAnalysisWorkflow`를 그대로 호출(자가교정·할루시네이션·재시도·코드실행 재사용). |
| 노드 트리거 | **새 카테고리 'analysis' 워커** | `ToolCategory`에 `"analysis"` 추가, search처럼 에이전트마다 워커로 등록. |
| 데이터 입력 소스 | **둘 다 지원** | 엑셀 파일이 있으면 파싱·분석, 없으면 검색결과/대화 문맥 분석. |
| 반환 흐름 | **supervisor로 복귀** | 분석 결과 `AIMessage` 반환 후 `quality_gate → supervisor` (answer_agent 처럼 END 아님). |

---

## 3. 수정 범위 (Scope)

| # | 위치 | 내용 | 우선순위 |
|---|------|------|----------|
| 1 | `src/domain/agent_builder/schemas.py` | `ToolCategory`에 `"analysis"` 추가 (`Literal["search", "action", "analysis"]`) | High |
| 2 | `src/application/agent_builder/supervisor_state.py` | `attachments: list[dict]` 필드 추가 (엑셀 파일 경로 등 첨부 전달용) | High |
| 3 | `src/application/agent_builder/supervisor_nodes.py::build_initial_state()` | `attachments` 파라미터 추가 및 초기 state에 포함 | High |
| 4 | `src/application/agent_builder/workflow_compiler.py` | `_create_analysis_node()` 신규 + `compile()`에 `category == "analysis"` 분기 + 그래프 엣지(analysis → quality_gate) 추가 | Critical |
| 5 | `src/application/agent_builder/workflow_compiler.py::__init__` | `excel_analysis_workflow_getter` (Callable, Optional) 주입 — 기존 `ExcelAnalysisWorkflow` 래핑용 | High |
| 6 | `src/api/main.py` | `WorkflowCompiler` 생성 시 `excel_analysis_workflow_getter` 와이어링 (이미 존재하는 `ExcelAnalysisWorkflow` DI 재사용) | High |
| 7 | `src/application/agent_builder/run_agent_use_case.py` | 실행 입력의 첨부(엑셀 경로 등)를 `build_initial_state(attachments=...)`로 전달 | Medium |
| 8 | (선택) `src/domain/agent_builder/tool_registry.py` | 분석용 가상 tool_id(예: `data_analysis`) 등록 — UI 노출/카테고리 기본값 제공 | Medium |
| 9 | `tests/application/agent_builder/test_workflow_compiler.py` | 분석 노드 단위/분기 테스트 (엑셀 O/X, 검색결과 O/X) | High |

**범위 외 (별도 처리)**:
- 엑셀 파일 업로드 자체의 저장/경로 발급 파이프라인(이미 standalone 라우터에 존재 — 경로 재사용 가정).
- `ExcelAnalysisWorkflow` 내부 로직 변경(자가교정/임계값 등) — 그대로 래핑만 한다.
- answer_agent와 analysis 노드의 우선순위/협업 프롬프트 튜닝(추후 별도 plan).

---

## 4. 설계 (Solution Design)

### 4-1. 카테고리 확장

```python
# src/domain/agent_builder/schemas.py
ToolCategory = Literal["search", "action", "analysis"]
```

`WorkerDefinition.category`는 이미 `str | None`이므로 구조 변경 없음. `_resolve_category()`는 DB override → TOOL_REGISTRY → 기본값 `"action"` 순서 그대로 사용.

### 4-2. SupervisorState 첨부 필드

```python
# supervisor_state.py
class SupervisorState(TypedDict):
    ...
    attachments: list[dict]   # 예: [{"type": "excel", "file_path": "...", "user_id": "..."}]
```

`build_initial_state(..., attachments: list[dict] | None = None)` → `"attachments": attachments or []`.

> sub_agent 흐름(`_wrap_sub_agent`)에서도 부모 state의 attachments를 전달할지는 1차 범위에서 제외(엑셀 분석은 top-level 워크플로우에서만 트리거 가정). 후속 이슈로 분리.

### 4-3. 분석 노드 `_create_analysis_node`

핵심 동작 분기:

```
analysis_node(state):
    question = 최신 user 메시지 content
    excel = state["attachments"] 중 type == "excel" 인 항목
    search_results = [m for m in messages if _is_search_result(m)]   # 기존 헬퍼 재사용

    if excel:                       # (a) 엑셀 분기 → 기존 워크플로우 래핑
        wf = self._excel_analysis_workflow_getter()
        initial = { ...ExcelAnalysisState..., user_query=question,
                    excel_data={file_path, user_id} }
        final = await wf.run(initial)
        analysis_text = final["analysis_text"]
    else:                           # (b) 검색결과/문맥 분기 → 직접 LLM 분석
        context = "\n\n---\n\n".join(search_results) if search_results
                  else "(검색 결과 없음 — 전체 대화 문맥 기준 분석)"
        conversation = [검색결과 AIMessage 제외한 messages]
        prompt = 분석가 system prompt + [분석 대상 데이터/검색결과] context
        response = await llm.ainvoke([system, *conversation])
        analysis_text = response.content

    return {
        "messages": [AIMessage(content=analysis_text, name=worker_id)],
        "last_worker_id": worker_id,
        "token_usage": state["token_usage"] + len(analysis_text)//4,
    }
```

설계 포인트:
- **`_is_search_result` 헬퍼 재사용**: 이미 `_create_answer_node` 내부에 동일 로직 존재 → 모듈 레벨 또는 인스턴스 메서드로 추출해 analysis/answer 양쪽이 공유(중복 제거 리팩토링).
- **(b) 분기의 "검색 결과 있으면 분석, 없으면 전체 문맥"** 동작이 사용자 요구사항과 정확히 일치.
- **"분석한 결과만 반환"**: 노드는 분석 텍스트만 `AIMessage`로 반환. 도구 호출/중간 사고는 노출하지 않음.
- **supervisor 복귀**: 다른 워커들과 동일하게 `graph.add_edge(worker_id, "quality_gate")` 경로를 타므로 별도 엣지 추가 불필요 — `worker_map`에 등록되면 기존 `for worker_id in worker_map: graph.add_edge(worker_id, "quality_gate")` 루프가 자동 처리. (answer_agent처럼 END로 가지 않음.)

### 4-4. `compile()` 분기 추가

```python
if category == "search":
    worker_map[wid] = self._create_search_node(wid, tool)
    has_search_workers = True
elif category == "analysis":
    worker_map[wid] = self._create_analysis_node(llm, wid, workflow.supervisor_prompt)
else:
    worker_map[wid] = create_react_agent(llm, tools=[tool], name=wid)
```

- analysis 노드는 search처럼 "함수형 노드"이므로 `compile()`의 노드 등록부에서 `_wrap_worker`가 아닌 함수 그대로 등록되어야 한다. 현재 코드는 `isinstance(worker_agent, type(lambda: None))`로 함수 여부를 판별(workflow_compiler.py:221) → analysis 노드도 async 함수이므로 동일 처리됨. **단 이 판별은 취약**하므로, search/analysis 노드를 명시적으로 함수 집합(set)에 기록해 분기하는 방식으로 개선 검토(아래 6 리스크).
- NodeType: 관측성 래핑(`_wrap_step`)에 전달할 타입은 `NodeType.WORKER` 재사용(또는 `NodeType.OTHER`). 신규 enum 값 추가는 선택.

### 4-5. DI 와이어링 (`main.py`)

`ExcelAnalysisWorkflow`는 이미 `main.py`에서 생성됨(lines 619, 905, 924 등). `WorkflowCompiler` 생성 지점에 getter를 전달:

```python
WorkflowCompiler(
    tool_factory=...,
    llm_factory=...,
    logger=...,
    agent_repository=...,
    llm_model_repository=...,
    excel_analysis_workflow_getter=lambda: get_configured_excel_analysis_workflow(),
)
```

`excel_analysis_workflow_getter`가 None이면 분석 노드는 (a) 엑셀 분기를 비활성화하고 (b) 문맥 분석만 수행(graceful degradation) → 테스트/부분 배포 안전.

---

## 5. 테스트 계획 (TDD)

**파일**: `tests/application/agent_builder/test_workflow_compiler.py`

1. **`test_analysis_category_creates_function_node`**: `category="analysis"` 워커가 `create_react_agent`가 아닌 함수 노드로 등록되는지.
2. **`test_analysis_node_excel_branch_wraps_workflow`**: `attachments`에 엑셀 존재 시 주입된 `ExcelAnalysisWorkflow.run`이 호출되고 그 `analysis_text`가 반환 메시지에 담기는지(Fake workflow mock).
3. **`test_analysis_node_uses_search_results_when_present`**: 엑셀 없고 검색결과 AIMessage가 있을 때 해당 결과가 분석 컨텍스트로 LLM에 전달되는지(FakeLLM 인자 검증).
4. **`test_analysis_node_uses_full_context_when_no_search`**: 엑셀·검색결과 모두 없을 때 전체 대화 문맥이 컨텍스트로 사용되는지.
5. **`test_analysis_node_returns_to_supervisor_not_end`**: 분석 노드가 `quality_gate` 엣지를 갖고 END로 직행하지 않는지(컴파일된 그래프 엣지 검증).
6. **`test_analysis_node_no_excel_getter_graceful`**: getter=None일 때 엑셀 분기 없이 문맥 분석으로 동작하는지.

각 테스트 RED 확인 후 구현.

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| `ToolCategory` 변경 | 낮음 | 값 추가만, 기존 search/action 영향 없음 |
| 함수 노드 판별 `isinstance(.., type(lambda))` | **중간 리스크** | analysis 노드 추가로 판별 취약성 노출 → 함수 노드 집합 명시 관리로 개선 권장 |
| `ExcelAnalysisWorkflow` 래핑 | 낮음 | 내부 변경 없음, getter 주입만 |
| `SupervisorState` 필드 추가 | 낮음 | TypedDict optional 사용 — 기존 build_initial_state 호출부 영향 점검 필요 |
| 엑셀 파일 경로 전달 경로 | **중간** | run_agent 입력 → state.attachments 와이어링 미정 부분. 업로드/경로 발급은 standalone 라우터 자산 재사용 가정 |
| 토큰 사용량 | 증가 가능 | 분석 노드가 전체 문맥/검색결과를 LLM에 전달 — token_limit 정책으로 방어 |
| `_is_search_result` 중복 | 낮음 | answer/analysis 공용 헬퍼 추출로 정리 |

---

## 7. 구현 순서

1. `test_workflow_compiler.py`에 5장 테스트 작성 (RED).
2. `schemas.py` `ToolCategory`에 `"analysis"` 추가.
3. `supervisor_state.py` + `build_initial_state()` `attachments` 추가.
4. `workflow_compiler.py`: `_is_search_result` 공용 헬퍼 추출 → `_create_analysis_node` 구현 → `compile()` 분기/엣지 추가 → `__init__` getter 주입.
5. 테스트 GREEN 확인.
6. `main.py` DI 와이어링 + `run_agent_use_case` attachments 전달.
7. 로컬 dev 서버 수동 검증: (a) 엑셀 첨부 분석, (b) 검색→분석, (c) 문맥-only 분석.
8. `/pdca analyze analysis-node-agent` → Gap 분석 → Report.

---

## 8. 미해결 / 후속 이슈

- **엑셀 경로 입력 계약**: 에이전트 `run` API가 첨부 파일을 받는 표준 방식(멀티파트 vs 사전 업로드 후 file_id) 확정 필요 — 별도 API 계약 plan 권장(`/api-contract-sync` 대상).
- **sub_agent 흐름의 attachments 전달**: 1차 범위 제외.
- **analysis ↔ answer_agent 협업 순서**: search→analysis→answer 다단 흐름의 supervisor 프롬프트 튜닝 후속.
- **함수 노드 판별 리팩토링**: `isinstance(.., type(lambda))` 휴리스틱을 명시적 노드 종류 레지스트리로 교체.
- **데이터 분석용 tool_id 등록 여부**: UI에서 분석 워커를 선택 가능하게 하려면 `TOOL_REGISTRY`에 `category="analysis"` 엔트리 필요.
