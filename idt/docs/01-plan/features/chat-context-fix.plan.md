# CHAT-CONTEXT-FIX: 채팅 API 문맥 유지 버그 수정

> 상태: Plan
> 연관 Task: CHAT-001
> 작성일: 2026-04-12
> 우선순위: High

---

## 1. 문제 정의 (Problem Statement)

`POST /api/v1/chat` 에서 대화 히스토리가 DB에 저장되지만, **ReAct 에이전트가 이전 대화 문맥을 실제로 활용하지 못하는** 버그가 있다.

사용자 관점에서: 두 번째 질문부터 AI가 첫 번째 대화를 전혀 기억하지 못하는 것처럼 응답함.

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. [백엔드] 시스템 프롬프트 미전달 (Critical)

**파일**: `src/application/general_chat/use_case.py`

```python
# _SYSTEM_PROMPT 가 정의만 되고 에이전트에 전달되지 않음
_SYSTEM_PROMPT = (
    "당신은 사용자의 일반 질문에 답하는 AI 어시스턴트입니다.\n"
    ...
)

def _create_agent(self, tools: list):
    llm = ChatOpenAI(...)
    # ❌ prompt 파라미터 누락 — 에이전트는 시스템 프롬프트 없이 실행됨
    return create_react_agent(llm, tools=tools)
```

`create_react_agent`의 `prompt` 파라미터로 `_SYSTEM_PROMPT`를 전달해야 한다.
시스템 프롬프트가 없으면 에이전트는 대화 문맥을 유지해야 한다는 지시를 받지 못한다.

### 2-2. [백엔드] 시스템 프롬프트가 문맥 유지 지시를 포함하지 않음 (High)

현재 `_SYSTEM_PROMPT`에는 도구 설명만 있고, **이전 대화를 참고해야 한다는 지시가 없다.**
LLM에게 명시적으로 "이전 대화 히스토리를 참고하여 답변하라"는 지시가 필요하다.

### 2-3. [프론트엔드] activeSessionId 초기화 버그 (Medium)

**파일**: `idt_front/src/pages/ChatPage/index.tsx`

```javascript
// ❌ 두 번의 createSession() 호출 → 서로 다른 UUID 생성
const [sessions, setSessions] = useState(() => [createSession()]);   // UUID-A
const [activeSessionId, setActiveSessionId] = useState(() => {
    const first = createSession();  // UUID-B (다른 호출!)
    return first.id;
});

// useEffect로 보정하지만 첫 렌더링 시 불일치 발생
useEffect(() => {
    setActiveSessionId(sessions[0].id);
}, []);
```

`sessions[0].id`와 `activeSessionId`가 초기에 불일치 → 첫 번째 메시지의 `session_id`가
실제 활성 세션 ID와 다를 수 있음 → 이후 메시지와 다른 세션으로 저장됨.

---

## 3. 수정 범위 (Scope)

| # | 수정 위치 | 내용 | 우선순위 |
|---|-----------|------|----------|
| 1 | `use_case.py` `_create_agent()` | `create_react_agent`에 `prompt=_SYSTEM_PROMPT` 전달 | Critical |
| 2 | `use_case.py` `_SYSTEM_PROMPT` | 대화 문맥 참고 지시 추가 | High |
| 3 | `ChatPage/index.tsx` | `activeSessionId` 초기화 단일 `createSession()` 호출로 통합 | Medium |

---

## 4. 수정 방향 (Solution Design)

### 4-1. 백엔드: 시스템 프롬프트 전달

```python
# 수정 후
_SYSTEM_PROMPT = (
    "당신은 사용자의 일반 질문에 답하는 AI 어시스턴트입니다.\n"
    "이전 대화 내용이 있다면 반드시 참고하여 문맥에 맞게 답변하세요.\n"
    "필요에 따라 다음 도구를 사용하세요:\n"
    "- tavily_search: 최신 웹 정보 검색\n"
    "- internal_document_search: 내부 문서(금융/정책 등) 검색\n"
    "- MCP 도구: 등록된 외부 서비스 연동\n"
    "항상 한국어로 답변하세요."
)

def _create_agent(self, tools: list):
    llm = ChatOpenAI(
        model=self._model_name,
        api_key=self._api_key or None,
        temperature=0,
    )
    # ✅ prompt 파라미터 전달
    return create_react_agent(llm, tools=tools, prompt=_SYSTEM_PROMPT)
```

### 4-2. 프론트엔드: 세션 초기화 통합

```typescript
// 수정 후 — 단일 createSession() 호출
const ChatPage = () => {
    const initialSession = createSession();  // 한 번만 생성
    const [sessions, setSessions] = useState<ChatSession[]>([initialSession]);
    const [activeSessionId, setActiveSessionId] = useState<string>(initialSession.id);
    // useEffect 불필요 → 제거
    ...
};
```

---

## 5. 영향 범위 (Impact)

### 변경 파일 목록
- `idt/src/application/general_chat/use_case.py` (백엔드)
- `idt_front/src/pages/ChatPage/index.tsx` (프론트엔드)

### 영향을 받지 않는 것
- DB 스키마 변경 없음
- API 스펙 변경 없음 (Request/Response 동일)
- 다른 UseCase 변경 없음
- 요약 정책(SummarizationPolicy) 변경 없음

---

## 6. TDD 계획

### 백엔드 테스트 (수정/추가)

**파일**: `tests/application/general_chat/test_use_case.py`

| 테스트 케이스 | 설명 |
|--------------|------|
| `test_create_agent_passes_system_prompt` | `_create_agent()` 호출 시 `prompt=_SYSTEM_PROMPT` 전달 확인 |
| `test_second_message_includes_history_in_context` | 두 번째 메시지 시 히스토리가 에이전트 입력에 포함됨 |
| `test_system_prompt_contains_context_instruction` | `_SYSTEM_PROMPT`에 "이전 대화" 문구 포함 확인 |

### 프론트엔드 테스트 (수정/추가)

**파일**: `idt_front/src/__tests__/ChatPage.test.tsx`

| 테스트 케이스 | 설명 |
|--------------|------|
| `test_initial_session_id_matches_active_session` | 마운트 시 `sessions[0].id === activeSessionId` 확인 |
| `test_subsequent_message_uses_same_session_id` | 두 번째 sendChat 호출 시 동일한 `session_id` 사용 확인 |

---

## 7. 완료 기준 (Definition of Done)

- [ ] 백엔드: `create_react_agent`에 `_SYSTEM_PROMPT` 전달
- [ ] 백엔드: `_SYSTEM_PROMPT`에 "이전 대화 참고" 지시 포함
- [ ] 프론트엔드: 초기 `sessions[0].id === activeSessionId` 보장
- [ ] 백엔드 신규 테스트 3개 통과
- [ ] 프론트엔드 신규 테스트 2개 통과
- [ ] 실제 멀티턴 대화에서 두 번째 질문부터 이전 대화 문맥 유지 확인
- [ ] `/verify-logging` 통과
- [ ] `/verify-architecture` 통과
- [ ] `/verify-tdd` 통과

---

## 8. 참고 문서

- `src/claude/task/task-general-chat-api.md` (CHAT-001)
- `src/claude/task/task-logging.md` (LOG-001)
- `src/application/general_chat/use_case.py`
- `idt_front/src/pages/ChatPage/index.tsx`
