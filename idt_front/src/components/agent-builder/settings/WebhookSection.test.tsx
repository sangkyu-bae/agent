// agent-webhook Design §6 — WebhookSection 단위 (훅 모킹: TestChatView 선례)
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import WebhookSection from './WebhookSection';
import { API_BASE_URL } from '@/constants/api';
import type { WebhookConfig, WebhookSecretIssue } from '@/types/agentWebhook';

const mocks = vi.hoisted(() => ({
  useAgentWebhook: vi.fn(),
  useEnableWebhook: vi.fn(),
  useRotateWebhookSecret: vi.fn(),
  useUpdateWebhook: vi.fn(),
  useDeleteWebhook: vi.fn(),
  useWebhookDeliveries: vi.fn(),
}));

vi.mock('@/hooks/useAgentWebhook', () => ({
  useAgentWebhook: mocks.useAgentWebhook,
  useEnableWebhook: mocks.useEnableWebhook,
  useRotateWebhookSecret: mocks.useRotateWebhookSecret,
  useUpdateWebhook: mocks.useUpdateWebhook,
  useDeleteWebhook: mocks.useDeleteWebhook,
  useWebhookDeliveries: mocks.useWebhookDeliveries,
  extractWebhookError: (e: unknown) =>
    e instanceof Error ? e.message : '요청에 실패했습니다.',
}));

const AGENT_ID = 'agent-1';

const configured: WebhookConfig = {
  configured: true,
  enabled: true,
  secret_hint: '1234',
  inbound_path: `/api/v1/webhooks/agents/${AGENT_ID}`,
  outbound_url: null,
  outbound_enabled: false,
  created_at: '2026-08-07T00:00:00',
};

const unconfigured: WebhookConfig = {
  configured: false,
  enabled: null,
  secret_hint: null,
  inbound_path: null,
  outbound_url: null,
  outbound_enabled: null,
  created_at: null,
};

const issue: WebhookSecretIssue = {
  secret: 'whsec_plain_once_ABCD',
  secret_hint: 'ABCD',
  enabled: true,
  inbound_path: `/api/v1/webhooks/agents/${AGENT_ID}`,
  created_at: '2026-08-07T00:00:00',
};

const idleMutation = () => ({ mutate: vi.fn(), isPending: false });

let enableMutation: ReturnType<typeof idleMutation>;
let rotateMutation: ReturnType<typeof idleMutation>;
let updateMutation: ReturnType<typeof idleMutation>;
let removeMutation: ReturnType<typeof idleMutation>;

