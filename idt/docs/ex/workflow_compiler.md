# WorkflowCompiler 코드 흐름 상세 설명

> 대상 파일: `src/application/agent_builder/workflow_compiler.py`
> 한 줄 요약: **DB에 저장된 `WorkflowDefinition`(Agent 정의)을 LangGraph `StateGraph`로 동적 컴파일**하여,
> Supervisor(감독자)가 여러 Worker(도구/노드)를 라우팅하는 실행 가능한 그래프(`CompiledGraph`)를 만들어낸다.

---

## 0. 한눈에 보는 전체 그림

```
WorkflowDefinition (DB에서 로드한 Agent 설계도)
        │
        │  WorkflowCompiler.compile()
        ▼
┌──────────────────────────────────────────────┐
│            StateGraph(SupervisorState)         │
│                                                │
│   (entry) → supervisor ──┐                     │
│                  ▲       │ route_to_worker     │
│                  │       ▼                      │
│   route_after_   │   ┌─ worker_A ─┐            │
│   quality        │   ├─ worker_B ─┤→ quality_gate
│                  └───┤  search    │            │
│                      ├─ analysis ─┤→ chart_router → quality_gate
│                      └─ sub_agent ┘            │
│                                                │
│   answer_agent → END   (검색 워커가 있을 때만)  │
└──────────────────────────────────────────────┘
        │
        ▼
   CompiledGraph (실행 가능한 그래프)
```

- **supervisor**: 매 턴 다음에 어떤 워커를 호출할지(또는 종료할지)를 LLM으로 결정하는 중앙 라우터.
- **worker**: 실제 일을 하는 노드. 종류에 따라 4가지로 컴파일된다(아래 §3).
- **quality_gate**: 워커 결과의 품질을 검증하고, 미달이면 재시도/통과를 결정하는 게이트.
- **chart_router**: analysis 워커 직후, 결과를 시각화할지(차트) 텍스트로 둘지 판단하는 라우터.
- **answer_agent**: 검색(search) 워커가 있을 때만 추가되는 가상 노드. 흩어진 검색 결과를 종합해 최종 답변 생성.

---

## 1. 클래스 개요와 의존성 (`__init__`, 66~87행)

`WorkflowCompiler`는 컴파일에 필요한 외부 의존성을 생성자에서 주입받는다(DI).

| 의존성 | 역할 | 비고 |
|--------|------|------|
| `tool_factory` | `tool_id` → 실제 LangChain Tool 객체 생성 | `bind_auth_ctx` 지원 시 인증 컨텍스트 주입 |
| `llm_factory` | `LlmModel` → LLM 인스턴스 생성 | provider/model_name/temperature 반영 |
| `logger` | 구조화 로깅 | `print()` 금지, 반드시 logger 사용 |
| `hooks` | Supervisor 루프 확장 훅 | 기본값 `DefaultHooks` |
| `agent_repository` | sub_agent 컴파일 시 참조 에이전트 조회 | 없으면 sub_agent 사용 불가 |
| `llm_model_repository` | sub_agent가 다른 LLM을 쓸 때 모델 조회 | 선택적 |
| `excel_analysis_workflow_getter` | analysis 노드의 엑셀 분기에서 재사용할 워크플로우 | `None`이면 엑셀 분기 비활성 → 문맥 분석으로 graceful fallback |

> **설계 포인트**: 컴파일러는 "설계도(WorkflowDefinition)를 그래프로 변환"하는 책임만 가진다.
> 실제 Tool/LLM 생성은 Factory에 위임하므로, DDD의 Application 레이어 책임(흐름 제어)에 충실하다.

---

## 2. `compile()` 메인 흐름 (89~344행)

`compile()`은 비동기 메서드이며, 크게 **검증 → 준비 → 워커 컴파일 → 그래프 조립 → compile()** 5단계로 진행된다.

### 2-1. 진입 검증 & 준비 (105~133행)

1. **중첩 깊이 검증** — `NestingDepthPolicy.validate_depth(depth)`
   sub_agent가 재귀적으로 자신을 컴파일할 때 무한 중첩을 방지한다.
2. **LLM/Policy 생성** — `llm = self._llm_factory.create(...)`, `policy = QualityGatePolicy()`.
3. **사용자 컨텍스트 블록 prepend** (120~128행)
   - `include_user_context=True`이고 `auth_ctx`가 있으면, supervisor 프롬프트 **앞에** 사용자 정보 블록을 붙인다.
   - `auth_ctx=None`이면 빈 문자열이 반환되어 graceful하게 통과 (시스템 봇 등은 `False`).
