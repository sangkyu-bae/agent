# SUPERVISOR-ATTACHMENT-ROUTING: 설계 문서

> 상태: Design
> Plan 참조: docs/01-plan/features/supervisor-attachment-routing.plan.md
> 연관 Task: SUP-ATTACH-001 (blockedBy: [Plan] supervisor-attachment-routing)
> 작성일: 2026-06-07
> 우선순위: Critical

---

## 1. 설계 개요

supervisor가 `state["attachments"]`를 인지하지 못해 엑셀 분석 질의를 거부하는 문제를, **레이어/아키텍처 변경 없이** 3개 지점의 최소 수정으로 해결한다. (CLAUDE.md §4 아키텍처·레이어 이동 금지 준수 — 기존 `SupervisorHooks` 프로토콜·`create_supervisor_node` 시그니처 그대로 사용.)

| # | 변경 | 파일 | 수정 범위 |
|---|------|------|-----------|
| C-1 | supervisor decision prompt에 첨부 인지 블록 주입 + 거부 억제 문구 | `supervisor_nodes.py` | `supervisor_node` 내부 prompt 조립 |
| C-2 | 엑셀 첨부 시 analysis 워커 결정적 강제 라우팅 훅 신설 | `supervisor_hooks.py` | `AttachmentRoutingHooks` 클래스 추가 |
| C-3 | analysis 워커 존재 시 기본 훅을 첨부 훅으로 연결 | `workflow_compiler.py` | `compile()` 내 supervisor 생성 직전 1블록 |

**설계 원칙**: LLM 판단(확률적)과 결정적 훅(deterministic)을 **이중**으로 적용한다. 훅이 1차로 보장하고, 프롬프트가 2차 진입(결과 종합)에서 거부를 막는다.

---

## 2. C-2: `AttachmentRoutingHooks` (신규) — `supervisor_hooks.py`

### 2-1. 현재 코드 (`supervisor_hooks.py:1-17`)

```python
class DefaultHooks:
    def force_worker(self, state: SupervisorState) -> str | None:
        return None
    def skip_workers(self, state: SupervisorState) -> list[str]:
        return []
```

### 2-2. 추가 코드

기존 `DefaultHooks`는 보존하고 아래 클래스를 **추가**한다.

```python
class AttachmentRoutingHooks:
    """엑셀 등 분석 가능한 첨부가 있으면 첫 진입에 analysis 워커로 강제 라우팅.

    supervisor LLM이 첨부를 인지 못해 거부(FINISH)하는 것을 결정적으로 차단한다.
    analysis 워커가 1회 실행된 뒤에는 강제하지 않아(루프 방지) LLM이 결과를
    종합/FINISH 하도록 둔다.
    """

    # 강제 라우팅 대상 첨부 타입 (현재 excel만; 추후 확장)
    _ROUTABLE_TYPES = ("excel",)

    def __init__(self, analysis_worker_ids: list[str]) -> None:
        self._analysis_worker_ids = analysis_worker_ids

    def force_worker(self, state: SupervisorState) -> str | None:
        if not self._analysis_worker_ids:
            return None
        attachments = state.get("attachments", []) or []
        has_routable = any(
            a.get("type") in self._ROUTABLE_TYPES for a in attachments
        )
        if not has_routable:
            return None
        target = self._analysis_worker_ids[0]
        # 가드: 이미 분석 워커가 실행됐으면 재강제 금지 (무한 루프 방지)
        if state.get("last_worker_id") == target:
            return None
        return target

    def skip_workers(self, state: SupervisorState) -> list[str]:
        return []
```

### 2-3. 동작 보장

`supervisor_node`는 이미 `forced = hooks.force_worker(state)`가 truthy면 **LLM 호출 없이 즉시 라우팅**한다(`supervisor_nodes.py:86-92`):

```python
forced = hooks.force_worker(state)
if forced:
    return {"next_worker": forced, "forced_worker": forced,
            "iteration_count": state["iteration_count"] + 1}
```

→ 엑셀 첨부 질의는 1차 supervisor 진입에서 **무조건 analysis 워커로** 간다. C-2만으로도 "노드 미진입" 증상은 해소된다.

---

## 3. C-1: 첨부 인지 블록 — `supervisor_nodes.py`

### 3-1. 현재 코드 (`supervisor_nodes.py:94-109`)

```python
skipped = hooks.skip_workers(state)

decision_prompt = (
    f"{supervisor_prompt}\n\n"
    f"사용 가능한 워커:\n{worker_descriptions}\n\n"
    f"다음 중 선택하세요:\n"
    f"- 워커 호출이 필요하면 해당 worker_id를 선택\n"
    f"- 워커 호출 없이 직접 답변할 수 있으면 'FINISH'를 선택하고 "
    f"answer 필드에 사용자에게 전달할 자연스러운 응답을 작성하세요\n"
    f"- 모든 작업이 완료되었으면 'FINISH'를 선택\n"
    f"스킵된 워커(사용 불가): {skipped}"
)
```

