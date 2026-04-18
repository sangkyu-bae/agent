# Design: General Chat API Integration

> Feature: `general-chat-api-integration`  
> Phase: Design  
> Created: 2026-04-12  
> Author: 배상규  
> Ref Plan: `docs/01-plan/features/general-chat-api-integration.plan.md`

---

## 1. 변경 파일 목록 및 변경 요약

| 파일 | 변경 유형 | 변경 요약 |
|------|----------|---------|
| `src/types/chat.ts` | 수정 | `DocumentSource`, `GeneralChatRequest`, `GeneralChatResponse` 추가; `Message.sources` 타입 변경 |
| `src/constants/api.ts` | 수정 | `GENERAL_CHAT: '/api/v1/chat'` 상수 추가 |
| `src/services/chatService.ts` | 수정 | `generalChat()` 메서드 추가 (`authClient` 사용) |
| `src/hooks/useChat.ts` | 수정 | `useGeneralChat()` 훅 추가 |
| `src/components/chat/SourceCitation.tsx` | 수정 | props 타입을 `DocumentSource[]`로 변경 |
| `src/pages/ChatPage/index.tsx` | 수정 | `useGeneralChat`으로 교체, `user_id` authStore 연동, `session_id` 동기화, `sources` 처리 |
| `src/__tests__/mocks/handlers.ts` | 신규 생성 | MSW 핸들러 파일 초기 생성 + `/api/v1/chat` 핸들러 추가 |
| `src/__tests__/mocks/server.ts` | 신규 생성 | MSW 서버 설정 |
| `src/hooks/useChat.test.ts` | 신규 생성 | `useGeneralChat` 단위 테스트 |

---

## 2. 타입 설계 (`src/types/chat.ts`)

### 2-1. 추가 타입

```typescript
/** General Chat API 문서 출처 */
export interface DocumentSource {
  content: string;   // 검색된 문서 청크 내용
  source: string;    // 출처 파일명 또는 URL
  chunk_id: string;  // 문서 청크 고유 ID
  score: number;     // 관련도 점수 (0.0 ~ 1.0)
}

/** CHAT-001: POST /api/v1/chat 요청 */
export interface GeneralChatRequest {
  user_id: string;       // 필수: 로그인 사용자 ID (string)
  session_id?: string;   // 선택: 생략 시 서버에서 UUID 신규 발급
  message: string;       // 필수: 사용자 메시지
  top_k?: number;        // 선택: 내부 문서 검색 결과 수 (기본 5)
}

/** CHAT-001: POST /api/v1/chat 응답 */
export interface GeneralChatResponse {
  user_id: string;
  session_id: string;        // 서버에서 발급 또는 그대로 반환
  answer: string;
  tools_used: string[];      // 사용된 도구 목록
  sources: DocumentSource[]; // 내부 문서 출처 (없으면 빈 배열)
  was_summarized: boolean;
  request_id: string;
}
```

### 2-2. 수정 타입

`Message.sources` 타입을 `SourceChunk[]` → `DocumentSource[]`로 변경:

```typescript
// Before
export interface Message {
  ...
  sources?: SourceChunk[];
}

// After
export interface Message {
  ...
  sources?: DocumentSource[];
}
```

### 2-3. SourceChunk deprecated 처리

`SourceChunk`는 `@deprecated` JSDoc 태그를 추가하되 삭제하지 않는다.  
`SourceCitation` 컴포넌트가 `DocumentSource`로 전환되면 `SourceChunk` 참조는 소멸된다.

```typescript
/** @deprecated Use DocumentSource instead */
export interface SourceChunk { ... }
```

---

## 3. 상수 설계 (`src/constants/api.ts`)

```typescript
// 기존 CONVERSATION_CHAT 아래에 추가
GENERAL_CHAT: '/api/v1/chat',
```

---

## 4. 서비스 설계 (`src/services/chatService.ts`)

### 4-1. import 변경

```typescript
import authClient from './api/authClient';   // 추가
import type {
  ...
  GeneralChatRequest,
  GeneralChatResponse,
} from '@/types/chat';
```

### 4-2. 메서드 추가

```typescript
/** CHAT-001: General Chat (LangGraph ReAct) — authClient 사용 */
generalChat: (payload: GeneralChatRequest) =>
  authClient.post<GeneralChatResponse>(API_ENDPOINTS.GENERAL_CHAT, payload),
```

