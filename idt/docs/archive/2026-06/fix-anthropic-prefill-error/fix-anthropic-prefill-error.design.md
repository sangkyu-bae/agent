# Design: fix-anthropic-prefill-error

> Created: 2026-06-11
> Phase: Design
> Plan: `docs/01-plan/features/fix-anthropic-prefill-error.plan.md`
> Scope: `idt/` 백엔드 — Anthropic(Claude 4.6+) assistant-last(=prefill) 400 오류 제거

---

## 0. 확정된 설계 결정

| # | 결정 사항 | 결정 |
|---|-----------|------|
| **D1** | trailing AIMessage 처리 방식: 변환(merge) vs 지시 메시지 append | **append 확정.** 마지막이 assistant면 지시 `HumanMessage`를 뒤에 추가한다. 중간 위치의 assistant 메시지는 Anthropic도 허용하므로 기존 메시지를 변형하지 않는다(비파괴). 워커 출력의 `name`/내용/순서가 보존되어 `_is_worker_output`/`_is_search_result` 분류 로직에 영향 없음. |
| **D2** | supervisor 결정 프롬프트 위치 | **system 선두 + 지시 HumanMessage 후미.** 기존처럼 끝에 system을 두면 langchain_anthropic이 top-level `system`으로 끌어올려 배열이 assistant로 끝난다. 프롬프트 **텍스트는 변경하지 않고** role/위치만 변경. |
| **D3** | `ClaudeClient._build_messages` 방어 방식: 예외 vs 정규화 | **경고 로그 + 정규화(continuation HumanMessage append).** 예외를 던져도 결국 사용자에게 500이므로 가용성 우선. warning 로그로 호출자 버그 가시성은 유지. |
| **D4** | 헬퍼 위치 | `src/application/agent_builder/message_normalization.py` 신규. domain 레이어는 LangChain 의존 금지 규칙이므로 application에 둔다. dict(`{"role","content"}`)와 LangChain 메시지 객체 **양쪽**을 지원해야 한다(state["messages"]에 두 형태가 혼재 — `build_initial_state`는 dict, 워커 노드는 `AIMessage` 추가). |
| **D5** | 빈 배열 처리 | instruction이 주어지면 `[HumanMessage(instruction)]` 반환, 없으면 그대로 반환. (Anthropic은 빈 messages도 400이므로 호출부가 빈 배열을 만들지 않는 것이 전제 — 방어만 한다.) |

---

## 1. 설계 개요

### 1-1. 핵심 불변식 (Invariant)

> **LLM `ainvoke`/`astream`에 전달되는 메시지 배열의 마지막 비-system 메시지는 user(human) 또는 tool 이어야 한다.**

- Anthropic Claude 4.6+(sonnet-4-6, opus-4-6/4.7/4.8, Fable 5)는 assistant-last 요청(prefill)을 400으로 거부.
- OpenAI/Ollama에서는 user-last가 어차피 유효하므로 본 불변식은 **provider-agnostic** — 분기 없이 전 경로에 적용한다.

### 1-2. 적용 지점 (4 + 1)

```
supervisor graph (per-run LLM = 임의 provider)
├─ supervisor_node      ← D2: system 선두 + Human 후미 (구조 변경)
├─ _wrap_worker         ← ensure_user_tail 적용 (react agent 진입 전)
├─ _analyze_context     ← ensure_user_tail 적용
└─ final_answer_node    ← ensure_user_tail 적용 (방어)

infrastructure
└─ ClaudeClient._build_messages ← D3: 경고 + 정규화 (최후 방어선)
```

---

## 2. 변경 상세

### 2-1. 신규: `src/application/agent_builder/message_normalization.py`

```python
"""LLM 호출 전 메시지 배열 정규화.

fix-anthropic-prefill-error D1: Claude 4.6+ 는 메시지 배열이 assistant로
끝나면(=prefill) 400을 반환한다. LLM 호출 직전 배열이 user로 끝나도록
지시 HumanMessage를 비파괴 append 한다. OpenAI/Ollama에도 무해.
"""
from langchain_core.messages import HumanMessage

DEFAULT_CONTINUATION = "위 결과를 참고하여 작업을 계속 진행하세요."

_ASSISTANT_ROLES = ("assistant", "ai")


def _tail_role(msg) -> str:
    """dict / LangChain 메시지 양쪽에서 role 추출."""
    if isinstance(msg, dict):
        return str(msg.get("role", ""))
    return str(getattr(msg, "type", ""))


def ensure_user_tail(
    messages: list,
    instruction: str = DEFAULT_CONTINUATION,
) -> list:
    """배열 마지막이 assistant면 지시 HumanMessage를 append한 새 리스트 반환.

    - user/human/tool/system-last → 입력 그대로 반환 (no-op)
    - assistant/ai-last → messages + [HumanMessage(instruction)]
    - 빈 배열 → instruction이 truthy면 [HumanMessage(instruction)], 아니면 그대로
    - 원본 리스트는 변형하지 않는다 (LangGraph state 공유 안전)
    """
    if not messages:
        return [HumanMessage(content=instruction)] if instruction else messages
    if _tail_role(messages[-1]) in _ASSISTANT_ROLES:
        return [*messages, HumanMessage(content=instruction)]
    return messages
```

