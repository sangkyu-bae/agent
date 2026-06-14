# SUPERVISOR-ATTACHMENT-ROUTING: 엑셀 첨부 질의가 데이터분석 노드를 안 타고 supervisor가 "권한 없음"으로 직접 거부하는 문제

> 상태: Plan
> 연관 Task: SUP-ATTACH-001
> 작성일: 2026-06-07
> 우선순위: Critical
> 대상 에이전트: `0605a131-06e4-4bb6-9df3-488e2f707ac9` (agent_tool.tool_id = `data_analysis` 보유)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `data_analysis` 워커를 가진 에이전트에 **엑셀을 첨부**하고 "내 남은 휴가일수 알려주고 전체 사용자 휴가정보 그래프로 그려줘"라고 물으면, 데이터분석 노드(`analysis_node`)에 **진입조차 못 하고** supervisor가 곧바로 `FINISH` + "죄송합니다. 현재 시스템에서는 ... 권한이 없습니다"로 거부한다. |
| **Solution** | supervisor 의사결정 단계가 `state["attachments"]`(엑셀 존재)를 **전혀 모른다**는 것이 핵심. ① supervisor decision prompt에 첨부 요약을 주입해 "엑셀이 첨부됐다"는 사실을 LLM이 인지하게 하고, ② 엑셀 첨부 + `analysis` 워커 존재 시 `force_worker` 훅으로 **데이터분석 노드를 결정적(deterministic)으로 라우팅**, ③ "처리 가능한 워커가 있으면 거부하지 말고 라우팅하라"는 지시를 decision prompt에 명시. |
| **Function UX Effect** | 엑셀 첨부 분석 질의가 거부되지 않고 `analysis_node` → `ExcelAnalysisWorkflow`로 정상 진입. "남은 휴가일수" 같은 데이터 기반 질문에 실제 첨부 데이터로 답변. |
| **Core Value** | 플랫폼의 **첨부 기반 데이터 분석** 기능이 비로소 end-to-end 동작. supervisor가 가진 능력을 스스로 거부하던 치명적 신뢰 손상("도구가 있는데 권한 없다고 함") 제거. |

---

## 1. 문제 정의 (Problem Statement)

### 재현 시나리오
1. 에이전트 `0605a131-06e4-4bb6-9df3-488e2f707ac9` — `agent_tool` 테이블에 `tool_id = data_analysis` 1건 보유 → 컴파일 시 `analysis` 카테고리 워커 1개를 가진 supervisor 그래프가 됨.
2. WS `/ws/agent/{run_id}` subscribe에 **엑셀 file_id를 attachments로 첨부**.
3. 질의: `"엑셀 올리고 현재 나의 남은 휴가일수를 알려주고 전체 사용자 휴가정보 그래프로 그려줄 수 있니?"`

### 관측된 증상
```
죄송합니다. 현재 시스템에서는 사용자의 남은 휴가일수나 전체 사용자 휴가정보를
그래프로 제공할 수 있는 권한이 없습니다. 인사팀이나 관련 부서에 문의하시면
정확한 정보를 얻으실 수 있습니다.
```
- **데이터분석 노드(`analysis_node`)에 한 번도 진입하지 않음** (사용자 직접 확인).
- 즉, 거부 응답은 `analysis_node`의 컨텍스트 분기가 아니라 **supervisor 노드의 `FINISH` + `answer` 경로**에서 나온 것.

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. [Critical] supervisor 의사결정이 첨부(엑셀)를 전혀 인지하지 못함

**파일**: `src/application/agent_builder/supervisor_nodes.py:74-145`

`supervisor_node`가 LLM에게 만들어 주는 의사결정 입력은 다음 3가지뿐:

```python
decision_prompt = (
    f"{supervisor_prompt}\n\n"            # = agent.system_prompt (schemas.py:105)
    f"사용 가능한 워커:\n{worker_descriptions}\n\n"   # 워커 description 나열
    f"...FINISH 시 answer에 직접 답변을 작성하세요..."
)
messages = state["messages"] + [{"role": "system", "content": decision_prompt}]
decision = await llm_with_structure.ainvoke(messages)   # SupervisorDecision(next, reasoning, answer)
```

여기 어디에도 **`state["attachments"]`가 들어가지 않는다.** 엑셀이 첨부됐다는 사실 자체가 LLM에 노출되지 않으므로, LLM 입장에서는:

