# Design: Agent Session Switching (에이전트 전환 시 세션/채팅 동기화)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-session-switching |
| Plan 참조 | `docs/01-plan/features/agent-session-switching.plan.md` |
| 작성일 | 2026-05-09 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 에이전트를 전환하면 헤더 텍스트만 바뀌고, 세션 목록/채팅 내역이 전혀 갱신되지 않음 |
| **Solution** | 에이전트별 세션 API 연동 + queryKey에 agent_id 포함하여 전환 시 자동 refetch |
| **Function UX Effect** | 에이전트 클릭 → 해당 에이전트의 세션 목록 + 채팅 이력이 즉시 표시 |
| **Core Value** | 멀티 에이전트 플랫폼에서 에이전트별 독립적 대화 관리 실현 |

---

## 1. 아키텍처 개요

### 1.1 현재 (버그 상태)

```
AppSidebar(에이전트 클릭)
  → layoutStore.selectedAgentId = "agent-xyz" ✅
  → AgentChatLayout.selectedAgent 변경 ✅
  → ChatPage 헤더 "~~와 대화하세요" ✅
  → useConversationSessions(userId) ❌ agent_id 미참조
  → 세션 목록/채팅 변화 없음 ❌
```

### 1.2 수정 후 (목표)

```
AppSidebar(에이전트 클릭) 또는 NAV "SUPER AI 에이전트" 클릭
  → layoutStore.selectedAgentId 업데이트
  → useAgentSessions(selectedAgentId, userId) 자동 재요청
  → ChatHistoryPanel에 해당 에이전트 세션 표시
  → activeSessionId 초기화 (첫 세션 or 드래프트)
  → ChatPage에 해당 세션 메시지 표시
```

### 1.3 데이터 흐름도

```
┌────────────────────────────────────────────────────────────┐
│  AppSidebar                                                │
│  ┌─────────────────┐   ┌───────────────────────────────┐   │
│  │ NAV: SUPER AI   │──▶│ selectAgent("super")          │   │
│  │ (handleNavClick  │   │ + navigate("/chatpage")       │   │
│  │ + selectAgent)   │   └──────────┬────────────────────┘   │
│  ├─────────────────┤              │                        │
│  │ Agent: 마케팅    │──▶ selectAgent("agent-abc-123")      │
│  └─────────────────┘              │                        │
└───────────────────────────────────┼────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────┐
│  layoutStore.selectedAgentId  (Zustand, persisted)         │
└───────────────────────────────┬────────────────────────────┘
                                ▼
┌────────────────────────────────────────────────────────────┐
│  AgentChatLayout                                           │
│                                                            │
│  useAgentSessions(selectedAgentId, userId)                 │
│    queryKey: ['chat', 'agentHistory', agentId, userId]     │
│    → GET /api/v1/conversations/agents/{agentId}/sessions   │
│                                                            │
│  useEffect: selectedAgentId 변경 시                         │
│    → activeSessionId = null (초기화)                        │
│    → draftSessions 유지 (에이전트별 분리 불필요)              │
│                                                            │
│  sessions = [...drafts, ...serverSessions]                 │
│  → 서버 세션 로드 후 첫 세션 자동 선택 or 드래프트 유지       │
│                                                            │
│  outletContext = { selectedAgent, activeSessionId, ... }    │
└───────────────┬──────────────────────┬─────────────────────┘
                ▼                      ▼
┌──────────────────────┐  ┌─────────────────────────────────┐
│  ChatHistoryPanel    │  │  ChatPage                       │
│  (세션 목록 표시)     │  │                                 │
│  - 에이전트별 세션    │  │  useAgentSessionMessages(       │
│  - 검색/필터         │  │    agentId, sessionId, userId   │
│  - 새 채팅 버튼      │  │  )                              │
│                      │  │  → GET .../agents/{id}/sessions │
│                      │  │       /{sessionId}/messages     │
│                      │  │                                 │
│                      │  │  generalChat 성공 시:            │
│                      │  │  → invalidate agentHistory      │
└──────────────────────┘  └─────────────────────────────────┘
```

---

## 2. 상세 설계

### 2.1 Agent ID 규약

| 구분 | agent_id 값 | 출처 |
|------|------------|------|
| Super AI (일반 채팅) | `"super"` | 백엔드 `SUPER_AGENT_ID = "super"` |
| 커스텀 에이전트 | UUID 문자열 | 백엔드 `agent_definition.agent_id` |

