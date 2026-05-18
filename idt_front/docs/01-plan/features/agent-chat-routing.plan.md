# Plan: Agent Chat API Routing

> Feature: `agent-chat-routing`  
> Phase: Plan  
> Created: 2026-05-11  
> Author: 배상규

---

## 1. 배경 및 목표

### 배경

현재 ChatPage에서 에이전트를 선택하고 채팅을 보내도, 항상 `POST /api/v1/chat` (General Chat API)로 요청이 전달된다.
에이전트별 전용 API인 `POST /api/v1/agents/{agent_id}/run`이 이미 구현되어 있으나, 프론트엔드에서 호출하지 않고 있다.

### 문제

- 특정 에이전트를 선택했을 때도 SUPER AI Agent(범용 Chat)로 요청이 감 → 에이전트별 커스텀 워크플로우 미적용
- 멀티턴 대화 시 에이전트 전용 session_id 관리가 되지 않음
- tools_used 응답 필드가 활용되지 않음

### 목표

에이전트 선택 여부에 따라 API 호출을 분기하여:
- **에이전트 미선택 (SUPER AI Agent)**: 기존 `POST /api/v1/chat` 유지
- **에이전트 선택됨**: `POST /api/v1/agents/{agent_id}/run` 호출

---

## 2. 구현 범위

### In Scope

| 항목 | 설명 |
|------|------|
| 엔드포인트 추가 | `API_ENDPOINTS.AGENT_CHAT_RUN` — `/api/v1/agents/${agentId}/run` |
| 타입 추가 | `AgentChatRequest`, `AgentChatResponse` |
| 서비스 추가 | `chatService.agentChat(agentId, payload)` |
| 훅 추가 | `useAgentChat()` — useMutation 기반 |
| ChatPage 분기 로직 | `selectedAgent` 유무에 따라 `useGeneralChat` / `useAgentChat` 분기 |
| 응답 매핑 | `AgentChatResponse` → 기존 `Message` 타입으로 변환 |
| session_id 관리 | 에이전트 채팅도 멀티턴 세션 유지 (응답의 session_id 활용) |

### Out of Scope

| 항목 | 이유 |
|------|------|
| SSE 스트리밍 | 1차에서는 동기 응답만 지원, 추후 별도 task |
| UI 차별화 (tools_used 표시 등) | 현재는 UI 동일 유지 |
| 에이전트별 RAG 설정 | 백엔드 에이전트 정의에서 처리됨 |

---

## 3. API 스펙 (백엔드 참조)

### POST /api/v1/agents/{agent_id}/run

**인증**: `Authorization: Bearer {access_token}` (필수)

**Path Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| agent_id | string | Yes | 실행할 에이전트 ID |

**Request Body**:

```json
{
  "query": "string",       // 필수, 1~2000자
  "user_id": "string",     // 필수
  "session_id": "string"   // 선택 (null이면 새 세션 생성)
}
```

**Response 200 OK**:

```json
{
  "agent_id": "abc-123",
  "query": "원래 보낸 질문",
  "answer": "에이전트 응답 텍스트",
  "tools_used": ["internal_document_search", "web_search"],
  "request_id": "uuid-xxx",
  "session_id": "session-uuid"
}
```

**Error Responses**:

| Status | Condition |
|--------|-----------|
| 403 Forbidden | 실행 권한 없음 (비공개 에이전트, 부서 제한) |
| 404 Not Found | agent_id에 해당하는 에이전트 없음 |
| 422 Unprocessable Entity | 유효성 검증 실패 |

**멀티턴 흐름**:
- 1회차: `session_id = null` → 응답의 `session_id` 수신
- 2회차~: 받은 `session_id` 재사용 → 컨텍스트 유지

---

## 4. 구현 순서

### Step 1: 타입 정의

**파일**: `src/types/chat.ts`

```typescript
// Agent Chat Request/Response
export interface AgentChatRequest {
  query: string;
  user_id: string;
  session_id: string | null;
}

export interface AgentChatResponse {
  agent_id: string;
  query: string;
  answer: string;
  tools_used: string[];
  request_id: string;
  session_id: string;
}
```

### Step 2: 엔드포인트 상수 추가

**파일**: `src/constants/api.ts`

```typescript
// 기존 AGENT_RUN은 legacy로 유지
AGENT_CHAT_RUN: (agentId: string) => `/api/v1/agents/${agentId}/run`,
```

### Step 3: 서비스 메서드 추가

**파일**: `src/services/chatService.ts`

