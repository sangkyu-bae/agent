# FIX-ANSWER-NODE-MULTITURN-CONTEXT: 멀티턴 대화에서 answer_node가 첫 user 질문만 사용하는 버그 수정

> 상태: Plan
> 연관 Task: ANSWER-CTX-001
> 작성일: 2026-05-19
> 우선순위: Critical

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `POST /api/v1/agents/{agent_id}/run` 멀티턴 호출 시 search 워커가 최신 질문으로 자료를 수집해도, 답변 에이전트(`answer_node`)는 **세션의 가장 앞 user 메시지("안녕")**를 user_query로 잡아 LLM에 보낸다. 사용자가 본 증상: 두 번째 질문에 답이 엉뚱하게 첫 인사 기준으로 생성됨. |
| **Solution** | `workflow_compiler.py::_create_answer_node()`가 `state["messages"]`를 `for ... break`로 첫 user만 뽑던 로직을 제거하고, **전체 대화 맥락 messages를 LLM에 그대로 전달**. 단, search_node가 추가한 검색결과 `AIMessage`는 system prompt의 `[수집된 검색 결과]` 블록과 중복되므로 messages에서 제외. |
| **Function UX Effect** | 멀티턴 대화에서 follow-up 질문, 지시어("그럼 그건?", "더 자세히"), 이전 컨텍스트 참조가 정상 동작. 검색결과는 최신 질문 기준으로 답변에 반영. |
| **Core Value** | RAG 기반 내부문서 질의응답의 **대화 일관성** 회복. 사용자 신뢰도 직접 영향 — "AI가 방금 한 말을 기억 못한다"는 치명적 인상 제거. |

---

## 1. 문제 정의 (Problem Statement)

`POST /api/v1/agents/{agent_id}/run` API에서 동일 `session_id`를 재사용한 멀티턴 시나리오:

```
turn 1) user: "안녕"
turn 2) ai:   "안녕하세요! 어떻게 도와드릴까요?"
turn 3) user: "우리 내부문서에서 ~~~ 알려줘"
```

3번째 턴에서 supervisor가 research 워커(예: `internal_document_search`) 호출 → search_node가 "우리 내부문서에서 ~~~" 쿼리로 검색 수행(여기까지 정상) → `answer_node` 진입 → **LLM에 전달되는 user 질문이 "안녕"으로 들어감** → 검색결과는 "내부문서~~"인데 질문은 "안녕"인 모순된 입력으로 답변 생성됨.

사용자 관점 증상: "내부 문서 질문을 했는데 답변이 첫 인사 기준으로 나온다."

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. [Critical] `_create_answer_node()`의 첫-매치-break 로직

**파일**: `src/application/agent_builder/workflow_compiler.py:237-282`

문제의 코드 (lines 250-256):

```python
user_query = ""
for msg in state["messages"]:           # ← 첫 메시지부터 정방향 순회
    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
    if role in ("user", "human"):
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
        user_query = content
        break                            # ← 첫 user 매치에서 즉시 종료
```

`RunAgentUseCase._build_messages()` (run_agent_use_case.py:247-273)가 DB에서 멀티턴 시 다음 형태로 messages를 빌드한다:

```python
[
    {"role": "user",      "content": "안녕"},              # turn 1
    {"role": "assistant", "content": "안녕하세요! ..."},   # turn 2
    {"role": "user",      "content": "우리 내부문서~~"},   # turn 3 (현재)
]
```

이 상태로 graph.ainvoke 진입 → supervisor → search_node가 마지막 user 질문으로 검색 → 검색결과 AIMessage가 messages에 추가됨:

```python
[
    {"role": "user",      "content": "안녕"},
    {"role": "assistant", "content": "안녕하세요! ..."},
    {"role": "user",      "content": "우리 내부문서~~"},
    AIMessage(name="research_worker", content="[research_worker 검색결과]\n...")
]
```

answer_node 진입 → `for msg in state["messages"]`로 정방향 순회 → **첫 매치 "안녕"이 user_query**로 확정 → break.

LLM에 최종 전달되는 입력:

```python
[
    {"role": "system", "content": f"{system_prompt}\n...[수집된 검색 결과]\n{내부문서 검색결과}"},
    {"role": "user",   "content": "안녕"},                                          # ← 버그
]
```

검색결과는 내부문서 자료인데 user 질문은 "안녕" → LLM이 검색결과를 무시하거나 어색한 답변 생성.

### 2-2. [부수 효과] 이전 대화 맥락이 답변 LLM에 전혀 전달되지 않음

현재 answer_node는 **단일 user 메시지 + system 프롬프트**만 LLM에 보낸다. 즉 멀티턴 follow-up 시나리오(예: "그럼 그 조건은?" 같은 지시어/생략) 처리가 원천적으로 불가능. 이번 수정으로 함께 해결됨.

### 2-3. [범위 외, 별도 이슈] search_node 연속 호출 시 query 추출 오류