- 사용자 질문 = "내 남은 휴가일수 + 전체 사용자 휴가 그래프" (텍스트만 존재)
- 참조할 데이터 = **보이지 않음**
- → 합리적 추론: "나는 HR/휴가 데이터에 접근 권한이 없다" → `next="FINISH"` + `answer="...권한이 없습니다..."`

즉, **데이터를 들고 있으면서도 그 사실을 모른 채 거부**하는 구조적 결함이다.

대조적으로 `analysis_node`는 `state["attachments"]`를 읽어 엑셀을 감지하고 `ExcelAnalysisWorkflow`로 분기한다(`workflow_compiler.py:503-539`). **노드는 첨부를 보는데, 그 노드로 보낼지 결정하는 supervisor는 첨부를 못 본다** — 정보 비대칭이 핵심.

### 2-2. [Critical] `FINISH` + `answer` 단락(short-circuit)으로 워커 호출 자체가 스킵됨

**파일**: `src/application/agent_builder/supervisor_nodes.py:123-133`

```python
if next_worker == "FINISH":
    next_worker = "__end__"
    if decision.answer:
        return {
            "next_worker": "__end__",
            "messages": [AIMessage(content=decision.answer)],   # ← 거부 문장이 그대로 최종 답변
            ...
        }
```

supervisor가 `FINISH`를 고르면 `__end__`로 직행하여 `route_to_worker`가 `END`로 보낸다(`workflow_compiler.py:302-303`). `analysis_node`는 등록은 돼 있으나 **edge가 한 번도 트리거되지 않는다** → "노드 자체를 안 탄다"는 증상과 정확히 일치.

### 2-3. [Contributing] 첨부에 대한 결정적 라우팅 훅이 없음

**파일**: `src/application/agent_builder/supervisor_hooks.py:12-17`

```python
class DefaultHooks:
    def force_worker(self, state): return None   # 항상 None
    def skip_workers(self, state): return []
```

`force_worker`는 LLM 판단을 우회해 워커를 강제 지정할 수 있는 확장 지점인데, 현재 구현이 항상 `None`이라 **"엑셀 첨부 시 무조건 analysis 워커로"** 같은 결정적 규칙이 없다. LLM의 확률적 판단(거부)에 100% 의존하는 상태.

### 2-4. [Contributing] decision prompt에 "거부 억제 / 라우팅 우선" 지시 부재

현재 prompt는 `워커 호출 없이 직접 답변할 수 있으면 FINISH + answer`를 **명시적으로 허용**한다(supervisor_nodes.py:101-102). "처리 가능한 워커가 존재하면 먼저 라우팅하고, 함부로 거부하지 말라"는 가드가 없어, LLM이 보수적으로 거부하는 쪽으로 쉽게 빠진다. (system_prompt = `agent.system_prompt`는 자동 생성/사용자 작성이라 라우팅 규율을 보장하지 못함 — schemas.py:105.)

### 2-5. [범위 일부 / 알려진 한계] "그래프로 그려줘"의 차트 렌더링

질문의 두 번째 요구("전체 사용자 휴가정보 그래프")는 차트 렌더링을 요구한다. 현재 supervisor 경로의 `chart_router`는 `viz_decision`만 기록하고 실제 차트를 만들지 않는다(`workflow_compiler.py:312-317` 주석: "후속 차트 처리 노드 도입 시 conditional edge로 교체"). 또한 차트 렌더링은 **General Chat 경로에만 연결**돼 있다(프로젝트 메모리 `chart-rendering-general-chat-only`). → 본 plan은 **"분석 노드 진입 + 텍스트 분석 답변 정상화"까지를 1차 목표**로 하고, supervisor 경로 차트 렌더링은 후속(§8)으로 분리한다.

### 인과 요약
```
엑셀 첨부 O  ─┐
              ├─ supervisor LLM은 첨부를 못 봄 (2-1)
질문은 데이터 ┘        │
의존적             → "데이터 없음 → 권한 없음" 추론
                       │
                  next=FINISH + answer(거부)  (2-2)
                       │
                  __end__ 직행 → analysis_node edge 미트리거
                       │
              "데이터분석 노드 자체를 안 탄다" + 거부 응답
```

---

## 3. 수정 범위 (Scope)

