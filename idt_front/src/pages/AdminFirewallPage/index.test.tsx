// firewall-admin-console module-3 — 페이지·상태 띠·차단 폼·차단 목록 (Design §8.3 #1~10).
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  FIREWALL_ALERTS_QUIET,
  FIREWALL_BLOCKS_EMPTY,
  FIREWALL_BLOCKS_TWO,
  FIREWALL_BLOCK_OK_DRY_RUN,
  FIREWALL_BLOCK_OK_LIVE,
  FIREWALL_STATUS_DRY_RUN,
  FIREWALL_STATUS_LIVE,
  FIREWALL_STATUS_NOT_CONFIGURED,
  FIREWALL_STATUS_UNREACHABLE,
  FIREWALL_UNBLOCK_ABSENT,
  FIREWALL_UNBLOCK_OK,
  firewallError,
} from '@/__tests__/mocks/firewallMocks';
import type { FirewallBlockListResponse, FirewallStatusResponse } from '@/types/firewall';
import AdminFirewallPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const STATUS = '*/api/v1/admin/firewall/status';
const BLOCKS = '*/api/v1/admin/firewall/blocks';

interface Recorder {
  listCalls: number;
  posts: unknown[];
  deletes: string[];
}

const setup = (
  status: FirewallStatusResponse = FIREWALL_STATUS_DRY_RUN,
  blocks: FirewallBlockListResponse = FIREWALL_BLOCKS_EMPTY,
): Recorder => {
  const rec: Recorder = { listCalls: 0, posts: [], deletes: [] };
  server.use(
    // 탭 배지용 조회 — 이 파일은 현황 탭을 보므로 조용한 기본 응답을 둔다 (탭 내용은 tabs.test.tsx)
    http.get('*/api/v1/admin/firewall/alerts', () => HttpResponse.json(FIREWALL_ALERTS_QUIET)),
    http.get('*/api/v1/approvals', () =>
      HttpResponse.json({ data: [], pagination: { total: 0, page: 1, size: 100 } }),
    ),
    http.get(STATUS, () => HttpResponse.json(status)),
    http.get(BLOCKS, () => {
      rec.listCalls += 1;
      return HttpResponse.json(blocks);
    }),
    http.post(BLOCKS, async ({ request }) => {
      rec.posts.push(await request.json());
      return HttpResponse.json(
        status.fwctl.dry_run ? FIREWALL_BLOCK_OK_DRY_RUN : FIREWALL_BLOCK_OK_LIVE,
        { status: 201 },
      );
    }),
    http.delete(`${BLOCKS}/:ip`, ({ params }) => {
      rec.deletes.push(String(params.ip));
      return HttpResponse.json(FIREWALL_UNBLOCK_OK);
    }),
  );
  return rec;
};

const renderPage = () => render(<AdminFirewallPage />, { wrapper: createWrapper() });

const fillForm = async (
  user: ReturnType<typeof userEvent.setup>,
  values: { ip?: string; ttl?: string; reason?: string },
) => {
  const ip = await screen.findByRole('textbox', { name: 'IP' });
  if (values.ip !== undefined) {
    await user.clear(ip);
    if (values.ip) await user.type(ip, values.ip);
  }
  if (values.ttl !== undefined) {
    const ttl = screen.getByRole('textbox', { name: '유지 시간(초)' });
    await user.clear(ttl);
    if (values.ttl) await user.type(ttl, values.ttl);
  }
  if (values.reason !== undefined) {
    const reason = screen.getByRole('textbox', { name: '사유' });
    await user.clear(reason);
    if (values.reason) await user.type(reason, values.reason);
  }
};

const submitButton = () => screen.getByRole('button', { name: '차단 요청' });

