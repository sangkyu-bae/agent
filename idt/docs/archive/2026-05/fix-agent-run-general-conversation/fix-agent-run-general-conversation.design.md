# fix-agent-run-general-conversation Design Document

> **Summary**: Agent Run API에서 일반 대화 질문에 대해 supervisor가 FINISH로 즉시 종료되어 응답이 사용자 질문 그대로 반환되는 버그 수정
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-18
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/fix-agent-run-general-conversation.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | "고마워", "안녕" 등 일반 대화 입력 시 supervisor가 FINISH 반환 → 사용자 쿼리가 answer로 그대로 반환 |
| **Solution** | `SupervisorDecision.answer` 필드 추가 + decision_prompt에 직접 응답 지시 + FINISH 시 AIMessage 생성 |
| **Function/UX Effect** | 도구 호출 불필요한 질문에도 자연스러운 대화 응답 생성 |
| **Core Value** | 에이전트 UX 정상화 — 모든 유형 질문에 적절한 응답 보장 |

---

## 1. Architecture Overview

### 1.1 현재 흐름 (Before)

```
User Query ("고마워")
  → supervisor_node()
    → decision_prompt: "워커 호출 or FINISH" (2가지만 존재)
    → LLM → SupervisorDecision(next="FINISH", reasoning="...")
    → next_worker = "__end__"
    → return {"next_worker": "__end__", ...}  (AI 메시지 없음)
  → 그래프 종료
  → _parse_result(): messages[-1] = 사용자 원본 쿼리 → answer = "고마워"
```

### 1.2 변경 후 흐름 (After)

```
User Query ("고마워")
  → supervisor_node()
    → decision_prompt: "워커 호출 or FINISH (+ answer 필드에 응답 작성)"
    → LLM → SupervisorDecision(next="FINISH", reasoning="...", answer="천만에요! ...")
    → next_worker = "__end__"
    → decision.answer 존재 → AIMessage(content="천만에요! ...") 생성
    → return {"next_worker": "__end__", "messages": [AIMessage], ...}
  → 그래프 종료
  → _parse_result(): messages[-1] = AIMessage → answer = "천만에요! ..."
```

### 1.3 변경 범위

```
src/application/agent_builder/
├── supervisor_nodes.py   ← SupervisorDecision + create_supervisor_node 수정
└── (다른 파일 변경 없음)

tests/application/agent_builder/
├── test_supervisor_nodes.py  ← FINISH + answer 테스트 추가
tests/api/
├── test_agent_builder_router.py  ← run API 일반 대화 테스트 추가
```

---

## 2. Detailed Design

### 2.1 SupervisorDecision 스키마 변경

**파일**: `src/application/agent_builder/supervisor_nodes.py:35-37`

**Before**:
```python
class SupervisorDecision(BaseModel):
    next: str = Field(description="다음 호출할 worker_id 또는 'FINISH'")
    reasoning: str = Field(description="선택 이유")
```

**After**:
```python
class SupervisorDecision(BaseModel):
    next: str = Field(description="다음 호출할 worker_id 또는 'FINISH'")
    reasoning: str = Field(description="선택 이유")
    answer: str = Field(
        default="",
        description="FINISH 선택 시 사용자에게 전달할 응답. 워커 호출 없이 직접 답변할 때 작성.",
    )
```

**설계 근거**:
- `default=""`: 워커 호출 시에는 빈 문자열, structured output 파싱 실패 방지
- 기존 `next`, `reasoning` 필드 변경 없음 → 하위 호환 유지

### 2.2 decision_prompt 수정

**파일**: `src/application/agent_builder/supervisor_nodes.py:73-79`

**Before**:
```python
decision_prompt = (
    f"{supervisor_prompt}\n\n"
    f"사용 가능한 워커:\n{worker_descriptions}\n\n"
    f"다음 중 선택하세요:\n"
    f"- 워커 호출이 필요하면 해당 worker_id를 선택\n"
    f"- 모든 작업이 완료되었으면 'FINISH'를 선택\n"
    f"스킵된 워커(사용 불가): {skipped}"
)
```

**After**:
```python
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

**설계 근거**:
- "워커 호출 없이 직접 답변" 옵션을 명시적으로 추가
- 기존 "모든 작업 완료 시 FINISH" 옵션 유지 → 워커 실행 후 종료 시에도 동작

### 2.3 FINISH 시 AIMessage 생성 로직

**파일**: `src/application/agent_builder/supervisor_nodes.py:94-106`

**Before**:
```python
if next_worker == "FINISH":
    next_worker = "__end__"