4. **인증 컨텍스트 주입** — `tool_factory`가 `bind_auth_ctx`를 지원하면 현재 `auth_ctx`를 도구에 주입한다.

### 2-2. 워커 컴파일 루프 (135~194행)

`workflow.workers`를 순회하며, 각 워커를 **카테고리별로 분기**하여 `worker_map[worker_id]`에 등록한다.
동시에 라우팅/엣지 구성에 필요한 보조 집합을 채운다.

| 보조 변수 | 의미 |
|-----------|------|
| `worker_map` | `worker_id` → 노드(콜러블 또는 react agent) |
| `function_node_ids` | LLM 래핑 없이 직접 실행되는 "함수형 노드"(search/analysis) 집합. `_wrap_worker` 우회 판별용 |
| `analysis_worker_ids` | analysis 카테고리 워커. 직후 `chart_router`로 보낼 대상 |
| `has_search_workers` | 검색 워커 존재 여부. `answer_agent` 추가 트리거 |

분기 로직(우선순위 순):

1. **`worker_type == "sub_agent"`** → `_compile_sub_agent()`로 재귀 컴파일 (§4).
2. **`category == "analysis"`** → `_create_analysis_node()`. 도구를 직접 쓰지 않으므로 tool 생성 생략. `function_node_ids` + `analysis_worker_ids`에 추가.
3. 그 외 → **Tool 생성** (`tool_id`가 `mcp_`로 시작하면 `create_async`, 아니면 `create`).
   - **`category == "search"`** → `_create_search_node()`. `function_node_ids`에 추가, `has_search_workers=True`.
   - **그 외(action 등)** → `create_react_agent(llm, tools=[tool])`로 표준 ReAct 에이전트 생성.

> 카테고리 결정은 `_resolve_category()`(401~409행):
> **DB 오버라이드(`worker_def.category`) → TOOL_REGISTRY 메타 → 기본값 `"action"`** 순서로 폴백한다.

### 2-3. Supervisor용 워커 목록 보강 (196~205행)

검색 워커가 있으면, supervisor가 "검색 종료 후 답변 종합"을 선택할 수 있도록
**가상 워커 `answer_agent`**(`tool_id="__virtual__"`, `sort_order=9999`)를 supervisor에게 노출되는 목록에 추가한다.
(실제 노드 등록은 §2-5에서 별도 처리)

### 2-4. Hook 결정 & Supervisor/QualityGate 노드 생성 (207~222행)

- **첨부 라우팅 훅 자동 대체**: analysis 워커가 있고 외부 주입 훅이 없는(기본 `DefaultHooks`) 경우에만
  `AttachmentRoutingHooks`로 교체한다. 명시적으로 주입한 훅은 존중(테스트/확장 보호).
  → 이 훅은 엑셀 등 분석 가능한 첨부가 있으면 **첫 진입에 analysis 워커로 강제 라우팅**하여,
  supervisor LLM이 첨부를 인지 못하고 거부(FINISH)하는 것을 결정적으로 차단한다.
- `create_supervisor_node(...)` / `create_quality_gate_node(...)`로 두 핵심 노드 함수를 생성한다.

### 2-5. 관측성 래퍼 `_wrap_step` (224~257행)

각 노드 함수를 `track_step` 컨텍스트 매니저로 감싸,
**`ai_run_step` 자동 영속화 + `ai_tool_call.step_id`/`ai_llm_call.step_id` FK 자동 연결**을 수행한다(M3, AGENT-OBS-003).

- `tracker / callback / run_id` 중 **하나라도 `None`이면 원본 함수 그대로 반환**(관측성 비활성, 무비용).
- 노드 결과 dict에 `_step_output_summary`(상수 `STEP_OUTPUT_SUMMARY_KEY`)가 있으면 그것을 우선 요약으로 사용,
  없으면 `_summarize_state_output(result)`로 자동 요약.

> 참고: supervisor 노드는 `decision.reasoning`을 `_step_output_summary`로 내보내(supervisor_nodes.py 146행),
> 추가 LLM 비용 없이 "왜 이 워커를 골랐는지"가 step 기록에 남는다.

