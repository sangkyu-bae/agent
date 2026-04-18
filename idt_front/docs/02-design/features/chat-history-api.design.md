---
template: design
version: 1.2
feature: chat-history-api
date: 2026-04-17
author: 배상규
project: idt_front
version_project: 0.0.0
---

# chat-history-api Design Document

> **Summary**: 백엔드 `CHAT-HIST-001` (`GET /api/v1/conversations/sessions`, `GET /api/v1/conversations/sessions/{session_id}/messages`)을 프론트에 연결해, Sidebar "최근 대화" 목록을 서버 데이터로 렌더링하고 세션 클릭 시 이전 메시지를 lazy-load하여 `ChatPage` 에 복원한다.
>
> **Project**: idt_front
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-04-17
> **Status**: Draft
> **Planning Doc**: [chat-history-api.plan.md](../../01-plan/features/chat-history-api.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 4 | [API Spec](../../api/chat-history-api.md) | ✅ |
| Phase 6 | UI Integration (this design) | 🔄 |

---

## 1. Overview

### 1.1 Design Goals

- 백엔드 스키마(snake_case)를 그대로 Response 타입으로 수용하되, UI에서 사용하는 도메인 모델(`ChatSession`, `Message`)은 **서비스 레이어 어댑터**로 변환한다.
- 세션 목록과 세션별 메시지는 **TanStack Query 캐시**를 Single Source of Truth로 삼는다. 로컬 state는 "전송 중 낙관적 업데이트" 용도로만 유지한다.
- 기존 `ChatPage.syncSessionId` 로직을 보존해 **클라이언트 임시 세션 → 서버 발급 session_id** 전환 시 UI 깜빡임이 없어야 한다.
- `user_id` 쿼리 파라미터는 `useAuthStore.user.id` 에서 파생한다. 비로그인 상태에서는 쿼리 자체를 비활성화한다 (`enabled: !!userId`).

### 1.2 Design Principles

- **Single Source of Truth**: 메시지/세션 목록의 원천은 TanStack Query 캐시. 로컬 `messagesBySession` state는 전송 중 버퍼/낙관적 추가 용도로만 사용.
- **Lazy Load**: 세션 메시지는 클릭 시점에만 요청. 수십 개 세션을 prefetch 하지 않는다.
- **Adapter at Boundary**: snake_case ↔ camelCase 변환은 `services/chatService` 내부에서 종결. 컴포넌트/훅에서는 도메인 모델만 다룬다.
- **Cache Isolation by User**: queryKey 에 `userId` 포함. 로그아웃 시 `queryClient.removeQueries({ queryKey: queryKeys.chat.all })` 로 교차 노출 방지.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ Presentation (pages/ChatPage, components/layout/Sidebar)     │
│   - sessions(ChatSession[]) / activeSessionId / messages     │
└──────┬──────────────────────────────────────────────▲────────┘
       │ useConversationSessions / useSessionMessages │
       ▼                                              │
┌──────────────────────────────────────────────────────────────┐
│ Application Hooks (hooks/useChat)                            │
│   - useConversationSessions(userId)                          │
│   - useSessionMessages(sessionId, userId)                    │
│   - (기존) useGeneralChat — onSuccess 시 invalidate 트리거   │
└──────┬──────────────────────────────────────────────▲────────┘
       │ chatService.getConversationSessions / ...    │
       ▼                                              │
┌──────────────────────────────────────────────────────────────┐
│ Service Layer (services/chatService)                         │
│   - HTTP 호출 (apiClient)                                    │
│   - toChatSession / toMessage 어댑터                          │
└──────┬──────────────────────────────────────────────▲────────┘
       │ GET /api/v1/conversations/sessions           │
       │ GET /api/v1/conversations/sessions/{id}/msgs │
       ▼                                              │
┌──────────────────────────────────────────────────────────────┐
│ Backend (idt — CHAT-HIST-001)                                │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

#### 2.2.1 사이드바 초기 로드

```
ChatPage mount
  → useAuthStore.user.id 획득
  → useConversationSessions(userId) (enabled=!!userId)
  → chatService.getConversationSessions(userId)
  → GET /api/v1/conversations/sessions?user_id={id}
  → 응답 (snake_case)
  → toChatSession 어댑터 (messages: [] 비워둠)
  → TanStack Query 캐시 저장 → Sidebar 렌더링
```

#### 2.2.2 세션 클릭 시 이전 메시지 로드

```
Sidebar onSelectSession(sessionId)
  → ChatPage setActiveSessionId(sessionId)
  → useSessionMessages(sessionId, userId) enabled=true
    (단, "새 대화"에 해당하는 임시 UUID 세션은 enabled=false)
  → GET /api/v1/conversations/sessions/{sessionId}/messages?user_id={id}
  → 응답 messages[] → toMessage 어댑터
  → TanStack Query 캐시 저장 (staleTime 1분)
  → MessageList 렌더링
```

#### 2.2.3 새 메시지 전송 → 사이드바 재정렬

```
ChatInput onSend
  → ChatPage handleSend (낙관적 userMessage 추가 — 로컬 state)
  → useGeneralChat.mutate
  → POST /api/v1/chat
  → onSuccess: data.session_id 확인
    → syncSessionId (임시 UUID → 서버 id)
    → 로컬 state 에 assistant 메시지 append
    → queryClient.invalidateQueries({ queryKey: queryKeys.chat.history(userId) })
    → queryClient.invalidateQueries({ queryKey: queryKeys.chat.sessionMessages(serverId, userId) })
  → Sidebar 재정렬 (last_message_at 갱신된 순서)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `useConversationSessions` | `chatService.getConversationSessions`, `queryKeys.chat.history` | 세션 목록 쿼리 |
| `useSessionMessages` | `chatService.getSessionMessages`, `queryKeys.chat.sessionMessages` | 세션 메시지 lazy 쿼리 |
| `ChatPage` | `useConversationSessions`, `useSessionMessages`, `useGeneralChat`, `useAuthStore` | 통합 오케스트레이션 |
| `Sidebar` | `ChatSession[]`, `isLoading`, `isError`, `onRetry` | 목록/로딩/에러 UI |
| `chatService.toChatSession` / `toMessage` | `types/chat.ts` Response 타입 | 도메인 변환 어댑터 |

---

## 3. Data Model

### 3.1 서버 응답 타입 (신규, `src/types/chat.ts` 추가)

```typescript
/** CHAT-HIST-001: 세션 요약 (백엔드 응답 원본) */
export interface SessionSummary {
  session_id: string;
  message_count: number;
  last_message: string;        // 최대 100자
  last_message_at: string;     // ISO 8601
}

/** CHAT-HIST-001: GET /api/v1/conversations/sessions 응답 */
export interface SessionSummaryListResponse {
  user_id: string;
  sessions: SessionSummary[];
}

/** CHAT-HIST-001: 세션 내 메시지 항목 (백엔드 응답 원본) */
export interface HistoryMessageItem {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  turn_index: number;
  created_at: string;          // ISO 8601
}

/** CHAT-HIST-001: GET /api/v1/conversations/sessions/{session_id}/messages 응답 */
export interface SessionMessagesResponse {
  user_id: string;
  session_id: string;
  messages: HistoryMessageItem[];
}
```

### 3.2 도메인 모델 (기존 재사용)

`ChatSession`, `Message` 기존 타입을 그대로 사용한다 (`src/types/chat.ts`).

### 3.3 어댑터 매핑

| Server (snake_case) | Domain (camelCase) | 변환 규칙 |
|---------------------|--------------------|-----------|
| `SessionSummary.session_id` | `ChatSession.id` | 복사 |
| `SessionSummary.last_message` | `ChatSession.title` | `.slice(0, 30)` — 기존 title 규칙 유지, 빈 문자열이면 `"새 대화"` |
| `SessionSummary.last_message_at` | `ChatSession.updatedAt` | 그대로 (ISO 문자열) |
| - | `ChatSession.createdAt` | `last_message_at` 로 대체 (서버에 createdAt 없음) |
| - | `ChatSession.messages` | `[]` — lazy load 전까지 빈 배열 |
| `HistoryMessageItem.id` | `Message.id` | `String(id)` (number → string) |
| `HistoryMessageItem.role` | `Message.role` | 그대로 |
| `HistoryMessageItem.content` | `Message.content` | 그대로 |
| `HistoryMessageItem.created_at` | `Message.createdAt` | 그대로 |
| - | `Message.sources` | `undefined` — history API는 sources 제공 안 함 |

### 3.4 Cache Key 전략

```typescript
// src/lib/queryKeys.ts 확장
chat: {
  all: ['chat'] as const,
  sessions: () => [...queryKeys.chat.all, 'sessions'] as const,
  session: (sessionId: string) => [...queryKeys.chat.sessions(), sessionId] as const,

  /** 신규: 사용자별 대화 세션 목록 (CHAT-HIST-001) */
  history: (userId: string) =>
    [...queryKeys.chat.all, 'history', userId] as const,

  /** 신규: 세션별 메시지 (CHAT-HIST-001) */
  sessionMessages: (sessionId: string, userId: string) =>
    [...queryKeys.chat.all, 'sessionMessages', sessionId, userId] as const,
},
```

> `userId` 를 key 에 포함 → 사용자 전환 시 캐시 격리.

---

## 4. API Specification (Frontend Side)

### 4.1 Endpoint Constants (`src/constants/api.ts` 추가)

```typescript
CONVERSATION_SESSIONS: '/api/v1/conversations/sessions',
CONVERSATION_SESSION_MESSAGES: (sessionId: string) =>
  `/api/v1/conversations/sessions/${sessionId}/messages`,
```

### 4.2 Service Methods (`src/services/chatService.ts` 추가)

```typescript
/** CHAT-HIST-001: 사용자 세션 목록 조회 */
getConversationSessions: async (userId: string): Promise<ChatSession[]> => {
  const res = await apiClient.get<SessionSummaryListResponse>(
    API_ENDPOINTS.CONVERSATION_SESSIONS,
    { params: { user_id: userId } },
  );
  return res.data.sessions.map(toChatSession);
},

/** CHAT-HIST-001: 특정 세션 메시지 조회 */
getSessionMessages: async (
  sessionId: string,
  userId: string,
): Promise<Message[]> => {
  const res = await apiClient.get<SessionMessagesResponse>(
    API_ENDPOINTS.CONVERSATION_SESSION_MESSAGES(sessionId),
    { params: { user_id: userId } },
  );
  return res.data.messages.map(toMessage);
},
```

### 4.3 Adapter Functions (동일 파일 내 private)

```typescript
const toChatSession = (summary: SessionSummary): ChatSession => ({
  id: summary.session_id,
  title: summary.last_message?.slice(0, 30) || '새 대화',
  messages: [],
  createdAt: summary.last_message_at,
  updatedAt: summary.last_message_at,
});

const toMessage = (item: HistoryMessageItem): Message => ({
  id: String(item.id),
  role: item.role,
  content: item.content,
  createdAt: item.created_at,
});
```

### 4.4 Hooks (`src/hooks/useChat.ts` 추가)

```typescript
/** 로그인 사용자의 대화 세션 목록 */
export const useConversationSessions = (userId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.chat.history(userId ?? ''),
    queryFn: () => chatService.getConversationSessions(userId as string),
    enabled: !!userId,
    staleTime: 60_000,
  });