**설계 근거**: `POST /api/v1/chat`는 `Authorization: Bearer` 헤더 필수이므로  
인터셉터에서 토큰 주입 + 자동 갱신을 처리하는 `authClient`를 사용한다.  
기존 `conversationChat()`이 사용하는 `apiClient`(공개 클라이언트)와 혼용하지 않는다.

---

## 5. 훅 설계 (`src/hooks/useChat.ts`)

```typescript
import type {
  SendMessageRequest,
  ConversationChatRequest,
  GeneralChatRequest,       // 추가
} from '@/types/chat';

/** CHAT-001: General Chat 뮤테이션 */
export const useGeneralChat = () =>
  useMutation({
    mutationFn: (payload: GeneralChatRequest) =>
      chatService.generalChat(payload).then((r) => r.data),
  });
```

`useConversationChat`은 `@deprecated` 주석을 추가하되 삭제하지 않는다.

---

## 6. SourceCitation 컴포넌트 수정 (`src/components/chat/SourceCitation.tsx`)

### 6-1. props 타입 변경

```typescript
// Before
import type { SourceChunk } from '@/types/chat';
interface SourceCitationProps { sources: SourceChunk[]; }

// After
import type { DocumentSource } from '@/types/chat';
interface SourceCitationProps { sources: DocumentSource[]; }
```

### 6-2. 렌더링 로직 변경

| 기존 (`SourceChunk`) | 변경 (`DocumentSource`) |
|----------------------|------------------------|
| `source.documentId` + `source.chunkIndex` (key) | `source.chunk_id` (key) |
| `source.documentName` (파일명 표시) | `source.source` (파일명 표시) |
| `source.score` (점수) | `source.score` (동일) |

```tsx
// Before
{sources.map((source, idx) => (
  <button key={`${source.documentId}-${source.chunkIndex}`}>
    <span>{source.documentName}</span>
    <span>{Math.round(source.score * 100)}%</span>
  </button>
))}

// After
{sources.map((source, idx) => (
  <button key={source.chunk_id}>
    <span className="max-w-[140px] truncate">{source.source}</span>
    <span className="font-semibold text-violet-500">{Math.round(source.score * 100)}%</span>
  </button>
))}
```

---

## 7. ChatPage 설계 (`src/pages/ChatPage/index.tsx`)

### 7-1. user_id 조달 방식 변경

기존 `getUserId()` (localStorage UUID) 제거 → `useAuthStore`에서 로그인 사용자 ID 사용.

```typescript
// Before
const getUserId = (): string => { ... localStorage ... };
const userId = useRef(getUserId()).current;

// After
import { useAuthStore } from '@/store/authStore';
const user = useAuthStore((s) => s.user);
// handleSend 내에서: user_id: user?.id ?? ''
```

**설계 근거**: `POST /api/v1/chat`는 Bearer 토큰 필수이므로 이미 `ProtectedRoute`로 보호됨.  
`user`가 `null`인 상태로 ChatPage에 도달하지 않는다. 타입 안전을 위해 `??''` fallback만 유지.

### 7-2. session_id 동기화

서버가 신규 `session_id`를 발급하는 경우 클라이언트의 `activeSessionId`를 업데이트해야 한다.

```typescript
// sessions 목록에서 id를 서버 session_id로 업데이트하는 헬퍼
const syncSessionId = (clientId: string, serverId: string) => {
  if (clientId === serverId) return;
  setSessions((prev) =>
    prev.map((s) => (s.id === clientId ? { ...s, id: serverId } : s)),
  );
  setMessagesBySession((prev) => {
    const msgs = prev[clientId];
    if (!msgs) return prev;
    const next = { ...prev };
    delete next[clientId];
    next[serverId] = msgs;
    return next;
  });
  setActiveSessionId(serverId);
};
```

### 7-3. handleSend 변경

```typescript
// Before
const { mutate: sendChat, isPending } = useConversationChat();
sendChat(
  { user_id: userId, session_id: activeSessionId, message: content },
  { onSuccess: (data) => { ... } }
);

// After
const { mutate: sendChat, isPending } = useGeneralChat();
sendChat(
  {
    user_id: user?.id ?? '',
    session_id: activeSessionId,
    message: content,
    top_k: useRag ? 5 : undefined,
  },
  {
    onSuccess: (data) => {
      // session_id 동기화
      syncSessionId(activeSessionId, data.session_id);

      const assistantMessage: Message = {
        id: data.request_id,
        role: 'assistant',
        content: data.answer,
        createdAt: new Date().toISOString(),
        sources: data.sources,   // DocumentSource[] 저장
      };
      addMessage(data.session_id, assistantMessage);  // 동기화된 id 사용
    },
    onError: () => { ... }  // 기존과 동일
  }
);
```

