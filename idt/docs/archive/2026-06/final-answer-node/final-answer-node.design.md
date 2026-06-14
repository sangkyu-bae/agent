# Design: final-answer-node

> Created: 2026-06-10
> Phase: Design
> Plan: `docs/01-plan/features/final-answer-node.plan.md`
> Scope: `idt/` 백엔드 — Supervisor 그래프에 워커 결과(웹서치·분석·차트)를 종합하는 필수 최종 답변 노드 `final_answer` 도입

---

## 1. 설계 결정 요약

### 1-1. Plan에서 확정된 결정 (D1~D4)

| # | 결정 |
|---|------|
| D1 | 워커 실행 시에만 final_answer 경유 (단순 대화는 즉시 END) |
| D2 | answer_agent를 final_answer로 통합·제거 (가상 워커 방식 폐기) |
| D3 | quality_gate 미경유, `final_answer → END` 직행 |
| D4 | depth=0(최상위 그래프)만 적용, sub_agent 미적용 |

### 1-2. Plan Open Questions → Design 확정 (DQ1~DQ5)

| # | 질문 | 결정 | 근거 |
|---|------|------|------|
| DQ1 | supervisor FINISH draft answer 처리 | **코드 가드로 폐기 + 프롬프트 안내**. `last_worker_id != ""`이면 FINISH 시 `decision.answer` 메시지를 messages에 추가하지 않는다. decision_prompt에 "워커 실행 후에는 answer 작성 불필요" 문구 추가 | answer 메시지가 남으면 final_answer의 대화 본체에 '이미 답변한 assistant 메시지'로 보여 LLM을 혼란시킴. 프롬프트 지시만으로는 비결정적 — 코드 가드가 결정적 |
| DQ2 | 강제 종료(max_iterations/token_limit) 시 실행 여부 | **실행한다**. 워커가 실행됐다면 부분 결과로라도 정제 답변 생성 | token_limit은 `len//4` 추정치(과금 한도 아님). final_answer는 END 직행이라 루프 위험 0. 사용자가 빈손으로 끝나는 것보다 부분 종합이 낫다 |
| DQ3 | 노드명 | **`final_answer`** (신규 명칭) | 역할이 "검색 종합"에서 "전체 결과 종합"으로 바뀌므로 의미 정확성 우선. 프론트는 kind 기반 필터라 기능 영향 없음(테스트 fixture만 정리) |
| DQ4 | 워커 산출물 수집 규칙 | **`name` 속성 기반 일반화**: `name`이 비어있지 않은 AIMessage = 워커 산출물. 그중 `_is_search_result` 매칭은 [검색 결과] 블록, 나머지는 [워커 작업 결과] 블록. 대화 본체에서는 워커 산출물 전부 제외(기존: 검색결과만 제외 → 일반화) | search/analysis/sub_agent 노드 모두 `AIMessage(name=worker_id)` 규약을 이미 따름. 문자열("검색결과") 매칭은 블록 분류 라벨로만 유지 |
| DQ5 | 차트 메타 주입 형식 | **개수 + 차트별 type/title만** 프롬프트에 주입. JSON 본문 인라인 금지 지시 포함 | 답변-차트 정합에는 "무슨 차트가 몇 개 있는지"면 충분. 축/데이터까지 주입하면 토큰 낭비 + JSON 모방 출력 유도 위험 |

---

## 2. 아키텍처

### 2-1. 그래프 변경 (As-Is → To-Be)

```
[As-Is]
supervisor ─route_to_worker─▶ {worker..., answer_agent(검색 시), __end__→END}
worker ─▶ (chart_router → chart_builder) → quality_gate ─route_after_quality─▶ supervisor | worker
answer_agent ─▶ END          ← 검색 워커 있을 때만 존재, supervisor LLM이 '선택'해야 실행

[To-Be, depth=0]
supervisor ─route_to_worker_or_final─▶ {worker..., final_answer, __end__→END}
worker ─▶ (chart_router → chart_builder) → quality_gate ─route_after_quality─▶ supervisor | worker
final_answer ─▶ END          ← FINISH && 워커 실행됨 → 라우팅 함수가 구조적으로 강제

[To-Be, depth>0 (sub_agent 내부)]
변경 없음: supervisor ─route_to_worker─▶ {worker..., __end__→END}
```

