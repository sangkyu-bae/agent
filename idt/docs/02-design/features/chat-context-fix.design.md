# CHAT-CONTEXT-FIX: 설계 문서

> 상태: Design
> Plan 참조: docs/01-plan/features/chat-context-fix.plan.md
> 연관 Task: CHAT-001
> 작성일: 2026-04-12

---

## 1. 설계 개요

두 가지 독립된 버그를 최소 변경으로 수정한다.

| # | 버그 | 파일 | 수정 범위 |
|---|------|------|-----------|
| B-1 | `_SYSTEM_PROMPT`이 `create_react_agent`에 전달되지 않음 | `use_case.py` | `_create_agent()` 1줄 |
| B-2 | `_SYSTEM_PROMPT`에 문맥 참고 지시 없음 | `use_case.py` | `_SYSTEM_PROMPT` 상수 1줄 추가 |
| B-3 | `activeSessionId` 초기화 시 `createSession()` 이중 호출 | `ChatPage/index.tsx` | 초기화 로직 재구성 |

---

## 2. 백엔드 설계 (`use_case.py`)

### 2-1. `_SYSTEM_PROMPT` 수정 (B-2)

**현재 코드** (`use_case.py:24-31`):

```python
_SYSTEM_PROMPT = (
    "당신은 사용자의 일반 질문에 답하는 AI 어시스턴트입니다.\n"
    "필요에 따라 다음 도구를 사용하세요:\n"
    "- tavily_search: 최신 웹 정보 검색\n"
    "- internal_document_search: 내부 문서(금융/정책 등) 검색\n"
    "- MCP 도구: 등록된 외부 서비스 연동\n"
    "항상 한국어로 답변하세요."
)
```

**수정 후**:

```python
_SYSTEM_PROMPT = (
    "당신은 사용자의 일반 질문에 답하는 AI 어시스턴트입니다.\n"
    "이전 대화 내용이 있다면 반드시 참고하여 문맥에 맞게 답변하세요.\n"
    "필요에 따라 다음 도구를 사용하세요:\n"
    "- tavily_search: 최신 웹 정보 검색\n"
    "- internal_document_search: 내부 문서(금융/정책 등) 검색\n"
    "- MCP 도구: 등록된 외부 서비스 연동\n"
    "항상 한국어로 답변하세요."
)
```

변경: 두 번째 줄 "이전 대화 내용이 있다면 반드시 참고하여 문맥에 맞게 답변하세요.\n" 추가.

### 2-2. `_create_agent()` 수정 (B-1)

**현재 코드** (`use_case.py:66-73`):

```python
def _create_agent(self, tools: list):
    llm = ChatOpenAI(
        model=self._model_name,
        api_key=self._api_key or None,
        temperature=0,
    )
    return create_react_agent(llm, tools=tools)
```

**수정 후**:

```python
def _create_agent(self, tools: list):
    llm = ChatOpenAI(
        model=self._model_name,
        api_key=self._api_key or None,
        temperature=0,
    )
    return create_react_agent(llm, tools=tools, prompt=_SYSTEM_PROMPT)
```

변경: `create_react_agent` 호출에 `prompt=_SYSTEM_PROMPT` 추가.

### 2-3. 문맥 전달 흐름

`_build_full_context`와 `_build_summarized_context`는 **변경 없음**.
이미 히스토리를 LangChain 메시지로 변환하여 에이전트에 전달하고 있다.
시스템 프롬프트가 `create_react_agent`의 `prompt`로 전달되면,
LangGraph 내부에서 이를 `SystemMessage`로 선두에 삽입한다.

```
에이전트 입력 구조 (수정 후):
SystemMessage(_SYSTEM_PROMPT)   ← create_react_agent가 prepend
HumanMessage("첫 질문")         ← _build_full_context 결과
AIMessage("첫 답변")
HumanMessage("두 번째 질문")    ← 새 메시지
```

---

## 3. 프론트엔드 설계 (`ChatPage/index.tsx`)

### 3-1. 문제 분석

**현재 코드** (`ChatPage/index.tsx:21-32`):