| # | 수정 위치 | 내용 | 우선순위 |
|---|-----------|------|----------|
| 1 | `supervisor_nodes.py::create_supervisor_node` | decision_prompt에 **첨부 요약 블록** 주입 (엑셀 파일명/타입 등). 첨부 있으면 "첨부 데이터를 분석할 수 있는 워커가 있으면 거부하지 말고 라우팅" 지시 추가 | Critical |
| 2 | `supervisor_hooks.py` | `AttachmentRoutingHooks`(신규) — 엑셀 첨부 존재 + `analysis` 워커 존재 + 아직 호출 안 함이면 `force_worker`로 해당 worker_id 반환 | Critical |
| 3 | `workflow_compiler.py::compile` | analysis 워커 id를 훅이 알 수 있도록 전달(또는 hooks 생성 시 주입). 첨부 라우팅 훅을 기본 훅으로 연결 | High |
| 4 | `supervisor_nodes.py` (force 경로) | 강제 라우팅이 1회만 일어나고 무한 루프/중복 호출 안 되도록 `last_worker_id`/`retry_counts` 가드 | High |
| 5 | `tests/application/agent_builder/` | supervisor 첨부 인지 + force_worker 라우팅 단위/회귀 테스트 | High |

**범위 외 (별도 처리 — §8)**:
- supervisor 경로 실제 차트 렌더링(`chart_router` → chart_builder)
- "내 남은 휴가일수" 계산을 위한 사번/유저 매핑 등 도메인 데이터 결합 로직
- 첨부 타입 확장(CSV, 이미지 등)

---

## 4. 수정 방향 (Solution Design)

### 4-1. supervisor decision prompt에 첨부 요약 주입

`create_supervisor_node` 내부 `supervisor_node`에서 `state["attachments"]`를 읽어 요약 블록을 만든다.

```python
async def supervisor_node(state: SupervisorState) -> dict:
    ...
    forced = hooks.force_worker(state)
    if forced:
        return {"next_worker": forced, "forced_worker": forced,
                "iteration_count": state["iteration_count"] + 1}

    skipped = hooks.skip_workers(state)

    # NEW: 첨부 인지 블록
    attachments = state.get("attachments", []) or []
    if attachments:
        kinds = ", ".join(
            f'{a.get("type","?")}({a.get("file_name") or a.get("file_path","")})'
            for a in attachments
        )
        attachment_block = (
            f"\n\n[첨부된 데이터]\n사용자가 다음 파일을 첨부했습니다: {kinds}.\n"
            f"이 데이터를 분석할 수 있는 워커가 사용 가능 목록에 있으면, "
            f"권한이 없다고 거부하지 말고 반드시 해당 워커로 라우팅하세요."
        )
    else:
        attachment_block = ""

    decision_prompt = (
        f"{supervisor_prompt}\n\n"
        f"사용 가능한 워커:\n{worker_descriptions}"
        f"{attachment_block}\n\n"
        f"다음 중 선택하세요:\n"
        f"- 워커 호출이 필요하면 해당 worker_id를 선택\n"
        f"- 처리 가능한 워커가 없을 때만 'FINISH' + answer로 직접 답변\n"
        f"- 모든 작업이 완료되었으면 'FINISH'\n"
        f"스킵된 워커(사용 불가): {skipped}"
    )
    ...
```

**핵심**: "데이터가 보인다 + 능력 있는 워커가 있다"는 사실을 LLM이 인지 → 거부 추론이 끊긴다.

### 4-2. 결정적 첨부 라우팅 훅 (`force_worker`)

LLM 판단에만 맡기지 않고, 엑셀 첨부가 있으면 **결정적으로** analysis 워커로 보낸다.

```python
# supervisor_hooks.py
class AttachmentRoutingHooks:
    """엑셀 등 첨부가 있으면 첫 턴에 분석 워커로 강제 라우팅."""

    def __init__(self, analysis_worker_ids: list[str]) -> None:
        self._analysis_worker_ids = analysis_worker_ids

    def force_worker(self, state: SupervisorState) -> str | None:
        if not self._analysis_worker_ids:
            return None
        attachments = state.get("attachments", []) or []
        has_excel = any(a.get("type") == "excel" for a in attachments)
        if not has_excel:
            return None
        target = self._analysis_worker_ids[0]
        # 가드: 이미 분석 워커가 한 번 실행됐으면 다시 강제하지 않음 (무한 루프 방지)
        if state.get("last_worker_id") == target:
            return None
        return target

    def skip_workers(self, state: SupervisorState) -> list[str]:
        return []
```