- `answer_agent` 가상 워커(`WorkerDefinition(tool_id="__virtual__")`), 노드, 엣지, route_map 항목 **전부 제거**.
- `final_answer`는 supervisor의 worker 선택지가 **아니다** — decision prompt의 워커 목록에 노출하지 않고, 라우팅 함수가 `__end__` 시점에 분기한다.

### 2-2. 실행 시나리오별 흐름

| 시나리오 | 흐름 |
|----------|------|
| 단순 대화 (워커 0회) | supervisor FINISH(answer 작성) → END. **기존과 동일, LLM +0회** |
| 검색만 | supervisor → search_node → quality_gate → supervisor FINISH → **final_answer** → END |
| 분석+차트 | supervisor → analysis_node → chart_router → chart_builder → quality_gate → supervisor FINISH → **final_answer** → END |
| 검색+분석+차트 혼합 | 워커 루프 반복 → supervisor FINISH → **final_answer**(전 소스 종합) → END |
| 강제 종료 (max_iterations/token_limit, 워커 실행됨) | supervisor가 `__end__` 강제 → **final_answer**(부분 결과 종합) → END (DQ2) |
| 강제 종료 (워커 미실행) | supervisor가 `__end__` 강제 → END (last_worker_id="") |

---

## 3. 상세 설계

### 3-1. 라우팅 — `supervisor_nodes.py`

신규 라우팅 함수 추가 (기존 `route_to_worker`는 depth>0용으로 유지):

```python
def route_to_worker_or_final(state: SupervisorState) -> str:
    """depth=0 전용: FINISH 시 워커 실행 이력이 있으면 final_answer로 우회."""
    next_worker = state["next_worker"]
    if next_worker == "__end__" and state.get("last_worker_id"):
        return "final_answer"
    return next_worker
```

- 판정 기준 `last_worker_id`: 모든 워커 노드(search/analysis/wrapped react/sub_agent)가 반환 시 자신의 worker_id로 갱신하는 기존 필드. 워커 미실행이면 초기값 `""` 유지 → D1 충족.
- `quality_gate` 경유 후 supervisor로 복귀하는 루프는 변경 없음.

### 3-2. supervisor FINISH answer 가드 — `supervisor_nodes.py` (DQ1)

`create_supervisor_node` 내 FINISH 분기 수정:

```python
if next_worker == "FINISH":
    next_worker = "__end__"
    # final-answer-node DQ1: 워커가 실행된 런은 final_answer가 최종 답변을 생성하므로
    # supervisor의 draft answer를 messages에 추가하지 않는다(이중 답변·본체 오염 방지).
    if decision.answer and not state["last_worker_id"]:
        ... 기존 AIMessage(answer) 추가 로직 ...
```

decision_prompt 문구 조정 (토큰 낭비 감소용 — 가드가 본질, 프롬프트는 보조):

```
- 모든 작업이 완료되었으면 'FINISH'를 선택 (워커를 이미 호출했다면 최종 답변은
  시스템이 워커 결과를 종합해 생성하므로 answer는 비워두세요)
- 어떤 워커로도 처리할 수 없을 때만 'FINISH'를 선택하고 answer 필드에 응답을 작성하세요
```

### 3-3. final_answer 노드 — `workflow_compiler.py`

`_create_answer_node` → `_create_final_answer_node(llm, system_prompt)`로 일반화.

#### 3-3-1. 워커 산출물 분류 (DQ4)

```python
def _is_worker_output(msg) -> bool:
    """워커 노드가 생성한 AIMessage 식별 (name=worker_id 규약)."""
    if isinstance(msg, dict):
        return False
    return bool(getattr(msg, "name", None)) and getattr(msg, "type", "") == "ai"
```

| 분류 | 조건 | 용도 |
|------|------|------|
| 검색 결과 | `_is_worker_output` ∧ `_is_search_result` | `[수집된 검색 결과]` 블록 |
| 작업/분석 결과 | `_is_worker_output` ∧ ¬`_is_search_result` | `[워커 작업 결과]` 블록 (worker_id 라벨 포함) |
| 대화 본체 | ¬`_is_worker_output` | LLM messages로 그대로 전달 (멀티턴 보존, G6) |

