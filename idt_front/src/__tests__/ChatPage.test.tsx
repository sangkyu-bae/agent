/**
 * ChatPage 세션 초기화 버그 수정 검증
 *
 * TC-FE-1: 초기화 시 crypto.randomUUID가 한 번만 호출된다
 *   (버그: createSession()이 sessions + activeSessionId 초기화에 각각 한 번씩 → 2회 호출)
 *   (수정: sessions[0].id를 직접 참조 → 1회 호출)
 *
 * TC-FE-2: 두 번째 메시지 발송 시 서버 반환 session_id를 사용한다
 *   (syncSessionId가 올바르게 동작하면 두 번째 요청은 서버 session_id를 사용해야 함)
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { server } from '@/__tests__/mocks/server';
import ChatPage from '@/pages/ChatPage';

// useAuthStore mock (hook + getState for authClient interceptor)
const mockAuthState = {
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

describe('ChatPage 세션 초기화', () => {
  it('TC-FE-1: 초기화 시 crypto.randomUUID는 한 번만 호출된다', () => {
    const uuidSpy = vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'uuid-session-1' as `${string}-${string}-${string}-${string}-${string}`,
    );

    render(<ChatPage />, { wrapper: createTestWrapper() });

    // sessions 초기화에서 1회만 호출되어야 함
    // 버그 상태: activeSessionId 초기화에서도 추가 호출 → 2회
    expect(uuidSpy).toHaveBeenCalledTimes(1);
  });

  it('TC-FE-2: 첫 응답 후 두 번째 메시지는 서버 반환 session_id를 사용한다', async () => {
    const capturedBodies: Array<{ session_id: string; message: string }> = [];

    server.use(
      http.post('*', async ({ request }) => {
        const body = (await request.json()) as { session_id: string; message: string };
        capturedBodies.push(body);
        return HttpResponse.json({
          user_id: '1',
          session_id: 'server-session-abc',
          answer: '테스트 답변',
          tools_used: [],
          sources: [],
          was_summarized: false,
          request_id: 'req-001',
        });
      }),
    );

    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('uuid-init-1' as `${string}-${string}-${string}-${string}-${string}`)
      .mockReturnValue('uuid-msg-id' as `${string}-${string}-${string}-${string}-${string}`);

    render(<ChatPage />, { wrapper: createTestWrapper() });

    const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');

    // 첫 번째 메시지 발송
    fireEvent.change(textarea, { target: { value: '첫 번째 질문' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    // 첫 번째 응답 대기
    await waitFor(() => expect(capturedBodies).toHaveLength(1));
    expect(capturedBodies[0].session_id).toBe('uuid-init-1');

    // 두 번째 메시지 발송
    fireEvent.change(textarea, { target: { value: '두 번째 질문' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    // 두 번째 요청 대기
    await waitFor(() => expect(capturedBodies).toHaveLength(2));

    // 두 번째 요청은 서버가 반환한 session_id를 사용해야 함
    expect(capturedBodies[1].session_id).toBe('server-session-abc');
  });
});