### 7-4. import 변경 요약

```typescript
// 제거
import { useConversationChat } from '@/hooks/useChat';

// 추가
import { useGeneralChat } from '@/hooks/useChat';
import { useAuthStore } from '@/store/authStore';
import type { Message, ChatSession } from '@/types/chat';  // 동일 유지
```

---

## 8. 테스트 설계

### 8-1. MSW 핸들러 (`src/__tests__/mocks/handlers.ts`)

```typescript
import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';

export const handlers = [
  http.post(`*${API_ENDPOINTS.GENERAL_CHAT}`, () =>
    HttpResponse.json({
      user_id: 'user-001',
      session_id: 'session-abc',
      answer: '테스트 답변입니다.',
      tools_used: ['hybrid_document_search'],
      sources: [
        { content: '청크 내용', source: 'doc.pdf', chunk_id: 'c-001', score: 0.92 },
      ],
      was_summarized: false,
      request_id: 'req-001',
    })
  ),
];
```

### 8-2. MSW 서버 (`src/__tests__/mocks/server.ts`)

```typescript
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
```

### 8-3. `useGeneralChat` 테스트 (`src/hooks/useChat.test.ts`)

| 테스트 케이스 | 검증 항목 |
|-------------|---------|
| 성공: 응답 answer 반환 | `data.answer === '테스트 답변입니다.'` |
| 성공: sources 배열 반환 | `data.sources.length === 1`, `data.sources[0].chunk_id === 'c-001'` |
| 성공: session_id 반환 | `data.session_id === 'session-abc'` |
| 실패: 401 | `isError === true` |

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { act } from 'react';
import { useGeneralChat } from '@/hooks/useChat';
import { createWrapper } from '@/__tests__/mocks/wrapper';

describe('useGeneralChat', () => {
  it('성공 시 answer와 sources를 반환한다', async () => {
    const { result } = renderHook(() => useGeneralChat(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate({
        user_id: 'user-001',
        session_id: 'session-abc',
        message: '안녕하세요',
        top_k: 5,
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.answer).toBe('테스트 답변입니다.');
    expect(result.current.data?.sources).toHaveLength(1);
    expect(result.current.data?.sources[0].chunk_id).toBe('c-001');
  });
});
```

---

## 9. 구현 순서 (Do Phase 참조)

```
Step 1  [Red]   useChat.test.ts 작성 — useGeneralChat 테스트 (실패 확인)
Step 2  [Red]   handlers.ts + server.ts 생성 (MSW 기반 API mock)
Step 3          src/types/chat.ts — DocumentSource, GeneralChatRequest, GeneralChatResponse 추가
                                     Message.sources 타입 변경 / SourceChunk deprecated
Step 4          src/constants/api.ts — GENERAL_CHAT 상수 추가
Step 5          src/services/chatService.ts — generalChat() 추가 (authClient)
Step 6          src/hooks/useChat.ts — useGeneralChat() 추가 / useConversationChat deprecated
Step 7  [Green] npm run test:run — useGeneralChat 테스트 통과 확인
Step 8          src/components/chat/SourceCitation.tsx — DocumentSource props 교체
Step 9          src/pages/ChatPage/index.tsx — useGeneralChat 교체, user_id, session_id 동기화, sources 처리
Step 10 [Check] npm run type-check && npm run test:run
```

---

## 10. 완료 기준

- [ ] `POST /api/v1/chat` 엔드포인트로 메시지 전송 성공
- [ ] Bearer 토큰(`authClient`)이 요청 헤더에 포함됨
- [ ] 응답 `answer`가 어시스턴트 메시지로 표시됨
- [ ] `sources` 있을 때 `SourceCitation`으로 표시됨 (`DocumentSource.source` 파일명 표시)
- [ ] `top_k`: RAG 토글 ON → `5`, OFF → `undefined`
- [ ] 서버 신규 `session_id` 발급 시 클라이언트 상태 동기화
- [ ] `useGeneralChat` 훅 테스트 3케이스 통과
- [ ] `npm run type-check` 오류 없음
- [ ] `useConversationChat` deprecated 처리 (삭제 X)
- [ ] `SourceChunk` deprecated 처리 (삭제 X)
