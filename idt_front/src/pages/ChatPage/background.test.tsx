/**
 * ChatPage 백그라운드 작업 통합 테스트 (background-jobs Design §6-M2).
 *
 * 검증: 진행중 세션 입력 잠금 + 진행중 배너(D5), 접수 배너, 409 지정 문구.
 * 스트림 훅은 streamRouting.test.tsx 와 동일하게 idle 로 모킹한다.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AxiosError } from 'axios';

import ChatPage from './index';
import type { AgentChatOutletContext } from '@/types/agent';
import type { BackgroundJob } from '@/types/backgroundJob';

const bg = vi.hoisted(() => ({
  useJobList: vi.fn(),
  useEnqueueJob: vi.fn(),
}));

// extractJobError / isJobConflictError 는 실제 구현 유지 (409 판별 검증 대상)
vi.mock('@/hooks/useBackgroundJobs', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/hooks/useBackgroundJobs')>();
  return {
    ...actual,
    useJobList: bg.useJobList,
    useEnqueueJob: bg.useEnqueueJob,
  };
});

vi.mock('@/hooks/useChatStream', () => ({
  useChatStream: (opts: { streamId?: string }) => ({
    status: 'idle',
    tokens: '',
    toolEvents: [],
    answer: null,
    sources: [],
    error: null,
    isDone: false,
    streamId: opts.streamId ?? '',
  }),
}));

vi.mock('@/hooks/useAgentRunStream', () => ({
  useAgentRunStream: (opts: { streamId?: string }) => ({
    status: 'idle',
    steps: [],
    tokens: '',
    answer: null,
    charts: [],
    error: null,
    isDone: false,
    streamId: opts.streamId ?? '',
  }),
}));

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({
      user: { id: 1, email: 't@t.com', role: 'user', status: 'approved' },
      accessToken: 'test-token',
      isAuthenticated: true,
    }),
}));

vi.mock('@/store/chatPreferencesStore', () => ({
  useChatPreferencesStore: (selector: (s: unknown) => unknown) =>
    selector({ showToolPreview: true, setShowToolPreview: vi.fn() }),
}));

vi.mock('@/hooks/useChat', () => ({
  useAgentSessionMessages: () => ({ data: [] }),
}));

window.HTMLElement.prototype.scrollIntoView = vi.fn();

const AGENT = {
  id: '11111111-2222-3333-4444-555555555555',
  name: 'My Agent',
  description: 'custom',
  category: 'user',
  isDefault: false,
};

const activeJob = (overrides: Partial<BackgroundJob> = {}): BackgroundJob => ({
  id: 'j1',
  agent_id: AGENT.id,
  agent_name: 'My Agent',
  source: 'chat',
  query: '보고서 만들어줘',
  session_id: 'sess-1',
  run_id: null,
  status: 'running',
  error_message: null,
  seen_at: null,
  queued_at: '2026-08-11T02:00:00',
  started_at: '2026-08-11T02:00:05',
  finished_at: null,
  ...overrides,
});

function renderChatPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ctx: AgentChatOutletContext = {
    selectedAgent: AGENT,
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

const mutateMock = vi.fn();

beforeEach(() => {
  bg.useJobList.mockReturnValue({ data: [] });
  bg.useEnqueueJob.mockReturnValue({ mutate: mutateMock, isPending: false });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('ChatPage — 백그라운드 작업 통합 (S9)', () => {
  it('현재 세션에 진행중 job 이 있으면 배너를 띄우고 입력을 잠근다 (D5)', async () => {
    bg.useJobList.mockReturnValue({ data: [activeJob()] });
    renderChatPage();
    expect(
      screen.getByText(/이 대화에서 백그라운드 작업이 실행 중입니다/),
    ).toBeInTheDocument();
    const textarea = await screen.findByPlaceholderText(
      '상플AI에게 메시지 보내기...',
    );
    expect(textarea).toBeDisabled();
  });

  it('다른 세션의 진행중 job 은 입력을 잠그지 않는다', async () => {
    bg.useJobList.mockReturnValue({
      data: [activeJob({ session_id: 'other-sess' })],
    });
    renderChatPage();
    expect(
      screen.queryByText(/이 대화에서 백그라운드 작업이 실행 중입니다/),
    ).not.toBeInTheDocument();
    const textarea = await screen.findByPlaceholderText(
      '상플AI에게 메시지 보내기...',
    );
    expect(textarea).not.toBeDisabled();
  });

  it('백그라운드 등록 성공 시 접수 배너를 표시한다', async () => {
    mutateMock.mockImplementation(
      (_vars: unknown, opts?: { onSuccess?: () => void }) =>
        opts?.onSuccess?.(),
    );
    renderChatPage();
    const textarea = await screen.findByPlaceholderText(
      '상플AI에게 메시지 보내기...',
    );
    fireEvent.change(textarea, { target: { value: '시장 조사 보고서' } });
    fireEvent.click(screen.getByRole('button', { name: '백그라운드로 실행' }));
    expect(mutateMock).toHaveBeenCalledWith(
      {
        agentId: AGENT.id,
        data: { query: '시장 조사 보고서', session_id: 'sess-1', source: 'chat' },
      },
      expect.anything(),
    );
    expect(
      screen.getByText(/백그라운드에서 실행 중입니다/),
    ).toBeInTheDocument();
  });

  it('409 응답이면 지정 문구를 표시한다 — 진행중 배너에 가려지지 않는다', async () => {
    const conflict = new AxiosError(
      'conflict',
      'ERR_BAD_REQUEST',
      undefined,
      undefined,
      {
        status: 409,
        statusText: 'Conflict',
        headers: {},
        config: {} as never,
        data: { detail: '해당 세션에 진행 중인 작업이 있습니다' },
      },
    );
    mutateMock.mockImplementation(
      (_vars: unknown, opts?: { onError?: (e: unknown) => void }) =>
        opts?.onError?.(conflict),
    );
    // 폴링 지연으로 아직 잠금 전인 경합 상황 — 서버 409 가 먼저 도착
    renderChatPage();
    const textarea = await screen.findByPlaceholderText(
      '상플AI에게 메시지 보내기...',
    );
    fireEvent.change(textarea, { target: { value: '중복 요청' } });
    fireEvent.click(screen.getByRole('button', { name: '백그라운드로 실행' }));
    expect(
      screen.getByText(/이미 이 대화에서 진행 중인 백그라운드 작업이 있어요/),
    ).toBeInTheDocument();
  });
});
