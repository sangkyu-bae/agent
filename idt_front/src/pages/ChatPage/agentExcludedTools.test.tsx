/**
 * tool-access-control FR-11 (Design §8.4 L2-7) — excluded_tools 가 오면 답변 아래 안내를 그린다.
 * streamRouting.test.tsx 와 같은 훅 mock 구성을 쓴다.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatPage from './index';
import type { AgentChatOutletContext } from '@/types/agent';

interface StreamOpts {
  enabled?: boolean;
  streamId?: string;
}
type Selector = (state: Record<string, unknown>) => unknown;

vi.mock('@/hooks/useChatStream', async () => ({
  useChatStream: (opts: StreamOpts) => ({
    status: 'idle', tokens: '', toolEvents: [], answer: null, sources: [],
    wasSummarized: false, error: null, isDone: false, isReplayed: false,
    streamId: opts.streamId ?? '',
  }),
}));

// 활성화되면 곧바로 제외 도구가 실린 완료 상태를 돌려준다.
vi.mock('@/hooks/useAgentRunStream', async () => ({
  useAgentRunStream: (opts: StreamOpts) => {
    const done = Boolean(opts.enabled && opts.streamId);
    return {
      status: 'idle', steps: [], tokens: '', charts: [], error: null,
      answer: done ? '권한 제한 답변' : null,
      isDone: done,
      sources: [],
      excludedTools: done
        ? [{ tool_id: 'internal:python_code_executor', name: 'Python 코드 실행', reason: 'no_permission' }]
        : [],
      streamId: opts.streamId ?? '',
    };
  },
}));

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: Selector) =>
    selector({
      user: { id: 1, email: 't@t.com', role: 'user', status: 'approved' },
      accessToken: 'test-token', refreshToken: 'r', isAuthenticated: true,
    }),
}));

vi.mock('@/store/chatPreferencesStore', () => ({
  useChatPreferencesStore: (selector: Selector) =>
    selector({ showToolPreview: true, setShowToolPreview: vi.fn(), toggleShowToolPreview: vi.fn() }),
}));

vi.mock('@/hooks/useChat', () => ({
  useAgentSessionMessages: () => ({ data: [] }),
}));

window.HTMLElement.prototype.scrollIntoView = vi.fn();

const renderWithAgent = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ctx: AgentChatOutletContext = {
    selectedAgent: {
      id: '11111111-2222-3333-4444-555555555555',
      name: 'My Agent', description: 'custom', category: 'user', isDefault: false,
    },
    activeSessionId: 'sess-1',
    setActiveSessionId: vi.fn(),
    handleNewChat: vi.fn(),
    sessions: [],
    refetchSessions: vi.fn(),
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/chatpage']}>
        <Routes>
          <Route element={<Outlet context={ctx} />}>
            <Route path="/chatpage" element={<ChatPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

afterEach(() => {
  vi.clearAllMocks();
});

describe('ChatPage — 권한 제외 도구 안내', () => {
  it('답변 완료 시 제외된 도구 이름을 안내한다', async () => {
    renderWithAgent();
    const textarea = await screen.findByPlaceholderText('상플AI에게 메시지 보내기...');
    fireEvent.change(textarea, { target: { value: '질문' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(await screen.findByText('권한 제한 답변')).toBeInTheDocument();
    expect(screen.getByText('권한이 없어 사용하지 않은 도구: Python 코드 실행')).toBeInTheDocument();
  });
});
