# Plan: Agent Session Switching (에이전트 전환 시 세션/채팅 동기화)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-session-switching |
| 작성일 | 2026-05-09 |
| 예상 소요 | 2~3시간 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 에이전트를 전환하면 메인 채팅 헤더 텍스트("~~와 대화하세요")만 바뀌고, 사이드 세션 목록과 채팅 내역이 전혀 갱신되지 않아 항상 동일한 세션을 보게 됨 |
| **Solution** | 기존 전체 세션 조회(`GET /conversations/sessions`)를 에이전트별 세션 조회(`GET /conversations/agents/{agent_id}/sessions`)로 교체하고, 에이전트 전환 시 세션/메시지 query를 자동 재요청 |
| **Function UX Effect** | Super AI 클릭 → Super AI 세션 목록 + 채팅 표시, 다른 에이전트 클릭 → 해당 에이전트 세션 목록 + 채팅 표시. 에이전트별 대화 이력이 완전히 분리됨 |
| **Core Value** | 멀티 에이전트 플랫폼에서 에이전트 전환이 실질적으로 동작하여, 각 에이전트와의 독립적 대화 관리가 가능해짐 |

---

## 1. 현재 상황 분석 (버그 원인)

### 1.1 현재 데이터 흐름

```
사용자 → AppSidebar에서 에이전트 클릭
       → layoutStore.selectedAgentId 업데이트 ✅
       → AgentChatLayout.selectedAgent 변경 ✅
       → ChatPage 헤더 텍스트 변경 ✅ ("~~와 대화하세요")
       → 세션 목록 갱신 ❌ (query가 selectedAgentId를 참조 안 함)
       → 채팅 메시지 갱신 ❌ (세션이 안 바뀌니 메시지도 그대로)
```

### 1.2 버그 원인 상세

| 파일 | 줄 | 문제 |
|------|-----|------|
| `src/hooks/useChat.ts` | 58-64 | `useConversationSessions(userId)` — `selectedAgentId`를 인자로 받지 않음 |
| `src/lib/queryKeys.ts` | 23-24 | `history: (userId)` — agent_id가 queryKey에 포함되지 않아 에이전트 전환 시 캐시 재사용 |
| `src/services/chatService.ts` | 54-60 | `getConversationSessions(userId)` — 백엔드에 agent_id 파라미터 미전달 |
| `src/constants/api.ts` | 16-17 | 에이전트별 세션 API 엔드포인트 상수 미정의 |
| `src/components/layout/AgentChatLayout.tsx` | 39-44 | `useConversationSessions(userId)` — agent_id 미전달 |

### 1.3 백엔드 API (이미 구현됨)

백엔드에는 에이전트별 세션/메시지 API가 이미 존재한다:

| Method | Endpoint | 용도 |
|--------|----------|------|
| `GET` | `/api/v1/conversations/agents` | 대화 기록이 있는 에이전트 목록 |
| `GET` | `/api/v1/conversations/agents/{agent_id}/sessions` | 에이전트별 세션 목록 |
| `GET` | `/api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages` | 에이전트 세션의 메시지 목록 |

현재 프론트엔드는 이 API를 전혀 사용하지 않고, 에이전트 구분 없는 전체 세션 API(`GET /api/v1/conversations/sessions`)만 호출하고 있다.

---

## 2. 구현 범위

### 2.1 In-Scope

| # | 항목 | 설명 |
|---|------|------|
| 1 | API 엔드포인트 상수 추가 | `src/constants/api.ts` — 에이전트별 세션/메시지 엔드포인트 |
| 2 | chatService 확장 | 에이전트별 세션 조회 + 에이전트별 메시지 조회 메서드 추가 |
| 3 | queryKeys 확장 | `agentHistory`, `agentSessionMessages` 키 추가 (agent_id 포함) |
| 4 | useChat 훅 수정 | `useConversationSessions` → agent_id 의존 버전으로 교체 |
| 5 | AgentChatLayout 수정 | selectedAgentId를 세션 쿼리에 전달, 에이전트 전환 시 activeSessionId 초기화 |
| 6 | ChatPage 수정 | 에이전트별 메시지 API 사용, generalChat에 agent_id 전달 |