elif next_worker in skipped:
    next_worker = "__end__"
elif next_worker not in available_ids and next_worker != "__end__":
    logger.warning("invalid worker selected", selected=next_worker)
    next_worker = "__end__"

return {
    "next_worker": next_worker,
    "skipped_workers": skipped,
    "iteration_count": state["iteration_count"] + 1,
}
```

**After**:
```python
if next_worker == "FINISH":
    next_worker = "__end__"
    if decision.answer:
        from langchain_core.messages import AIMessage
        return {
            "next_worker": next_worker,
            "messages": [AIMessage(content=decision.answer)],
            "skipped_workers": skipped,
            "iteration_count": state["iteration_count"] + 1,
        }
elif next_worker in skipped:
    next_worker = "__end__"
elif next_worker not in available_ids and next_worker != "__end__":
    logger.warning("invalid worker selected", selected=next_worker)
    next_worker = "__end__"

return {
    "next_worker": next_worker,
    "skipped_workers": skipped,
    "iteration_count": state["iteration_count"] + 1,
}
```

**설계 근거**:
- `decision.answer`가 비어있지 않을 때만 AIMessage 생성
- `messages` 키에 AIMessage를 추가하면 `SupervisorState.messages`의 `add_messages` annotator가 기존 메시지에 append 처리
- 워커 실행 후 FINISH 시에도 answer가 있으면 최종 응답으로 사용 가능
- 기존 return 구조와 동일, `messages` 키만 추가

### 2.4 영향 분석: _parse_result 변경 불필요

**파일**: `src/application/agent_builder/run_agent_use_case.py:235-247`

```python
def _parse_result(self, result: dict) -> tuple[str, list[str]]:
    messages = result.get("messages", [])
    answer = ""
    if messages:
        last = messages[-1]
        answer = last.content if hasattr(last, "content") else str(last)
    ...
```

- 변경 후: FINISH + answer 시 `messages[-1]`이 AIMessage(content=answer) → 자연스럽게 추출
- 변경 불필요, 기존 로직 그대로 동작

### 2.5 그래프 구조 변경 없음

`workflow_compiler.py`의 그래프 구조(노드, 엣지, 라우팅)는 변경하지 않는다.
- supervisor → `__end__` 라우팅은 기존과 동일
- AIMessage가 state.messages에 추가되므로 `_parse_result`가 정상 추출

---

## 3. Test Design

### 3.1 단위 테스트 — supervisor_nodes

**파일**: `tests/application/agent_builder/test_supervisor_nodes.py`

#### TC-NEW-01: FINISH + answer → AIMessage 생성

```python
@pytest.mark.asyncio
async def test_finish_with_answer_creates_ai_message(self):
    """FINISH + answer 필드 → messages에 AIMessage 포함."""
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = "FINISH"
    decision.reasoning = "일반 대화이므로 직접 응답"
    decision.answer = "천만에요! 다른 도움이 필요하시면 말씀해주세요."
    mock_structured = AsyncMock(return_value=decision)
    mock_llm.with_structured_output.return_value.ainvoke = mock_structured

    fn = create_supervisor_node(
        llm=mock_llm, workers=_make_workers(),
        supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
    )
    result = await fn(_make_state())
    assert result["next_worker"] == "__end__"
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "천만에요! 다른 도움이 필요하시면 말씀해주세요."
```

#### TC-NEW-02: FINISH + answer 빈 문자열 → messages 키 없음 (기존 동작)

```python
@pytest.mark.asyncio
async def test_finish_without_answer_no_messages(self):
    """FINISH + answer="" → messages 키 없음 (기존 동작 유지)."""
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = "FINISH"
    decision.reasoning = "done"
    decision.answer = ""
    mock_structured = AsyncMock(return_value=decision)
    mock_llm.with_structured_output.return_value.ainvoke = mock_structured

    fn = create_supervisor_node(
        llm=mock_llm, workers=_make_workers(),
        supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
    )
    result = await fn(_make_state())
    assert result["next_worker"] == "__end__"
    assert "messages" not in result
```

#### TC-NEW-03: 워커 선택 시 answer 무시

```python
@pytest.mark.asyncio
async def test_worker_selection_ignores_answer(self):
    """워커 선택 시 answer 필드가 있어도 무시."""
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = "worker_0"
    decision.reasoning = "search needed"
    decision.answer = "이 answer는 무시되어야 함"
    mock_structured = AsyncMock(return_value=decision)
    mock_llm.with_structured_output.return_value.ainvoke = mock_structured

    fn = create_supervisor_node(
        llm=mock_llm, workers=_make_workers(),
        supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
    )
    result = await fn(_make_state())
    assert result["next_worker"] == "worker_0"
    assert "messages" not in result