- `_is_search_result`는 유지하되 **수집이 아닌 블록 분류**에만 사용 (취약한 문자열 매칭의 영향 축소).
- 기존 "검색결과만 본체에서 제외" 규칙을 "워커 산출물 전부 제외"로 일반화 — 컨텍스트 블록과의 중복 제거 원칙은 동일(FIX-ANSWER-NODE-MULTITURN-CONTEXT 패턴 계승).
- 한계(허용): create_react_agent 워커의 내부 메시지는 name이 없을 수 있어 본체에 남는다. 기존 answer_node도 동일 동작 — 회귀 아님.

#### 3-3-2. 차트 메타 블록 (DQ5)

```python
def _summarize_charts(charts: list[dict]) -> str:
    """state["charts"] → 프롬프트용 메타 요약. 키 부재 시 graceful."""
    lines = []
    for i, c in enumerate(charts, 1):
        chart_type = c.get("type", "unknown")
        title = (
            c.get("options", {}).get("plugins", {}).get("title", {}).get("text", "")
            or "(제목 없음)"
        )
        lines.append(f"{i}. {chart_type} — {title}")
    return "\n".join(lines)
```

프롬프트 주입 (charts 비어있으면 블록 생략):

```
[생성된 차트]
아래 {N}개의 차트가 답변과 함께 화면에 표시됩니다. 차트 JSON·코드블록을 출력하지 말고,
답변에서 차트를 자연스럽게 언급하세요 (예: "아래 차트에서 보듯이 ...").
1. bar — 부서별 매출
2. line — 월별 추이
```

#### 3-3-3. 노드 본체

```python
async def final_answer_node(state: SupervisorState) -> dict:
    worker_outputs = [m for m in state["messages"] if _is_worker_output(m)]
    search_results = [m.content for m in worker_outputs if _is_search_result(m)]
    work_results = [
        f"[{m.name}]\n{m.content}" for m in worker_outputs if not _is_search_result(m)
    ]
    conversation = [m for m in state["messages"] if not _is_worker_output(m)]
    charts = state.get("charts", [])

    # 블록 조립: 검색/작업/차트 — 비어있는 블록은 생략, 전부 비면 "(수집된 결과 없음)"
    answer_prompt = (
        f"{system_prompt}\n\n"
        "아래 수집된 결과들을 종합하여 사용자의 가장 최근 질문에 하나의 완결된 답변을 작성하세요.\n"
        "수집된 결과에 없는 내용은 추측하지 마세요. 이전 대화 맥락도 참고하세요.\n\n"
        f"{블록들}"
    )
    response = await llm.ainvoke(
        [{"role": "system", "content": answer_prompt}, *conversation]
    )
    token_delta = len(coerce 가능한 content) // 4
    return {
        "messages": [response],
        "last_worker_id": "final_answer",
        "token_usage": state["token_usage"] + token_delta,
    }
```

- **charts 비파괴**: 반환 dict에 `charts` 키를 포함하지 않는다 → state 병합으로 그대로 보존, `run_agent_use_case`의 chart_builder output 캡처(`:582`)도 영향 없음.
- **사후 sanitize 안 함**: `ANALYSIS_OUTPUT_SANITIZER`는 적용하지 않는다 — 사용자가 코드 답변을 요청한 경우 정당한 코드블록까지 제거될 수 있음. 차트 JSON 억제는 프롬프트 지시(§3-3-2)로 처리.
- 검색결과 없음 fallback("(검색 결과 없음)")은 "(수집된 결과 없음)"으로 일반화.

### 3-4. compile() 재배선 — `workflow_compiler.py`

```python
# 제거: has_search_workers, answer_agent 가상 WorkerDefinition(:213~222),
#       answer_agent add_node(:302~310), route_map["answer_agent"](:344~345),
#       add_edge("answer_agent", END)(:369~370)

# 추가 (depth == 0 일 때만, D4):
if depth == 0:
    graph.add_node(
        "final_answer",
        _wrap_step(
            "final_answer", NodeType.OTHER,
            self._create_final_answer_node(llm, workflow.supervisor_prompt),
        ),
    )
    route_map["final_answer"] = "final_answer"
    graph.add_conditional_edges("supervisor", route_to_worker_or_final, route_map)
    graph.add_edge("final_answer", END)
else:
    graph.add_conditional_edges("supervisor", route_to_worker, route_map)
```

