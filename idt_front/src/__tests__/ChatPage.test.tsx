/**
 * ChatPage Unit Tests
 *
 * ChatPage는 AgentChatLayout이 Outlet context로 세션 상태를 전달한다.
 * 단위 테스트에서는 useOutletContext를 mock하여 ChatPage 고유 로직만 검증한다.
 *
 * TC-FE-1: 빈 세션에서 EmptyAgentState가 표시된다
 * TC-FE-2: 메시지 전송 성공 시 syncSessionId가 올바르게 동작한다
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { server } from '@/__tests__/mocks/server';
import ChatPage from '@/pages/ChatPage';

const mockSetActiveSessionId = vi.fn();
const mockRefetchSessions = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useOutletContext: () => ({
      selectedAgent: { id: 'super', name: 'SUPER AI Agent', description: 'test', category: 'system', isDefault: true },
      activeSessionId: 'test-session-1',
      setActiveSessionId: mockSetActiveSessionId,
      handleNewChat: vi.fn(),
      sessions: [{ id: 'test-session-1', title: '새 대화', messages: [], createdAt: '2026-04-17T10:00:00Z', updatedAt: '2026-04-17T10:00:00Z' }],
      refetchSessions: mockRefetchSessions,
    }),
  };
});

const mockAuthState: {
  user: { id: number; email: string; role: string; status: string } | null;
  accessToken: string | null;
  refreshToken: string | null;
  updateAccessToken: ReturnType<typeof vi.fn>;
  logout: ReturnType<typeof vi.fn>;
} = {
  user: { id: 1, email: 'test@test.com', role: 'user', status: 'approved' },
  accessToken: 'test-token',
  refreshToken: null,
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

window.HTMLElement.prototype.scrollIntoView = vi.fn();

const createTestWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
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
});
afterAll(() => server.close());

describe('ChatPage 단위 테스트', () => {
  it('TC-FE-1: 빈 세션(draft)에서 EmptyAgentState가 표시된다', () => {
    render(<ChatPage />, { wrapper: createTestWrapper() });
    expect(screen.getByText(/SUPER AI Agent와 대화하세요/)).toBeInTheDocument();
  });

  it('TC-FE-2: 메시지 전송 성공 시 setActiveSessionId가 서버 세션 ID로 호출된다', async () => {
    server.use(
      http.post('*/api/v1/chat', () =>
        HttpResponse.json({
          user_id: '1',
          session_id: 'server-session-abc',
          answer: '테스트 답변',
          tools_used: [],
          sources: [],
          was_summarized: false,
          request_id: 'req-001',
        }),
      ),
    );

    render(<ChatPage />, { wrapper: createTestWrapper() });

    const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
    fireEvent.change(textarea, { target: { value: '첫 번째 질문' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(mockSetActiveSessionId).toHaveBeenCalledWith('server-session-abc');
    });
  });
});