### 2.2 Out-of-Scope

- Super AI Agent의 에이전트 라우팅 로직 (백엔드 책임)
- 에이전트별 세션 생성 시 agent_id 자동 바인딩 (현재 generalChat API가 처리)
- 세션 삭제/이름 변경 기능

---

## 3. 구현 순서

### Step 1: API 엔드포인트 상수 추가 (`src/constants/api.ts`)

```typescript
// Conversation History — Agent-scoped
CONVERSATION_AGENTS: '/api/v1/conversations/agents',
CONVERSATION_AGENT_SESSIONS: (agentId: string) =>
  `/api/v1/conversations/agents/${agentId}/sessions`,
CONVERSATION_AGENT_SESSION_MESSAGES: (agentId: string, sessionId: string) =>
  `/api/v1/conversations/agents/${agentId}/sessions/${sessionId}/messages`,
```

### Step 2: chatService 확장 (`src/services/chatService.ts`)

```typescript
/** 에이전트별 세션 목록 조회 */
getAgentSessions: async (agentId: string, userId: string): Promise<ChatSession[]> => {
  const res = await apiClient.get<AgentSessionListResponse>(
    API_ENDPOINTS.CONVERSATION_AGENT_SESSIONS(agentId),
    { params: { user_id: userId } },
  );
  return res.data.sessions.map(toChatSession);
},

/** 에이전트 세션의 메시지 조회 */
getAgentSessionMessages: async (
  agentId: string, sessionId: string, userId: string
): Promise<Message[]> => {
  const res = await apiClient.get<AgentMessageListResponse>(
    API_ENDPOINTS.CONVERSATION_AGENT_SESSION_MESSAGES(agentId, sessionId),
    { params: { user_id: userId } },
  );
  return res.data.messages.map(toMessage);
},
```

### Step 3: queryKeys 확장 (`src/lib/queryKeys.ts`)

```typescript
chat: {
  // ... 기존 유지
  /** 에이전트별 세션 목록 */
  agentHistory: (agentId: string, userId: string) =>
    [...queryKeys.chat.all, 'agentHistory', agentId, userId] as const,
  /** 에이전트별 세션 메시지 */
  agentSessionMessages: (agentId: string, sessionId: string, userId: string) =>
    [...queryKeys.chat.all, 'agentSessionMessages', agentId, sessionId, userId] as const,
},
```

### Step 4: useChat 훅 추가/수정 (`src/hooks/useChat.ts`)

```typescript
/** 에이전트별 세션 목록 (에이전트 전환 시 자동 재요청) */
export const useAgentSessions = (agentId: string | null, userId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.chat.agentHistory(agentId ?? '', userId ?? ''),
    queryFn: () => chatService.getAgentSessions(agentId!, userId!),
    enabled: !!agentId && !!userId,
    staleTime: 60_000,
  });

/** 에이전트별 세션 메시지 */
export const useAgentSessionMessages = (
  agentId: string | null,
  sessionId: string | null,
  userId: string | undefined,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: queryKeys.chat.agentSessionMessages(agentId ?? '', sessionId ?? '', userId ?? ''),
    queryFn: () => chatService.getAgentSessionMessages(agentId!, sessionId!, userId!),
    enabled: !!agentId && !!sessionId && !!userId && (options?.enabled ?? true),
    staleTime: 60_000,
  });
```

### Step 5: AgentChatLayout 수정 (`src/components/layout/AgentChatLayout.tsx`)

핵심 변경:
1. `useConversationSessions(userId)` → `useAgentSessions(selectedAgentId, userId)` 교체
2. `selectedAgentId` 변경 시 `activeSessionId`를 초기화 (첫 번째 세션 또는 새 드래프트)
3. `draftSessions`를 에이전트별로 관리 (`Record<string, ChatSession[]>`)
4. outletContext에 `selectedAgentId` 추가 전달