describe('AdminFirewallPage — 모듈 상태', () => {
  it('꺼져 있으면(status 404) 안내만 보이고 탭·폼이 없다 (Plan SC-1)', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })));
    renderPage();
    expect(await screen.findByText('방화벽 관리 기능이 꺼져 있습니다.')).toBeInTheDocument();
    expect(screen.getByText('FIREWALL_ADMIN_ENABLED')).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '차단 요청' })).not.toBeInTheDocument();
  });

  it('status 조회 실패는 오류로 보여 준다', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })));
    renderPage();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  it('켜져 있으면 탭 4개와 Grafana 링크가 보인다', async () => {
    setup();
    renderPage();
    const tablist = await screen.findByRole('tablist', { name: '방화벽 관리' });
    expect(within(tablist).getAllByRole('tab').map((t) => t.textContent)).toEqual([
      '현황', '탐지', '감사', '승인',
    ]);
    const link = screen.getByRole('link', { name: /Grafana 대시보드/ });
    expect(link).toHaveAttribute('href', 'http://127.0.0.1:3000/d/fireware-firewall-lab');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('Grafana 주소가 없으면 링크를 내지 않는다', async () => {
    setup(FIREWALL_STATUS_NOT_CONFIGURED);
    renderPage();
    await screen.findByRole('tablist');
    expect(screen.queryByRole('link', { name: /Grafana 대시보드/ })).not.toBeInTheDocument();
  });

  it('꺼져 있으면 탭 배지용 조회(알림·승인)도 하지 않는다', async () => {
    let extra = 0;
    server.use(
      http.get(STATUS, () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })),
      http.get('*/api/v1/admin/firewall/alerts', () => {
        extra += 1;
        return HttpResponse.json(FIREWALL_ALERTS_QUIET);
      }),
      http.get('*/api/v1/approvals', () => {
        extra += 1;
        return HttpResponse.json({ data: [], pagination: { total: 0, page: 1, size: 100 } });
      }),
    );
    renderPage();
    await screen.findByText('방화벽 관리 기능이 꺼져 있습니다.');
    await new Promise((r) => setTimeout(r, 50));
    expect(extra).toBe(0);
  });
});

describe('상태 띠 (Plan FR-17)', () => {
  it('DRY-RUN: 배지와 안내 문구', async () => {
    setup(FIREWALL_STATUS_DRY_RUN);
    renderPage();
    const bar = await screen.findByRole('region', { name: '방화벽 상태' });
    expect(within(bar).getByText('연결됨')).toBeInTheDocument();
    expect(within(bar).getByText('DRY-RUN')).toBeInTheDocument();
    expect(
      within(bar).getByText('차단 요청은 기록만 되고 실제로 적용되지 않습니다.'),
    ).toBeInTheDocument();
    expect(within(bar).getByText(/3600초/)).toBeInTheDocument();
    expect(within(bar).getByText(/0\.1\.0/)).toBeInTheDocument();
  });

  it('LIVE: 배지가 LIVE 이고 dry-run 안내가 없다', async () => {
    setup(FIREWALL_STATUS_LIVE);
    renderPage();
    const bar = await screen.findByRole('region', { name: '방화벽 상태' });
    expect(within(bar).getByText('LIVE')).toBeInTheDocument();
    expect(within(bar).queryByText('DRY-RUN')).not.toBeInTheDocument();
    expect(within(bar).queryByText(/기록만 되고/)).not.toBeInTheDocument();
  });

  it('연결 안 됨: 폼이 비활성이고 목록을 조회하지 않는다 (Plan SC-8)', async () => {
    const rec = setup(FIREWALL_STATUS_UNREACHABLE);
    renderPage();
    const bar = await screen.findByRole('region', { name: '방화벽 상태' });
    expect(within(bar).getByText('연결 안 됨')).toBeInTheDocument();
    expect(within(bar).queryByText('DRY-RUN')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'IP' })).toBeDisabled();
    expect(submitButton()).toBeDisabled();
    expect(screen.getByText('fwctl에 연결되면 차단 목록이 표시됩니다.')).toBeInTheDocument();
    expect(rec.listCalls).toBe(0);
  });

  it('설정 필요: 설정 이름을 안내한다', async () => {
    setup(FIREWALL_STATUS_NOT_CONFIGURED);
    renderPage();
    const bar = await screen.findByRole('region', { name: '방화벽 상태' });
    expect(within(bar).getByText('설정 필요')).toBeInTheDocument();
    expect(within(bar).getByText('FIREWALL_ADMIN_FWCTL_TOKEN')).toBeInTheDocument();
    expect(submitButton()).toBeDisabled();
  });
});