### 2-6. 그래프 노드 등록 (259~305행)

`StateGraph(SupervisorState)`를 만들고 노드를 등록한다. 모든 노드는 `_wrap_step`으로 감싼다.

| 노드 | NodeType | 래핑 방식 |
|------|----------|-----------|
| `supervisor` | SUPERVISOR | supervisor_fn |
| `quality_gate` | GATE | quality_gate_fn |
| 함수형 워커(search/analysis) | WORKER | 원본 콜러블 직접 (이미 노드 함수) |
| 일반 워커(react agent/sub_agent) | WORKER | `self._wrap_worker(...)`로 한 번 더 감쌈 |
| `answer_agent` | OTHER | `_create_answer_node(...)` — 검색 워커 있을 때만 |
| `chart_router` | OTHER | `create_chart_router_node(...)` — analysis 워커 있을 때만 |

> **핵심 분기**: `worker_id in function_node_ids` 여부로 `_wrap_worker` 적용을 결정한다(270행).
> 함수형 노드는 이미 `state → dict` 시그니처라 추가 래핑이 불필요하지만,
> react agent/sub_agent는 호출 규약(`{"messages": ...}` 입력)이 달라 `_wrap_worker`로 어댑팅이 필요하다.

### 2-7. 엣지 & 라우팅 구성 (307~335행)

```
set_entry_point("supervisor")

supervisor ──(conditional: route_to_worker)──▶ route_map
    route_map = { 각 worker_id → 동일 노드, "answer_agent"→answer_agent(검색시), "__end__"→END }

각 worker_id ──▶
    analysis 워커면  → chart_router
    그 외           → quality_gate

chart_router ──▶ quality_gate          (analysis 워커 있을 때만)
answer_agent ──▶ END                    (검색 워커 있을 때만)

quality_gate ──(conditional: route_after_quality)──▶ qg_route_map
    qg_route_map = { "supervisor"→supervisor, 각 worker_id→동일 노드 }
```

- **`route_to_worker`**(supervisor_nodes.py 236행): `state["next_worker"]` 값을 그대로 다음 노드 이름으로 반환.
  supervisor 노드가 LLM 결정으로 채운 `next_worker`("FINISH"는 `__end__`로 변환됨)가 라우팅을 좌우한다.
- **`route_after_quality`**(240행): quality_gate가 채운 `next_worker`가 비어있거나 `__end__`면 → **supervisor로 복귀**,
  아니면 해당 워커로(재시도) 라우팅.
- **chart_router의 현재 동작**(322~327행): 라우터는 `viz_decision`만 기록하고 일단 quality_gate로 직진한다.
  주석에 후속 차트 처리 노드 도입 시 conditional edge로 교체하는 방법이 명시돼 있다(확장 지점).

### 2-8. 컴파일 & 예외 처리 (337~344행)

- `graph.compile()`로 `CompiledGraph` 생성 후 반환.
- 전체 `try/except`로 감싸, 실패 시 **스택 트레이스를 포함**(`exception=e`)해 error 로깅 후 re-raise.
  (CLAUDE.md "스택 트레이스 없는 에러 처리 금지" 준수)

---

## 3. 4가지 워커 노드 타입 상세

컴파일러가 워커를 변환하는 4가지 방식. 각각 LangGraph 노드(`state → dict`)로 귀결된다.

### 3-1. 일반 액션 워커 — `create_react_agent` + `_wrap_worker` (191~194, 618~637행)

표준 LangChain ReAct 에이전트로 생성된 뒤, `_wrap_worker`로 LangGraph 노드 규약에 맞춘다.

`_wrap_worker`가 하는 일:
1. `worker_agent.ainvoke({"messages": state["messages"]})` 호출.
2. 결과 messages 길이 기반으로 토큰 사용량 추정(`len(content)//4`).
3. `{messages, last_worker_id, token_usage}` 반환.

### 3-2. 검색 워커 — `_create_search_node` (469~501행)

**LLM 래핑 없이 도구를 직접 실행**하는 함수형 노드.

1. 마지막 메시지를 쿼리로 추출.
2. `tool.ainvoke({"query": query})` 직접 호출(실패 시 에러 문자열로 graceful).
3. 결과를 `AIMessage(content="[{worker_id} 검색결과]\n...", name=worker_id)` 형태로 반환.
   → 이 특수 포맷이 나중에 `_is_search_result()`(53~63행)로 식별되어, answer/analysis 노드에서 컨텍스트로 모인다.