/** 특정 세션의 이전 메시지 (lazy) */
export const useSessionMessages = (
  sessionId: string | null,
  userId: string | undefined,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: queryKeys.chat.sessionMessages(sessionId ?? '', userId ?? ''),
    queryFn: () =>
      chatService.getSessionMessages(sessionId as string, userId as string),
    enabled: !!sessionId && !!userId && (options?.enabled ?? true),
    staleTime: 60_000,
  });
```

### 4.5 Invalidation Policy

| Trigger | Invalidated Keys | 목적 |
|---------|------------------|------|
| `useGeneralChat.onSuccess` | `queryKeys.chat.history(userId)` | 사이드바 재정렬 |
| `useGeneralChat.onSuccess` | `queryKeys.chat.sessionMessages(serverSessionId, userId)` | 서버 기준 메시지 동기화 |
| 로그아웃 (`authStore.logout`) | `queryKeys.chat.all` (removeQueries) | 사용자 간 캐시 격리 |

> 낙관적 업데이트 → invalidate 순서: (1) 로컬 state 에 즉시 append, (2) mutate 성공 후 invalidate, (3) 다음 렌더에서 서버 데이터로 치환.

---

## 5. UI/UX Design

### 5.1 Sidebar 상태별 렌더링

```
┌─────────────────────────────────┐
│  + 새 대화                      │
├─────────────────────────────────┤
│  최근 대화                      │
│                                 │
│  [isLoading]                    │
│  ┌──────────────┐              │
│  │ ▓▓▓▓▓▓▓▓▓   │ ← 스켈레톤  │
│  │ ▓▓▓         │    3행       │
│  └──────────────┘              │
│                                 │
│  [isError]                      │
│  ⚠ 불러오기 실패               │
│  [ 다시 시도 ]                  │
│                                 │
│  [success + sessions.length>0] │
│  • 세션 1  (2분 전)            │
│  • 세션 2  (어제)              │
│                                 │
│  [success + empty]              │
│  대화 내역이 없습니다          │
└─────────────────────────────────┘
```

### 5.2 `ChatPage` 상태 결합 규칙

| Case | `sessions` 원천 | `messages` 원천 | 비고 |
|------|----------------|-----------------|------|
| 로그인 + 기존 세션 클릭 | 서버 (`useConversationSessions`) | 서버 (`useSessionMessages`) | 정상 케이스 |
| 로그인 + "새 대화" 버튼 | 로컬 추가 + 서버 (병합) | 로컬 state (임시 UUID) | 전송 성공 전 |
| 로그인 + 메시지 전송 성공 | 서버 invalidate 재조회 | 로컬 → 서버 invalidate | `syncSessionId` 후 invalidate |
| 비로그인 | `[]` (쿼리 비활성) | `[]` | Sidebar 빈 상태 |

### 5.3 Sidebar Props 확장

```typescript
interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  isLoading?: boolean;   // 신규
  isError?: boolean;     // 신규
  onRetry?: () => void;  // 신규
}
```

### 5.4 Component List

| Component | Location | 변경 내용 |
|-----------|----------|----------|
| `Sidebar` | `src/components/layout/Sidebar.tsx` | loading 스켈레톤 / error 배너 + 재시도 |
| `ChatPage` | `src/pages/ChatPage/index.tsx` | 로컬 state → 서버 데이터 병합, 임시 세션 합치기, invalidate 트리거 |
| `useChat` | `src/hooks/useChat.ts` | `useConversationSessions`, `useSessionMessages` 추가 |
| `chatService` | `src/services/chatService.ts` | `getConversationSessions`, `getSessionMessages` + 어댑터 |

---

## 6. Error Handling

### 6.1 Error Matrix

| Source | HTTP | UI 동작 | Fallback |
|--------|------|---------|----------|
| `useConversationSessions` 422 | 422 | 콘솔 에러 + Sidebar 에러 배너 | 빈 목록 유지 |
| `useConversationSessions` 500 | 500 | Sidebar 에러 배너 + "다시 시도" | 이전 캐시(있으면) |
| `useSessionMessages` 500 | 500 | 채팅 영역 상단 inline 경고 + 자동 1회 retry (React Query `retry: 1`) | 빈 메시지 목록 |
| `useSessionMessages` 빈 배열 | 200 | `MessageList` 빈 상태 (기존 UI) | - |
| 네트워크 오류 (fetch fail) | - | 동일한 에러 배너 처리 | 오프라인 토스트 (향후) |

### 6.2 Error Boundaries

- `ChatPage` 자체 래핑은 추가하지 않고, 개별 쿼리의 `isError` 상태를 활용해 부분 실패가 전체 UI 중단으로 이어지지 않도록 한다.
- 채팅 전송(`useGeneralChat`) 과 히스토리 조회는 **독립 실패** 가능. 한 쪽이 실패해도 다른 쪽은 계속 동작해야 한다.

---

## 7. Security Considerations

- [x] `user_id` 쿼리 파라미터 — URL 에 노출되므로 민감정보 포함 금지 (이미 현재 `id` 는 숫자 PK).
- [x] XSS — `MessageList` 가 `react-markdown` 사용 시 `rehype-sanitize` 유지 (기존 설정 준수).
- [x] 사용자 분리 — queryKey 에 `userId` 포함 + 로그아웃 시 `removeQueries` 로 교차 노출 방지.
- [ ] Auth 미적용 (백엔드 정책) — 향후 JWT 기반 인증 적용 시 `authClient` 로 전환 필요 (Plan Section 6.2 참조).
- [x] HTTPS — 운영 환경은 리버스 프록시에서 강제 (프론트 영향 없음).

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | 어댑터 함수 (`toChatSession`, `toMessage`) | Vitest |
| Hook | `useConversationSessions`, `useSessionMessages` | Vitest + @testing-library/react + MSW |
| Integration | `ChatPage` 사이드바 클릭 → 이전 메시지 렌더 | RTL + user-event + MSW |

### 8.2 Test Cases

#### 8.2.1 `chatService.test.ts` (신규 — 어댑터 단위)

| # | 케이스 | 검증 |
|---|--------|------|
| 1 | `toChatSession` — 정상 변환 | id/title/updatedAt 매핑 확인 |
| 2 | `toChatSession` — `last_message` 비었을 때 | title = `"새 대화"` |
| 3 | `toChatSession` — `last_message` 30자 초과 | 30자 truncate |
| 4 | `toMessage` — number id → string id | `id === "1001"` |
| 5 | `toMessage` — role 보존 | `"user"` / `"assistant"` |

#### 8.2.2 `useChat.test.ts` (확장)

| # | 케이스 | Mock | 검증 |
|---|--------|------|------|
| H1 | `useConversationSessions` — userId 제공 시 성공 | MSW 200 (2 sessions) | `data.length === 2` |
| H2 | `useConversationSessions` — userId 없음 | 호출 안 함 | `isLoading === false`, `fetchStatus === 'idle'` |
| H3 | `useConversationSessions` — 빈 배열 응답 | MSW 200 sessions: [] | `data.length === 0` |
| H4 | `useConversationSessions` — 500 에러 | MSW 500 | `isError === true` |
| M1 | `useSessionMessages` — 정상 | MSW 200 (3 messages) | 메시지 3개 + `id === string` |
| M2 | `useSessionMessages` — sessionId null | 호출 안 함 | `fetchStatus === 'idle'` |
| M3 | `useSessionMessages` — 캐시 재사용 | 동일 key 로 2회 rerender | fetch count === 1 |
| M4 | `useSessionMessages` — 빈 배열 | MSW 200 messages: [] | `data.length === 0` |

#### 8.2.3 `ChatPageIntegration.test.tsx` (신규 통합)

| # | 시나리오 | 검증 |
|---|----------|------|
| I1 | 마운트 후 사이드바에 서버 세션 2개가 렌더링된다 | `findAllByRole('button', { name: /세션/ })` |
| I2 | 사이드바 세션 클릭 시 이전 메시지가 MessageList 에 렌더된다 | `findByText(이전 user content)` |
| I3 | 새 메시지 전송 성공 → 사이드바 invalidate → 재조회 호출 | MSW handler spy `calls === 2` |
| I4 | 비로그인 상태에서는 히스토리 호출이 발생하지 않는다 | MSW handler spy `calls === 0` |
| I5 | 500 에러 시 사이드바에 에러 배너 + 재시도 버튼 표시 | `getByText(/다시 시도/)` |

### 8.3 MSW Handlers 확장

```typescript
// src/__tests__/mocks/handlers.ts
http.get(`*${API_ENDPOINTS.CONVERSATION_SESSIONS}`, ({ request }) => {
  const url = new URL(request.url);
  const userId = url.searchParams.get('user_id');
  return HttpResponse.json({
    user_id: userId,
    sessions: [
      { session_id: 's1', message_count: 4, last_message: '안녕', last_message_at: '2026-04-17T10:00:00Z' },
      { session_id: 's2', message_count: 2, last_message: '이전 질문', last_message_at: '2026-04-16T12:00:00Z' },
    ],
  });
}),

