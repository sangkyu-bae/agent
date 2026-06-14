# FIX-ANTHROPIC-PREFILL-ERROR: Claude(Anthropic) 연동 시 "assistant message prefill" 400 오류 수정

> 상태: Plan
> 연관 Task: ANTHROPIC-PREFILL-001
> 작성일: 2026-06-11
> 우선순위: Critical

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | LangGraph 멀티에이전트(supervisor) 실행에서 Anthropic provider(claude-sonnet-4-6 등) 사용 시 `anthropic.BadRequestError 400 — "This model does not support assistant message prefill. The conversation must end with a user message."` 발생. 워커 노드가 결과를 `AIMessage`로 state에 누적한 뒤 다음 LLM 호출이 일어나면 메시지 배열이 assistant로 끝나는데, Claude 4.6+ 모델군은 assistant-last(=prefill)를 거부한다. OpenAI/Ollama에서는 허용되는 패턴이라 Anthropic 전환 시에만 터지는 provider 종속 버그. |
| **Solution** | (1) "LLM 호출 직전 메시지 배열은 user(또는 tool_result)로 끝나야 한다"를 보장하는 공통 정규화 헬퍼를 도입하고, (2) supervisor/worker/analysis/final_answer 등 메시지 배열을 그대로 LLM에 넘기는 4개 호출 지점에 적용한다. 특히 supervisor_node가 결정 프롬프트를 **메시지 끝에 system으로 append**하는 구조(→ langchain_anthropic이 system을 top-level로 끌어올려 실제 배열은 AIMessage로 끝남)를 system 선두 배치 + 지시 HumanMessage 후미 배치로 변경. |
| **Function UX Effect** | Anthropic 모델 선택 시 멀티에이전트 대화가 2번째 supervisor 판단(워커 1회 실행 후)부터 500으로 죽던 현상 해소. OpenAI/Ollama 경로는 동작 변화 없음(정규화는 no-op 또는 무해). |
| **Core Value** | 플랫폼의 핵심 가치인 **LLM provider 교체 자유**(OpenAI ↔ Anthropic ↔ Ollama) 회복. provider별 메시지 규칙 차이를 한 곳에서 흡수해 향후 모델 추가 시 재발 방지. |

---

## 1. 문제 정의 (Problem Statement)

Anthropic provider로 에이전트 실행 시 다음 오류가 발생한다:

```
anthropic.BadRequestError: Error code: 400 - {
  'type': 'error',
  'error': {
    'type': 'invalid_request_error',
    'message': 'This model does not support assistant message prefill.
                The conversation must end with a user message.'
  }
}
```

스택트레이스: `langchain_core.chat_models._agenerate_with_cache → langchain_anthropic._astream → anthropic.messages.create` — LangGraph `astream_events(v2)` 하에서 노드 내부 LLM 호출이 스트리밍으로 위임되며 발생.

### 1-1. 오류의 의미 (Anthropic API 스펙)

- Anthropic Messages API에서 메시지 배열이 `role: "assistant"`로 끝나면 **prefill**(모델 응답의 앞부분을 미리 채우는 기능)로 해석된다.
- **Claude Opus 4.6 / Sonnet 4.6 / Opus 4.7 / 4.8 / Fable 5부터 prefill이 제거**되어, assistant-last 요청은 무조건 400을 반환한다. (구형 sonnet-4-5 등에서는 허용되던 패턴)
- 본 프로젝트 seed 모델은 `claude-sonnet-4-6`(`src/infrastructure/llm_model/seed.py:34`) → prefill 거부 대상.

### 1-2. 재현 시나리오

```
1) user 질문 → supervisor 1차 판단 (messages: [Human, System(결정프롬프트)]) → 정상
2) search/analysis 워커 실행 → AIMessage(name=worker_id) state 누적
3) supervisor 2차 판단:
   messages = [Human, AIMessage(워커결과), {"role":"system", 결정프롬프트}]
   → langchain_anthropic이 system을 top-level `system` 파라미터로 끌어올림
   → 실제 API messages 배열 = [user, assistant]  ← assistant로 끝남
   → 400 prefill 오류
```

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. [Critical] `supervisor_node` — 결정 프롬프트를 메시지 끝에 system으로 append

**파일**: `src/application/agent_builder/supervisor_nodes.py:136-142`