describe('차단 폼 (Plan FR-18·19·23)', () => {
  it('기본 유지 시간이 채워져 있고, 빈 폼은 제출할 수 없다', async () => {
    setup();
    renderPage();
    expect(await screen.findByRole('textbox', { name: '유지 시간(초)' })).toHaveValue('600');
    expect(submitButton()).toBeDisabled();
  });

  it.each([
    ['CIDR', { ip: '10.0.0.0/8', reason: 'r' }, 'IPv4 주소 한 개를 입력하세요.'],
    ['범위 밖 옥텟', { ip: '300.1.1.1', reason: 'r' }, 'IPv4 주소 한 개를 입력하세요.'],
    ['TTL 0', { ip: '1.2.3.4', ttl: '0', reason: 'r' }, '유지 시간은 1~3600초입니다.'],
    ['TTL 초과', { ip: '1.2.3.4', ttl: '99999', reason: 'r' }, '유지 시간은 1~3600초입니다.'],
    ['TTL 소수', { ip: '1.2.3.4', ttl: '1.5', reason: 'r' }, '유지 시간은 1~3600초입니다.'],
  ])('잘못된 입력(%s)은 메시지를 보이고 제출을 막는다 (Plan SC-5)', async (_n, values, message) => {
    const rec = setup();
    const user = userEvent.setup();
    renderPage();
    await fillForm(user, values);
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(submitButton()).toBeDisabled();
    expect(rec.posts).toEqual([]);
  });

  it('사유가 비면 제출할 수 없다', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await fillForm(user, { ip: '172.28.10.66', reason: '   ' });
    expect(submitButton()).toBeDisabled();
  });

  it('확인창이 모드·IP·유지 시간·사유를 다시 보여 주고, 취소하면 요청하지 않는다', async () => {
    const rec = setup();
    const user = userEvent.setup();
    renderPage();
    await fillForm(user, { ip: ' 172.28.10.66 ', ttl: '120', reason: 'R02 포트 스캔' });
    await user.click(submitButton());

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('IP 차단 확인')).toBeInTheDocument();
    expect(within(dialog).getByText('DRY-RUN')).toBeInTheDocument();
    expect(within(dialog).getByText('172.28.10.66')).toBeInTheDocument();
    expect(within(dialog).getByText('120초')).toBeInTheDocument();
    expect(within(dialog).getByText('R02 포트 스캔')).toBeInTheDocument();
    expect(within(dialog).queryByText(/실제 트래픽이 차단됩니다/)).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: '취소' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(rec.posts).toEqual([]);
  });

  it('DRY-RUN 성공: 실제로 차단되지 않았다고 알리고 목록을 다시 조회한다 (Plan SC-3)', async () => {
    const rec = setup();
    const user = userEvent.setup();
    renderPage();
    await fillForm(user, { ip: '172.28.10.66', ttl: '600', reason: 'R02 포트 스캔' });
    await waitFor(() => expect(rec.listCalls).toBe(1));
    await user.click(submitButton());
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '차단' }));

    expect(await screen.findByText(/실제로 차단되지 않았습니다\(DRY-RUN\)/)).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    // actor 는 보내지 않는다 — 서버가 채운다
    expect(rec.posts).toEqual([
      { ip: '172.28.10.66', ttl_seconds: 600, reason: 'R02 포트 스캔' },
    ]);
    await waitFor(() => expect(rec.listCalls).toBe(2));
    expect(screen.getByRole('textbox', { name: 'IP' })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: '사유' })).toHaveValue('');
  });

  it('새 요청을 시작하면 이전 결과 안내를 지운다 (브라우저 확인에서 발견)', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await fillForm(user, { ip: '172.28.10.66', reason: 'first' });
    await user.click(submitButton());
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '차단' }));
    expect(await screen.findByText(/실제로 차단되지 않았습니다/)).toBeInTheDocument();

    server.use(
      http.post(BLOCKS, () =>
        HttpResponse.json(firewallError('FORBIDDEN_WHITELIST', 'protected'), { status: 403 }),
      ),
    );
    await fillForm(user, { ip: '172.28.10.10', reason: 'second' });
    await user.click(submitButton());
    expect(screen.queryByText(/실제로 차단되지 않았습니다/)).not.toBeInTheDocument();
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: '차단' }));
    expect(await within(dialog).findByText('보호 대상 주소라 차단할 수 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/실제로 차단되지 않았습니다/)).not.toBeInTheDocument();
  });

  it('LIVE: 확인창에 경고가 있고, 성공하면 만료 시각을 알린다', async () => {
    setup(FIREWALL_STATUS_LIVE);
    const user = userEvent.setup();
    renderPage();
    await fillForm(user, { ip: '172.28.10.66', reason: 'R02' });
    await user.click(submitButton());
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('LIVE')).toBeInTheDocument();
    expect(within(dialog).getByText(/실제 트래픽이 차단됩니다/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: '차단' }));
    const notice = await screen.findByText(/172\.28\.10\.66을\(를\) 차단했습니다\. 만료:/);
    expect(notice).toBeInTheDocument();
    expect(screen.queryByText(/실제로 차단되지 않았습니다/)).not.toBeInTheDocument();
  });

  it.each([
    [403, 'FORBIDDEN_WHITELIST', 'protected', '보호 대상 주소라 차단할 수 없습니다.'],
    [502, 'FWCTL_AUDIT_ERROR', 'audit', '차단은 적용됐지만 감사 기록에 실패했습니다. 운영자에게 알려 주세요.'],
    [504, 'FWCTL_TIMEOUT', 'slow', 'fwctl 응답이 지연되고 있습니다.'],
    [422, 'INVALID_TTL', '유지 시간은 1~1800초입니다', '유지 시간은 1~1800초입니다'],
  ])('오류 %i %s 는 확인창 안에 문구로 보이고 입력이 남는다 (Plan SC-5)', async (status, code, message, shown) => {
    setup();
    server.use(
      http.post(BLOCKS, () => HttpResponse.json(firewallError(code, message), { status })),
    );
    const user = userEvent.setup();
    renderPage();
    await fillForm(user, { ip: '172.28.10.10', reason: 'r' });
    await user.click(submitButton());
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: '차단' }));
    expect(await within(dialog).findByText(shown)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'IP' })).toHaveValue('172.28.10.10');
    expect(screen.queryByText(/실제로 차단되지 않았습니다/)).not.toBeInTheDocument();
  });

  it('처리 중에는 버튼이 잠겨 요청이 한 번만 나간다 (Plan FR-23)', async () => {
    const rec = setup();
    let posts = 0;
    server.use(
      http.post(BLOCKS, async () => {
        posts += 1;
        await delay(150);
        return HttpResponse.json(FIREWALL_BLOCK_OK_DRY_RUN, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await fillForm(user, { ip: '172.28.10.66', reason: 'r' });
    await user.click(submitButton());
    const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: '차단' });
    await user.click(confirm);
    // 응답 전: 확인 버튼과 제출 버튼이 isPending 으로 잠긴다
    await waitFor(() => expect(posts).toBe(1));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    for (const button of within(screen.getByRole('dialog')).getAllByRole('button')) {
      if (button.textContent !== '취소') expect(button).toBeDisabled();
    }
    expect(screen.getByRole('button', { name: /요청 중/ })).toBeDisabled();
    expect(await screen.findByText(/실제로 차단되지 않았습니다/)).toBeInTheDocument();
    expect(posts).toBe(1);
    expect(rec.posts).toEqual([]); // 지연 핸들러가 대신 받았다
  });
});

