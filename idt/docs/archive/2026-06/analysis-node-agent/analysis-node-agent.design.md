# analysis-node-agent Design Document

> **Summary**: Supervisor 그래프에 `category="analysis"` 전용 노드를 추가한다. 엑셀 첨부 시 기존 `ExcelAnalysisWorkflow`를 래핑 호출, 없으면 직전 검색결과(있으면)/전체 대화 문맥(없으면)을 질문 기준으로 LLM 분석하고 결과만 반환 후 `quality_gate → supervisor`로 복귀한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: FastAPI + LangGraph
> **Author**: 배상규
> **Date**: 2026-06-04
> **Status**: Draft
> **Planning Doc**: [analysis-node-agent.plan.md](../../01-plan/features/analysis-node-agent.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- supervisor 그래프에 "분석" 책임을 가진 1급 노드를 `search` 노드와 동일한 등급으로 추가.
- 엑셀 분석은 기존 `ExcelAnalysisWorkflow`(자가교정·할루시네이션·재시도·코드실행)를 **그대로 래핑**해 재사용.
- 엑셀이 없으면 검색결과/대화 문맥을 종합 분석 — "검색 결과 있으면 분석, 없으면 전체 문맥" 동작.
- 분석 결과만 `AIMessage`로 반환하고 supervisor로 복귀(answer_agent 와 달리 END 아님).
- Thin DDD 레이어 규칙 준수: domain은 카테고리 enum만 확장, application(WorkflowCompiler)이 흐름 제어, infrastructure 의존은 getter 주입으로 역전.

### 1.2 Design Principles

- **단일 책임**: 분석 노드는 "질문+데이터 → 분석 결과 텍스트" 변환만 담당.
- **기존 자산 재사용 (DRY)**: 엑셀 자가교정 로직을 재구현하지 않고 `ExcelAnalysisWorkflow.run()` 호출.
- **Graceful degradation**: `excel_analysis_workflow_getter`가 None이면 엑셀 분기 비활성, 문맥 분석만 수행 → 부분 배포/테스트 안전.
- **기존 흐름 비침투**: search/action 노드 동작 불변, 그래프 엣지 등록 로직 재사용.

---

## 2. Architecture

### 2.1 노드 위치 (Supervisor 그래프)

```
                 ┌───────────────┐
   entry ───────▶│  supervisor   │◀──────────────┐
                 └──────┬────────┘               │
        route_to_worker │ (next_worker)          │ route_after_quality
            ┌───────────┼───────────┬─────────┐  │
            ▼           ▼           ▼         ▼  │
      ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌────────┐
      │ search   │ │ action  │ │ analysis │ │__end__ │
      │ node     │ │(react)  │ │ node ★NEW│ └────────┘
      └────┬─────┘ └────┬────┘ └────┬─────┘
           │            │           │
           └────────────┴───────────┘
                        ▼
                 ┌───────────────┐
                 │ quality_gate  │── pass ──▶ supervisor
                 └───────────────┘
   (search 워커 존재 시) answer_agent ──▶ END  (분석 노드와 무관, 기존 유지)
```

- analysis 노드는 `worker_map`에 등록 → 기존 `for worker_id in worker_map: graph.add_edge(worker_id, "quality_gate")` 루프가 자동으로 `analysis → quality_gate` 엣지 생성. **별도 엣지 추가 코드 불필요.**

### 2.2 Data Flow

```
RunAgentUseCase._prepare_graph
   → build_initial_state(messages, config, available_workers, attachments)   # attachments 신규
   → graph.ainvoke(initial_state)
        supervisor → (analysis 워커 선택)
            analysis_node(state):
              question = 최신 user 메시지
              ┌ attachments에 type=="excel" 있음 ──▶ ExcelAnalysisWorkflow.run() ──▶ analysis_text
              └ 없음 ──▶ search 결과 있으면 그걸, 없으면 전체 문맥 ──▶ llm.ainvoke ──▶ analysis_text
              return AIMessage(content=analysis_text, name=worker_id)
            → quality_gate → supervisor → FINISH/answer
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `WorkflowCompiler._create_analysis_node` | `llm`, `ExcelAnalysisWorkflow` (getter) | 분석 노드 생성 |
| `WorkflowCompiler` | `excel_analysis_workflow_getter: Callable` | 엑셀 워크플로우 lazy 주입 (infra 역의존) |
| `main.py` DI | 기존 `ExcelAnalysisWorkflow` 빌더 | getter 와이어링 |
| `RunAgentUseCase` | `build_initial_state(attachments=...)` | 첨부 전달 |
| `SupervisorState` | — | `attachments` 필드 보유 |

---

## 3. Data Model

### 3.1 ToolCategory 확장 (domain)

```python
# src/domain/agent_builder/schemas.py
ToolCategory = Literal["search", "action", "analysis"]   # "analysis" 추가
```

`WorkerDefinition.category: str | None` 은 변경 없음. `ToolMeta.category` 기본값 `"action"` 유지.

### 3.2 SupervisorState 확장 (application)

```python
# src/application/agent_builder/supervisor_state.py
class SupervisorState(TypedDict):
    ...
    attachments: list[dict]   # 예: [{"type": "excel", "file_path": "/tmp/x.xlsx", "user_id": "u1"}]
```

> TypedDict에 키 추가 시 기존 `build_initial_state`가 항상 채워주므로 KeyError 없음. 노드 내부 접근은 `state.get("attachments", [])`로 방어.

### 3.3 attachment dict 스키마 (비공식 계약, 1차)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | str | ✅ | `"excel"` (확장 가능) |
| file_path | str | excel일 때 ✅ | 서버 로컬 경로 (업로드 라우터가 발급) |
| user_id | str | excel일 때 ✅ | `ExcelAnalysisWorkflow` parse_excel에 전달 |

---

## 4. 핵심 구현 설계

### 4.1 `build_initial_state` 시그니처 변경

```python
# supervisor_nodes.py
def build_initial_state(
    messages: list[dict],
    config: SupervisorConfig,
    available_workers: list[str],
    attachments: list[dict] | None = None,   # 신규 (default None → 하위호환)
) -> SupervisorState:
    return {
        ...,
        "attachments": attachments or [],
    }
```

기존 호출부 2곳 점검:
- `run_agent_use_case.py:457` → `attachments=request.attachments`(아래 4.5) 추가.
- `workflow_compiler.py:464` (`_wrap_sub_agent`) → attachments 미전달(기본 `[]`). **sub_agent 흐름은 1차 범위 제외** (Plan §8).

### 4.2 `_is_search_result` 공용 헬퍼 추출

현재 `_create_answer_node` 내부의 중첩 함수를 모듈/인스턴스 레벨로 승격해 answer/analysis 공유.

```python
# workflow_compiler.py (모듈 함수)
def _is_search_result(msg) -> bool:
    if isinstance(msg, dict):
        return False
    name = getattr(msg, "name", None)
    content = getattr(msg, "content", "")
    return bool(name) and "검색결과" in content
```

`_create_answer_node`의 기존 동일 로컬 함수는 이 모듈 함수 호출로 교체(동작 동일, 회귀 없음).

### 4.3 `_create_analysis_node`

```python
def _create_analysis_node(self, llm, worker_id: str, system_prompt: str):
    logger = self._logger
    get_excel_wf = self._excel_analysis_workflow_getter

    def _latest_user_question(messages) -> str:
        for msg in reversed(messages):
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
            if role in ("user", "human"):
                return msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
        return ""

    async def analysis_node(state: SupervisorState) -> dict:
        question = _latest_user_question(state["messages"])
        attachments = state.get("attachments", [])
        excel = next((a for a in attachments if a.get("type") == "excel"), None)

        if excel and get_excel_wf is not None:
            analysis_text = await self._run_excel_analysis(get_excel_wf(), question, excel)
        else:
            analysis_text = await self._analyze_context(llm, system_prompt, question, state["messages"])

        from langchain_core.messages import AIMessage
        return {
            "messages": [AIMessage(content=analysis_text, name=worker_id)],
            "last_worker_id": worker_id,
            "token_usage": state["token_usage"] + len(analysis_text) // 4,
        }

    return analysis_node
```

#### 4.3.1 엑셀 분기 — 기존 워크플로우 래핑

```python
async def _run_excel_analysis(self, wf, question: str, excel: dict) -> str:
    initial = {
        "request_id": "", "user_query": question,
        "excel_data": {"file_path": excel["file_path"], "user_id": excel.get("user_id", "")},
        "current_attempt": 0, "max_attempts": 3,
        "analysis_text": "", "confidence_score": 0.0, "hallucination_score": 0.0,
        "needs_web_search": False, "web_search_results": "",
        "needs_code_execution": False, "code_to_execute": "", "code_output": {},
        "attempts_history": [], "is_complete": False,
        "final_status": "pending", "error_message": "",
    }
    final = await wf.run(initial)
    return final.get("analysis_text", "") or "(엑셀 분석 결과 없음)"
```

> `ExcelAnalysisState` 초기값은 `AnalyzeExcelUseCase.execute()`(analyze_excel_use_case.py:64~85)와 동일 형태. 재사용 시 `max_attempts`는 워크플로우 내부 `_parse_excel_node`가 재설정하므로 임시값 3 무방.

#### 4.3.2 문맥 분기 — 검색결과 있으면 그걸, 없으면 전체 문맥

```python
async def _analyze_context(self, llm, system_prompt: str, question: str, messages: list) -> str:
    search_results = [getattr(m, "content", "") for m in messages if _is_search_result(m)]
    if search_results:
        context = "\n\n---\n\n".join(search_results)
        source_hint = "아래 검색 결과를 데이터로 삼아"
    else:
        context = "(별도 검색 결과 없음 — 전체 대화 문맥을 분석 대상으로 함)"
        source_hint = "아래 대화 문맥 전체를 데이터로 삼아"

    conversation = [m for m in messages if not _is_search_result(m)]
    analysis_prompt = (
        f"{system_prompt}\n\n"
        f"당신은 데이터 분석가입니다. {source_hint} 사용자의 질문에 대해 분석한 결과만 간결히 반환하세요.\n"
        f"데이터에 없는 내용은 추측하지 마세요.\n\n"
        f"[분석 대상 데이터]\n{context}\n\n[질문]\n{question}"
    )
    response = await llm.ainvoke([{"role": "system", "content": analysis_prompt}, *conversation])
    return response.content if hasattr(response, "content") else str(response)
```

### 4.4 `compile()` 분기 추가

```python
category = self._resolve_category(worker_def)
if category == "search":
    worker_map[wid] = self._create_search_node(wid, tool)
    has_search_workers = True
elif category == "analysis":
    worker_map[wid] = self._create_analysis_node(llm, wid, workflow.supervisor_prompt)
else:
    worker_map[wid] = create_react_agent(llm, tools=[tool], name=wid)
```

- 노드 등록부(`workflow_compiler.py:220-234`)의 함수 판별 `isinstance(worker_agent, type(lambda: None))`은 async def 함수도 function 타입이라 analysis 노드도 함수 그대로 등록됨(search 노드와 동일 경로). **Plan §6 리스크 — 명시적 함수 노드 집합 관리로 개선**:

```python
self._function_node_ids: set[str] = set()   # search/analysis 등록 시 add
...
if worker_id in self._function_node_ids:
    graph.add_node(worker_id, _wrap_step(worker_id, NodeType.WORKER, worker_agent))
else:
    graph.add_node(worker_id, _wrap_step(worker_id, NodeType.WORKER, self._wrap_worker(worker_id, worker_agent)))
```

- NodeType: `NodeType.WORKER` 재사용(enum 신규 값 추가 안 함). 관측성 step은 worker로 기록.

### 4.5 `WorkflowCompiler.__init__` getter 주입 + main.py 와이어링

```python
# workflow_compiler.py
def __init__(self, tool_factory, llm_factory, logger, hooks=None,
             agent_repository=None, llm_model_repository=None,
             excel_analysis_workflow_getter: Callable[[], object] | None = None):
    ...
    self._excel_analysis_workflow_getter = excel_analysis_workflow_getter
```

```python
# src/api/main.py:1730
workflow_compiler = WorkflowCompiler(
    tool_factory=tool_factory, llm_factory=_llm_factory, logger=app_logger,
    hooks=DefaultHooks(),
    excel_analysis_workflow_getter=get_configured_excel_analysis_workflow,  # 기존 빌더 재사용
)
```

> `get_configured_*` 헬퍼가 없으면 `create_*_workflow` 캐시 함수를 만들어 lazy 반환 (이미 `_analyze_excel_use_case` 캐시 패턴 존재, main.py:454/509).

### 4.6 RunAgentUseCase / Request 첨부 전달 (Medium)

```python
# run_agent_use_case.py:457
initial_state = build_initial_state(
    messages=messages, config=sv_config,
    available_workers=[w.worker_id for w in workflow.workers],
    attachments=getattr(request, "attachments", None),
)
```

`RunAgentRequest`에 `attachments: list[dict] | None = None` 추가(스키마 호환 — Optional). **엑셀 파일 경로를 request로 넣는 표준 API 계약은 후속**(Plan §8, `/api-contract-sync` 대상). 본 설계에서는 필드 통로만 마련.

---

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| `excel_analysis_workflow_getter is None` 인데 엑셀 첨부 | 엑셀 분기 skip → 문맥 분석으로 graceful fallback (Plan: getter None 안전) |
| `ExcelAnalysisWorkflow.run()` 예외 | try/except로 감싸 `"엑셀 분석 실패: {e}"` 반환 + `logger.error(exception=e)` (스택트레이스 보존, search_node 패턴과 동일) |
| 최신 user 메시지 없음 | `question=""` → 문맥 분석 프롬프트는 그대로 동작(데이터 기반 요약) |
| 검색결과·엑셀 모두 없음 | "(전체 대화 문맥)" 분석 — 정상 경로 |

> 로깅: 노드 진입 시 `logger.info("analysis_node executing", worker_id=, branch="excel"/"context", has_search=...)`. LOG-001 준수.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `_create_analysis_node` 분기 (엑셀 O/X, 검색 O/X) | pytest + Fake LLM/Workflow |
| Unit | `build_initial_state(attachments=...)` | pytest |
| Unit | 컴파일 그래프 엣지 (analysis → quality_gate, ≠ END) | pytest |
| Regression | `_create_answer_node` 헬퍼 추출 후 동작 동일 | pytest (기존 테스트 유지) |

### 8.2 Test Cases (Plan §5 매핑)

- [ ] `test_analysis_category_creates_function_node` — analysis 워커가 function 노드로 등록.
- [ ] `test_analysis_node_excel_branch_wraps_workflow` — attachments 엑셀 시 주입 workflow.run 호출 + analysis_text 반환.
- [ ] `test_analysis_node_uses_search_results_when_present` — 검색결과가 LLM 컨텍스트로 전달.
- [ ] `test_analysis_node_uses_full_context_when_no_search` — 검색결과 없으면 전체 문맥 사용.
- [ ] `test_analysis_node_returns_to_supervisor_not_end` — quality_gate 엣지 존재, END 직행 아님.
- [ ] `test_analysis_node_no_excel_getter_graceful` — getter=None 시 문맥 분석으로 동작.
- [ ] `test_excel_workflow_failure_returns_error_message` — run 예외 시 에러 메시지 반환 + 그래프 비중단.

> ⚠️ 테스트 격리: 메모리상 알려진 Windows 이벤트 루프 teardown flakiness — `test_workflow_compiler.py`는 가능하면 단독 실행으로 검증.

---

## 9. Clean Architecture (Thin DDD)

### 9.1 레이어 배치

| Component | Layer | Location | 규칙 준수 |
|-----------|-------|----------|----------|
| `ToolCategory` 확장 | Domain | `src/domain/agent_builder/schemas.py` | enum만, 외부 의존 없음 ✅ |
| `SupervisorState.attachments` | Application | `src/application/agent_builder/supervisor_state.py` | 상태 정의 ✅ |
| `build_initial_state` | Application | `supervisor_nodes.py` | 흐름 데이터 구성 ✅ |
| `_create_analysis_node` / 분기 | Application | `workflow_compiler.py` | 흐름 제어 ✅ (비즈니스 규칙 X) |
| `ExcelAnalysisWorkflow` 호출 | Application→Application | getter 경유 | 기존 워크플로우 재사용 ✅ |
| DI 와이어링 | Infrastructure/Composition | `main.py` | getter 주입 ✅ |

### 9.2 의존성 규칙 점검

- domain(schemas)은 application/infra 미참조 — ✅.
- application(WorkflowCompiler)이 infra 구체 클래스(`ExcelAnalysisWorkflow`는 application 레이어 워크플로우)에 직접 import하지 않고 **getter(Callable) 주입**으로 결합 역전 — ✅.
- 분석 노드는 "분석 결과 텍스트 생성" 흐름만 담당, 품질 판정 등 규칙은 기존 `ExcelAnalysisWorkflow`/`QualityGatePolicy`에 위임 — ✅ (router/노드에 비즈니스 규칙 작성 금지 준수).

---

## 11. Implementation Guide

### 11.1 변경 파일

```
src/domain/agent_builder/schemas.py                  # ToolCategory += "analysis"
src/application/agent_builder/supervisor_state.py    # attachments 필드
src/application/agent_builder/supervisor_nodes.py    # build_initial_state(attachments=)
src/application/agent_builder/workflow_compiler.py   # _is_search_result 추출 + _create_analysis_node + compile 분기 + __init__ getter + 함수노드 집합
src/api/main.py                                      # getter 와이어링
src/application/agent_builder/run_agent_use_case.py  # attachments 전달
src/application/agent_builder/schemas.py (Request)   # RunAgentRequest.attachments (Optional)
tests/application/agent_builder/test_workflow_compiler.py  # 신규/추가 테스트
```

### 11.2 Implementation Order (TDD)

1. [ ] `test_workflow_compiler.py`에 8.2 테스트 작성 (RED).
2. [ ] `schemas.py` `ToolCategory` 확장.
3. [ ] `supervisor_state.py` + `build_initial_state` attachments.
4. [ ] `workflow_compiler.py`: `_is_search_result` 추출 → `_create_analysis_node`/`_run_excel_analysis`/`_analyze_context` → `compile` 분기 → 함수노드 집합 → `__init__` getter.
5. [ ] 테스트 GREEN.
6. [ ] `main.py` getter 와이어링 + `run_agent_use_case`/`RunAgentRequest` attachments.
7. [ ] 로컬 수동 검증: (a) 엑셀 첨부, (b) 검색→분석, (c) 문맥-only.
8. [ ] `/pdca analyze analysis-node-agent`.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-04 | Initial draft (Plan 확정 결정 4건 반영) | 배상규 |