```python
messages = state["messages"] + [
    {"role": "system", "content": decision_prompt}
]
llm_with_structure = llm.with_structured_output(SupervisorDecision)
decision = await llm_with_structure.ainvoke(messages)
```

- langchain_anthropic은 SystemMessage를 위치와 무관하게 top-level `system` 파라미터로 변환한다. 따라서 끝에 붙인 system은 배열에서 제거되고, 워커가 1회라도 실행된 뒤에는 배열 마지막이 `AIMessage(name=worker_id)` → prefill 400.
- OpenAI는 system role을 배열 내 임의 위치에 허용하므로 기존에는 문제가 드러나지 않았다.

### 2-2. [High] `_wrap_worker` — 워커 ReAct 에이전트에 assistant-last 메시지 전달

**파일**: `src/application/agent_builder/workflow_compiler.py:702-721`

```python
result = await worker_agent.ainvoke({"messages": state["messages"]})
```

- supervisor가 워커 A 실행 후 워커 B를 연속 호출하면, state["messages"]가 워커 A의 `AIMessage`로 끝난 채 워커 B(create_react_agent)의 첫 LLM 호출로 전달 → 동일 400.

### 2-3. [High] `_analyze_context` — conversation이 assistant로 끝날 수 있음

**파일**: `src/application/agent_builder/workflow_compiler.py:683-697`

```python
conversation = [m for m in messages if not _is_search_result(m)]
response = await llm.ainvoke(
    [{"role": "system", "content": analysis_prompt}, *conversation]
)
```

- 검색 결과만 필터링하므로, 검색이 아닌 다른 워커 출력(`AIMessage(name=...)`)이나 직전 assistant 턴이 배열 마지막에 남으면 동일 400.
- 질문은 이미 `analysis_prompt`(system)에 포함되어 있어, 배열 끝에 user 메시지가 보장되지 않는 구조.

### 2-4. [Medium] `final_answer_node` — 방어적 보정 필요

**파일**: `src/application/agent_builder/workflow_compiler.py:537-550`

```python
llm_messages = [
    {"role": "system", "content": answer_prompt},
    *conversation_messages,
]
response = await llm.ainvoke(llm_messages)
```

- `conversation_messages`는 `name` 보유 워커 출력을 제외하므로 통상 user로 끝나지만, `name` 없는 assistant 메시지(supervisor draft answer 등)가 마지막에 남는 경로가 생기면 동일 400. 정규화 헬퍼로 방어한다.

### 2-5. [Low] `ClaudeClient._build_messages` — 역할 무검증 통과

**파일**: `src/infrastructure/llm/claude_client.py:51-63`

- 호출자가 assistant로 끝나는 `request.messages`를 넘기면 그대로 API로 전달된다. 현재 호출 경로는 user-last를 지키지만, 인프라 레이어 방어 가드(또는 명시적 예외)를 추가해 재발 방지.

### 2-6. 비원인 (확인 완료)

- `GeneralChatUseCase._build_full_context / _build_summarized_context`(`use_case.py:571-615`): 항상 `HumanMessage(new_message)`로 끝남 — 정상.
- ReAct 루프 내부의 ToolMessage-last: Anthropic 변환 시 `tool_result`(user측 블록)이므로 정상.

---

## 3. 해결 방안 (Solution Design 개요)

### FR-1. 공통 메시지 정규화 헬퍼 도입

- 위치(안): `src/application/agent_builder/message_normalization.py` (application 레이어 — LangChain 메시지 의존이므로 domain 금지 규칙 준수)
- 시그니처(안): `ensure_user_tail(messages: list, *, instruction: str | None = None) -> list`
- 규칙:
  1. 마지막 메시지가 Human/ToolMessage면 그대로 반환 (no-op).
  2. 마지막이 AIMessage(들)이면: trailing AIMessage들을 `[이전 단계 결과]` 컨텍스트로 묶은 HumanMessage로 변환하거나, `instruction`이 주어지면 지시 HumanMessage를 append.
  3. provider 무관 적용 (OpenAI/Ollama에 무해 — assistant-last 회피는 모든 provider에서 유효한 패턴).

### FR-2. `supervisor_node` 메시지 구성 변경

- 결정 프롬프트를 **배열 선두 system**으로 이동하고, 배열 끝에는 "위 대화와 워커 결과를 바탕으로 다음 워커를 결정하세요" 류의 **지시 HumanMessage**를 append.
- 부수 효과: system이 안정적 prefix가 되어 Anthropic prompt cache 적중률에도 유리.