describe('차단 목록 (Plan FR-20)', () => {
  it('행과 남은 시간 형식을 보여 준다', async () => {
    setup(FIREWALL_STATUS_LIVE, FIREWALL_BLOCKS_TWO);
    renderPage();
    const list = await screen.findByRole('region', { name: '현재 차단 목록' });
    expect(await within(list).findByText('172.28.10.66')).toBeInTheDocument();
    expect(within(list).getByText('현재 차단 목록 (2)')).toBeInTheDocument();
    expect(within(list).getByText('10초마다 갱신')).toBeInTheDocument();
    const rows = within(list).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText(/^9분 \d{1,2}초$/)).toBeInTheDocument();
    expect(within(rows[1]).getByText(/^\d{1,2}초$/)).toBeInTheDocument();
    expect(within(rows[0]).getByText('720')).toBeInTheDocument();
  });

  it('비어 있으면 빈 상태 문구', async () => {
    setup();
    renderPage();
    expect(await screen.findByText('차단 중인 IP가 없습니다.')).toBeInTheDocument();
  });

  it('목록 조회 실패는 오류 문구로 보여 준다', async () => {
    setup();
    server.use(
      http.get(BLOCKS, () =>
        HttpResponse.json(firewallError('FWCTL_UNAVAILABLE', 'down'), { status: 502 }),
      ),
    );
    renderPage();
    expect(await screen.findByText('fwctl에 연결할 수 없습니다.')).toBeInTheDocument();
  });

  it('해제: 확인 후 DELETE 하고 목록을 다시 조회한다', async () => {
    const rec = setup(FIREWALL_STATUS_LIVE, FIREWALL_BLOCKS_TWO);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '172.28.10.66 해제' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/172\.28\.10\.66 차단을 지금 해제합니다/)).toBeInTheDocument();
    expect(rec.deletes).toEqual([]);
    await user.click(within(dialog).getByRole('button', { name: '해제' }));
    expect(await screen.findByText('172.28.10.66 차단을 해제했습니다.')).toBeInTheDocument();
    expect(rec.deletes).toEqual(['172.28.10.66']);
    await waitFor(() => expect(rec.listCalls).toBe(2));
  });

  it('해제 취소는 요청하지 않는다', async () => {
    const rec = setup(FIREWALL_STATUS_LIVE, FIREWALL_BLOCKS_TWO);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '203.0.113.9 해제' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '취소' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(rec.deletes).toEqual([]);
  });

  it('이미 해제된 주소는 안내 문구를 보여 준다', async () => {
    setup(FIREWALL_STATUS_LIVE, FIREWALL_BLOCKS_TWO);
    server.use(http.delete(`${BLOCKS}/:ip`, () => HttpResponse.json(FIREWALL_UNBLOCK_ABSENT)));
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '172.28.10.66 해제' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '해제' }));
    expect(await screen.findByText('172.28.10.66은(는) 이미 해제된 주소입니다.')).toBeInTheDocument();
  });

  it('해제 실패는 확인창 안에 문구로 보인다', async () => {
    setup(FIREWALL_STATUS_LIVE, FIREWALL_BLOCKS_TWO);
    server.use(
      http.delete(`${BLOCKS}/:ip`, () =>
        HttpResponse.json(firewallError('FWCTL_TIMEOUT', 'slow'), { status: 504 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '172.28.10.66 해제' }));
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: '해제' }));
    expect(await within(dialog).findByText('fwctl 응답이 지연되고 있습니다.')).toBeInTheDocument();
  });
});