- `workers_for_supervisor = list(workflow.workers)` — 가상 워커 추가 로직 삭제로 단순화.
- supervisor system prompt에는 final_answer 노출 없음 (§2-1).
- user context prepend(`effective_supervisor_prompt`)는 final_answer에도 동일 적용 여부: **워크플로 원본 `workflow.supervisor_prompt`가 아닌 `effective_supervisor_prompt`를 전달** — answer 생성 시에도 사용자 컨텍스트(부서·이름) 반영 (기존 answer_node는 원본을 받았으나, agent-user-context 설계 의도에 맞게 정정).

### 3-5. 관측성/스트리밍 — `run_agent_use_case.py`

| 위치 | 변경 |
|------|------|
| `_node_type_for`(:118) | `"answer_agent"` → `"final_answer"` (NodeType.OTHER 유지) |
| `_collect_node_names`(:133) | `{"supervisor", "quality_gate", "final_answer"}` |
| TOKEN 스트리밍 | 변경 없음 — `_map_chat_stream`은 노드 무관하게 `coerce_message_text`로 정규화 후 발행(:659~675). final_answer의 LLM 토큰은 `langgraph_node="final_answer"` 메타로 자동 스트림 |
| ANSWER_COMPLETED | 변경 없음 — `messages[-1]`이 final_answer의 응답이 됨(:819~823). charts 캡처(:582)도 비파괴 보장으로 유지 |
| `_wrap_step` | compile에서 `NodeType.OTHER`로 래핑 → ai_run_step 영속화 자동 |

### 3-6. 프론트엔드 (idt_front)

- **기능 변경 없음**: step 필터는 `kind` 기반(`agentStepToToolEvent.ts:17`), TOKEN 누적은 노드 무관(`useAgentRunStream.ts:132~137`).
- 정리(선택): `useAgentRunStream.test.ts` fixture의 `answer_agent` → `final_answer`, `agentStepToToolEvent.ts:7` 주석 갱신.
- API 스키마/엔드포인트 변경 없음 → `/api-contract-sync` 불필요 (확정).

---

## 4. 영향 파일 목록

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `src/application/agent_builder/supervisor_nodes.py` | 수정 | `route_to_worker_or_final` 추가, FINISH answer 가드(DQ1), decision_prompt 문구 |
| `src/application/agent_builder/workflow_compiler.py` | 수정 | `_create_final_answer_node`(일반화), `_is_worker_output`/`_summarize_charts` 헬퍼, compile 재배선(depth 게이트), answer_agent 제거 |
| `src/application/agent_builder/run_agent_use_case.py` | 수정 | 노드명 교체 2곳(:118, :133) |
| `tests/application/agent_builder/test_answer_node.py` | 개명·갱신 | → `test_final_answer_node.py` (TC 이관 + 신규) |
| `tests/application/agent_builder/test_workflow_compiler.py` | 갱신 | answer_agent 단언 → final_answer 라우팅/등록 단언 |
| `tests/application/agent_builder/test_run_agent_use_case_stream.py` | 갱신 | 노드명 fixture |
| `tests/api/test_ws_agent_router.py` 외 fixture 4곳 | 갱신 | 노드명 fixture (grep: `answer_agent`) |
| `idt_front/src/hooks/useAgentRunStream.test.ts` | 선택 | fixture 노드명 정리 |

---

## 5. 테스트 설계 (TDD)

### 5-1. 라우팅 (`test_supervisor_nodes.py` 또는 신규)

| TC | 시나리오 | 기대 |
|----|----------|------|
| TC-R01 | `next_worker="__end__"`, `last_worker_id=""` | `"__end__"` (단순 대화 즉시 종료) |
| TC-R02 | `next_worker="__end__"`, `last_worker_id="w1"` | `"final_answer"` |
| TC-R03 | `next_worker="w1"` | `"w1"` (워커 라우팅 불변) |

### 5-2. supervisor 가드 (DQ1)

| TC | 시나리오 | 기대 |
|----|----------|------|
| TC-S01 | FINISH + answer 작성 + `last_worker_id="w1"` | messages에 answer AIMessage **미추가**, `next_worker="__end__"` |
| TC-S02 | FINISH + answer 작성 + `last_worker_id=""` | answer AIMessage 추가 (기존 동작 보존) |