`force_worker`가 값을 반환하면 supervisor는 LLM 호출 없이 즉시 그 워커로 라우팅한다(supervisor_nodes.py:86-92). → 엑셀 첨부 질의는 **무조건 analysis_node 진입 보장**.

### 4-3. 컴파일러에서 훅 연결

`WorkflowCompiler.compile`은 이미 `analysis_worker_ids` 집합을 만든다(`workflow_compiler.py:136, 166`). 이를 활용해 supervisor 생성 직전 훅을 구성한다.

```python
# workflow_compiler.py compile() 내부, supervisor_fn 생성 직전
effective_hooks = self._hooks
if analysis_worker_ids and isinstance(self._hooks, DefaultHooks):
    effective_hooks = AttachmentRoutingHooks(sorted(analysis_worker_ids))

supervisor_fn = create_supervisor_node(
    llm=llm, workers=workers_for_supervisor,
    supervisor_prompt=effective_supervisor_prompt,
    hooks=effective_hooks, logger=self._logger,
)
```

> 주의: 외부에서 명시적 hooks를 주입한 경우(테스트 등)는 존중하고, 기본(`DefaultHooks`)일 때만 첨부 훅으로 대체한다. (CLAUDE.md §4 "아키텍처 변경 금지" 준수 — 기존 훅 프로토콜/시그니처 그대로 사용.)

### 4-4. force 라우팅 후 흐름 가드

- analysis 워커 직후 edge: `analysis_node → chart_router → quality_gate → supervisor`(workflow_compiler.py:306-317, 322-325).
- 두 번째 supervisor 진입 시 `force_worker`는 `last_worker_id == target` 가드로 `None` 반환 → 이번엔 §4-1 프롬프트(첨부 인지)로 LLM이 정상 판단(보통 결과 종합 후 `FINISH`).
- 무한 루프는 기존 `max_iterations`/`retry_counts`로 2중 방어.

---

## 5. 테스트 계획 (TDD)

> CLAUDE.md: 테스트 먼저(RED) → 구현(GREEN) → 리팩토링. Windows 이벤트루프 flakiness 있으므로 해당 테스트 파일 **격리 실행**으로 검증(메모리 `backend-test-eventloop-flakiness`).

### 5-1. supervisor가 첨부를 decision prompt에 노출하는지 (단위)
```python
async def test_supervisor_includes_attachment_block_when_excel_present():
    fake_llm = FakeStructuredLLM(next="data_analysis", reasoning="분석 필요")
    node = create_supervisor_node(fake_llm, workers=[analysis_worker], 
                                  supervisor_prompt="P", hooks=DefaultHooks(), logger=NoopLogger())
    state = build_initial_state(
        messages=[{"role": "user", "content": "남은 휴가일수 알려줘"}],
        config=SupervisorConfig(),
        available_workers=["data_analysis"],
        attachments=[{"type": "excel", "file_path": "/tmp/x.xlsx"}],
    )
    await node(state)
    sent = fake_llm.last_invocation_messages
    sys_contents = " ".join(m["content"] for m in sent if m["role"] == "system")
    assert "[첨부된 데이터]" in sys_contents
    assert "거부하지 말고" in sys_contents
```

### 5-2. 엑셀 첨부 시 force_worker가 analysis 워커로 라우팅 (단위)
```python
def test_attachment_hook_forces_analysis_worker_on_excel():
    hooks = AttachmentRoutingHooks(["data_analysis"])
    state = {"attachments": [{"type": "excel"}], "last_worker_id": ""}
    assert hooks.force_worker(state) == "data_analysis"

def test_attachment_hook_no_force_after_analysis_ran():
    hooks = AttachmentRoutingHooks(["data_analysis"])
    state = {"attachments": [{"type": "excel"}], "last_worker_id": "data_analysis"}
    assert hooks.force_worker(state) is None

def test_attachment_hook_no_force_without_excel():
    hooks = AttachmentRoutingHooks(["data_analysis"])
    assert hooks.force_worker({"attachments": [], "last_worker_id": ""}) is None
```