```typescript
/** Agent Run API — 특정 에이전트로 채팅 전송 */
agentChat: (agentId: string, payload: AgentChatRequest) =>
  authClient.post<AgentChatResponse>(
    API_ENDPOINTS.AGENT_CHAT_RUN(agentId),
    payload,
  ),
```

### Step 4: 훅 추가

**파일**: `src/hooks/useChat.ts`

```typescript
/** 에이전트 전용 채팅 뮤테이션 */
export const useAgentChat = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, ...payload }: AgentChatRequest & { agentId: string }) =>
      chatService.agentChat(agentId, payload).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.chat.agentHistory(data.agent_id, data./* userId */),
      });
    },
  });
};
```

### Step 5: ChatPage 분기 로직

**파일**: `src/pages/ChatPage/index.tsx`

핵심 변경:

```typescript
const { mutate: sendGeneralChat, isPending: isGeneralPending } = useGeneralChat();
const { mutate: sendAgentChat, isPending: isAgentPending } = useAgentChat();
const isPending = isGeneralPending || isAgentPending;

const handleSend = (content: string) => {
  if (!activeSessionId) return;

  // ... userMessage 추가 로직 동일

  if (selectedAgent) {
    // 에이전트 선택됨 → Agent Run API
    sendAgentChat(
      {
        agentId: selectedAgent.id,
        query: content,
        user_id: userId ?? '',
        session_id: isDraftSession ? null : activeSessionId,
      },
      {
        onSuccess: (data) => {
          syncSessionId(currentSessionId, data.session_id);
          const assistantMessage: Message = {
            id: data.request_id,
            role: 'assistant',
            content: data.answer,
            createdAt: new Date().toISOString(),
          };
          addMessage(data.session_id, assistantMessage);
          // 세션 목록 갱신
        },
        onError: () => { /* 에러 메시지 */ },
      },
    );
  } else {
    // SUPER AI Agent → General Chat API (기존 로직)
    sendGeneralChat({ ... }, { ... });
  }
};
```

---

## 5. 주요 고려사항

### 5-1. session_id 관리

| 상태 | General Chat | Agent Chat |
|------|-------------|------------|
| 새 대화 시작 | `session_id: currentSessionId` | `session_id: null` |
| 이어서 대화 | 그대로 전달 | 응답에서 받은 session_id 전달 |

현재 General Chat은 클라이언트에서 생성한 session_id를 사용하지만,
Agent Chat은 서버에서 세션을 생성하므로 **첫 요청은 `null`**, 이후 서버 응답의 `session_id`를 재사용한다.

→ `isDraftSession`(새 대화)이면 `null`로 전송, 기존 세션이면 activeSessionId 전달

### 5-2. 에러 처리

- 403: "이 에이전트의 실행 권한이 없습니다" 메시지
- 404: "에이전트를 찾을 수 없습니다" 메시지
- 나머지: 기존 공통 에러 처리 유지

### 5-3. 인증

Agent Run API는 `Authorization: Bearer` 필수 → `authClient` 사용

---

## 6. 영향 범위

| 파일 | 변경 유형 |
|------|-----------|
| `src/types/chat.ts` | 타입 추가 (AgentChatRequest, AgentChatResponse) |
| `src/constants/api.ts` | 엔드포인트 상수 추가 |
| `src/services/chatService.ts` | agentChat 메서드 추가 |
| `src/hooks/useChat.ts` | useAgentChat 훅 추가 |
| `src/pages/ChatPage/index.tsx` | handleSend 분기 로직 |

---

## 7. 테스트 계획

| 테스트 | 검증 내용 |
|--------|-----------|
| useAgentChat 훅 단위 테스트 | 올바른 엔드포인트로 요청 전송, 응답 매핑 |
| ChatPage 통합 테스트 | 에이전트 선택 시 Agent Run API 호출 확인 |
| 멀티턴 세션 테스트 | 첫 요청 null → 응답 session_id 재사용 확인 |
| 에러 케이스 | 403/404 시 적절한 에러 메시지 표시 |

---

## 8. 완료 기준

- [ ] SUPER AI Agent 선택 시 기존 General Chat API로 정상 동작
- [ ] 특정 에이전트 선택 시 `/api/v1/agents/{id}/run`으로 요청 전송
- [ ] 멀티턴 대화 (session_id 재활용) 정상 동작
- [ ] 에러 시 사용자 친화적 메시지 표시
- [ ] 기존 에이전트 세션 히스토리 조회 정상 유지
