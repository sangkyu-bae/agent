/**
 * ChatPage Integration Tests — Design §8.2.3
 *
 * I1: /chat 진입 시 Sidebar에 서버 세션 목록 렌더
 * I2: 세션 클릭 → MessageList에 해당 세션 메시지 렌더
 * I3: 메시지 전송 후 sidebar 세션 invalidate → 재조회 호출
 * I4: 비로그인 상태 → 세션 쿼리 disabled, 빈 상태 UI
 * I5: 세션 조회 실패 → Sidebar에 error banner + "다시 시도" 버튼 → retry 시 재요청
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { server } from '@/__tests__/mocks/server';
import ChatPage from '@/pages/ChatPage';

// useAuthStore mock — same pattern as ChatPage.test.tsx:21-33
// mutable so individual tests (I4) can simulate signed-out state
const mockAuthState: {
  user: { id: number } | null;
  accessToken: string | null;
  refreshToken: string | null;
  updateAccessToken: ReturnType<typeof vi.fn>;
  logout: ReturnType<typeof vi.fn>;
} = {
  user: { id: 1 },
  accessToken: null,
  refreshToken: null,
  updateAccessToken: vi.fn(),
  logout: vi.fn(),
};
vi.mock('@/store/authStore', () => ({
  useAuthStore: Object.assign(
    (selector: (state: typeof mockAuthState) => unknown) => selector(mockAuthState),
    { getState: () => mockAuthState },
  ),
}));

// jsdom does not support scrollIntoView
window.HTMLElement.prototype.scrollIntoView = vi.fn();

const createTestWrapper = (queryClient?: QueryClient) => {
  const qc = queryClient ?? new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  Wrapper.displayName = 'TestWrapper';
  return Wrapper;
};

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
  // restore default auth state between tests (I4 mutates it)
  mockAuthState.user = { id: 1 };
});
afterAll(() => server.close());

describe('ChatPage Integration (CHAT-HIST-001)', () => {
  it('I1: /chat 진입 시 Sidebar에 서버 세션 2개가 렌더링된다', async () => {
    render(<ChatPage />, { wrapper: createTestWrapper() });

    // MSW default handler returns sessions s1='안녕', s2='이전 질문'
    await waitFor(() => {
      expect(screen.getByText('안녕')).toBeInTheDocument();
    });
    expect(screen.getByText('이전 질문')).toBeInTheDocument();
  });

  it('I2: 사이드바 세션 클릭 시 이전 메시지가 MessageList에 렌더된다', async () => {
    render(<ChatPage />, { wrapper: createTestWrapper() });

    // Wait for sessions to load
    const sessionButton = await screen.findByText('안녕');
    fireEvent.click(sessionButton);

    // MSW handler returns messages: '이전 질문입니다', '이전 답변입니다'
    await waitFor(() => {
      expect(screen.getByText('이전 질문입니다')).toBeInTheDocument();
    });
    expect(screen.getByText('이전 답변입니다')).toBeInTheDocument();
  });

  it('I3: 새 메시지 전송 성공 → sessions endpoint 재조회 발생한다 (invalidation triggers refetch)', async () => {
    let sessionsCallCount = 0;

    server.use(
      http.get('*/api/v1/conversations/sessions', ({ request }) => {
        sessionsCallCount += 1;
        const url = new URL(request.url);
        const userId = url.searchParams.get('user_id');
        return HttpResponse.json({
          user_id: userId,
          sessions: [
            {
              session_id: 's1',
              message_count: sessionsCallCount + 3,
              last_message: '새로 업데이트된 메시지',
              last_message_at: '2026-04-17T11:00:00Z',
            },
          ],
        });
      }),
      http.post('*/api/v1/chat', () =>
        HttpResponse.json({
          user_id: '1',
          session_id: 'uuid-init-1',
          answer: '테스트 답변입니다.',
          tools_used: [],
          sources: [],
          was_summarized: false,
          request_id: 'req-001',
        }),
      ),
    );

    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('uuid-init-1' as `${string}-${string}-${string}-${string}-${string}`)
      .mockReturnValue('uuid-msg-id' as `${string}-${string}-${string}-${string}-${string}`);

    render(<ChatPage />, { wrapper: createTestWrapper() });

    // Wait for initial sessions load (call #1)
    await waitFor(() => expect(sessionsCallCount).toBeGreaterThanOrEqual(1));
    const callsAfterMount = sessionsCallCount;

    // Send a message to trigger invalidation
    const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
    fireEvent.change(textarea, { target: { value: '새 메시지' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    // After send success, invalidation should trigger a re-fetch (call count increases)
    await waitFor(() => {
      expect(sessionsCallCount).toBeGreaterThan(callsAfterMount);
    });
  });

  it('I4: 비로그인 상태에서는 히스토리 API 호출이 발생하지 않는다', async () => {
    // Simulate signed-out user — selector will now see user: null
    mockAuthState.user = null;

    let sessionsCallCount = 0;
    server.use(
      http.get('*/api/v1/conversations/sessions', () => {
        sessionsCallCount += 1;
        return HttpResponse.json({ user_id: null, sessions: [] });
      }),
    );

    render(<ChatPage />, { wrapper: createTestWrapper() });

    // Give react-query a chance to run enabled check and confirm no fetch occurs
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(sessionsCallCount).toBe(0);
  });

  it('I5: 500 에러 시 Sidebar에 에러 배너 + "다시 시도" 버튼이 표시된다', async () => {
    server.use(
      http.get('*/api/v1/conversations/sessions', () =>
        HttpResponse.json({ detail: 'Internal Server Error' }, { status: 500 }),
      ),
    );

    render(<ChatPage />, { wrapper: createTestWrapper() });

    // Error banner should appear
    await waitFor(() => {
      expect(screen.getByText(/불러오지 못했습니다/)).toBeInTheDocument();
    });

    // Retry button should be present
    const retryButton = screen.getByText('다시 시도');
    expect(retryButton).toBeInTheDocument();

    // Click retry — should trigger another request
    let retryCallCount = 0;
    server.use(
      http.get('*/api/v1/conversations/sessions', ({ request }) => {
        retryCallCount += 1;
        const url = new URL(request.url);
        return HttpResponse.json({
          user_id: url.searchParams.get('user_id'),
          sessions: [
            { session_id: 's1', message_count: 1, last_message: '복구됨', last_message_at: '2026-04-17T10:00:00Z' },
          ],
        });
      }),
    );

    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(retryCallCount).toBeGreaterThanOrEqual(1);
    });
  });
});
