/* eslint-disable @typescript-eslint/no-explicit-any -- 훅 mock 인자 (streamRouting.test 와 동일 패턴) */
/**
 * ChatPage 이미지 첨부 — chat-image-attachment Design §8.3 #8~#10.
 * - 업로드 2건 + 엑셀 1건 → subscribe attachments 길이 3, type 조합
 * - 비전 미지원 모델 → 이미지 버튼 비활성
 * - 서버 VISION_NOT_SUPPORTED → 안내 문구 + 첨부 되돌림
 * - 전송된 말풍선에 썸네일
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatPage from './index';
import type { AgentChatOutletContext } from '@/types/agent';

const agentRunCalls: Array<{ enabled?: boolean; attachments?: Array<{ type: string; file_id: string }> }> = [];
let agentRunResult: Record<string, unknown> = {};

vi.mock('@/hooks/useChatStream', () => ({
  useChatStream: (opts: any) => ({
    status: 'idle', tokens: '', toolEvents: [], answer: null, sources: [], wasSummarized: false,
    error: null, isDone: false, isReplayed: false, streamId: opts.streamId ?? '',
  }),
}));

vi.mock('@/hooks/useAgentRunStream', () => ({
  useAgentRunStream: (opts: any) => {
    agentRunCalls.push({ enabled: opts.enabled, attachments: opts.attachments });
    return {
      status: 'idle', steps: [], tokens: '', answer: null, error: null, isDone: false,
      streamId: opts.streamId ?? '',
      ...agentRunResult,
    };
  },
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

const llmModels: Array<{ id: string; supports_vision?: boolean }> = [];
vi.mock('@/hooks/useLlmModels', () => ({ useLlmModels: () => ({ data: llmModels }) }));

const uploadImage = vi.fn();
const uploadExcel = vi.fn();
vi.mock('@/services/agentAttachmentService', () => ({
  default: {
    uploadImage: (...a: unknown[]) => uploadImage(...a),
    uploadExcel: (...a: unknown[]) => uploadExcel(...a),
  },
}));

window.HTMLElement.prototype.scrollIntoView = vi.fn();
(globalThis.URL as any).createObjectURL = vi.fn(() => 'blob:preview');
(globalThis.URL as any).revokeObjectURL = vi.fn();

const AGENT = {
  id: '11111111-2222-3333-4444-555555555555',
  name: 'Vision Agent',
  description: 'd',
  category: 'user',
  isDefault: false,
  llmModelId: 'model-v',
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

const png = (name: string) => new File([new Uint8Array([0x89, 0x50])], name, { type: 'image/png' });

beforeEach(() => {
  agentRunCalls.length = 0;
  agentRunResult = {};
  llmModels.length = 0;
  llmModels.push({ id: 'model-v', supports_vision: true });
  uploadImage.mockReset().mockImplementation(async (f: File) => ({
    file_id: `id-${f.name}`, type: 'image', filename: f.name, size: 2, width: 10, height: 10,
  }));
  uploadExcel.mockReset().mockResolvedValue({ file_id: 'xl-1', type: 'excel', filename: 's.xlsx', size: 3 });
});
afterEach(() => vi.clearAllMocks());

const sendMessage = (text: string) => {
  const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
};

describe('ChatPage — 이미지 첨부', () => {
  it('이미지 2장 + 엑셀 1건을 올리고 전송하면 subscribe attachments 에 3건이 실린다', async () => {
    renderChatPage();
    await userEvent.upload(screen.getByTestId('image-file-input'), [png('a.png'), png('b.png')]);
    await screen.findByText('b.png');
    await userEvent.upload(
      screen.getByTestId('excel-file-input'),
      new File(['x'], 's.xlsx', { type: 'application/vnd.ms-excel' }),
    );
    await screen.findByText('s.xlsx');

    sendMessage('표 값은?');

    const last = agentRunCalls[agentRunCalls.length - 1];
    expect(last.enabled).toBe(true);
    expect(last.attachments).toEqual([
      { type: 'image', file_id: 'id-a.png' },
      { type: 'image', file_id: 'id-b.png' },
      { type: 'excel', file_id: 'xl-1' },
    ]);
    // 전송 후 칩은 비워진다
    expect(screen.queryByText('a.png')).not.toBeInTheDocument();
    // 말풍선 썸네일 2개
    expect(screen.getByTestId('user-image-previews').querySelectorAll('img')).toHaveLength(2);
  });

  it('업로드가 413 으로 실패하면 크기 안내를 보여준다 (G-I6)', async () => {
    const { ApiError } = await import('@/services/api/ApiError');
    uploadImage.mockRejectedValueOnce(new ApiError('too big', 413, 'ATTACHMENT_TOO_LARGE'));
    renderChatPage();
    await userEvent.upload(screen.getByTestId('image-file-input'), png('big.png'));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('10MB'));
  });

  it('비이미지 파일을 드롭하면 안내한다 (G-I5)', async () => {
    renderChatPage();
    const zone = screen.getByTestId('chat-input-dropzone');
    fireEvent.drop(zone, { dataTransfer: { files: [new File(['x'], 'n.txt', { type: 'text/plain' })], types: ['Files'] } });
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('엑셀(.xlsx/.xls) 또는 이미지'));
    expect(uploadImage).not.toHaveBeenCalled();
  });

  it('비전 미지원 모델이면 이미지 버튼이 비활성이다', () => {
    llmModels.length = 0;
    llmModels.push({ id: 'model-v', supports_vision: false });
    renderChatPage();
    expect(screen.getByRole('button', { name: '이미지 첨부' })).toBeDisabled();
  });

  it('모델 목록에 없으면(미로드) 버튼을 막지 않는다 — 권위는 서버', () => {
    llmModels.length = 0;
    renderChatPage();
    expect(screen.getByRole('button', { name: '이미지 첨부' })).toBeEnabled();
  });

  it('6장째는 업로드하지 않고 안내한다', async () => {
    renderChatPage();
    const files = Array.from({ length: 6 }, (_, i) => png(`${i}.png`));
    await userEvent.upload(screen.getByTestId('image-file-input'), files);
    await waitFor(() => expect(uploadImage).toHaveBeenCalledTimes(5));
    expect(screen.getByRole('status')).toHaveTextContent('최대 5장');
  });

  it('서버가 VISION_NOT_SUPPORTED 로 거절하면 안내 문구를 보이고 첨부를 되돌린다', async () => {
    // 훅 mock 이 전송 직후 완료+오류를 돌려주도록 설정 (streamId 는 opts 그대로라 가드 통과)
    agentRunResult = {
      isDone: true,
      error: { code: 'VISION_NOT_SUPPORTED', message: "'GPT-X' 모델은 이미지 입력을 지원하지 않습니다." },
    };
    renderChatPage();
    await userEvent.upload(screen.getByTestId('image-file-input'), png('a.png'));
    await screen.findByText('a.png');
    sendMessage('질문');

    await waitFor(() =>
      expect(screen.getAllByText(/이미지 입력을 지원하지 않습니다/).length).toBeGreaterThan(0),
    );
    // 첨부 되돌림 → 칩 재표시
    expect(await screen.findByText('a.png')).toBeInTheDocument();
  });
});