### 5-3. final_answer 노드 (`test_final_answer_node.py`)

| TC | 시나리오 | 기대 |
|----|----------|------|
| TC-F01 | 검색결과 2건 + 분석결과 1건 혼합 state | system prompt에 [수집된 검색 결과]·[워커 작업 결과] 블록 모두 포함, 분석결과에 worker_id 라벨 |
| TC-F02 | `charts` 2건 존재 | 반환 dict에 `charts` 키 없음(비파괴), 프롬프트에 차트 개수·type·title 포함 + JSON 출력 금지 지시 |
| TC-F03 | `charts` 빈 리스트 | 차트 블록 생략 |
| TC-F04 | 멀티턴 (기존 TC-A06~A08 이관) | 전체 대화 맥락 전달, 첫 user만 전달 금지, 워커 산출물 본체 제외 |
| TC-F05 | 워커 산출물 0건 (강제 라우팅 등 edge) | "(수집된 결과 없음)" fallback, 정상 응답 |
| TC-F06 | 정상 실행 | `last_worker_id == "final_answer"`, token_usage 증가 |
| TC-F07 | user context 포함 컴파일 | effective_supervisor_prompt(사용자 블록 포함)가 answer_prompt에 반영 |

### 5-4. compile 통합 (`test_workflow_compiler.py`)

| TC | 시나리오 | 기대 |
|----|----------|------|
| TC-C01 | depth=0 컴파일 | `final_answer` 노드 존재, `answer_agent` 부재, 가상 워커 미생성 |
| TC-C02 | sub_agent 포함 컴파일 | 서브 그래프(depth=1)에 `final_answer` 미등록 |
| TC-C03 | 그래프 e2e (mock LLM): 검색 워커 실행 → FINISH | final_answer 경유 후 END, 최종 메시지=final_answer 응답 |
| TC-C04 | 그래프 e2e: 워커 미실행 FINISH(answer 직접) | final_answer 미경유, supervisor answer가 최종 메시지 |
| TC-C05 | max_iterations 강제 종료 (워커 실행됨) | final_answer 경유 (DQ2) |

### 5-5. 스트리밍/관측성

| TC | 시나리오 | 기대 |
|----|----------|------|
| TC-O01 | `_collect_node_names` | `final_answer` 포함, `answer_agent` 미포함 |
| TC-O02 | stream e2e (기존 fixture 갱신) | final_answer NODE_STARTED/COMPLETED 이벤트, TOKEN node_name="final_answer" |

---

## 6. 구현 순서

1. **(Red→Green)** §3-1 `route_to_worker_or_final` + §3-2 FINISH 가드·프롬프트 — TC-R01~03, TC-S01~02
2. **(Red→Green)** §3-3 `_create_final_answer_node` + 헬퍼 — TC-F01~F07 (test_answer_node.py 이관 포함)
3. **(Red→Green)** §3-4 compile 재배선 + answer_agent 제거 — TC-C01~C05
4. **(Red→Green)** §3-5 run_agent_use_case 노드명 — TC-O01~O02
5. **(갱신)** 잔여 fixture: test_ws_agent_router / test_ws_adapter / test_sse_formatter / test_llm_call_repository / test_agent_run_router
6. **(verify)** `verify-architecture`, `verify-logging`, `verify-tdd`, pytest 격리 실행 (Windows 이벤트 루프 flakiness 회피)

---

## 7. 리스크 대응 (Plan §6 매핑)

| Plan 리스크 | Design 대응 |
|-------------|------------|
| R1 이중 답변 | §3-2 코드 가드 (TC-S01) |
| R2 강제 종료 | DQ2 확정 — 실행 (TC-C05) |
| R3 멀티턴 회귀 | §3-3-1 본체 분리 규칙 계승 + TC-F04 이관 |
| R4 WS 스트리밍 | §3-5 — `coerce_message_text` 경로 무변경 확인 (TC-O02) |
| R5 산출물 식별 | DQ4 name 기반 일반화. react agent 내부 메시지 한계는 기존 동작과 동일(비회귀) |
| R6 의존 테스트 | §4 fixture 8곳 식별 완료, §6-5에서 일괄 갱신 |
| R7 flakiness | §6-6 격리 실행 |

---

## 8. 다음 단계

```
/pdca do final-answer-node
```