```

### 3.2 기존 테스트 호환성

기존 `test_finish_returns_end` (TC-02) 테스트는 `decision.answer` 속성이 없는 MagicMock을 사용한다.
MagicMock은 존재하지 않는 속성 접근 시 falsy한 새 MagicMock을 반환하므로 `if decision.answer:` 조건이 False로 평가되어 **기존 테스트 변경 없이 통과**한다.

검증:
```python
from unittest.mock import MagicMock
d = MagicMock()
d.answer  # → <MagicMock ...>
bool(d.answer)  # → True  ← 주의! MagicMock은 truthy
```

**수정 필요**: MagicMock()은 truthy이므로 기존 TC-02의 mock에 `decision.answer = ""` 추가 필요.

### 3.3 라우터 통합 테스트

**파일**: `tests/api/test_agent_builder_router.py`

#### TC-NEW-04: run API 일반 대화 응답 검증

```python
class TestRunAgent:
    def test_run_agent_general_conversation_returns_proper_answer(self):
        """일반 대화 질문 → answer가 query와 다른 자연스러운 응답."""
        agent_id = str(uuid.uuid4())
        mock_uc = MagicMock()
        response = RunAgentResponse(
            agent_id=agent_id,
            query="고마워",
            answer="천만에요! 다른 도움이 필요하시면 말씀해주세요.",
            tools_used=[],
            request_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
        )
        mock_uc.execute = AsyncMock(return_value=response)
        client = _make_client({get_run_agent_use_case: lambda: mock_uc})

        resp = client.post(f"/api/v1/agents/{agent_id}/run", json={
            "query": "고마워",
            "user_id": "user-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] != data["query"]
        assert len(data["answer"]) > 0
```

---

## 4. Implementation Order

| Step | File | Action | TDD Phase |
|------|------|--------|-----------|
| 1 | `tests/application/agent_builder/test_supervisor_nodes.py` | TC-NEW-01, TC-NEW-02, TC-NEW-03 테스트 추가 | Red |
| 2 | `src/application/agent_builder/supervisor_nodes.py:35-37` | `SupervisorDecision.answer` 필드 추가 | Green |
| 3 | `src/application/agent_builder/supervisor_nodes.py:73-79` | decision_prompt에 직접 응답 지시 추가 | Green |
| 4 | `src/application/agent_builder/supervisor_nodes.py:94-106` | FINISH + answer 시 AIMessage 생성 로직 | Green |
| 5 | `tests/application/agent_builder/test_supervisor_nodes.py` | 기존 TC-02 mock에 `decision.answer = ""` 추가 | Fix |
| 6 | `tests/api/test_agent_builder_router.py` | TC-NEW-04 라우터 테스트 추가 | Red→Green |
| 7 | 전체 테스트 실행 | `pytest tests/` | Verify |

---

## 5. Risk & Edge Cases

### 5.1 Edge Cases

| Case | Expected Behavior | Handling |
|------|-------------------|----------|
| FINISH + answer가 매우 긴 경우 | 정상 반환 (token_limit은 supervisor 호출 횟수 기준) | 추가 처리 불필요 |
| 워커 실행 후 FINISH + answer | answer가 최종 응답으로 추가됨 | 정상 동작, 워커 결과 + answer 모두 messages에 존재 |
| LLM이 answer 필드를 생략 | `default=""` → 기존 동작 | Pydantic default 처리 |
| LLM 파싱 실패 (except 블록) | `__end__` 폴백 (기존 동작) | 변경 없음 |
| MagicMock truthy 문제 | 기존 TC-02에 `answer=""` 명시 | Step 5에서 처리 |

### 5.2 Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| structured output에 필드 추가 시 일부 LLM provider 호환 문제 | Low | OpenAI function calling은 optional 필드 정상 지원 |
| decision_prompt 길이 증가로 토큰 소모 증가 | Low | 약 40자 추가, 무시 가능 수준 |
| 기존 MagicMock 테스트 깨짐 | Medium | Step 5에서 명시적 answer="" 추가로 해결 |

---

## 6. Non-Goals (변경하지 않는 것)

- `workflow_compiler.py` 그래프 구조 변경
- `run_agent_use_case.py` `_parse_result` 로직 변경
- `PromptGenerator` 시스템 프롬프트 템플릿 변경
- `supervisor_state.py` 상태 필드 추가
- 새로운 노드(fallback_answer 등) 추가