http.get(`*/api/v1/conversations/sessions/:sessionId/messages`, ({ params, request }) => {
  const url = new URL(request.url);
  return HttpResponse.json({
    user_id: url.searchParams.get('user_id'),
    session_id: params.sessionId,
    messages: [
      { id: 1, role: 'user', content: '이전 질문입니다', turn_index: 1, created_at: '2026-04-17T10:00:00Z' },
      { id: 2, role: 'assistant', content: '이전 답변입니다', turn_index: 1, created_at: '2026-04-17T10:00:03Z' },
    ],
  });
}),
```

---

## 9. Clean Architecture

### 9.1 Layer Assignment

| Layer | Responsibility | 이번 기능 매핑 |
|-------|---------------|----------------|
| **Presentation** | UI + 사용자 상호작용 | `pages/ChatPage/index.tsx`, `components/layout/Sidebar.tsx` |
| **Application** | Orchestration (훅) | `hooks/useChat.ts` (`useConversationSessions`, `useSessionMessages`) |
| **Domain** | 타입/모델 | `types/chat.ts` (`ChatSession`, `Message`, `SessionSummary` 등) |
| **Infrastructure** | HTTP / 캐시 | `services/chatService.ts`, `services/api/client.ts`, `lib/queryClient.ts`, `lib/queryKeys.ts` |

### 9.2 Import Rules Compliance

| From | To | 허용 여부 |
|------|------|----------|
| `pages/ChatPage` → `hooks/useChat` | Presentation → Application | ✅ |
| `hooks/useChat` → `services/chatService` | Application → Infrastructure | ✅ |
| `services/chatService` → `types/chat` | Infrastructure → Domain | ✅ |
| `components/Sidebar` → `services/*` | Presentation → Infrastructure **직접** | ❌ (금지, 훅 경유) |

---

## 10. Coding Convention Reference

### 10.1 이번 기능 적용 컨벤션

| Item | Convention Applied |
|------|-------------------|
| 서버 응답 타입 네이밍 | `SessionSummary`, `SessionSummaryListResponse`, `HistoryMessageItem`, `SessionMessagesResponse` — snake_case 필드 유지 |
| 어댑터 함수 위치 | `services/chatService.ts` 파일 내 private 상수 (`toChatSession`, `toMessage`) |
| queryKey 확장 | `queryKeys.chat.history(userId)`, `queryKeys.chat.sessionMessages(sessionId, userId)` |
| 훅 명명 | `useXxx` (camelCase) — `useConversationSessions`, `useSessionMessages` |
| 파일 명명 | 기존 `useChat.ts` 에 함수 추가 (신규 파일 X) |
| 테스트 파일 | 소스 옆 `useChat.test.ts` (기존), 통합은 `src/__tests__/components/ChatPageIntegration.test.tsx` |

### 10.2 Import Order (기존 유지)

```typescript
// 1. 외부 라이브러리
import { useQuery } from '@tanstack/react-query';

// 2. 내부 절대 경로
import { chatService } from '@/services/chatService';
import { queryKeys } from '@/lib/queryKeys';

// 3. 타입
import type { ChatSession, Message, SessionSummary } from '@/types/chat';
```

---

## 11. Implementation Guide

### 11.1 변경 파일 목록

#### 신규 파일 (2개)

| 파일 | 역할 |
|------|------|
| `src/hooks/useConversationHistory.test.ts` *(또는 기존 `useChat.test.ts` 확장)* | 훅 단위 테스트 |
| `src/__tests__/components/ChatPageIntegration.test.tsx` | 통합 테스트 |

#### 수정 파일 (6개)

| 파일 | 변경 내용 |
|------|----------|
| `src/constants/api.ts` | `CONVERSATION_SESSIONS`, `CONVERSATION_SESSION_MESSAGES` 추가 |
| `src/types/chat.ts` | `SessionSummary`, `SessionSummaryListResponse`, `HistoryMessageItem`, `SessionMessagesResponse` 추가 |
| `src/lib/queryKeys.ts` | `chat.history`, `chat.sessionMessages` 추가 |
| `src/services/chatService.ts` | `getConversationSessions`, `getSessionMessages` + `toChatSession`, `toMessage` |
| `src/hooks/useChat.ts` | `useConversationSessions`, `useSessionMessages` + `useGeneralChat.onSuccess` invalidate |
| `src/components/layout/Sidebar.tsx` | `isLoading` / `isError` / `onRetry` props + 로딩 스켈레톤 + 에러 배너 |
| `src/pages/ChatPage/index.tsx` | 로컬 `sessions` state → 서버 병합, 메시지 로드 연동, invalidate 트리거 |
| `src/__tests__/mocks/handlers.ts` | 2개 GET 핸들러 추가 |

### 11.2 TDD 구현 순서

```
1. Red — src/hooks/useChat.test.ts 에 useConversationSessions 케이스 H1~H4 작성
      → vitest 실패 확인
2. Green — 타입/상수/queryKey 추가
      → src/services/chatService.ts 에 getConversationSessions + 어댑터
      → src/hooks/useChat.ts 에 useConversationSessions
      → MSW handler 추가
      → vitest H1~H4 통과
3. Red — useSessionMessages 케이스 M1~M4 작성
4. Green — chatService.getSessionMessages + 어댑터 + useSessionMessages 구현
5. Red — ChatPageIntegration.test.tsx I1~I5 작성
6. Green — Sidebar props 확장 + ChatPage 리팩터링
      → useGeneralChat onSuccess 에 invalidate 추가
7. Refactor
      - ChatPage 200줄 초과 시 useChatPageSessions 훅으로 추출 검토
      - 어댑터 함수 재사용성 검토
8. 수동 E2E
      - 백엔드 로컬 기동 후 새 대화 → 메시지 전송 → 새로고침 → 이전 대화 클릭 검증
```

### 11.3 `ChatPage` 리팩터링 상세

#### Before
```tsx
const [sessions, setSessions] = useState<ChatSession[]>(() => [createSession()]);
```

#### After (핵심 변경)
```tsx
const user = useAuthStore((s) => s.user);
const userId = user?.id != null ? String(user.id) : undefined;

const { data: serverSessions = [], isLoading, isError, refetch } =
  useConversationSessions(userId);

const [draftSessions, setDraftSessions] = useState<ChatSession[]>([]); // 임시(전송 전) 세션만
const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

const sessions = useMemo(() => {
  // 임시 세션을 우선 배치, 중복 id 제거
  const serverIds = new Set(serverSessions.map((s) => s.id));
  const drafts = draftSessions.filter((s) => !serverIds.has(s.id));
  return [...drafts, ...serverSessions];
}, [draftSessions, serverSessions]);

const { data: serverMessages } = useSessionMessages(
  activeSessionId,
  userId,
  { enabled: !!activeSessionId && !draftSessions.some((d) => d.id === activeSessionId) },
);

// 로컬 버퍼(낙관적 추가) + 서버 메시지 병합
const messages = useMemo(() => {
  const local = messagesBySession[activeSessionId ?? ''] ?? [];
  if (local.length > 0) return local;
  return serverMessages ?? [];
}, [activeSessionId, messagesBySession, serverMessages]);
```

> `syncSessionId` 로직은 유지하되, 서버 id 로 전환된 뒤 `draftSessions` 에서 해당 항목 제거 + `queryKeys.chat.history(userId)` invalidate.

---

## 12. Definition of Done

- [ ] FR-01 ~ FR-10 구현 완료
- [ ] 신규/확장 테스트 (Unit 5 + Hook 8 + Integration 5 = **18개**) 모두 통과
- [ ] `npm run type-check`, `npm run lint`, `npm run test:run` 통과
- [ ] `npm run build` 성공
- [ ] 백엔드 로컬 기동 후 수동 E2E 검증 완료
  - 새 대화 → 메시지 전송 → 새로고침 → Sidebar 에서 해당 대화 클릭 → 이전 메시지 그대로 보임
- [ ] 비로그인 진입 시 히스토리 API 호출 0건
- [ ] 로그아웃 → 재로그인 시 이전 사용자 세션이 노출되지 않음

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-17 | Initial draft — Plan 기반 설계 (타입/훅/어댑터/UI/테스트 매핑) | 배상규 |
