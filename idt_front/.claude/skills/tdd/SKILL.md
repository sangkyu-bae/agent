---
name: tdd
description: Test-Driven Development skill for IDT Front. Guides Red→Green→Refactor cycle using Vitest + React Testing Library + MSW. Use when writing tests for hooks, components, or utilities in this project.
---

이 스킬은 IDT Front 프로젝트의 TDD 가이드라인(CLAUDE.md)을 따라 테스트를 작성하고 구현을 진행한다.
프로젝트 기술 스택: **Vitest + React Testing Library + MSW (Mock Service Worker)**

## TDD 사이클 — Red → Green → Refactor

사용자가 기능 또는 파일을 지정하면 다음 순서로 진행한다:

```
1. Red    — 실패하는 테스트 먼저 작성 (구현 없이)
2. Green  — 테스트가 통과하는 최소한의 코드 구현
3. Refactor — 테스트를 유지하며 코드 품질 개선
```

**중요**: 구현 전 반드시 테스트 파일을 먼저 작성한다. 테스트 없는 구현 코드는 작성하지 않는다.

---

## 테스트 파일 위치 규칙

```
# 단위 테스트: 소스 파일 옆에 배치
src/hooks/useChat.ts          → src/hooks/useChat.test.ts
src/utils/formatters.ts       → src/utils/formatters.test.ts
src/components/chat/MessageBubble.tsx → src/components/chat/MessageBubble.test.tsx

# 통합 테스트
src/__tests__/hooks/
src/__tests__/components/

# MSW 핸들러 및 공통 Mock
src/__tests__/mocks/handlers.ts
src/__tests__/mocks/server.ts
src/__tests__/mocks/wrapper.tsx   ← QueryClientProvider 래퍼
```

---

## 테스트 패턴 — 대상별 작성 방법

### 1. 커스텀 훅 테스트 (useQuery/useMutation 포함)

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { useChatSessions } from '@/hooks/useChat';

