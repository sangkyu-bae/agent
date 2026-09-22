// approval-gate Check G3 / FR-22 — 에이전트 편집 화면의 승인 게이트 설정
// 실제 TanStack Query + MSW 경로를 태운다 (훅 모킹 없음).
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import ApprovalGateSettingsPanel from './ApprovalGateSettingsPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const settings = (over = {}) => ({
  available: true,
  enabled: true,
  is_enforced: false,
  config: { mode: 'always', execute_after: '0 0 * * *', expires_hours: 24, on_expire: 'expire' },
  ...over,
});

const useSettings = (body: object) =>
  server.use(
    http.get('*/api/v1/agents/ag1/approval-gate', () => HttpResponse.json(body)),
  );

const renderPanel = () =>
  render(<ApprovalGateSettingsPanel agentId="ag1" />, { wrapper: createWrapper() });

describe('ApprovalGateSettingsPanel — 조회', () => {
  it('저장된 설정을 폼에 채운다', async () => {
    useSettings(settings());
    renderPanel();
    expect(await screen.findByLabelText('집행 시각 cron')).toHaveValue('0 0 * * *');
    expect(screen.getByLabelText('만료 시간')).toHaveValue(24);
    expect(screen.getByLabelText('승인 게이트 사용')).toBeChecked();
  });

  it('적용 전(enabled=false)이면 꺼진 것으로 보인다', async () => {
    useSettings(settings({ enabled: false }));
    renderPanel();
    expect(await screen.findByLabelText('승인 게이트 사용')).not.toBeChecked();
  });

  it('타임존 기준을 안내한다 (Check G13)', async () => {
    useSettings(settings());
    renderPanel();
    expect(await screen.findByText(/Asia\/Seoul 기준/)).toBeInTheDocument();
  });

  it('관리자가 비활성화했으면 안내만 보인다', async () => {
    useSettings(settings({ available: false }));
    renderPanel();
    expect(
      await screen.findByText('관리자가 승인 게이트를 활성화하지 않았습니다.'),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('승인 게이트 사용')).not.toBeInTheDocument();
  });

  it('강제면 토글이 잠긴다', async () => {
    useSettings(settings({ is_enforced: true }));
    renderPanel();
    expect(await screen.findByLabelText('승인 게이트 사용')).toBeDisabled();
    expect(screen.getByText('관리자 강제')).toBeInTheDocument();
  });

  it('조회 실패 시 alert', async () => {
    server.use(
      http.get('*/api/v1/agents/ag1/approval-gate', () =>
        HttpResponse.json({ detail: 'x' }, { status: 500 }),
      ),
    );
    renderPanel();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});

describe('ApprovalGateSettingsPanel — 저장', () => {
  it('변경 전에는 저장 버튼이 비활성이다', async () => {
    useSettings(settings());
    renderPanel();
    await screen.findByLabelText('집행 시각 cron');
    expect(screen.getByRole('button', { name: '승인 게이트 저장' })).toBeDisabled();
  });

  it('수정 후 저장하면 PUT 으로 config 를 보낸다', async () => {
    useSettings(settings());
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.put('*/api/v1/agents/ag1/approval-gate', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(settings({ config: captured }));
      }),
    );
    const user = userEvent.setup();
    renderPanel();
    const cron = await screen.findByLabelText('집행 시각 cron');
    await user.clear(cron);
    await user.type(cron, '30 23 * * *');
    await user.click(screen.getByRole('button', { name: '승인 게이트 저장' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({ execute_after: '30 23 * * *', expires_hours: 24 });
    expect(await screen.findByRole('status')).toHaveTextContent('저장했습니다');
  });

  it('검증 실패(400)는 서버 메시지를 보여준다', async () => {
    useSettings(settings());
    server.use(
      http.put('*/api/v1/agents/ag1/approval-gate', () =>
        HttpResponse.json(
          { detail: { code: 'APPROVAL_GATE_INVALID_CONFIG', message: 'invalid cron expression' } },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPanel();
    const cron = await screen.findByLabelText('집행 시각 cron');
    await user.clear(cron);
    await user.type(cron, 'x');
    await user.click(screen.getByRole('button', { name: '승인 게이트 저장' }));
    expect(await screen.findByRole('status')).toHaveTextContent('invalid cron');
  });
});
