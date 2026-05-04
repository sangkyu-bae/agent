# agent-chat-history Plan

> 에이전트별 대화 내역 분리 조회 및 ChatPage UI 연동

## 1. 배경 및 목표

### AS-IS (현재)

- `AgentChatLayout`이 `useConversationSessions(userId)`로 **전체 세션 목록**을 조회함
- 세션은 에이전트와 무관하게 flat한 리스트로 표시됨
- 사이드바에서 에이전트를 선택해도 **대화 내역이 필터링되지 않음**
- 기존 API: `GET /api/v1/conversations/sessions` (에이전트 구분 없음)

### TO-BE (목표)

- 사이드바에서 에이전트를 선택하면 **해당 에이전트의 세션만** 표시
- 백엔드 `agent-chat-history` API 3개 엔드포인트 연동
- 에이전트 선택 → 세션 목록 로드 → 세션 선택 → 메시지 로드 흐름 완성

---

## 2. API 스펙 요약 (docs/api/agent-chat-history.md)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/conversations/agents` | 대화 기록이 있는 에이전트 목록 |
| GET | `/api/v1/conversations/agents/{agent_id}/sessions` | 에이전트별 세션 목록 |
| GET | `/api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages` | 세션 메시지 조회 |

모든 엔드포인트에 `user_id` query param 필수. Bearer 토큰 인증.

---

## 3. 구현 범위

### 3-1. 타입 정의 (`src/types/chat.ts`)

```typescript
/** 에이전트별 대화 기록 — 에이전트 항목 */
interface AgentConversationItem {
  agent_id: string;
  agent_name: string;
  session_count: number;
  last_chat_at: string;
}

/** GET /api/v1/conversations/agents 응답 */
interface AgentConversationListResponse {
  user_id: string;
  agents: AgentConversationItem[];
}

/** 에이전트별 세션 항목 */
interface AgentSessionSummary {
  session_id: string;
  message_count: number;
  last_message: string;
  last_message_at: string;
}

/** GET /api/v1/conversations/agents/{agent_id}/sessions 응답 */
interface AgentSessionListResponse {
  user_id: string;
  agent_id: string;
  sessions: AgentSessionSummary[];
}

/** GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages 응답
 *  (기존 SessionMessagesResponse와 동일 구조 + agent_id 필드) */
interface AgentSessionMessagesResponse {
  user_id: string;
  agent_id: string;
  session_id: string;
  messages: HistoryMessageItem[];
}
```

### 3-2. API 상수 (`src/constants/api.ts`)

```typescript
// Conversation History — Agent-scoped (agent-chat-history)
CONVERSATION_AGENTS: '/api/v1/conversations/agents',
CONVERSATION_AGENT_SESSIONS: (agentId: string) =>
  `/api/v1/conversations/agents/${agentId}/sessions`,
CONVERSATION_AGENT_SESSION_MESSAGES: (agentId: string, sessionId: string) =>
  `/api/v1/conversations/agents/${agentId}/sessions/${sessionId}/messages`,
```

### 3-3. 서비스 레이어 (`src/services/chatService.ts`)

| 메서드 | 설명 |
|--------|------|
| `getAgentConversations(userId)` | 에이전트 목록 조회 |
| `getAgentSessions(agentId, userId)` | 에이전트별 세션 목록 → `ChatSession[]`로 변환 |
| `getAgentSessionMessages(agentId, sessionId, userId)` | 세션 메시지 → `Message[]`로 변환 |

기존 `toChatSession`, `toMessage` 매핑 함수 재활용. `AgentSessionSummary` → `ChatSession` 변환 추가.

### 3-4. 쿼리 키 (`src/lib/queryKeys.ts`)

```typescript
chat: {
  // ... 기존 유지
  /** 에이전트 목록 (대화 기록 있는) */
  agents: (userId: string) =>
    [...queryKeys.chat.all, 'agents', userId] as const,
  /** 에이전트별 세션 목록 */
  agentSessions: (agentId: string, userId: string) =>
    [...queryKeys.chat.all, 'agentSessions', agentId, userId] as const,
  /** 에이전트 세션별 메시지 */
  agentSessionMessages: (agentId: string, sessionId: string, userId: string) =>
    [...queryKeys.chat.all, 'agentSessionMessages', agentId, sessionId, userId] as const,
}
```

### 3-5. 커스텀 훅 (`src/hooks/useChat.ts`)

| 훅 | 설명 |
|----|------|
| `useAgentConversations(userId)` | 에이전트 목록 조회 (staleTime 60s) |
| `useAgentSessions(agentId, userId)` | 에이전트별 세션 목록 (agentId, userId 모두 있을 때 enabled) |
| `useAgentSessionMessages(agentId, sessionId, userId)` | 세션 메시지 (세 값 모두 있을 때 enabled) |

