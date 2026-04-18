# Plan: General Chat API Integration

> Feature: `general-chat-api-integration`  
> Phase: Plan  
> Created: 2026-04-12  
> Author: 배상규

---

## 1. 배경 및 목표

### 배경

현재 ChatPage는 `POST /api/v1/conversation/chat` (CONV-001) 엔드포인트를 사용하고 있다.
신규 General Chat API (`POST /api/v1/chat`)가 구현되었으며, 이 API는 LangGraph ReAct 에이전트 기반으로
`tools_used`, `sources(DocumentSource[])` 등 더 풍부한 응답을 제공한다.

### 목표

ChatPage의 API 연동을 기존 CONV-001에서 신규 General Chat API로 교체하고,
응답에 포함된 `sources`, `tools_used`, `was_summarized` 정보를 UI에 반영한다.

---

## 2. 구현 범위

### In Scope

| 항목 | 설명 |
|------|------|
| 엔드포인트 변경 | `/api/v1/conversation/chat` → `/api/v1/chat` |
| 인증 클라이언트 변경 | `apiClient` → `authClient` (Bearer 토큰 필수) |
| 타입 추가 | `GeneralChatRequest`, `GeneralChatResponse`, `DocumentSource` |
| 서비스 추가 | `chatService.generalChat()` |
| 훅 추가 | `useGeneralChat()` |
| ChatPage 연동 변경 | `useConversationChat` → `useGeneralChat` 교체 |
| sources UI 반영 | 응답의 `sources`를 `Message.sources`에 저장, `SourceCitation` 표시 |
| top_k 파라미터 | ChatInput의 RAG 토글 상태에 따라 `top_k` 전송 여부 결정 |

### Out of Scope

| 항목 | 이유 |
|------|------|
| `tools_used` UI 표시 | 현재 컴포넌트 없음 — 별도 태스크(ToolCallDisplay) |
| `was_summarized` 알림 | 부가 기능 — Phase 2에서 처리 |
| 세션 서버 저장 | 현재 클라이언트 메모리 방식 유지 |
| SSE 스트리밍 전환 | 현재 API가 동기 응답 — 스트리밍은 별도 태스크 |

---

## 3. API 스펙

### 엔드포인트

```
POST /api/v1/chat
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Request Body

```typescript
interface GeneralChatRequest {
  user_id: string;          // 필수: 사용자 ID (localStorage에서 관리)
  session_id?: string;      // 선택: 생략 시 서버에서 UUID 신규 발급
  message: string;          // 필수: 사용자 메시지
  top_k?: number;           // 선택: 내부 문서 검색 결과 수 (기본 5)
}
```

### Response Body

```typescript
interface DocumentSource {
  content: string;   // 검색된 문서 청크 내용
  source: string;    // 출처 파일명 또는 URL
  chunk_id: string;  // 문서 청크 고유 ID
  score: number;     // 관련도 점수 (0.0 ~ 1.0)
}

interface GeneralChatResponse {
  user_id: string;
  session_id: string;       // 서버에서 발급 또는 그대로 반환
  answer: string;
  tools_used: string[];     // 사용된 도구 목록
  sources: DocumentSource[];// 내부 문서 출처 (없으면 빈 배열)
  was_summarized: boolean;
  request_id: string;
}
```

### 에러 응답

| 코드 | 원인 | 처리 |
|------|------|------|
| 401 | 토큰 없음/만료 | authClient 인터셉터에서 자동 갱신 시도 → 실패 시 /login 리다이렉트 |
| 422 | user_id 또는 message 누락 | UI 레벨 유효성 검사로 사전 차단 |

---

## 4. 변경 파일 목록

### 수정 파일

| 파일 | 변경 내용 |
|------|---------|
| `src/constants/api.ts` | `GENERAL_CHAT: '/api/v1/chat'` 상수 추가 |
| `src/types/chat.ts` | `GeneralChatRequest`, `GeneralChatResponse`, `DocumentSource` 타입 추가 |
| `src/services/chatService.ts` | `generalChat()` 메서드 추가 (`authClient` 사용) |
| `src/hooks/useChat.ts` | `useGeneralChat()` 훅 추가 |
| `src/pages/ChatPage/index.tsx` | `useConversationChat` → `useGeneralChat` 교체, sources 처리 |

### 기존 타입 호환성

- `SourceChunk`는 삭제하지 않음 (다른 곳 참조 여부 확인 후 deprecated 처리)
- `Message.sources` 타입을 `DocumentSource[]`로 변경 — `SourceChunk`와 필드명 차이 존재
  - `SourceChunk.documentName` → `DocumentSource.source`
  - `SourceChunk.chunkIndex` → `DocumentSource.chunk_id`
  - `SourceChunk.documentId` 없어짐

---

## 5. 데이터 흐름

```
사용자 입력
  ↓
