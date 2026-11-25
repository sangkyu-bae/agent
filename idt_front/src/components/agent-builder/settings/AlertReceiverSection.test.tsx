// firewall-agent design §5.2·§5.4 — 빌더 설정 탭 "알림 수신"
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import type { AlertReceiverConfig } from '@/types/alertReceiver';
import AlertReceiverSection from './AlertReceiverSection';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const BASE = '*/api/v1/agents/agent-1/alert-receiver';

const CONFIGURED: AlertReceiverConfig = {
  configured: true,
  enabled: false,
  skip_when_busy: true,
  instruction_prefix: '정책대로 처리하라.',
  token_hint: 'wxyz',
  inbound_path: '/api/v1/alert-hooks/agents/agent-1',
  updated_at: '2026-11-24T05:00:00',
};

const setup = (initial: AlertReceiverConfig) => {
  const puts: unknown[] = [];
  let current = initial;
  server.use(
    http.get(BASE, () => HttpResponse.json(current)),
    http.put(BASE, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      puts.push(body);
      const created = !current.configured;
      current = {
        ...CONFIGURED,
        ...(created ? { enabled: false, instruction_prefix: '' } : current),
        ...body,
      } as AlertReceiverConfig;
      return HttpResponse.json({ config: current, token: created ? 'tok-first-ABCD' : null });
    }),
    http.post(`${BASE}/token`, () =>
      HttpResponse.json({ config: { ...current, token_hint: 'EFGH' }, token: 'tok-rotated-EFGH' }),
    ),
    http.get(`${BASE}/receipts`, () =>
      HttpResponse.json([
        {
          id: 'rc-1',
          result: 'skipped_busy',
          skip_reason: 'approval_pending',
          firing_count: 3,
          job_id: null,
          received_at: '2026-11-24T05:12:00',
        },
      ]),
    ),
  );
  return puts;
};

const renderSection = (agentId: string | null = 'agent-1') =>
  render(<AlertReceiverSection agentId={agentId} />, { wrapper: createWrapper() });

describe('AlertReceiverSection', () => {
  it('저장 전 에이전트는 안내만 보여 준다', () => {
    renderSection(null);
    expect(screen.getByText(/에이전트를 먼저 저장하면/)).toBeInTheDocument();
  });

  it('미설정이면 설정 버튼 → 토큰을 한 번만 보여 준다', async () => {
    const user = userEvent.setup();
    const puts = setup({ ...CONFIGURED, configured: false, enabled: null, token_hint: null, inbound_path: null });
    renderSection();
    await user.click(await screen.findByRole('button', { name: '알림 수신 설정' }));
    await waitFor(() => expect(puts).toEqual([{}]));
    const dialog = await screen.findByRole('dialog', { name: '알림 수신 토큰' });
    expect(within(dialog).getByText('tok-first-ABCD')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: '확인' }));
    expect(screen.queryByText('tok-first-ABCD')).not.toBeInTheDocument();
    expect(await screen.findByText(/····wxyz|····ABCD/)).toBeInTheDocument();
  });

  it('수신 주소·토큰 힌트·옵션을 보여 준다', async () => {
    setup(CONFIGURED);
    renderSection();
    expect(await screen.findByText(/\/api\/v1\/alert-hooks\/agents\/agent-1$/)).toBeInTheDocument();
    expect(screen.getByText('····wxyz')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: '알림 수신 토글' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('checkbox', { name: /승인 대기 중이면 건너뛰기/ })).toBeChecked();
    expect(screen.getByRole('textbox', { name: '지침 앞머리' })).toHaveValue('정책대로 처리하라.');
  });

  it('켜기·건너뜀·앞머리는 바뀐 필드만 보낸다', async () => {
    const user = userEvent.setup();
    const puts = setup(CONFIGURED);
    renderSection();
    await user.click(await screen.findByRole('switch', { name: '알림 수신 토글' }));
    await waitFor(() => expect(puts).toContainEqual({ enabled: true }));
    await user.click(screen.getByRole('checkbox', { name: /승인 대기 중이면 건너뛰기/ }));
    await waitFor(() => expect(puts).toContainEqual({ skip_when_busy: false }));
    const prefix = screen.getByRole('textbox', { name: '지침 앞머리' });
    await user.clear(prefix);
    await user.type(prefix, '탐지 정책 v0.2 대로');
    await user.click(screen.getByRole('button', { name: '앞머리 저장' }));
    await waitFor(() => expect(puts).toContainEqual({ instruction_prefix: '탐지 정책 v0.2 대로' }));
  });

  it('토큰 재발급은 확인 후 새 토큰을 한 번 보여 준다', async () => {
    const user = userEvent.setup();
    setup(CONFIGURED);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderSection();
    await user.click(await screen.findByRole('button', { name: '토큰 재발급' }));
    expect(confirmSpy).toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog', { name: '알림 수신 토큰' });
    expect(within(dialog).getByText('tok-rotated-EFGH')).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it('최근 수신을 펼치면 결과·사유를 보여 준다', async () => {
    const user = userEvent.setup();
    setup(CONFIGURED);
    renderSection();
    await user.click(await screen.findByRole('button', { name: /최근 수신/ }));
    expect(await screen.findByText('건너뜀')).toBeInTheDocument();
    expect(screen.getByText(/발화 3건 · 승인 대기 중/)).toBeInTheDocument();

  });
});