```typescript
const [sessions, setSessions] = useState<ChatSession[]>(() => [createSession()]);  // UUID-A 생성
const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    const first = createSession();  // UUID-B 생성 (다른 UUID!)
    return first.id;
});

useEffect(() => {
    setActiveSessionId(sessions[0].id);  // 렌더링 후 보정 (불필요한 재렌더링)
}, []);
```

초기화 순간 `sessions[0].id`(UUID-A)와 `activeSessionId`(UUID-B)가 다르다.
`useEffect`로 보정되지만, 보정 전 첫 렌더링에서 `activeSessionId`가 잘못된 값이다.
첫 번째 메시지 발송 시점에 따라 잘못된 `session_id`로 API가 호출될 수 있다.

### 3-2. 수정 방향

초기 세션을 컴포넌트 외부(또는 초기화 함수 내)에서 한 번만 생성하고,
`sessions`와 `activeSessionId` 모두 동일 객체에서 파생시킨다.

**수정 후**:

```typescript
const ChatPage = () => {
  const user = useAuthStore((s) => s.user);

  // 단일 createSession() 호출로 초기 세션 생성
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const initial = createSession();
    return [initial];
  });
  const [activeSessionId, setActiveSessionId] = useState<string>(
    () => sessions[0].id   // sessions 초기값에서 파생 (같은 UUID)
  );
  // useEffect 제거
  ...
};
```

> `useState`의 initializer 함수는 첫 렌더링에 한 번만 실행된다.
> `activeSessionId`의 initializer에서 `sessions` state의 초기값을
> 직접 참조할 수 없으므로, `sessions` initializer 내부에서 생성한 객체를
> 클로저 밖으로 꺼낼 수 없다.
>
> 대신, `activeSessionId` initializer를 **별도의 `useState` 호출** 방식으로
> 분리하되, `sessions` 초기값과 같은 방식으로 `sessions[0].id`를 참조한다.

실제로 `useState` initializer 내부에서 다른 `useState`의 값을 읽을 수 없기 때문에
다음 패턴을 사용한다:

```typescript
// 컴포넌트 함수 본문 시작 시 상수로 분리
const ChatPage = () => {
  const user = useAuthStore((s) => s.user);

  const [sessions, setSessions] = useState<ChatSession[]>(() => [createSession()]);
  const [activeSessionId, setActiveSessionId] = useState<string>(sessions[0].id);
  // useEffect 제거
  ...
};
```

`sessions`의 `useState` initializer는 첫 렌더링에만 실행되고,
`activeSessionId`의 `useState` 초기값으로 `sessions[0].id`를 직접 전달한다.
이 시점에서 `sessions`는 이미 초기화된 상태이므로 `sessions[0].id`가 유효하다.

> **주의**: `sessions[0].id`를 직접 초기값으로 넘기는 것은 첫 렌더링 시에만 적용된다.
> 이후 `sessions` 변경은 `activeSessionId`에 자동 반영되지 않지만,
> `handleNewChat` 등에서 명시적으로 `setActiveSessionId`를 호출하므로 문제없다.

### 3-3. `useEffect` 제거

```typescript
// 제거 대상
useEffect(() => {
    setActiveSessionId(sessions[0].id);
}, []);
```

초기화가 올바르게 이루어지면 이 `useEffect`는 불필요한 재렌더링만 유발한다.

---

## 4. 테스트 설계

### 4-1. 백엔드 신규 테스트 (`tests/application/general_chat/test_use_case.py`)

기존 TC-1 ~ TC-12 구조를 유지하고, TC-13 ~ TC-15를 추가한다.

#### TC-13: `_create_agent`가 `prompt` 파라미터를 전달하는지 확인

```python
def test_create_agent_passes_system_prompt():
    """TC-13: _create_agent()가 create_react_agent에 prompt=_SYSTEM_PROMPT를 전달한다."""
    from unittest.mock import patch, MagicMock
    from src.application.general_chat.use_case import _SYSTEM_PROMPT

    with patch("src.application.general_chat.use_case.create_react_agent") as mock_create:
        mock_create.return_value = MagicMock()
        uc = GeneralChatUseCase(...)  # 실제 의존성 주입
        uc._create_agent(tools=[])
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs.get("prompt") == _SYSTEM_PROMPT
```