beforeEach(() => {
  enableMutation = idleMutation();
  rotateMutation = idleMutation();
  updateMutation = idleMutation();
  removeMutation = idleMutation();
  mocks.useEnableWebhook.mockReturnValue(enableMutation);
  mocks.useRotateWebhookSecret.mockReturnValue(rotateMutation);
  mocks.useUpdateWebhook.mockReturnValue(updateMutation);
  mocks.useDeleteWebhook.mockReturnValue(removeMutation);
  mocks.useAgentWebhook.mockReturnValue({ data: configured, isLoading: false });
  mocks.useWebhookDeliveries.mockReturnValue({ data: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('WebhookSection — create 모드 (agentId 없음, D9)', () => {
  it('저장 안내만 표시하고 활성화 버튼이 없다', () => {
    mocks.useAgentWebhook.mockReturnValue({ data: undefined, isLoading: false });
    render(<WebhookSection agentId={null} />);
    expect(
      screen.getByText('에이전트를 먼저 저장하면 웹훅을 설정할 수 있습니다.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '웹훅 활성화' }),
    ).not.toBeInTheDocument();
  });
});

describe('WebhookSection — 미설정 상태', () => {
  beforeEach(() => {
    mocks.useAgentWebhook.mockReturnValue({
      data: unconfigured,
      isLoading: false,
    });
  });

  it('활성화 버튼 클릭 시 enable mutation을 호출한다', async () => {
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    await user.click(screen.getByRole('button', { name: '웹훅 활성화' }));
    expect(enableMutation.mutate).toHaveBeenCalledWith(
      { agentId: AGENT_ID },
      expect.any(Object),
    );
  });

  it('발급 성공 시 시크릿 모달을 1회 노출하고 복사할 수 있다', async () => {
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    await user.click(screen.getByRole('button', { name: '웹훅 활성화' }));

    const opts = enableMutation.mutate.mock.calls[0][1] as {
      onSuccess: (r: WebhookSecretIssue) => void;
    };
    opts.onSuccess(issue);

    const dialog = await screen.findByRole('dialog', { name: '웹훅 시크릿' });
    expect(dialog).toHaveTextContent('whsec_plain_once_ABCD');
    expect(dialog).toHaveTextContent('한 번만 표시');

    await user.click(screen.getByRole('button', { name: '시크릿 복사' }));
    // userEvent.setup()이 설치한 클립보드 스텁으로 실제 기록값 검증
    expect(await navigator.clipboard.readText()).toBe('whsec_plain_once_ABCD');

    await user.click(screen.getByRole('button', { name: '확인' }));
    expect(
      screen.queryByRole('dialog', { name: '웹훅 시크릿' }),
    ).not.toBeInTheDocument();
  });
});

describe('WebhookSection — 설정됨 상태', () => {
  it('수신 URL(전체)·시크릿 hint·소유자 경고문을 표시한다', () => {
    render(<WebhookSection agentId={AGENT_ID} />);
    expect(
      screen.getByText(`${API_BASE_URL}/api/v1/webhooks/agents/${AGENT_ID}`),
    ).toBeInTheDocument();
    expect(screen.getByText('whsec_····1234')).toBeInTheDocument();
    expect(
      screen.getByText(/소유자\(나\)의 권한으로 실행됩니다/),
    ).toBeInTheDocument();
  });

  it('토글 클릭 시 반대 값으로 update mutation을 호출한다', async () => {
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    const toggle = screen.getByRole('switch', { name: 'Webhook 토글' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    await user.click(toggle);
    expect(updateMutation.mutate).toHaveBeenCalledWith(
      { agentId: AGENT_ID, data: { enabled: false } },
      expect.any(Object),
    );
  });

  it('키 재발급은 confirm 통과 시에만 rotate mutation을 호출한다', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi
      .spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    render(<WebhookSection agentId={AGENT_ID} />);

    await user.click(screen.getByRole('button', { name: '키 재발급' }));
    expect(rotateMutation.mutate).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '키 재발급' }));
    expect(rotateMutation.mutate).toHaveBeenCalledWith(
      { agentId: AGENT_ID },
      expect.any(Object),
    );
    expect(confirmSpy).toHaveBeenCalledTimes(2);
  });

  it('웹훅 삭제는 confirm 통과 시에만 delete mutation을 호출한다', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<WebhookSection agentId={AGENT_ID} />);
    await user.click(screen.getByRole('button', { name: '웹훅 삭제' }));
    expect(removeMutation.mutate).toHaveBeenCalledWith(
      { agentId: AGENT_ID },
      expect.any(Object),
    );
  });

  it('수신 URL 복사 버튼이 전체 URL을 클립보드에 쓴다', async () => {
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    await user.click(screen.getByRole('button', { name: '수신 URL 복사' }));
    expect(await navigator.clipboard.readText()).toBe(
      `${API_BASE_URL}/api/v1/webhooks/agents/${AGENT_ID}`,
    );
  });
});

describe('WebhookSection — Outbound (M2)', () => {
  it('URL 입력 후 저장 시 outbound_url로 update를 호출한다', async () => {
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    await user.type(
      screen.getByRole('textbox', { name: 'outbound URL' }),
      'https://intra.example.com/receive',
    );
    await user.click(screen.getByRole('button', { name: 'URL 저장' }));
    expect(updateMutation.mutate).toHaveBeenCalledWith(
      {
        agentId: AGENT_ID,
        data: { outbound_url: 'https://intra.example.com/receive' },
      },
      expect.any(Object),
    );
  });

  it('URL 등록 상태에서 해제 클릭 시 null을 전송한다', async () => {
    mocks.useAgentWebhook.mockReturnValue({
      data: { ...configured, outbound_url: 'https://intra.example.com/receive' },
      isLoading: false,
    });
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    await user.click(screen.getByRole('button', { name: '해제' }));
    expect(updateMutation.mutate).toHaveBeenCalledWith(
      { agentId: AGENT_ID, data: { outbound_url: null } },
      expect.any(Object),
    );
  });

  it('Outbound 토글 클릭 시 반대 값으로 update를 호출한다', async () => {
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    const toggle = screen.getByRole('switch', { name: 'Outbound 토글' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await user.click(toggle);
    expect(updateMutation.mutate).toHaveBeenCalledWith(
      { agentId: AGENT_ID, data: { outbound_enabled: true } },
      expect.any(Object),
    );
  });

  it('이력은 접힘 기본 — 펼침 시에만 조회를 활성화한다 (D21)', async () => {
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    expect(mocks.useWebhookDeliveries).toHaveBeenLastCalledWith(AGENT_ID, {
      enabled: false,
    });
    await user.click(screen.getByRole('button', { name: /최근 전송 이력/ }));
    expect(mocks.useWebhookDeliveries).toHaveBeenLastCalledWith(AGENT_ID, {
      enabled: true,
    });
    expect(screen.getByText('아직 발송 이력이 없습니다')).toBeInTheDocument();
  });

  it('이력 행을 성공/실패 배지·계기·상태코드와 함께 렌더한다', async () => {
    mocks.useWebhookDeliveries.mockReturnValue({
      data: [
        {
          id: 'd1', trigger_source: 'schedule', success: true,
          status_code: 200, attempts: 1, error: null, duration_ms: 42,
          created_at: '2026-08-07T09:00:00',
        },
        {
          id: 'd2', trigger_source: 'webhook', success: false,
          status_code: null, attempts: 4, error: 'connection refused',
          duration_ms: 7100, created_at: '2026-08-07T08:00:00',
        },
      ],
    });
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    await user.click(screen.getByRole('button', { name: /최근 전송 이력/ }));
    expect(screen.getByText('성공')).toBeInTheDocument();
    expect(screen.getByText('실패')).toBeInTheDocument();
    expect(screen.getByText('스케줄')).toBeInTheDocument();
    expect(screen.getByText('웹훅')).toBeInTheDocument();
    expect(screen.getByText(/연결 실패 · 4회/)).toBeInTheDocument();
    expect(screen.getByText('connection refused')).toBeInTheDocument();
  });

  it('저장 실패(422) 시 서버 메시지를 인라인 에러로 표출한다', async () => {
    updateMutation.mutate.mockImplementation((_vars, opts) => {
      (opts as { onError: (e: Error) => void }).onError(
        new Error('outbound URL은 http/https 형식이어야 합니다'),
      );
    });
    const user = userEvent.setup();
    render(<WebhookSection agentId={AGENT_ID} />);
    await user.type(
      screen.getByRole('textbox', { name: 'outbound URL' }),
      'ftp://bad',
    );
    await user.click(screen.getByRole('button', { name: 'URL 저장' }));
    expect(screen.getByRole('alert')).toHaveTextContent(
      'outbound URL은 http/https 형식이어야 합니다',
    );
  });

  it('미설정 상태에서는 outbound UI가 없다', () => {
    mocks.useAgentWebhook.mockReturnValue({
      data: unconfigured,
      isLoading: false,
    });
    render(<WebhookSection agentId={AGENT_ID} />);
    expect(
      screen.queryByRole('textbox', { name: 'outbound URL' }),
    ).not.toBeInTheDocument();
  });
});