**현재 문제**: 프론트엔드에서 Super AI의 ID가 `"super-ai"`로 하드코딩되어 있고, 백엔드에서는 `"super"`를 사용한다.

**수정**: 프론트엔드의 Super AI 식별자를 `"super"`로 통일한다.

| 파일 | 변경 |
|------|------|
| `src/store/layoutStore.ts:16` | `selectedAgentId: 'super-ai'` → `'super'` |
| `src/components/layout/AppSidebar.tsx:17` | NAV_ITEMS `id: 'super-ai'` → `'super'` |

### 2.2 API 엔드포인트 상수 — `src/constants/api.ts`

```typescript
// Conversation History — Agent-scoped (신규 추가)
CONVERSATION_AGENT_SESSIONS: (agentId: string) =>
  `/api/v1/conversations/agents/${agentId}/sessions`,
CONVERSATION_AGENT_SESSION_MESSAGES: (agentId: string, sessionId: string) =>
  `/api/v1/conversations/agents/${agentId}/sessions/${sessionId}/messages`,
```

기존 `CONVERSATION_SESSIONS`는 삭제하지 않는다 (하위호환).

### 2.3 타입 정의 — `src/types/chat.ts`

기존 타입 재사용 가능. 백엔드 에이전트별 세션 응답의 sessions 필드는 기존 `SessionSummary[]`와 동일한 구조.

```typescript
/** 에이전트별 세션 목록 응답 */
export interface AgentSessionListResponse {
  user_id: string;
  agent_id: string;
  sessions: SessionSummary[];
}

/** 에이전트별 세션 메시지 응답 */
export interface AgentSessionMessagesResponse {
  user_id: string;
  agent_id: string;
  session_id: string;
  messages: HistoryMessageItem[];
}
```

### 2.4 서비스 레이어 — `src/services/chatService.ts`

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
  agentId: string,
  sessionId: string,
  userId: string,
): Promise<Message[]> => {
  const res = await apiClient.get<AgentSessionMessagesResponse>(
    API_ENDPOINTS.CONVERSATION_AGENT_SESSION_MESSAGES(agentId, sessionId),
    { params: { user_id: userId } },
  );
  return res.data.messages.map(toMessage);
},
```

### 2.5 Query Keys — `src/lib/queryKeys.ts`

```typescript
chat: {
  all: ['chat'] as const,
  sessions: () => [...queryKeys.chat.all, 'sessions'] as const,
  session: (sessionId: string) => [...queryKeys.chat.sessions(), sessionId] as const,
  history: (userId: string) => [...queryKeys.chat.all, 'history', userId] as const,
  sessionMessages: (sessionId: string, userId: string) =>
    [...queryKeys.chat.all, 'sessionMessages', sessionId, userId] as const,

  // ── 신규 추가 ──
  /** 에이전트별 세션 목록 */
  agentHistory: (agentId: string, userId: string) =>
    [...queryKeys.chat.all, 'agentHistory', agentId, userId] as const,
  /** 에이전트별 세션 메시지 */
  agentSessionMessages: (agentId: string, sessionId: string, userId: string) =>
    [...queryKeys.chat.all, 'agentSessionMessages', agentId, sessionId, userId] as const,
},
```

**핵심**: `agentHistory` queryKey에 `agentId`가 포함되므로, `selectedAgentId`가 변경되면 TanStack Query가 자동으로 새로운 queryKey에 대해 fetch를 실행한다.

### 2.6 TanStack Query 훅 — `src/hooks/useChat.ts`

```typescript
/** 에이전트별 세션 목록 (에이전트 전환 시 자동 재요청) */
export const useAgentSessions = (
  agentId: string | null,
  userId: string | undefined,
) =>
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
    queryKey: queryKeys.chat.agentSessionMessages(
      agentId ?? '', sessionId ?? '', userId ?? '',
    ),
    queryFn: () =>
      chatService.getAgentSessionMessages(agentId!, sessionId!, userId!),
    enabled: !!agentId && !!sessionId && !!userId && (options?.enabled ?? true),
    staleTime: 60_000,
  });