describe('useChatSessions', () => {
  it('세션 목록을 성공적으로 조회한다', async () => {
    // Arrange: MSW로 성공 응답 설정
    server.use(
      http.get('*/api/chat/sessions', () =>
        HttpResponse.json({ items: mockSessions, total: 2, page: 1, pageSize: 20, hasNext: false })
      )
    );

    // Act
    const { result } = renderHook(() => useChatSessions(), {
      wrapper: createWrapper(),
    });

    // Assert
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(2);
  });

  it('API 오류 시 error 상태가 된다', async () => {
    server.use(
      http.get('*/api/chat/sessions', () => HttpResponse.error())
    );

    const { result } = renderHook(() => useChatSessions(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
```

### 2. Zustand 슬라이스 테스트

```typescript
import { act } from '@testing-library/react';
import { useChatStore } from '@/store/chatStore';

describe('chatStore', () => {
  beforeEach(() => {
    // 스토어 초기화
    useChatStore.getState().reset();
  });

  it('스트리밍 델타를 누적한다', () => {
    const { appendStreamingContent, setStreaming } = useChatStore.getState();

    act(() => {
      setStreaming(true);
      appendStreamingContent('안녕');
      appendStreamingContent('하세요');
    });

    expect(useChatStore.getState().streamingContent).toBe('안녕하세요');
  });
});
```

### 3. 컴포넌트 테스트 (React Testing Library + user-event)

```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import ChatInput from '@/components/chat/ChatInput';

describe('ChatInput', () => {
  it('메시지 입력 후 전송 버튼 클릭 시 onSubmit이 호출된다', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<ChatInput onSubmit={onSubmit} isDisabled={false} />);

    await user.type(screen.getByRole('textbox'), '테스트 메시지');
    await user.click(screen.getByRole('button', { name: /전송/ }));

    expect(onSubmit).toHaveBeenCalledWith('테스트 메시지');
  });

  it('isDisabled=true이면 전송 버튼이 비활성화된다', () => {
    render(<ChatInput onSubmit={vi.fn()} isDisabled={true} />);
    expect(screen.getByRole('button', { name: /전송/ })).toBeDisabled();
  });
});
```

### 4. 유틸리티 함수 테스트 (순수 함수)

```typescript
import { describe, it, expect } from 'vitest';
import { formatFileSize, formatDate } from '@/utils/formatters';

describe('formatFileSize', () => {
  it('1024 바이트를 1 KB로 변환한다', () => {
    expect(formatFileSize(1024)).toBe('1 KB');
  });

  it('1048576 바이트를 1 MB로 변환한다', () => {
    expect(formatFileSize(1048576)).toBe('1 MB');
  });
});
```

### 5. WebSocket 훅 테스트

```typescript
import { renderHook, act } from '@testing-library/react';
import { useWebSocket } from '@/hooks/useWebSocket';

describe('useWebSocket', () => {
  it('연결 시 status가 connected가 된다', async () => {
    const mockWs = { /* WebSocket mock */ };
    vi.stubGlobal('WebSocket', vi.fn(() => mockWs));

    const { result } = renderHook(() => useWebSocket({}));

    act(() => result.current.connect('ws://localhost:8000/ws/test'));

    // onopen 트리거
    act(() => mockWs.onopen?.());

    expect(result.current.status).toBe('connected');
    expect(result.current.isConnected).toBe(true);
  });
});
```

---

## MSW 공통 설정 패턴

### `src/__tests__/mocks/handlers.ts`
```typescript
import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';

export const handlers = [
  // Chat
  http.get(`*${API_ENDPOINTS.CHAT_SESSIONS}`, () =>
    HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 20, hasNext: false })
  ),
  http.post(`*${API_ENDPOINTS.CHAT_MESSAGE}`, () =>
    HttpResponse.json({ data: { messageId: 'msg-1', sessionId: 'session-1' }, success: true })
  ),

  // Documents
  http.get(`*${API_ENDPOINTS.DOCUMENTS}`, () =>
    HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 20, hasNext: false })
  ),

  // Agent
  http.post(`*${API_ENDPOINTS.AGENT_RUN}`, () =>
    HttpResponse.json({ data: { runId: 'run-1' }, success: true })
  ),
];
```

### `src/__tests__/mocks/server.ts`
```typescript
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
```

### `src/__tests__/mocks/wrapper.tsx`
```typescript
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

export const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};
```

---

## 테스트 우선순위 (CLAUDE.md 기준)

| 우선순위 | 대상 | 커버리지 목표 |
|---------|------|:------------:|
| **P1** | 커스텀 훅 (`useChat`, `useDocuments`, `useAgent`, `useWebSocket`) | 80%+ |
| **P1** | 유틸리티 (`formatters`, `streamParser`, `validators`) | 80%+ |
| **P1** | Zustand 슬라이스 (`commonSlices`, 각 스토어) | 80%+ |
| **P2** | UI 컴포넌트 (`ChatInput`, `MessageBubble`, `SourceCitation`) | 60%+ |
| **P3** | 페이지 통합 (`ChatPage`) | 40%+ |

---

## 실행 명령어

```bash
npm run test          # watch 모드 (개발 중)
npm run test:run      # 1회 실행 (CI)
npm run coverage      # 커버리지 리포트
```

---

## 작업 절차

사용자가 특정 파일/기능의 TDD를 요청하면:

1. **대상 파일 읽기** — 구현 코드(또는 인터페이스)를 먼저 파악
2. **Red 단계** — 테스트 파일 작성 (실패하는 테스트, 아직 구현 없음)
3. **Green 단계** — 테스트를 통과시키는 최소 구현 작성
4. **Refactor 단계** — 코드 품질 개선 (테스트는 계속 통과해야 함)
5. **커버리지 확인** — 우선순위별 목표 달성 여부 안내