`workflow_compiler.py:288-292` 의 search_node는 `state["messages"][-1]`로 query를 뽑는다. supervisor가 search 워커를 2회 이상 연속 호출하면 두 번째 호출 시 마지막 메시지가 직전 검색결과 AIMessage가 되어 검색결과를 또 검색하는 형태로 빠진다. **이번 plan에서는 다루지 않고 별도 이슈로 분리.**

---

## 3. 수정 범위 (Scope)

| # | 수정 위치 | 내용 | 우선순위 |
|---|-----------|------|----------|
| 1 | `workflow_compiler.py::_create_answer_node()` | user_query 첫-매치-break 로직 제거. 전체 messages를 LLM에 전달하되 검색결과 AIMessage(`name`이 worker_id 부여된 것)는 제외 | Critical |
| 2 | `tests/application/agent_builder/test_workflow_compiler.py` (신규 또는 기존 추가) | answer_node 단위 테스트 + 멀티턴 회귀 테스트 | High |

**범위 외 (별도 처리)**:
- search_node 연속 호출 시 query 추출 오류 (위 2-3)
- supervisor가 첫 턴 "안녕"에서 FINISH로 직접 답변하는 경로 (정상 동작, 보존)

---

## 4. 수정 방향 (Solution Design)

### 4-1. 새로운 answer_node 로직

**전략**: search_node가 추가한 검색결과 AIMessage(= `name` 속성이 worker_id로 설정된 AIMessage)는 system prompt의 `[수집된 검색 결과]` 블록과 중복되므로 messages 본체에서는 제외하고, 나머지 user/assistant/system(이전 대화 요약) 메시지는 그대로 LLM에 전달한다.

```python
def _create_answer_node(self, llm, system_prompt: str):
    logger = self._logger

    async def answer_node(state: SupervisorState) -> dict:
        # 1) 검색결과 수집 (system prompt에 합칠 컨텍스트)
        search_results: list[str] = []
        for msg in state["messages"]:
            name = getattr(msg, "name", None)
            content = getattr(msg, "content", "") if not isinstance(msg, dict) else msg.get("content", "")
            if name and "검색결과" in content:
                search_results.append(content)

        context = "\n\n---\n\n".join(search_results) if search_results else "(검색 결과 없음)"
        if not search_results:
            logger.warning("answer_node: no search results found")

        # 2) 대화 맥락 messages 빌드 — 검색결과 AIMessage만 제외
        conversation_messages: list = []
        for msg in state["messages"]:
            # 검색결과 메시지 (search_node가 name=worker_id로 추가한 것) 제외
            if not isinstance(msg, dict) and getattr(msg, "name", None) and "검색결과" in getattr(msg, "content", ""):
                continue
            conversation_messages.append(msg)

        # 3) system prompt에 검색결과 컨텍스트 prepend → 대화 맥락 전체 전달
        answer_prompt = (
            f"{system_prompt}\n\n"
            f"아래 검색 결과를 바탕으로 사용자의 가장 최근 질문에 정확하게 답변하세요.\n"
            f"검색 결과에 없는 내용은 추측하지 마세요. 이전 대화 맥락도 참고하세요.\n\n"
            f"[수집된 검색 결과]\n{context}"
        )

        messages = [{"role": "system", "content": answer_prompt}, *conversation_messages]

        logger.info(
            "answer_node executing",
            search_result_count=len(search_results),
            conversation_message_count=len(conversation_messages),
        )

        response = await llm.ainvoke(messages)
        token_delta = len(response.content) // 4 if hasattr(response, "content") else 0

        return {
            "messages": [response],
            "last_worker_id": "answer_agent",
            "token_usage": state["token_usage"] + token_delta,
        }

    return answer_node
```

**핵심 변경점**:
- `user_query` 단일 추출 제거
- `state["messages"]`를 그대로 전달 (검색결과 AIMessage만 필터)
- system prompt에 "가장 최근 질문에 답하라"는 지시 명시

### 4-2. 검색결과 식별 기준

`_create_search_node()` (workflow_compiler.py:302-306)에서 검색결과는 다음 형태로 추가됨:

```python
result_msg = AIMessage(
    content=f"[{worker_id} 검색결과]\n{result_str}",
    name=worker_id,
)
```

식별 조건: **`msg.name` 속성이 truthy AND `msg.content`에 "검색결과" 포함**.
(단순히 `name` 존재만으로 거르면 quality_gate retry 메시지 등 다른 name 부여 메시지까지 잘못 거를 위험이 있어 content 검사 병행.)

### 4-3. dict / BaseMessage 혼합 처리

`state["messages"]`는 langgraph `add_messages` reducer에 의해 BaseMessage 인스턴스로 변환되지만, 초기 build_initial_state에서 dict로 들어간 메시지도 있을 수 있다. 위 코드는 `isinstance(msg, dict)` 분기로 양쪽 모두 안전 처리.

---

## 5. 테스트 계획 (TDD)