### 3-3. 분석 워커 — `_create_analysis_node` (503~616행)

도구 없이 LLM(또는 엑셀 워크플로우)으로 분석하는 함수형 노드. **2개 분기**:

- **엑셀 분기** (`branch="excel"`): `attachments`에 `type=="excel"`이 있고 `excel_analysis_workflow_getter`가 주입돼 있으면
  `_run_excel_analysis()`로 기존 `ExcelAnalysisWorkflow`를 래핑 호출. 예외 시 에러 메시지 반환(그래프 비중단).
- **문맥 분기** (`branch="context"`): `_analyze_context()`로
  직전 검색 결과(있으면) 또는 전체 대화 문맥(없으면)을 데이터 삼아 LLM 분석.

결과는 `AIMessage(name=worker_id)`로 반환되고, 그래프상에서는 **chart_router를 경유**해 quality_gate로 간다.

### 3-4. 서브 에이전트 워커 — `_compile_sub_agent` + `_wrap_sub_agent` (346~399, 639~670행)

다른 Agent를 통째로 **하위 그래프로 내장**(중첩 그래프)한다. §4에서 상세 설명.

---

## 4. 서브 에이전트 재귀 컴파일 (`_compile_sub_agent`, 346~399행)

`WorkflowCompiler`의 가장 강력한 기능 — **에이전트 안에 에이전트**(중첩).

```
compile(depth=0)
   └─ worker_type=="sub_agent" 발견
        └─ _compile_sub_agent(depth=1)
             ├─ CircularReferencePolicy.validate_no_cycle(ref_id, visited)  ← 순환 참조 차단
             ├─ agent_repository.find_by_id(ref_id)                          ← 참조 에이전트 로드
             ├─ (필요시) llm_model_repository로 서브 에이전트 전용 LLM 해석
             ├─ sub_agent.to_workflow_definition()                          ← 다시 WorkflowDefinition으로
             └─ self.compile(... depth=depth, visited=new_visited ...)       ← 재귀!
                  └─ 반환된 sub_graph를 _wrap_sub_agent로 노드화
```

방어 장치 2종:
- **`NestingDepthPolicy`**: depth 상한으로 무한 중첩 차단.
- **`CircularReferencePolicy`**: `visited` 집합으로 A→B→A 같은 순환 참조 차단.

전파되는 컨텍스트:
- `include_user_context`는 **부모와 자식의 AND**(`include_user_context and sub_agent.include_user_context`).
  → 부모가 `False`면 자식도 무조건 `False`.
- `tracker/callback/run_id/auth_ctx`는 그대로 전파되어 **관측성/인증이 하위 그래프까지 일관**되게 유지.

`_wrap_sub_agent`(639~670행)가 하위 그래프를 단일 노드로 어댑팅:
1. 마지막 메시지를 task로 추출.
2. `build_initial_state`로 **독립된 초기 상태** 구성 (`token_limit`은 부모의 **절반**으로 제한 → 폭주 방지).
3. `sub_graph.ainvoke(sub_initial)` 실행.
4. 하위 그래프 최종 답변을 `AIMessage(name=worker_id)`로 변환, `token_usage`는 부모 상태에 합산.

---

## 5. SupervisorState — 그래프가 공유하는 상태 (`supervisor_state.py`)

모든 노드가 읽고 쓰는 `TypedDict`. 주요 필드:

| 필드 | 역할 |
|------|------|
| `messages` | `Annotated[list, add_messages]` — 누적 대화 메시지(LangGraph가 자동 병합) |
| `iteration_count` / `max_iterations` | supervisor 루프 횟수 / 상한 |
| `token_usage` / `token_limit` | 토큰 사용량 추정 / 상한 |
| `next_worker` | **라우팅의 핵심** — 다음에 갈 노드 이름(`route_to_worker`/`route_after_quality`가 소비) |
| `last_worker_id` | 직전에 실행된 워커(품질 재시도 타깃) |
| `quality_gate_enabled` / `retry_counts` / `max_retries_per_worker` | 품질 게이트 제어 |
| `forced_worker` / `skipped_workers` | Hook이 채우는 강제/스킵 워커 |
| `attachments` | analysis 노드 입력용 첨부(예: 엑셀 경로) |
| `viz_decision` | chart_router 판단 결과(`"visualize"`/`"text"`/`""`) |