```typescript
// 에이전트 전환 시 세션 초기화
useEffect(() => {
  if (selectedAgentId) {
    setActiveSessionId(null); // → 서버 세션 로드 후 첫 세션 or 새 드래프트 자동 선택
  }
}, [selectedAgentId]);
```

### Step 6: ChatPage 수정 (`src/pages/ChatPage/index.tsx`)

1. `useSessionMessages` → `useAgentSessionMessages`로 교체 (agent_id 포함)
2. `useGeneralChat` onSuccess 시 `queryKeys.chat.agentHistory` invalidate
3. generalChat 요청에 `agent_id` 필드 전달 (백엔드에서 세션-에이전트 바인딩)

---

## 4. 상세 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `src/constants/api.ts` | 3개 엔드포인트 상수 추가 |
| `src/types/chat.ts` | `AgentSessionListResponse`, `AgentMessageListResponse` 타입 추가 |
| `src/services/chatService.ts` | `getAgentSessions`, `getAgentSessionMessages` 메서드 추가 |
| `src/lib/queryKeys.ts` | `agentHistory`, `agentSessionMessages` 키 추가 |
| `src/hooks/useChat.ts` | `useAgentSessions`, `useAgentSessionMessages` 훅 추가 |
| `src/components/layout/AgentChatLayout.tsx` | 세션 쿼리를 에이전트별로 교체, 에이전트 전환 시 초기화 |
| `src/pages/ChatPage/index.tsx` | 메시지 쿼리를 에이전트별로 교체, generalChat에 agent_id 전달 |

---

## 5. 에이전트 전환 시 기대 동작

```
1. AppSidebar에서 "Super AI" 클릭
   → layoutStore.selectedAgentId = "super"
   → useAgentSessions("super", userId) 호출
   → 사이드 패널에 Super AI 세션 목록 표시
   → activeSessionId = 첫 번째 세션 또는 새 드래프트
   → ChatPage에 해당 세션 메시지 표시

2. AppSidebar에서 "마케팅 Agent" 클릭
   → layoutStore.selectedAgentId = "agent-abc-123"
   → useAgentSessions("agent-abc-123", userId) 호출
   → 사이드 패널에 마케팅 Agent 세션 목록 표시
   → activeSessionId = 첫 번째 세션 또는 새 드래프트
   → ChatPage에 해당 세션 메시지 표시
```

---

## 6. 에러 처리

| 상황 | 처리 |
|------|------|
| 에이전트 세션 조회 실패 | ChatHistoryPanel에 에러 상태 + 재시도 버튼 (기존 패턴 재사용) |
| 해당 에이전트 세션 0건 | 자동으로 새 드래프트 세션 생성, EmptyAgentState 표시 |
| 메시지 조회 실패 | 기존 에러 처리 패턴 유지 |

---

## 7. 테스트 계획

| 대상 | 파일 | 테스트 항목 |
|------|------|-----------|
| chatService | `chatService.test.ts` | `getAgentSessions`, `getAgentSessionMessages` URL/파라미터 검증 |
| useAgentSessions | `useChat.test.ts` | agentId 변경 시 자동 refetch, enabled 조건 |
| AgentChatLayout | `AgentChatLayout.test.tsx` | 에이전트 전환 → 세션 목록 교체 → activeSessionId 초기화 |

---

## 8. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 에이전트 전환 시 이전 세션의 로컬 메시지(draft) 유실 | `messagesBySession`은 sessionId 키이므로 에이전트 전환과 무관하게 보존됨 |
| Super AI agent_id가 "super"로 하드코딩 | 백엔드에서 agent_id="super"를 일반 채팅 식별자로 사용 중이므로 그대로 활용 |
| generalChat API에 agent_id 필드 미지원 | 백엔드 `POST /api/v1/chat` 스키마 확인 필요 — 미지원 시 세션 생성 후 바인딩 방식 검토 |