### 5-1. 단위 테스트: answer_node 멀티턴 입력 → LLM 호출 인자 검증

**파일**: `tests/application/agent_builder/test_workflow_compiler.py` (신규 또는 추가)

```python
async def test_answer_node_passes_full_conversation_with_latest_user_question():
    """멀티턴 state에서 answer_node가 LLM에 전체 대화 + 최신 user 질문을 전달한다."""
    # given
    fake_llm = FakeLLM(response_content="내부문서 기반 답변")
    compiler = WorkflowCompiler(...)
    answer_node = compiler._create_answer_node(fake_llm, system_prompt="당신은 어시스턴트입니다.")

    state = {
        "messages": [
            HumanMessage(content="안녕"),
            AIMessage(content="안녕하세요!"),
            HumanMessage(content="우리 내부문서에서 X 알려줘"),
            AIMessage(content="[research_worker 검색결과]\nX는 ...", name="research_worker"),
        ],
        "token_usage": 0,
        # ... other state fields
    }

    # when
    result = await answer_node(state)

    # then: LLM에 전달된 messages 검증
    sent = fake_llm.last_invocation_messages
    assert sent[0]["role"] == "system"
    assert "[수집된 검색 결과]" in sent[0]["content"]
    assert "X는 ..." in sent[0]["content"]

    # 검색결과 AIMessage는 messages 본체에서 제외되어야 함
    contents = [
        m["content"] if isinstance(m, dict) else m.content
        for m in sent[1:]
    ]
    assert "안녕" in contents
    assert "우리 내부문서에서 X 알려줘" in contents
    assert not any("검색결과" in c for c in contents)
```

### 5-2. 회귀 테스트: 첫 user 메시지가 user_query로 잡히지 않는다

```python
async def test_answer_node_does_not_pick_first_user_message_when_multiturn():
    """레거시 버그 회귀 방지: 첫 user='안녕'이 단독으로 LLM에 전달되면 안 된다."""
    state = build_multiturn_state(first_user="안녕", latest_user="내부문서 X")
    await answer_node(state)
    sent = fake_llm.last_invocation_messages

    # 단일 user 메시지만 전달되는 레거시 형태(messages 길이 2)는 더 이상 발생하지 않음
    assert len(sent) > 2
    # 최신 user가 마지막 user 메시지여야 함
    user_msgs = [m for m in sent if (m["role"] if isinstance(m, dict) else m.type) in ("user", "human")]
    last_user_content = user_msgs[-1]["content"] if isinstance(user_msgs[-1], dict) else user_msgs[-1].content
    assert last_user_content == "내부문서 X"
```

### 5-3. 단일 턴 정상 동작 보존 테스트

```python
async def test_answer_node_single_turn_still_works():
    """첫 턴 단일 user + 검색결과 케이스도 기존처럼 동작."""
    state = {
        "messages": [
            HumanMessage(content="X에 대해 알려줘"),
            AIMessage(content="[research_worker 검색결과]\n...", name="research_worker"),
        ],
        "token_usage": 0,
    }
    result = await answer_node(state)
    assert "messages" in result
```

### 5-4. 검색 결과 없는 경고 로깅 보존

기존 `logger.warning("answer_node: no search results found")` 동작은 유지하여 회귀하지 않도록 한다.

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| `_create_answer_node()` 외부 호출 | 없음 (WorkflowCompiler 내부 사용) | private 메서드 |
| LangGraph 그래프 컴파일 흐름 | 변경 없음 | 노드 시그니처 동일 |
| 토큰 사용량 | **증가 가능** | 멀티턴 시 전체 messages 전달 → `_build_summarized_context`의 요약 정책이 이미 있어 과도한 증가는 방지됨 |
| LangSmith trace | 변경 없음 | callback/metadata 동일 |
| 기존 단일턴 동작 | **보존** | 검색결과만 있고 user 1개인 케이스 동일 결과 |
| supervisor FINISH 직접답변 경로 | **변경 없음** | answer_node를 안 타는 경로라 영향 X |

---

## 7. 구현 순서

1. `tests/application/agent_builder/test_workflow_compiler.py`에 5-1, 5-2, 5-3 테스트 작성 (RED 확인)
2. `workflow_compiler.py::_create_answer_node()` 4-1 코드로 교체
3. 테스트 GREEN 확인
4. 로컬 dev 서버에서 멀티턴 시나리오 수동 검증 (안녕 → 안녕하세요 → 내부문서 질문)
5. Gap 분석 → Report

---

## 8. 미해결/후속 이슈

- **search_node 연속 호출 query 오추출**: `state["messages"][-1]`이 직전 검색결과가 되는 케이스. 별도 plan으로 추적.
- **검색결과 식별 휴리스틱**: `"검색결과" in content`는 한국어 고정 문자열에 의존. 추후 구조화된 메타데이터(예: `additional_kwargs["msg_type"] = "search_result"`)로 개선 검토.