```

### 2.7 AgentChatLayout 수정 — `src/components/layout/AgentChatLayout.tsx`

#### 변경 사항

| # | 변경 | 상세 |
|---|------|------|
| 1 | import 변경 | `useConversationSessions` → `useAgentSessions` |
| 2 | 세션 쿼리 변경 | `useConversationSessions(userId)` → `useAgentSessions(selectedAgentId, userId)` |
| 3 | 에이전트 전환 시 초기화 | `selectedAgentId` 변경 → `activeSessionId = null`, `draftSessions = [newDraft]` |
| 4 | 서버 세션 로드 후 자동 선택 | 서버 세션이 있으면 첫 번째 세션 선택, 없으면 드래프트 유지 |
| 5 | outletContext 확장 | `selectedAgentId` 추가 전달 |

#### 에이전트 전환 시 초기화 로직

```typescript
// selectedAgentId 변경 시 세션 상태 초기화
useEffect(() => {
  const newDraft = createDraftSession();
  setDraftSessions([newDraft]);
  setActiveSessionId(newDraft.id);
}, [selectedAgentId]);

// 서버 세션 로드 완료 후 → 서버 세션 있으면 첫 번째 선택
useEffect(() => {
  if (serverSessions.length > 0 && activeSessionId) {
    const isDraft = draftSessions.some((d) => d.id === activeSessionId);
    if (isDraft) {
      setActiveSessionId(serverSessions[0].id);
    }
  }
}, [serverSessions]);
```

#### NAV "SUPER AI 에이전트" 클릭 처리

현재 `NAV_ITEMS`의 "SUPER AI 에이전트" 클릭은 `handleNavClick(item.path)`만 호출하여 라우팅만 한다. `selectAgent`를 함께 호출해야 한다.

```typescript
// AppSidebar.tsx — NAV_ITEMS 클릭 핸들러 수정
const handleNavClick = (item: typeof NAV_ITEMS[number]) => {
  if (item.id === 'super') {
    onSelectAgent('super');
  }
  navigate(item.path);
};
```

### 2.8 ChatPage 수정 — `src/pages/ChatPage/index.tsx`

#### 변경 사항

| # | 변경 | 상세 |
|---|------|------|
| 1 | outletContext 확장 | `selectedAgentId` 사용 |
| 2 | 메시지 쿼리 교체 | `useSessionMessages` → `useAgentSessionMessages` |
| 3 | generalChat invalidation | 성공 시 `agentHistory` invalidate |

```typescript
// 메시지 쿼리: 에이전트별 API 사용
const { data: serverMessages } = useAgentSessionMessages(
  selectedAgent?.id ?? null,
  activeSessionId,
  userId,
  { enabled: !!activeSessionId && !isDraftSession },
);
```

### 2.9 AgentChatOutletContext 확장 — `src/types/agent.ts`

```typescript
export interface AgentChatOutletContext {
  selectedAgent: AgentSummary | null;
  activeSessionId: string | null;
  setActiveSessionId: (id: string) => void;
  handleNewChat: () => void;
  sessions: import('@/types/chat').ChatSession[];
  refetchSessions: () => void;  // 신규: generalChat 성공 후 세션 갱신용
}
```

### 2.10 generalChat 연동 — 세션-에이전트 바인딩

현재 백엔드 `POST /api/v1/chat`의 `GeneralChatRequest`에는 `agent_id` 필드가 없다. 메시지 저장 시 하드코딩으로 `AgentId.super()`를 사용한다.

**대응 방안**:
- 현재 generalChat API는 Super AI 전용이므로 `agent_id="super"` 바인딩은 정상
- 커스텀 에이전트 채팅은 별도 API (`POST /api/v1/agents/{id}/run` 등)를 통해 처리될 예정
- 이번 스코프에서는 generalChat을 Super AI 에이전트 전용으로 유지하고, 다른 에이전트 선택 시에는 기존 세션 히스토리 조회만 지원

---

## 3. 구현 순서 체크리스트

```
[ ] Step 1: src/constants/api.ts — 에이전트별 API 엔드포인트 상수 추가
[ ] Step 2: src/types/chat.ts — AgentSessionListResponse, AgentSessionMessagesResponse 타입 추가
[ ] Step 3: src/types/agent.ts — AgentChatOutletContext에 refetchSessions 추가
[ ] Step 4: src/services/chatService.ts — getAgentSessions, getAgentSessionMessages 메서드 추가
[ ] Step 5: src/lib/queryKeys.ts — agentHistory, agentSessionMessages 키 추가
[ ] Step 6: src/hooks/useChat.ts — useAgentSessions, useAgentSessionMessages 훅 추가
[ ] Step 7: src/store/layoutStore.ts — selectedAgentId 초기값 "super-ai" → "super" 변경
[ ] Step 8: src/components/layout/AppSidebar.tsx — NAV_ITEMS id 변경 + 클릭 시 selectAgent 호출
[ ] Step 9: src/components/layout/AgentChatLayout.tsx — 세션 쿼리 교체 + 전환 초기화 로직
[ ] Step 10: src/pages/ChatPage/index.tsx — 메시지 쿼리 교체 + invalidation 수정
```

---

## 4. 파일별 변경 요약

| 파일 | 변경 유형 | LOC (추정) |
|------|----------|-----------|
| `src/constants/api.ts` | 추가 | +4 |
| `src/types/chat.ts` | 추가 | +14 |
| `src/types/agent.ts` | 수정 | +1 |
| `src/services/chatService.ts` | 추가 | +22 |
| `src/lib/queryKeys.ts` | 추가 | +6 |
| `src/hooks/useChat.ts` | 추가 | +26 |
| `src/store/layoutStore.ts` | 수정 | +1 (id값 변경) |
| `src/components/layout/AppSidebar.tsx` | 수정 | +5 |
| `src/components/layout/AgentChatLayout.tsx` | 수정 | +20 |
| `src/pages/ChatPage/index.tsx` | 수정 | +10 |
| **합계** | | **~109** |

---

## 5. 에러 핸들링

| 상황 | HTTP | 프론트 처리 |
|------|------|-----------|
| 에이전트 세션 조회 실패 | 4xx/5xx | ChatHistoryPanel 에러 상태 + 재시도 (기존 패턴) |
| 에이전트 세션 0건 | 200 (빈 배열) | 드래프트 세션 표시 + EmptyAgentState |
| 메시지 조회 실패 | 4xx/5xx | 빈 메시지 + 에러 토스트 (기존 패턴) |
| agent_id가 null | — | useQuery `enabled: false` → 요청 안 함 |

---

## 6. 테스트 계획

| 대상 | 테스트 항목 |
|------|-----------|
| `chatService.getAgentSessions` | URL에 agentId 포함 확인, user_id 파라미터 전달 확인 |
| `chatService.getAgentSessionMessages` | URL에 agentId + sessionId 포함 확인 |
| `useAgentSessions` | agentId 변경 시 queryKey 변경 → refetch 트리거 확인 |
| `useAgentSessionMessages` | enabled 조건 (agentId + sessionId + userId 모두 필수) |
| `AgentChatLayout` | 에이전트 전환 → 세션 목록 교체 + activeSessionId 초기화 |
| `AppSidebar` | "SUPER AI" 클릭 시 selectAgent("super") + navigate 동시 호출 |

---

## 7. 의존성

| 의존 항목 | 상태 | 비고 |
|----------|------|------|
| 백엔드 `GET /api/v1/conversations/agents/{id}/sessions` | ✅ 구현 완료 | conversation_history_router.py:164-190 |
| 백엔드 `GET /api/v1/conversations/agents/{id}/sessions/{sid}/messages` | ✅ 구현 완료 | conversation_history_router.py:193-225 |
| layoutStore (Zustand, persist) | ✅ 존재 | selectedAgentId 초기값 변경 필요 |
| queryKeys 팩토리 | ✅ 존재 | 확장만 필요 |
| ChatHistoryPanel | ✅ 존재 | props 변경 없음 (sessions 배열만 달라짐) |

---

## 8. 리스크 및 대응

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| layoutStore persist로 인해 기존 사용자의 `selectedAgentId`가 `"super-ai"`로 남아있음 | 높음 | 세션 조회 실패 | AgentChatLayout에서 `selectedAgentId`가 에이전트 목록에 없으면 `"super"`로 fallback |
| generalChat으로 생성된 세션이 커스텀 에이전트에도 보일 수 있음 | 낮음 | UX 혼란 | 백엔드가 agent_id 기반 필터링을 하므로 발생하지 않음 |
| 에이전트 전환 속도가 느릴 경우 | 중간 | UX 지연 | staleTime 60s + 이전 캐시 표시 (TanStack Query 기본 동작) |