ChatPage.handleSend(content)
  ↓
useGeneralChat.mutate({
  user_id: userId,          ← localStorage UUID
  session_id: activeSessionId,
  message: content,
  top_k: useRag ? 5 : undefined
})
  ↓
chatService.generalChat(payload) — authClient.post('/api/v1/chat')
  ↓
GeneralChatResponse
  ↓
Message 생성: {
  id: response.request_id,
  role: 'assistant',
  content: response.answer,
  sources: response.sources   ← DocumentSource[]
}
  ↓
MessageBubble → SourceCitation 표시
```

---

## 6. 테스트 계획 (TDD)

### Red → Green → Refactor 사이클

| 테스트 파일 | 테스트 항목 |
|------------|------------|
| `src/hooks/useChat.test.ts` | `useGeneralChat` 성공/실패/소스 반환 케이스 |
| `src/services/chatService.test.ts` | `generalChat()` authClient 사용 확인, payload 검증 |
| `src/__tests__/mocks/handlers.ts` | `/api/v1/chat` MSW 핸들러 추가 |

### MSW 핸들러 추가

```typescript
http.post('*/api/v1/chat', () =>
  HttpResponse.json({
    user_id: 'test-user',
    session_id: 'test-session',
    answer: '테스트 답변입니다.',
    tools_used: ['hybrid_document_search'],
    sources: [{ content: '...', source: 'doc.pdf', chunk_id: 'c-001', score: 0.9 }],
    was_summarized: false,
    request_id: 'req-001',
  })
)
```

---

## 7. 완료 기준 (Definition of Done)

- [ ] `POST /api/v1/chat` 엔드포인트로 메시지 전송 성공
- [ ] Bearer 토큰이 요청 헤더에 포함됨
- [ ] 응답의 `answer`가 어시스턴트 메시지로 표시됨
- [ ] `sources`가 있으면 `SourceCitation` 컴포넌트로 표시됨
- [ ] 인증 실패(401) 시 자동 갱신 또는 /login 리다이렉트
- [ ] `useGeneralChat` 훅 테스트 통과
- [ ] 기존 `useConversationChat` 훅은 deprecated 처리 (삭제 X)
- [ ] TypeScript 타입 검사 통과 (`npm run type-check`)

---

## 8. 구현 순서 (Do Phase 참조)

```
1. TDD Red: useGeneralChat 테스트 작성 (실패)
2. types/chat.ts — GeneralChatRequest, GeneralChatResponse, DocumentSource 추가
3. constants/api.ts — GENERAL_CHAT 상수 추가
4. services/chatService.ts — generalChat() 추가 (authClient)
5. hooks/useChat.ts — useGeneralChat() 추가
6. TDD Green: 테스트 통과 확인
7. pages/ChatPage/index.tsx — useGeneralChat으로 교체, sources 처리
8. TDD Refactor: 코드 정리, SourceChunk deprecated 처리
9. npm run type-check && npm run test:run
```

---

## 9. 리스크

| 리스크 | 대응 |
|--------|------|
| 인증 토큰 없는 상태에서 ChatPage 접근 | `ProtectedRoute`가 이미 /login 리다이렉트 처리 |
| `SourceChunk` → `DocumentSource` 필드명 불일치 | `SourceCitation` 컴포넌트 props 타입 확인 필요 |
| `session_id` 서버 신규 발급 시 클라이언트 동기화 | 응답의 `session_id`를 activeSessionId로 업데이트 필요 |