> `_make_use_case`는 `_create_agent`를 MagicMock으로 패치하므로,
> TC-13은 `_make_use_case`를 사용하지 않고 직접 `create_react_agent`를 패치한다.

#### TC-14: 두 번째 메시지 시 히스토리가 에이전트 입력에 포함됨

```python
async def test_second_message_includes_history_in_context():
    """TC-14: 히스토리 2개(USER+ASSISTANT)가 있을 때 에이전트 입력에 포함된다."""
    history = [
        _make_msg(MessageRole.USER, "첫 질문", 1),
        _make_msg(MessageRole.ASSISTANT, "첫 답변", 2),
    ]
    uc, mocks = _make_use_case(history=history)
    mocks["policy"].needs_summarization = MagicMock(return_value=False)

    captured = []
    async def capture(input_dict):
        captured.extend(input_dict["messages"])
        return {"messages": [AIMessage(content="두 번째 답변")]}
    mocks["agent"].ainvoke.side_effect = capture

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="두 번째 질문")
    await uc.execute(req, request_id="req-1")

    # HumanMessage("첫 질문") + AIMessage("첫 답변") + HumanMessage("두 번째 질문") = 3개
    assert len(captured) == 3
    assert isinstance(captured[0], HumanMessage)
    assert captured[0].content == "첫 질문"
```

#### TC-15: `_SYSTEM_PROMPT`에 문맥 참고 지시 포함

```python
def test_system_prompt_contains_context_instruction():
    """TC-15: _SYSTEM_PROMPT에 '이전 대화' 지시가 포함된다."""
    from src.application.general_chat.use_case import _SYSTEM_PROMPT
    assert "이전 대화" in _SYSTEM_PROMPT
```

### 4-2. 프론트엔드 신규 테스트

**파일**: `idt_front/src/__tests__/ChatPage.test.tsx` (신규 생성)

테스트 환경: Vitest + React Testing Library

#### TC-FE-1: 마운트 시 `sessions[0].id === activeSessionId`

```typescript
it('초기 세션 id와 activeSessionId가 일치한다', () => {
    // ChatPage를 렌더링하고,
    // 첫 번째 sendChat 호출 시 session_id가
    // sessions[0].id와 동일한지 확인
});
```

#### TC-FE-2: 두 번째 sendChat 호출 시 동일한 `session_id` 사용

```typescript
it('두 번째 메시지 발송 시 같은 session_id를 사용한다', () => {
    // 첫 번째 sendChat → 두 번째 sendChat 호출 시
    // 동일한 session_id가 전달되는지 확인
});
```

---

## 5. 구현 순서 (Do Phase 참고용)

```
[백엔드]
1. TC-15 작성 → 실패 확인
2. _SYSTEM_PROMPT 수정 → TC-15 통과
3. TC-13 작성 → 실패 확인
4. _create_agent() 수정 → TC-13 통과
5. TC-14 작성 → 통과 확인 (기존 동작이 이미 히스토리 포함)
6. /verify-logging, /verify-architecture, /verify-tdd 실행

[프론트엔드]
7. TC-FE-1, TC-FE-2 작성 → 실패 확인
8. ChatPage/index.tsx 수정 → 통과 확인
```

---

## 6. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|-----------|-----------|
| `idt/src/application/general_chat/use_case.py` | 수정 | `_SYSTEM_PROMPT` + `_create_agent()` |
| `idt/tests/application/general_chat/test_use_case.py` | 수정 | TC-13, TC-14, TC-15 추가 |
| `idt_front/src/pages/ChatPage/index.tsx` | 수정 | 세션 초기화 단순화, `useEffect` 제거 |
| `idt_front/src/__tests__/ChatPage.test.tsx` | 신규 | TC-FE-1, TC-FE-2 |

---

## 7. 영향 범위

- DB 스키마 변경 없음
- API 스펙 변경 없음 (Request/Response 동일)
- 다른 UseCase/컴포넌트 변경 없음
- `SummarizationPolicy`, `_build_full_context`, `_build_summarized_context` 변경 없음