주의: `_tail_role`은 `search_pipeline._message_role`과 동일 규약(dict→`role`, 객체→`type`). 중복을 피하려면 `search_pipeline`의 `_message_role`을 public으로 승격해 재사용해도 된다 — 구현 시 선택(테스트 동일).

> system-last를 no-op으로 두는 이유: langchain_anthropic이 system을 끌어올린 뒤의 실제 마지막은 그 앞 메시지지만, 본 수정 후 system-last를 만드는 호출부는 없다(2-2에서 제거). 방어 단순성을 위해 assistant-last만 교정한다.

### 2-2. `src/application/agent_builder/supervisor_nodes.py` — supervisor_node

**현재 (136-142):**

```python
messages = state["messages"] + [
    {"role": "system", "content": decision_prompt}
]
llm_with_structure = llm.with_structured_output(SupervisorDecision)
decision = await llm_with_structure.ainvoke(messages)
```

**변경:**

```python
from src.application.agent_builder.message_normalization import ensure_user_tail

SUPERVISOR_TAIL_INSTRUCTION = (
    "위 대화와 워커 결과를 바탕으로 다음 행동(워커 선택 또는 FINISH)을 결정하세요."
)

messages = ensure_user_tail(
    [{"role": "system", "content": decision_prompt}, *state["messages"]],
    instruction=SUPERVISOR_TAIL_INSTRUCTION,
)
decision = await llm_with_structure.ainvoke(messages)
```

- `decision_prompt` 텍스트 자체는 무변경 (라우팅 품질 보존).
- 1차 호출(state=[Human])에서는 tail이 user이므로 지시 메시지가 붙지 않는다 → 기존과 거의 동일한 입력.
- 2차 호출(워커 AIMessage-last)에서만 지시 Human이 추가된다.

### 2-3. `src/application/agent_builder/workflow_compiler.py` — `_wrap_worker` (702-721)

**현재:** `result = await worker_agent.ainvoke({"messages": state["messages"]})`

**변경:**

```python
WORKER_TAIL_INSTRUCTION = (
    "위 대화 맥락과 이전 단계 결과를 참고하여 당신의 역할에 해당하는 작업을 수행하세요."
)

result = await worker_agent.ainvoke(
    {"messages": ensure_user_tail(state["messages"], WORKER_TAIL_INSTRUCTION)}
)
```

- create_react_agent 내부 첫 LLM 호출이 user-last로 보장됨.
- 반환 `new_messages`는 그대로 사용(append된 지시 Human도 state에 합류하지만, `latest_user_question`은 워딩상 실제 질문이 아니어도 동작에 영향 없도록 지시 문구를 질문 형태가 아닌 명령형으로 유지. 필요 시 `QUALITY_FEEDBACK_PREFIX`처럼 식별 프리픽스 부여는 과설계로 보류 — quality_gate 피드백과 달리 supervisor가 이 메시지를 질문으로 오인할 경로 없음).

### 2-4. `workflow_compiler.py` — `_analyze_context` (683-697)

**변경:**

```python
conversation = ensure_user_tail(
    [m for m in messages if not _is_search_result(m)],
    instruction="위 데이터를 바탕으로 분석을 수행하세요.",
)
response = await llm.ainvoke(
    [{"role": "system", "content": analysis_prompt}, *conversation]
)
```

(질문 본문은 기존대로 `analysis_prompt`의 `[질문]` 블록에 포함 — 변경 없음.)

### 2-5. `workflow_compiler.py` — `final_answer_node` (537-550)

**변경:**

```python
llm_messages = [
    {"role": "system", "content": answer_prompt},
    *ensure_user_tail(
        conversation_messages,
        instruction="수집된 결과를 종합하여 마지막 질문에 대한 최종 답변을 작성하세요.",
    ),
]
```

- 통상 경로(user-last)에서는 no-op → 기존 동작·기존 테스트(`test_final_answer_node.py`) 영향 없음.

### 2-6. `src/infrastructure/llm/claude_client.py` — `_build_messages` (51-63)

**변경 (메서드 끝에 가드 추가):**

```python
def _build_messages(self, request: ClaudeRequest) -> list[...]:
    ...
    if messages and isinstance(messages[-1], AIMessage):
        # Claude 4.6+ prefill 거부 방어 (fix-anthropic-prefill-error D3)
        self._logger.warning(
            "message list ends with assistant; appending continuation "
            "to avoid Anthropic prefill rejection",
            request_id=request.request_id,
        )
        messages.append(HumanMessage(content="계속 진행하세요."))
    return messages
```

