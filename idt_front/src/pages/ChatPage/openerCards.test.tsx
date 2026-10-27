/**
 * agent-opener Design §5.2 / §8.3 #8~#11 — 채팅 빈 상태 오프너 카드.
 *   - openers 있음 → 오프너 카드, 고정 4종 미표시
 *   - 카드 클릭 → 그 문장이 즉시 전송된다 (useAgentRunStream enabled + query)
 *   - openers 없음 / super → 고정 4종
 *   - 텍스트는 문자 그대로 렌더 (마크다운·HTML 미해석)
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatPage from './index';
import type { AgentChatOutletContext } from '@/types/agent';

const agentRunCalls: Array<{ enabled?: boolean; query: string }> = [];

vi.mock('@/hooks/useChatStream', () => ({
  useChatStream: (opts: { streamId?: string }) => ({
    status: 'idle', tokens: '', toolEvents: [], answer: null, sources: [],
    wasSummarized: false, error: null, isDone: false, isReplayed: false,
    streamId: opts.streamId ?? '',
  }),
}));

vi.mock('@/hooks/useAgentRunStream', () => ({
  useAgentRunStream: (opts: { enabled?: boolean; query: string; streamId?: string }) => {
    agentRunCalls.push({ enabled: opts.enabled, query: opts.query });
    return {
      status: 'idle', steps: [], tokens: '', answer: null, error: null,
      isDone: false, streamId: opts.streamId ?? '',
    };
  },
}));

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({
      user: { id: 1, email: 't@t.com', role: 'user', status: 'approved' },
      accessToken: 'test-token', refreshToken: 'r', isAuthenticated: true,
    }),
}));

vi.mock('@/store/chatPreferencesStore', () => ({
  useChatPreferencesStore: (selector: (s: unknown) => unknown) =>
    selector({ showToolPreview: true, setShowToolPreview: vi.fn(), toggleShowToolPreview: vi.fn() }),
}));

vi.mock('@/hooks/useChat', () => ({
  useAgentSessionMessages: () => ({ data: [] }),
}));

window.HTMLElement.prototype.scrollIntoView = vi.fn();

// 고정 카드의 보조 문구 — 'AI Agent' 같은 레이블은 헤더에도 있어 유일하지 않다
const FIXED_LABELS = ['업로드한 문서를 요약해줘', '관련 자료를 찾아줘', 'Agent로 데이터 분석해줘', '자유롭게 질문하기'];

function renderWith(selectedAgent: AgentChatOutletContext['selectedAgent']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ctx: AgentChatOutletContext = {
    selectedAgent,
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
}

const customAgent = (openers?: string[]) => ({
  id: '11111111-2222-3333-4444-555555555555',
  name: 'BIS 분석 봇',
  description: '저축은행 BIS 비율 분석',
  category: 'owned',
  openers,
});

beforeEach(() => {
  agentRunCalls.length = 0;
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('ChatPage 빈 상태 — 오프너 카드 (agent-opener)', () => {
  it('오프너가 있으면 그 카드만 보이고 고정 4종은 숨는다', async () => {
    renderWith(customAgent(['BIS 상위 3개사 분석해줘', '변동 원인 요약해줘', '비교 보고서 작성해줘']));
    expect(await screen.findByText('BIS 상위 3개사 분석해줘')).toBeInTheDocument();
    expect(screen.getByText('변동 원인 요약해줘')).toBeInTheDocument();
    expect(screen.getByText('비교 보고서 작성해줘')).toBeInTheDocument();
    for (const label of FIXED_LABELS) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it('오프너 카드 클릭 → 그 문장으로 에이전트 실행이 시작된다', async () => {
    renderWith(customAgent(['BIS 상위 3개사 분석해줘']));
    fireEvent.click(await screen.findByRole('button', { name: /BIS 상위 3개사 분석해줘/ }));
    const started = agentRunCalls.find(
      (c) => c.enabled === true && c.query === 'BIS 상위 3개사 분석해줘',
    );
    expect(started).toBeDefined();
  });

  it('오프너가 없으면 고정 4종을 유지한다', async () => {
    renderWith(customAgent([]));
    expect(await screen.findByText('업로드한 문서를 요약해줘')).toBeInTheDocument();
    for (const label of FIXED_LABELS) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('super 에이전트는 openers가 있어도 고정 4종이다', async () => {
    renderWith({
      id: 'super', name: 'SUPER AI Agent', description: 'meta', category: 'system',
      isDefault: true, openers: ['무시되어야 함'],
    });
    expect(await screen.findByText('업로드한 문서를 요약해줘')).toBeInTheDocument();
    expect(screen.queryByText('무시되어야 함')).not.toBeInTheDocument();
  });

  it('오프너 텍스트는 문자 그대로 렌더된다 (HTML 미해석)', async () => {
    renderWith(customAgent(['<script>alert(1)</script>']));
    expect(await screen.findByText('<script>alert(1)</script>')).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
  });
});