---

## 6. 런타임 한 사이클 예시 (검색 에이전트)

사용자: "우리 회사 휴가 규정 알려줘" (search 워커 1개 + answer_agent 자동 추가된 그래프)

```
1. supervisor   → LLM 결정: next_worker="policy_search"
2. policy_search→ 도구 직접 호출, AIMessage("[policy_search 검색결과]\n...") 추가 → quality_gate
3. quality_gate → 검색 결과 AIMessage 품질 OK → next_worker="" → supervisor 복귀
4. supervisor   → LLM 결정: 검색 완료 → next_worker="answer_agent"
5. answer_agent → 검색결과 메시지만 골라 컨텍스트로 종합, 최종 답변 생성 → END
```

> 품질 미달이었다면 3단계에서 `quality_gate`가 `retry_counts`를 올리고 `next_worker=last_worker`로 설정,
> `route_after_quality`가 다시 해당 워커로 보내 재생성한다(`max_retries_per_worker` 도달 시 강제 통과).

---

## 7. 설계상 눈여겨볼 포인트 (요약)

1. **데이터 기반 동적 그래프**: 코드를 바꾸지 않고 DB의 `WorkflowDefinition`만으로 그래프 형태가 바뀐다.
2. **카테고리 폴백 체인**: DB 오버라이드 → TOOL_REGISTRY → `"action"`. 명시적·안전한 기본값.
3. **함수형 노드 vs ReAct 에이전트 구분**: `function_node_ids`로 래핑 우회를 명시 관리(취약한 isinstance 휴리스틱 회피).
4. **관측성의 옵트인 설계**: `_wrap_step`은 tracker/callback/run_id가 모두 있을 때만 활성 → 테스트/내부 호출은 무비용.
5. **graceful degradation 일관**: auth_ctx 없음·엑셀 워크플로우 미주입·도구 실패 등에서 그래프를 멈추지 않고 폴백.
6. **중첩 안전장치**: depth 상한 + 순환 참조 차단으로 sub_agent 재귀를 방어.
7. **확장 지점 명시**: chart_router → (현재는 quality_gate 직결) 후속 차트 빌더 노드를 conditional edge로 끼울 자리를 주석으로 표시.

---

## 부록 A. 주요 함수/메서드 인덱스

| 위치(행) | 이름 | 역할 |
|----------|------|------|
| 53 | `_is_search_result` | search 노드가 만든 검색결과 AIMessage 식별 |
| 89 | `compile` | 메인 컴파일 진입점 |
| 346 | `_compile_sub_agent` | sub_agent 재귀 컴파일 |
| 401 | `_resolve_category` | 워커 카테고리 결정(폴백 체인) |
| 411 | `_create_answer_node` | 검색결과 종합 답변 노드 |
| 469 | `_create_search_node` | 도구 직접 실행 검색 노드 |
| 503 | `_create_analysis_node` | 분석 노드(엑셀/문맥 분기) |
| 551 | `_latest_user_question` | 최근 user 메시지 추출 |
| 563 | `_run_excel_analysis` | ExcelAnalysisWorkflow 래핑 호출 |
| 592 | `_analyze_context` | 검색결과/문맥 기반 LLM 분석 |
| 618 | `_wrap_worker` | react agent → LangGraph 노드 어댑터 |
| 639 | `_wrap_sub_agent` | 하위 그래프 → 단일 노드 어댑터 |

## 부록 B. 관련 파일

| 파일 | 관계 |
|------|------|
| `supervisor_nodes.py` | supervisor/quality_gate 노드 + 라우팅 함수(`route_to_worker`, `route_after_quality`) |
| `supervisor_state.py` | `SupervisorState` TypedDict 정의 |
| `supervisor_hooks.py` | `DefaultHooks`, `AttachmentRoutingHooks` (force/skip 워커 훅) |
| `src/domain/agent_builder/policies.py` | `NestingDepthPolicy`, `CircularReferencePolicy`, `QualityGatePolicy` |
| `src/domain/agent_builder/schemas.py` | `WorkflowDefinition`, `WorkerDefinition`, `SupervisorConfig` |
| `src/application/visualization/chart_router.py` | `create_chart_router_node` (analysis 후 시각화 판단) |
| `src/application/agent_run/step_tracking.py` | `track_step` 관측성 컨텍스트 매니저 |