### 3-2. 수정 후

```python
skipped = hooks.skip_workers(state)

# 첨부 인지 블록 — supervisor가 첨부 데이터의 존재를 알게 한다.
attachment_block = _render_attachment_block(state.get("attachments", []))

decision_prompt = (
    f"{supervisor_prompt}\n\n"
    f"사용 가능한 워커:\n{worker_descriptions}"
    f"{attachment_block}\n\n"
    f"다음 중 선택하세요:\n"
    f"- 워커 호출이 필요하면 해당 worker_id를 선택\n"
    f"- 처리 가능한 워커가 사용 가능 목록에 있으면 거부하지 말고 그 워커를 선택\n"
    f"- 어떤 워커로도 처리할 수 없을 때만 'FINISH'를 선택하고 "
    f"answer 필드에 사용자에게 전달할 자연스러운 응답을 작성하세요\n"
    f"- 모든 작업이 완료되었으면 'FINISH'를 선택\n"
    f"스킵된 워커(사용 불가): {skipped}"
)
```

### 3-3. 모듈 레벨 헬퍼 추가 (`supervisor_nodes.py` 상단)

```python
def _render_attachment_block(attachments: list[dict] | None) -> str:
    """첨부 목록 → supervisor decision용 인지 블록 (없으면 빈 문자열)."""
    if not attachments:
        return ""
    labels = []
    for a in attachments:
        kind = a.get("type", "파일")
        # 임시경로 노출 방지: file_name 우선, 없으면 타입만 표기
        name = a.get("file_name")
        labels.append(f"{kind}({name})" if name else kind)
    joined = ", ".join(labels)
    return (
        f"\n\n[첨부된 데이터]\n사용자가 다음을 첨부했습니다: {joined}.\n"
        f"이 데이터를 분석할 수 있는 워커가 사용 가능 목록에 있으면, "
        f"권한이 없다고 거부하지 말고 반드시 그 워커로 라우팅하세요."
    )
```

> **함수 길이 가드(CLAUDE.md §3, 40줄)**: prompt 조립이 길어지므로 인지 블록 생성을 별도 순수 함수로 분리하여 `supervisor_node` 길이를 억제하고 단위 테스트 가능하게 한다.

### 3-4. file_name 가용성

현재 attachment dict는 `{"type", "file_path"|"file_id", "user_id"}` 형태(`run_agent_use_case` 주석·`ws_router._resolve_ws_attachments`). `file_name`이 없을 수 있으므로 헬퍼는 **없으면 타입만** 표기(임시경로 비노출). file_name 보강은 §7 후속.

---

## 4. C-3: 컴파일러 훅 연결 — `workflow_compiler.py`

### 4-1. 현재 코드 (`workflow_compiler.py:203-209`)

```python
supervisor_fn = create_supervisor_node(
    llm=llm,
    workers=workers_for_supervisor,
    supervisor_prompt=effective_supervisor_prompt,
    hooks=self._hooks,
    logger=self._logger,
)
```

이 시점에 `analysis_worker_ids`(set)는 이미 채워져 있다(`workflow_compiler.py:136, 166`).

### 4-2. 수정 후

```python
# 첨부 라우팅: analysis 워커가 있고 외부 주입 훅이 없을(기본) 때만
# AttachmentRoutingHooks로 대체. 명시적 주입 훅은 존중(테스트/확장).
effective_hooks = self._hooks
if analysis_worker_ids and isinstance(self._hooks, DefaultHooks):
    effective_hooks = AttachmentRoutingHooks(sorted(analysis_worker_ids))

supervisor_fn = create_supervisor_node(
    llm=llm,
    workers=workers_for_supervisor,
    supervisor_prompt=effective_supervisor_prompt,
    hooks=effective_hooks,
    logger=self._logger,
)
```

### 4-3. import 추가

```python
from src.application.agent_builder.supervisor_hooks import (
    AttachmentRoutingHooks, DefaultHooks, SupervisorHooks,
)
```

(기존 `from ... import DefaultHooks, SupervisorHooks`에 `AttachmentRoutingHooks` 추가 — `workflow_compiler.py:7`)

### 4-4. 결정적 라우팅 후 흐름 (시퀀스)

