// firewall-agent design §5.1·§5.4 — 방화벽 화면 자동 점검 (스케줄·알림 수신 토글)
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  FIREWALL_AUTOMATION_NOT_SET,
  FIREWALL_AUTOMATION_ON,
  firewallError,
} from '@/__tests__/mocks/firewallMocks';
import type { FirewallAutomationResponse } from '@/types/firewall';
import FirewallAutomationBar from './FirewallAutomationBar';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const URL = '*/api/v1/admin/firewall/automation';

const setup = (initial: FirewallAutomationResponse) => {
  const puts: unknown[] = [];
  let current = initial;
  server.use(
    http.get(URL, () => HttpResponse.json(current)),
    http.put(URL, async ({ request }) => {
      const body = (await request.json()) as { schedule_enabled?: boolean; alert_enabled?: boolean };
      puts.push(body);
      current = {
        ...current,
        schedules: current.schedules.map((s) =>
          body.schedule_enabled === undefined ? s : { ...s, enabled: body.schedule_enabled },
        ),
        alert_receiver:
          current.alert_receiver && body.alert_enabled !== undefined
            ? { ...current.alert_receiver, enabled: body.alert_enabled }
            : current.alert_receiver,
      };
      return HttpResponse.json(current);
    }),
  );
  return puts;
};

const renderBar = () => render(<FirewallAutomationBar />, { wrapper: createWrapper() });

describe('FirewallAutomationBar', () => {
  it('보안 에이전트 미설정이면 설정 이름을 안내한다', async () => {
    setup(FIREWALL_AUTOMATION_NOT_SET);
    renderBar();
    expect(await screen.findByText(/보안 에이전트가 지정되지 않았습니다/)).toBeInTheDocument();
    expect(screen.getByText('FIREWALL_ADMIN_AGENT_ID')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('에이전트를 찾지 못하면 그렇게 안내한다', async () => {
    setup({ ...FIREWALL_AUTOMATION_NOT_SET, reason: 'AGENT_NOT_FOUND' });
    renderBar();
    expect(await screen.findByText(/보안 에이전트를 찾을 수 없습니다/)).toBeInTheDocument();
  });

  it('스케줄·알림 수신 상태와 마지막 결과를 보여 준다', async () => {
    setup(FIREWALL_AUTOMATION_ON);
    renderBar();
    expect(await screen.findByText('방화벽 보안 에이전트')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: '스케줄 자동 점검' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByRole('switch', { name: '알림 수신 자동 점검' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByText(/건너뜀 \(승인 대기 중\)/)).toBeInTheDocument();
    expect(screen.getByText(/마지막 수신 .*실행/)).toBeInTheDocument();
  });

  it('끌 때는 확인창을 거친다', async () => {
    const user = userEvent.setup();
    const puts = setup(FIREWALL_AUTOMATION_ON);
    renderBar();
    await user.click(await screen.findByRole('switch', { name: '스케줄 자동 점검' }));
    expect(await screen.findByText(/새 탐지에 대한 자동 판단이 멈춥니다/)).toBeInTheDocument();
    expect(puts).toEqual([]);
    await user.click(screen.getByRole('button', { name: '끄기' }));
    await waitFor(() => expect(puts).toEqual([{ schedule_enabled: false }]));
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: '스케줄 자동 점검' })).toHaveAttribute(
        'aria-checked',
        'false',
      ),
    );
  });

  it('켤 때는 바로 반영한다', async () => {
    const user = userEvent.setup();
    const puts = setup({
      ...FIREWALL_AUTOMATION_ON,
      alert_receiver: { ...FIREWALL_AUTOMATION_ON.alert_receiver!, enabled: false },
    });
    renderBar();
    await user.click(await screen.findByRole('switch', { name: '알림 수신 자동 점검' }));
    await waitFor(() => expect(puts).toEqual([{ alert_enabled: true }]));
  });

  it('스케줄·수신 설정이 없으면 토글 대신 안내한다', async () => {
    setup({ ...FIREWALL_AUTOMATION_ON, schedules: [], alert_receiver: { ...FIREWALL_AUTOMATION_ON.alert_receiver!, configured: false, enabled: null } });
    renderBar();
    expect(await screen.findByText('스케줄 없음')).toBeInTheDocument();
    expect(screen.getByText('알림 수신 미설정')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('조회 실패는 이 영역에만 표시한다', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json(firewallError('INTERNAL', 'boom'), { status: 500 }),
      ),
    );
    renderBar();
    // 다른 탭과 같이 서버 메시지를 우선 쓴다 (firewallErrorMessage)
    const region = await screen.findByRole('region', { name: '자동 점검' });
    expect(await within(region).findByText('boom')).toBeInTheDocument();
  });
});