### FR-3. `_wrap_worker` 호출 전 정규화

- `worker_agent.ainvoke({"messages": ensure_user_tail(state["messages"], instruction=...)})`
- 직전 워커 결과는 컨텍스트 HumanMessage로 변환되어 워커가 참조 가능.

### FR-4. `_analyze_context` / `final_answer_node` 정규화 적용

- 두 곳 모두 `ensure_user_tail` 통과 후 ainvoke.

### FR-5. `ClaudeClient._build_messages` 방어 가드

- assistant-last 입력 감지 시 경고 로그 + 정규화(또는 `ClaudeInvalidRequestError` 사전 발생 — Design에서 결정).

### 비기능 요구사항

- **TDD 필수**: 각 수정 지점별 실패 테스트 선작성 — fake LLM으로 ainvoke에 전달되는 메시지 배열을 캡처하여 "마지막 메시지가 assistant가 아님"을 검증.
- 기존 OpenAI 경로 회귀 없음 (기존 supervisor/worker 테스트 전부 통과 유지).
- 레이어 규칙 준수: domain에 LangChain 의존 추가 금지.

---

## 4. 범위 (Scope)

### 포함

| # | 파일 | 변경 |
|---|------|------|
| 1 | `src/application/agent_builder/message_normalization.py` (신규) | `ensure_user_tail` 헬퍼 |
| 2 | `src/application/agent_builder/supervisor_nodes.py` | 결정 프롬프트 system 선두 이동 + 지시 HumanMessage |
| 3 | `src/application/agent_builder/workflow_compiler.py` | `_wrap_worker` / `_analyze_context` / `final_answer_node` 정규화 적용 |
| 4 | `src/infrastructure/llm/claude_client.py` | `_build_messages` 방어 가드 |
| 5 | `tests/` | 지점별 단위 테스트 (TDD) |

### 제외 (Out of Scope)

- `temperature` 파라미터 제거: claude-sonnet-4-6은 temperature 허용. 단, **Opus 4.7+/Fable 5로 업그레이드 시 `temperature`도 400**이 되므로 `LLMFactory._create_anthropic`(`llm_factory.py:42-50`)·`ClaudeClient._create_chat_model`의 후속 과제로 기록만 한다.
- `ClaudeModel` enum(`schemas.py`)의 4.5 세대 모델 ID 현행화 — 별도 과제.
- 대화 메모리 정책 / Parent-Child 문서 구조 변경 없음 (금지 규칙).

---

## 5. 성공 기준 (Acceptance Criteria)

1. Anthropic provider로 supervisor 에이전트 실행 시 워커 1회 이상 경유 후에도 400 prefill 오류 미발생.
2. fake LLM 캡처 테스트: 4개 호출 지점 모두 LLM에 전달되는 메시지 배열의 마지막이 user(또는 tool) role.
3. 기존 OpenAI/Ollama 경로 테스트 전부 통과 (회귀 없음).
4. `ensure_user_tail` 단위 테스트: user-last no-op / 단일 AI-last / 연속 AI-last / 빈 배열 케이스 커버.

---

## 6. 리스크 및 참고

| 리스크 | 대응 |
|--------|------|
| supervisor 결정 프롬프트 위치 변경으로 판단 품질 변화 가능 | 기존 프롬프트 텍스트는 유지하고 위치/role만 변경. 수동 스모크 테스트로 라우팅 품질 확인 |
| trailing AIMessage → Human 변환 시 컨텍스트 의미 변형 | `[이전 단계 결과]` 명시 라벨로 출처를 보존 |
| Windows pytest 이벤트 루프 산발 실패 (기지 이슈) | 신규 테스트는 격리 실행으로 검증 (기존 메모 준수) |

- 참고: Anthropic 공식 마이그레이션 가이드 — "Assistant-turn prefills return 400 (Opus 4.6 and Sonnet 4.6)"; 대체 수단은 `output_config.format`(structured output) 또는 user-turn 지시. supervisor는 이미 `with_structured_output`을 사용 중이므로 메시지 순서만 교정하면 된다.

---

## 다음 단계

`/pdca design fix-anthropic-prefill-error` — 정규화 헬퍼 시그니처·노드별 적용 방식·테스트 목록 상세 설계.