### 2-7. 변경하지 않는 것

- `GeneralChatUseCase` 컨텍스트 빌더(항상 Human-last — Plan §2-6 확인).
- `decision_prompt`/`answer_prompt`/`analysis_prompt` 텍스트 본문.
- 대화 메모리 정책·요약 규칙·Parent/Child 문서 구조 (금지 규칙).
- `LLMFactory`의 temperature (sonnet-4-6 허용; 4.7+ 업그레이드 시 별도 과제 — Plan §4 Out of Scope).

---

## 3. 테스트 설계 (TDD — 구현 전 작성)

### 3-1. 신규 `tests/application/agent_builder/test_message_normalization.py`

| TC | 입력 | 기대 |
|----|------|------|
| TC-01 | `[Human("q")]` | 동일 리스트 (no-op, append 없음) |
| TC-02 | `[Human, AIMessage(name="w0")]` | 마지막이 `HumanMessage(instruction)`, 원본 비변형 |
| TC-03 | `[Human, AI, AI]` (연속 assistant) | Human 1개만 append (배열 길이 +1) |
| TC-04 | `[Human, AI, ToolMessage]` | no-op |
| TC-05 | dict 형태 `[{"role":"user"...},{"role":"assistant"...}]` | append 발생 |
| TC-06 | `[]` + instruction | `[HumanMessage(instruction)]` |
| TC-07 | 원본 리스트 불변(mutation 없음) 확인 | `id(result) != id(input)` 또는 input 무변형 |

### 3-2. `test_supervisor_nodes.py` 추가

| TC | 시나리오 | 검증 |
|----|----------|------|
| TC-08 | state.messages = `[dict(user)]` (1차 판단) | ainvoke 캡처: `messages[0]`이 system(결정 프롬프트), 마지막이 user |
| TC-09 | state.messages = `[dict(user), AIMessage(name="worker_0")]` (2차 판단) | ainvoke 캡처: 마지막 메시지가 `HumanMessage` (assistant 아님) |

### 3-3. `test_workflow_compiler.py` 추가

| TC | 대상 | 검증 |
|----|------|------|
| TC-10 | `_wrap_worker`: messages가 AIMessage-last인 state로 호출 | `worker_agent.ainvoke` 캡처: `messages` 마지막이 Human |
| TC-11 | `_analyze_context`: 비검색 워커 AIMessage-last | `llm.ainvoke` 캡처: 마지막이 Human |
| TC-12 | `final_answer_node`: conversation이 user-last (통상) | 기존 입력 보존 (no-op 회귀 확인) |

### 3-4. `tests/infrastructure/llm/test_claude_client.py` 추가

| TC | 시나리오 | 검증 |
|----|----------|------|
| TC-13 | `request.messages`가 assistant-last | `_build_messages` 결과 마지막이 HumanMessage + warning 로그 1회 |
| TC-14 | user-last (통상) | 가드 미발동, 로그 없음 |

### 3-5. 회귀

- 기존 `test_supervisor_nodes.py` / `test_final_answer_node.py` / `test_workflow_compiler*.py` 전체 통과.
- Windows 이벤트 루프 이슈로 인해 신규 테스트는 파일 단위 격리 실행으로 1차 검증.

---

## 4. 구현 순서

1. `test_message_normalization.py` 작성 → Red 확인
2. `message_normalization.py` 구현 → Green
3. TC-08/09 작성 → Red → `supervisor_nodes.py` 수정 → Green
4. TC-10~12 작성 → Red → `workflow_compiler.py` 3개 지점 수정 → Green
5. TC-13/14 작성 → Red → `claude_client.py` 가드 → Green
6. agent_builder + llm 테스트 전체 회귀 실행
7. (수동 스모크) Anthropic provider로 supervisor 에이전트 2-스텝 실행 — 400 미발생 확인

---

## 5. 영향 범위 / 리스크

| 항목 | 영향 |
|------|------|
| OpenAI/Ollama 경로 | 2차 supervisor 판단부터 지시 Human 1개가 추가 입력됨(토큰 소폭 증가, 의미상 무해). 1차 판단·통상 final_answer는 no-op |
| supervisor 라우팅 품질 | 결정 프롬프트가 끝(system) → 앞(system)으로 이동. 텍스트 무변경이지만 위치 효과로 판단이 달라질 수 있음 → 스모크 테스트 항목에 포함 |
| state 누적 | `_wrap_worker`의 지시 Human이 react agent 반환 메시지에 포함되어 state에 누적될 수 있음 — `latest_user_question` 오인 여부는 명령형 워딩으로 회피, Check 단계에서 실측 확인 |
| 토큰 사용량 | 지시 메시지 1~2문장/호출 — 무시 가능 수준 |
