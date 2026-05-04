/**
 * ChatPage Integration Tests — Design §8.2.3
 *
 * Renders the full AgentChatLayout → ChatPage routing tree.
 * Session management lives in AgentChatLayout; ChatPage consumes it via outlet context.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { server } from '@/__tests__/mocks/server';
import AgentChatLayout from '@/components/layout/AgentChatLayout';
import ChatPage from '@/pages/ChatPage';

const mockAuthState: {
  user: { id: number; email: string; role: string; status: string } | null;
  accessToken: string | null;
  refreshToken: string | null;
  updateAccessToken: ReturnType<typeof vi.fn>;
  logout: ReturnType<typeof vi.fn>;
} = {
  user: { id: 1, email: 'test@test.com', role: 'user', status: 'approved' },
  accessToken: 'test-token',
  refreshToken: 'test-refresh',
  updateAccessToken: vi.fn(),
  logout: vi.fn(),
};

vi.mock('@/store/authStore', () => ({
  useAuthStore: Object.assign(
    (selector?: (state: typeof mockAuthState) => unknown) =>
      selector ? selector(mockAuthState) : mockAuthState,
    { getState: () => mockAuthState },
  ),
}));

vi.mock('@/store/layoutStore', () => ({
  useLayoutStore: () => ({
    isChatPanelOpen: true,
    selectedAgentId: 'super-ai',
    toggleChatPanel: vi.fn(),
    setChatPanelOpen: vi.fn(),
    selectAgent: vi.fn(),
  }),
}));

window.HTMLElement.prototype.scrollIntoView = vi.fn();

const renderChatApp = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/chatpage']}>
        <Routes>
          <Route element={<AgentChatLayout />}>
            <Route path="/chatpage" element={<ChatPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
  mockAuthState.user = { id: 1, email: 'test@test.com', role: 'user', status: 'approved' };
});
afterAll(() => server.close());

describe('ChatPage Integration (CHAT-HIST-001)', () => {
  it('I1: /chatpage 진입 시 ChatHistoryPanel에 서버 세션 2개가 렌더링된다', async () => {
    renderChatApp();

    await waitFor(() => {
      expect(screen.getByText('안녕')).toBeInTheDocument();
    });
    expect(screen.getByText('이전 질문')).toBeInTheDocument();
  });

  it('I2: 사이드바 세션 클릭 시 이전 메시지가 MessageList에 렌더된다', async () => {
    renderChatApp();

    const sessionButton = await screen.findByText('안녕');
    fireEvent.click(sessionButton);

    await waitFor(() => {
      expect(screen.getByText('이전 질문입니다')).toBeInTheDocument();
    });
    expect(screen.getByText('이전 답변입니다')).toBeInTheDocument();
  });

  it('I3: 새 메시지 전송 성공 → sessions endpoint 재조회 발생한다', async () => {
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
          session_id: 'server-session-1',
          answer: '테스트 답변입니다.',
          tools_used: [],
          sources: [],
          was_summarized: false,
          request_id: 'req-001',
        }),
      ),
    );

    renderChatApp();

    await waitFor(() => expect(sessionsCallCount).toBeGreaterThanOrEqual(1));
    const callsAfterMount = sessionsCallCount;

    const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
    fireEvent.change(textarea, { target: { value: '새 메시지' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(sessionsCallCount).toBeGreaterThan(callsAfterMount);
    });
  });

  it('I4: 비로그인 상태에서는 히스토리 API 호출이 발생하지 않는다', async () => {
    mockAuthState.user = null;

    let sessionsCallCount = 0;
    server.use(
      http.get('*/api/v1/conversations/sessions', () => {
        sessionsCallCount += 1;
        return HttpResponse.json({ user_id: null, sessions: [] });
      }),
    );

    renderChatApp();

    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(sessionsCallCount).toBe(0);
  });

  it('I5: 500 에러 시 에러 배너 + "다시 시도" 버튼이 표시된다', async () => {
    server.use(
      http.get('*/api/v1/conversations/sessions', () =>
        HttpResponse.json({ detail: 'Internal Server Error' }, { status: 500 }),
      ),
    );

    renderChatApp();

    await waitFor(() => {
      expect(screen.getByText(/불러오지 못했습니다/)).toBeInTheDocument();
    });

    const retryButton = screen.getByText('다시 시도');
    expect(retryButton).toBeInTheDocument();

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
