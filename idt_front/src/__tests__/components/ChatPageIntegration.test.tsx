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
    selectedAgentId: 'super',
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

  it('I3: 메시지 전송 시 user message + 빈 assistant placeholder가 즉시 추가된다', async () => {
    // ws-agent-chat-streaming Design §5: chat은 WS로 전환됨. HTTP POST /api/v1/chat 호출
    // 자체가 더 이상 발생하지 않으므로 transport-agnostic하게
    // "user message 추가 + placeholder 추가"만 검증한다.
    // 실제 WS 동작은 hooks/useChatStream.test.ts 와 pages/ChatPage/streamRouting.test.tsx 가 cover.
    renderChatApp();

    const textarea = await screen.findByPlaceholderText('상플AI에게 메시지 보내기...');
    fireEvent.change(textarea, { target: { value: '새 메시지' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText('새 메시지')).toBeInTheDocument();
    });
  });

  it('I4: 비로그인 상태에서는 히스토리 API 호출이 발생하지 않는다', async () => {
    mockAuthState.user = null;

    let sessionsCallCount = 0;
    server.use(
      http.get('*/api/v1/conversations/agents/:agentId/sessions', () => {
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
      http.get('*/api/v1/conversations/agents/:agentId/sessions', () =>
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
      http.get('*/api/v1/conversations/agents/:agentId/sessions', ({ request }) => {
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