```
supervisor (force=data_analysis, last_worker_id="")   ← C-2 훅이 강제
   │  next_worker = data_analysis
   ▼
analysis_node  ← state["attachments"]의 excel 감지 → ExcelAnalysisWorkflow
   │  last_worker_id = data_analysis
   ▼
chart_router (viz_decision 기록만)            ← workflow_compiler.py:312-317
   ▼
quality_gate → supervisor
   │
supervisor (force=None: last_worker_id==target 가드)  ← C-2가 재강제 안 함
   │  이번엔 C-1 프롬프트로 LLM 판단: 결과 종합 후 보통 FINISH
   ▼
__end__
```

무한 루프 2중 방어: ① `last_worker_id == target` 가드, ② 기존 `max_iterations`/`retry_counts`.

---

## 5. 테스트 설계 (TDD)

> Windows 이벤트루프 flakiness 대비 해당 테스트 파일 **격리 실행**으로 검증(메모리 `backend-test-eventloop-flakiness`). 비동기 supervisor_node 테스트는 `pytest.mark.asyncio`.

**신규 파일**: `tests/application/agent_builder/test_supervisor_attachment.py`

### TC-1: `_render_attachment_block` 엑셀 인지 (단위, 동기)
```python
def test_render_attachment_block_with_excel():
    from src.application.agent_builder.supervisor_nodes import _render_attachment_block
    block = _render_attachment_block([{"type": "excel", "file_name": "vac.xlsx"}])
    assert "[첨부된 데이터]" in block
    assert "excel(vac.xlsx)" in block
    assert "거부하지 말고" in block

def test_render_attachment_block_empty_returns_blank():
    from src.application.agent_builder.supervisor_nodes import _render_attachment_block
    assert _render_attachment_block([]) == ""
    assert _render_attachment_block(None) == ""

def test_render_attachment_block_no_filename_hides_path():
    from src.application.agent_builder.supervisor_nodes import _render_attachment_block
    block = _render_attachment_block([{"type": "excel", "file_path": "/tmp/secret.xlsx"}])
    assert "/tmp/secret.xlsx" not in block   # 임시경로 비노출
    assert "excel" in block
```

### TC-2: `AttachmentRoutingHooks.force_worker` (단위, 동기)
```python
def test_hook_forces_analysis_on_excel():
    hooks = AttachmentRoutingHooks(["data_analysis"])
    assert hooks.force_worker(
        {"attachments": [{"type": "excel"}], "last_worker_id": ""}
    ) == "data_analysis"

def test_hook_no_force_after_analysis_ran():
    hooks = AttachmentRoutingHooks(["data_analysis"])
    assert hooks.force_worker(
        {"attachments": [{"type": "excel"}], "last_worker_id": "data_analysis"}
    ) is None

def test_hook_no_force_without_routable_attachment():
    hooks = AttachmentRoutingHooks(["data_analysis"])
    assert hooks.force_worker({"attachments": [], "last_worker_id": ""}) is None
    assert hooks.force_worker(
        {"attachments": [{"type": "image"}], "last_worker_id": ""}
    ) is None

def test_hook_no_force_when_no_analysis_worker():
    hooks = AttachmentRoutingHooks([])
    assert hooks.force_worker(
        {"attachments": [{"type": "excel"}], "last_worker_id": ""}
    ) is None
```

### TC-3: supervisor_node가 force 시 LLM 우회 라우팅 (단위, 비동기)
```python
@pytest.mark.asyncio
async def test_supervisor_force_skips_llm_and_routes():
    fake_llm = _FakeStructuredLLM(next="FINISH", answer="권한이 없습니다")  # LLM은 거부 의도
    node = create_supervisor_node(
        llm=fake_llm,
        workers=[WorkerDefinition(tool_id="data_analysis", worker_id="data_analysis",
                                  description="분석", sort_order=1)],
        supervisor_prompt="P",
        hooks=AttachmentRoutingHooks(["data_analysis"]),
        logger=_NoopLogger(),
    )
    state = build_initial_state(
        messages=[{"role": "user", "content": "남은 휴가일수 분석"}],
        config=SupervisorConfig(),
        available_workers=["data_analysis"],
        attachments=[{"type": "excel", "file_path": "/tmp/x.xlsx"}],
    )
    result = await node(state)
    assert result["next_worker"] == "data_analysis"   # 거부 아님
    assert fake_llm.call_count == 0                    # LLM 우회 확인
```