### 5-3. supervisor가 force 시 LLM 호출 없이 즉시 라우팅 (회귀)
```python
async def test_supervisor_force_skips_llm_and_routes():
    fake_llm = FakeStructuredLLM(next="FINISH", answer="권한이 없습니다")  # LLM은 거부하려 함
    node = create_supervisor_node(fake_llm, workers=[analysis_worker], supervisor_prompt="P",
                                  hooks=AttachmentRoutingHooks(["data_analysis"]), logger=NoopLogger())
    state = build_initial_state(messages=[{"role":"user","content":"분석"}],
        config=SupervisorConfig(), available_workers=["data_analysis"],
        attachments=[{"type":"excel","file_path":"/tmp/x.xlsx"}])
    result = await node(state)
    assert result["next_worker"] == "data_analysis"   # 거부가 아니라 라우팅
    assert fake_llm.call_count == 0                    # LLM 우회 확인
```

### 5-4. 첨부 없을 때 기존 동작 보존 (회귀)
```python
async def test_supervisor_no_attachment_behaves_as_before():
    # 첨부 없음 → attachment_block 미삽입, 기존 FINISH/라우팅 로직 그대로
    ...
```

### 5-5. 컴파일러 통합: data_analysis 워커 + 엑셀 첨부 → analysis_node 진입 (통합)
```python
async def test_compiled_graph_enters_analysis_node_with_excel():
    # ExcelAnalysisWorkflow getter를 가짜로 주입, attachments에 excel
    # graph.ainvoke 후 analysis_node가 실행됐는지(last_worker_id 등)로 검증
    ...
```

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| `create_supervisor_node` 시그니처 | **변경 없음** | 내부 prompt 조립만 변경 |
| `DefaultHooks` | **보존** | 신규 `AttachmentRoutingHooks` 추가, 기본 동작 유지 |
| 외부 주입 hooks | **존중** | `isinstance(DefaultHooks)`일 때만 대체 |
| 첨부 없는 일반 질의 | **불변** | attachment_block 빈 문자열, force_worker None |
| 토큰 사용량 | 미미한 증가 | 첨부 있을 때만 짧은 블록 추가 |
| 무한 루프 | 낮음 | `last_worker_id` 가드 + `max_iterations` 2중 방어 |
| 차트 요구("그래프") | **미해결** | §8 후속. 1차는 텍스트 분석 답변까지 |
| sub_agent 경로 | 영향 적음 | 동일 compile 경유, analysis 워커 보유 시 동일 이점 |

---

## 7. 구현 순서

1. `tests/application/agent_builder/test_supervisor_attachment.py` 신규 — 5-1~5-4 작성 (RED).
2. `supervisor_hooks.py`에 `AttachmentRoutingHooks` 구현.
3. `supervisor_nodes.py::supervisor_node`에 첨부 인지 블록 + prompt 문구 수정.
4. `workflow_compiler.py::compile`에서 analysis 워커 존재 시 훅 연결.
5. 단위 테스트 GREEN (격리 실행).
6. 5-5 통합 테스트 추가 + GREEN.
7. 로컬 dev 서버에서 대상 에이전트(`0605a131…`)로 엑셀 첨부 수동 재현 → analysis_node 진입 + 분석 답변 확인.
8. `/pdca analyze supervisor-attachment-routing` Gap 분석 → Report.

---

## 8. 미해결 / 후속 이슈

- **supervisor 경로 차트 렌더링**: `chart_router`가 `viz_decision`만 기록. 실제 차트 생성 노드(chart_builder) + conditional edge 도입 필요. 현재 차트는 General Chat 경로 전용(메모리 `chart-rendering-general-chat-only`) → supervisor/Excel 경로 확장은 별도 plan.
- **"내 남은 휴가일수" 도메인 결합**: 엑셀에 본인 식별(사번/이메일) 매핑이 있어야 "나의" 값을 산출. `auth_ctx`(사용자 컨텍스트)와 엑셀 행 매칭 로직은 별도 설계 필요.
- **첨부 타입 확장**: 현재 `type == "excel"`만 강제 라우팅. CSV/이미지 등은 추후.
- **첨부 인지 휴리스틱**: file_name 부재 시 file_path 노출 — 임시경로가 프롬프트에 노출되지 않도록 표시용 라벨 정제 검토.
