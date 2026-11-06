/* eslint-disable @typescript-eslint/no-explicit-any -- 훅 mock 인자 (imageAttachment.test 와 동일 패턴) */
/**
 * ChatPage 에이전트 답변 평가 노출 — agent-run-feedback-wiring Design §8.3 #4~#5.
 * - agent_answer_completed 가 assistant_message_id 를 주면 말풍선에 👍/👎 버튼
 * - id 가 없으면 버튼 미노출
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatPage from './index';
import type { AgentChatOutletContext } from '@/types/agent';

let agentRunResult: Record<string, unknown> = {};

vi.mock('@/hooks/useChatStream', () => ({
  useChatStream: (opts: any) => ({
    status: 'idle', tokens: '', toolEvents: [], answer: null, sources: [], wasSummarized: false,
    error: null, isDone: false, isReplayed: false, streamId: opts.streamId ?? '',
    assistantMessageId: null,
  }),
}));

vi.mock('@/hooks/useAgentRunStream', () => ({
  useAgentRunStream: (opts: any) => ({
    status: 'idle', steps: [], tokens: '', answer: null, error: null, isDone: false, charts: [],
    assistantMessageId: null,
    streamId: opts.streamId ?? '',
    ...agentRunResult,
  }),
}));

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: any) =>
    selector({ user: { id: 1, email: 't@t.com', role: 'user', status: 'approved' }, accessToken: 't', refreshToken: 'r', isAuthenticated: true }),
}));
vi.mock('@/store/chatPreferencesStore', () => ({
  useChatPreferencesStore: (selector: any) =>
    selector({ showToolPreview: true, setShowToolPreview: vi.fn(), toggleShowToolPreview: vi.fn() }),
}));
vi.mock('@/hooks/useChat', () => ({ useAgentSessionMessages: () => ({ data: [] }) }));
vi.mock('@/hooks/useBackgroundJobs', () => ({
  useEnqueueJob: () => ({ mutate: vi.fn(), isPending: false }),
  useJobHistory: () => ({ data: undefined }),
  extractJobError: () => '',
  isJobConflictError: () => false,
}));
vi.mock('@/hooks/useLlmModels', () => ({ useLlmModels: () => ({ data: [] }) }));
// 평가 컴포넌트가 쓰는 조회·전송 훅은 네트워크 없이 고정
vi.mock('@/hooks/useMessageFeedback', () => ({
  useMessageFeedback: () => ({ data: undefined }),
  useSubmitFeedback: () => ({ mutate: vi.fn(), isPending: false }),
}));

window.HTMLElement.prototype.scrollIntoView = vi.fn();

const AGENT = {
  id: '11111111-2222-3333-4444-555555555555',
  name: 'Agent',
  description: 'd',
  category: 'user',
  isDefault: false,
  llmModelId: 'model-1',
};

function renderChatPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

const sendMessage = (text: string) => {
  const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
};

beforeEach(() => {
  agentRunResult = {};
});
afterEach(() => vi.clearAllMocks());

describe('ChatPage — 에이전트 답변 평가 노출', () => {
  it('assistant_message_id 가 오면 완료된 답변 아래에 👍/👎 버튼이 보인다', async () => {
    agentRunResult = { answer: '검토 결과입니다.', isDone: true, assistantMessageId: 4821 };
    renderChatPage();
    sendMessage('규정 근거 알려줘');

    expect(await screen.findByText('검토 결과입니다.')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '좋아요' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '싫어요' })).toBeInTheDocument();
  });

  it('assistant_message_id 가 없으면(미저장·구 서버) 평가 버튼을 보이지 않는다', async () => {
    agentRunResult = { answer: '검토 결과입니다.', isDone: true, assistantMessageId: null };
    renderChatPage();
    sendMessage('규정 근거 알려줘');

    expect(await screen.findByText('검토 결과입니다.')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '좋아요' })).not.toBeInTheDocument(),
    );
  });
});