### TC-4: supervisor_node가 첨부를 prompt에 노출 (단위, 비동기)
```python
@pytest.mark.asyncio
async def test_supervisor_includes_attachment_block_in_prompt():
    fake_llm = _FakeStructuredLLM(next="data_analysis", reasoning="분석")
    node = create_supervisor_node(
        llm=fake_llm, workers=[_analysis_worker()], supervisor_prompt="P",
        hooks=DefaultHooks(), logger=_NoopLogger(),   # 훅 없이 prompt 경로만 검증
    )
    state = build_initial_state(
        messages=[{"role": "user", "content": "분석해줘"}],
        config=SupervisorConfig(), available_workers=["data_analysis"],
        attachments=[{"type": "excel", "file_name": "v.xlsx"}],
    )
    await node(state)
    sys_msgs = [m for m in fake_llm.last_invocation_messages if m["role"] == "system"]
    joined = " ".join(m["content"] for m in sys_msgs)
    assert "[첨부된 데이터]" in joined
    assert "거부하지 말고" in joined
```

### TC-5: 첨부 없을 때 기존 동작 보존 (회귀, 비동기)
```python
@pytest.mark.asyncio
async def test_supervisor_no_attachment_behaves_as_before():
    fake_llm = _FakeStructuredLLM(next="FINISH", answer="안녕하세요")
    node = create_supervisor_node(
        llm=fake_llm, workers=[_analysis_worker()], supervisor_prompt="P",
        hooks=AttachmentRoutingHooks(["data_analysis"]), logger=_NoopLogger(),
    )
    state = build_initial_state(
        messages=[{"role": "user", "content": "안녕"}],
        config=SupervisorConfig(), available_workers=["data_analysis"],
        attachments=None,
    )
    result = await node(state)
    assert result["next_worker"] == "__end__"        # 정상 FINISH 보존
    joined = " ".join(
        m["content"] for m in fake_llm.last_invocation_messages if m["role"] == "system"
    )
    assert "[첨부된 데이터]" not in joined            # 블록 미삽입
```

### TC-6: 컴파일러 통합 — 엑셀 첨부 시 analysis_node 진입 (통합, 비동기)
```python
@pytest.mark.asyncio
async def test_compiled_graph_enters_analysis_node_with_excel():
    """data_analysis 워커 + 엑셀 첨부 → analysis_node 실행됨(last_worker_id로 검증)."""
    # ExcelAnalysisWorkflow getter를 가짜로 주입 → analysis_text 반환
    # graph.ainvoke({...attachments: excel...}) 후
    # 최종 메시지가 거부 문구가 아니라 가짜 분석 결과를 포함하는지 확인
```

### 테스트 헬퍼
- `_FakeStructuredLLM`: `with_structured_output(SupervisorDecision)` → 자기 자신 반환, `ainvoke`가 지정 `SupervisorDecision` 반환 + `call_count`/`last_invocation_messages` 기록.
- `_NoopLogger`: `LoggerInterface` 더미.

---

## 6. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|-----------|-----------|
| `idt/src/application/agent_builder/supervisor_hooks.py` | 수정 | `AttachmentRoutingHooks` 추가 (DefaultHooks 보존) |
| `idt/src/application/agent_builder/supervisor_nodes.py` | 수정 | `_render_attachment_block` 헬퍼 + `supervisor_node` prompt 조립 |
| `idt/src/application/agent_builder/workflow_compiler.py` | 수정 | import 1줄 + `compile()` 훅 연결 1블록 |
| `idt/tests/application/agent_builder/test_supervisor_attachment.py` | 신규 | TC-1 ~ TC-6 |

---

## 7. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| `create_supervisor_node` 시그니처 | **불변** | prompt 조립 내부만 변경 |
| `SupervisorHooks` 프로토콜 | **불변** | force_worker/skip_workers 동일 |
| `DefaultHooks` | **보존** | 신규 훅은 별도 클래스 |
| 외부 주입 hooks(테스트 등) | **존중** | `isinstance(DefaultHooks)`일 때만 대체 |
| 첨부 없는 일반 질의 | **불변** | block="" , force=None |
| DB 스키마 / API 스펙 | **변경 없음** | RunAgentRequest.attachments 기존 필드 사용 |
| sub_agent 경로 | analysis 워커 보유 시 동일 이점 | 동일 compile 경유 |
| 토큰 사용량 | 미미 | 첨부 있을 때만 짧은 블록 |
| 무한 루프 | 낮음 | last_worker_id 가드 + max_iterations |

---

## 8. 미해결 / 후속 (Plan §8 동기화)

- supervisor 경로 **실제 차트 렌더링**(chart_router → chart_builder + conditional edge) — 별도 plan. 현재 차트는 General Chat 전용(메모리 `chart-rendering-general-chat-only`).
- attachment dict에 **file_name 보강**(ws_router resolve 단계) → 인지 블록 가독성 향상.
- "내 남은 휴가일수" **도메인 결합**(auth_ctx ↔ 엑셀 행 매핑) — 별도 설계.
- 강제 라우팅 첨부 타입 **확장**(CSV 등) — `_ROUTABLE_TYPES`에 추가.