`useGeneralChat` 의 `onSuccess`에서 에이전트 관련 쿼리도 invalidate 추가.

### 3-6. AgentChatLayout 변경 (`src/components/layout/AgentChatLayout.tsx`)

**변경 포인트:**

1. `useConversationSessions(userId)` → `useAgentSessions(selectedAgentId, userId)` 교체
2. 에이전트 변경 시 `activeSessionId` 리셋
3. `OutletContext`에 `selectedAgentId` 전달 추가 (메시지 조회 시 필요)

```typescript
// AgentChatOutletContext 확장
interface AgentChatOutletContext {
  selectedAgent: AgentSummary | null;
  selectedAgentId: string | null;   // 추가
  activeSessionId: string | null;
  setActiveSessionId: (id: string) => void;
  handleNewChat: () => void;
  sessions: ChatSession[];
}
```

### 3-7. ChatPage 변경 (`src/pages/ChatPage/index.tsx`)

**변경 포인트:**

1. `useSessionMessages` → `useAgentSessionMessages` 교체
2. `outletContext`에서 `selectedAgentId` 받아서 사용
3. 메시지 전송 후 `agentSessions` 쿼리도 invalidate

### 3-8. agent_id 매핑 전략

| 프론트 에이전트 ID | 백엔드 agent_id | 설명 |
|-------------------|----------------|------|
| `'super-ai'` | `'super'` | SUPER AI Agent (일반 채팅) |
| UUID 기반 ID | 그대로 전달 | 커스텀 에이전트 |

`layoutStore.selectedAgentId` → 백엔드 `agent_id` 변환 유틸 필요:

```typescript
const toBackendAgentId = (frontendId: string | null): string => {
  if (!frontendId || frontendId === 'super-ai') return 'super';
  return frontendId;
};
```

---

## 4. 변경 파일 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/types/chat.ts` | **수정** | 에이전트별 타입 3개 추가 |
| `src/types/agent.ts` | **수정** | `AgentChatOutletContext`에 `selectedAgentId` 추가 |
| `src/constants/api.ts` | **수정** | 엔드포인트 상수 3개 추가 |
| `src/services/chatService.ts` | **수정** | 서비스 메서드 3개 추가 |
| `src/lib/queryKeys.ts` | **수정** | 쿼리 키 3개 추가 |
| `src/hooks/useChat.ts` | **수정** | 훅 3개 추가, `useGeneralChat` invalidation 업데이트 |
| `src/components/layout/AgentChatLayout.tsx` | **수정** | 에이전트별 세션 조회로 교체 |
| `src/pages/ChatPage/index.tsx` | **수정** | 에이전트별 메시지 조회로 교체 |
| `src/utils/agentMapping.ts` | **신규** | `toBackendAgentId` 유틸 함수 |

---

## 5. 구현 순서 (TDD)

### Phase 1: 타입 + 상수 + 유틸

1. `src/types/chat.ts` — 타입 추가
2. `src/types/agent.ts` — `AgentChatOutletContext` 확장
3. `src/constants/api.ts` — 엔드포인트 상수
4. `src/utils/agentMapping.ts` — ID 변환 유틸 + 테스트

### Phase 2: 서비스 + 쿼리 키 + 훅

5. `src/lib/queryKeys.ts` — 쿼리 키 추가
6. `src/services/chatService.ts` — API 메서드 추가
7. `src/hooks/useChat.ts` — 훅 추가 + 테스트

### Phase 3: 레이아웃 + 페이지 UI 연동

8. `src/components/layout/AgentChatLayout.tsx` — 에이전트별 세션 조회 연동
9. `src/pages/ChatPage/index.tsx` — 에이전트별 메시지 조회 연동

---

## 6. 기존 API와의 호환성

- 기존 `useConversationSessions`, `useSessionMessages` 훅은 **삭제하지 않음**
- `AgentChatLayout`에서만 새 훅으로 교체
- 기존 `CONVERSATION_SESSIONS`, `CONVERSATION_SESSION_MESSAGES` 상수도 유지
- 점진적 마이그레이션 후 안정화되면 기존 API 제거 가능

---

## 7. 테스트 전략

| 대상 | 방법 |
|------|------|
| `toBackendAgentId` 유틸 | 단위 테스트 (Vitest) |
| `useAgentSessions`, `useAgentSessionMessages` | renderHook + MSW |
| `AgentChatLayout` | 에이전트 변경 시 세션 리로드 확인 |
| `ChatPage` | 에이전트별 메시지 표시 확인 |

---

## 8. 비기능 요구사항

- `authClient` 사용 (Bearer 토큰 인증 필수)
- staleTime 60초 유지 (기존 convention 따름)
- 에이전트 변경 시 이전 세션 캐시 유지 (gcTime 5분)
- 에이전트 변경 시 draft 세션은 초기화
