// firewall-admin-console module-4 — 탐지·감사·승인 탭 (Design §8.3 #11~19).
// 페이지 전체를 렌더링해 탭 전환·배지·초안 전달까지 실제 경로로 확인한다.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { queryClient } from '@/lib/queryClient';
import { server } from '@/__tests__/mocks/server';
import {
  FIREWALL_ALERTS,
  FIREWALL_ALERTS_QUIET,
  FIREWALL_APPROVALS,
  FIREWALL_AUDIT,
  FIREWALL_AUDIT_EMPTY,
  FIREWALL_BLOCKS_EMPTY,
  FIREWALL_BLOCKS_TWO,
  FIREWALL_EVENTS,
  FIREWALL_EVENTS_EMPTY,
  FIREWALL_STATUS_DRY_RUN,
  FIREWALL_STATUS_NOT_CONFIGURED,
  FIREWALL_STATUS_UNREACHABLE,
  firewallError,
} from '@/__tests__/mocks/firewallMocks';
import type { ApprovalItem } from '@/types/approval';
import type {
  FirewallAlertsResponse,
  FirewallAuditResponse,
  FirewallBlockListResponse,
  FirewallEventsResponse,
  FirewallStatusResponse,
} from '@/types/firewall';
import AdminFirewallPage from './index';

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  queryClient.clear();
});
afterAll(() => server.close());

const FW = '*/api/v1/admin/firewall';
const APPROVALS = '*/api/v1/approvals';

interface Options {
  status?: FirewallStatusResponse;
  alerts?: FirewallAlertsResponse;
  events?: FirewallEventsResponse;
  audit?: FirewallAuditResponse;
  blocks?: FirewallBlockListResponse;
  approvals?: ApprovalItem[];
  approvalTotal?: number;
}

interface Recorder {
  eventQueries: Record<string, string>[];
  auditQueries: Record<string, string>[];
  approvalQueries: Record<string, string>[];
  approved: string[];
  rejected: { id: string; body: unknown }[];
}

const query = (url: string) => Object.fromEntries(new URL(url).searchParams);

const setup = (options: Options = {}): Recorder => {
  const rec: Recorder = {
    eventQueries: [], auditQueries: [], approvalQueries: [], approved: [], rejected: [],
  };
  let approvals = options.approvals ?? [];
  server.use(
    http.get(`${FW}/status`, () => HttpResponse.json(options.status ?? FIREWALL_STATUS_DRY_RUN)),
    http.get(`${FW}/blocks`, () => HttpResponse.json(options.blocks ?? FIREWALL_BLOCKS_EMPTY)),
    http.get(`${FW}/alerts`, () => HttpResponse.json(options.alerts ?? FIREWALL_ALERTS)),
    http.get(`${FW}/events`, ({ request }) => {
      rec.eventQueries.push(query(request.url));
      return HttpResponse.json(options.events ?? FIREWALL_EVENTS);
    }),
    http.get(`${FW}/audit`, ({ request }) => {
      rec.auditQueries.push(query(request.url));
      return HttpResponse.json(options.audit ?? FIREWALL_AUDIT);
    }),
    http.get(APPROVALS, ({ request }) => {
      rec.approvalQueries.push(query(request.url));
      return HttpResponse.json({
        data: approvals,
        pagination: { total: options.approvalTotal ?? approvals.length, page: 1, size: 100 },
      });
    }),
    http.post(`${APPROVALS}/:id/approve`, ({ params }) => {
      rec.approved.push(String(params.id));
      approvals = approvals.filter((a) => a.id !== params.id);
      return HttpResponse.json({
        id: params.id, status: 'approved', execute_after: null, message: '승인 처리되었습니다.',
      });
    }),
    http.post(`${APPROVALS}/:id/reject`, async ({ params, request }) => {
      rec.rejected.push({ id: String(params.id), body: await request.json() });
      approvals = approvals.filter((a) => a.id !== params.id);
      return HttpResponse.json({
        id: params.id, status: 'rejected', execute_after: null, message: '거절 처리되었습니다.',
      });
    }),
  );
  return rec;
};

// 승인 훅(useApprovals 계열)은 앱의 공용 queryClient 를 직접 무효화한다.
// 실제 앱과 같은 경로를 타도록 테스트도 공용 클라이언트를 쓰고 매번 비운다.
const renderPage = () => {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/firewall']}>
        <AdminFirewallPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const openTab = async (user: ReturnType<typeof userEvent.setup>, name: RegExp) => {
  await user.click(await screen.findByRole('tab', { name }));
};

describe('탭 배지', () => {
  it('탐지 탭에 발화 건수, 승인 탭에 방화벽 요청 건수를 보여 준다', async () => {
    setup({ approvals: FIREWALL_APPROVALS });
    renderPage();
    // 발화 2건, 승인 3건 중 방화벽 도구 2건
    // 파일의 첫 테스트라 모듈 로딩까지 기다린다 (전체 실행 부하에서 기본 1초로는 부족했다)
    const slow = { timeout: 5000 };
    expect(await screen.findByRole('tab', { name: /탐지\s*2/ }, slow)).toBeInTheDocument();
    expect(await screen.findByRole('tab', { name: /승인\s*2/ }, slow)).toBeInTheDocument();
  });

  it('0건이면 배지가 없다', async () => {
    setup({ alerts: FIREWALL_ALERTS_QUIET });
    renderPage();
    const detection = await screen.findByRole('tab', { name: /탐지/ });
    await waitFor(() => expect(detection.textContent).toBe('탐지'));
    expect(screen.getByRole('tab', { name: /승인/ }).textContent).toBe('승인');
  });
});

describe('탐지 탭 (Plan FR-12·13·21)', () => {
  it('룰 8개를 서버가 준 순서(발화 우선)로 보여 주고 상태·심각도·권고를 표시한다', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);

    const section = await screen.findByRole('region', { name: '탐지 룰' });
    expect(await within(section).findByText('탐지 룰 (8)')).toBeInTheDocument();
    expect(within(section).getByText('발화 2건')).toBeInTheDocument();

    const first = within(section).getByTestId('rule-fw-r02-port-scan');
    expect(within(first).getByText('발화')).toBeInTheDocument();
    expect(within(first).getByText('R02 Vertical Port Scan')).toBeInTheDocument();
    expect(within(first).getByText('high')).toBeInTheDocument();
    expect(within(first).getByText('차단')).toBeInTheDocument();

    const ruleRows = within(section).getAllByTestId(/^rule-/);
    expect(ruleRows).toHaveLength(8);
    expect(ruleRows.slice(0, 3).map((r) => r.getAttribute('data-testid'))).toEqual([
      'rule-fw-r02-port-scan', 'rule-fw-r06-distributed-probe', 'rule-fw-r04-sensitive-port',
    ]);
    expect(within(ruleRows[2]).getByText('대기')).toBeInTheDocument();
    expect(within(ruleRows[7]).getByText('연장')).toBeInTheDocument();
  });

  it('발화·대기 룰은 출발지가 펼쳐져 있고, 조건식 결과값은 표시하지 않는다', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    const list = await screen.findByRole('list', { name: 'R02 Vertical Port Scan 출발지' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText('172.28.10.66')).toBeInTheDocument();
    expect(within(items[0]).getByText(/^시작 /)).toBeInTheDocument();
    expect(within(list).queryByText(/값 /)).not.toBeInTheDocument();
    expect(within(items[1]).getByText('데이터 없음')).toBeInTheDocument();
    // 차단 버튼은 발화·대기 중인 출발지에만 있다 (브라우저 확인에서 발견)
    expect(within(items[0]).getByRole('button', { name: '172.28.10.66 차단' })).toBeInTheDocument();
    expect(within(items[1]).queryByRole('button')).not.toBeInTheDocument();
  });

  it('"이 IP 차단"은 현황 탭으로 넘어가 IP 와 사유 초안을 채운다', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    const list = await screen.findByRole('list', { name: 'R02 Vertical Port Scan 출발지' });
    await user.click(within(list).getByRole('button', { name: '172.28.10.66 차단' }));

    expect(screen.getByRole('tab', { name: /현황/ })).toHaveAttribute('aria-selected', 'true');
    const ip = screen.getByRole('textbox', { name: 'IP' });
    expect(ip).toHaveValue('172.28.10.66');
    expect(ip).toHaveFocus();
    expect(screen.getByRole('textbox', { name: '사유' })).toHaveValue(
      'R02 Vertical Port Scan 탐지',
    );
    // 유지 시간은 기본값 그대로, 요청은 아직 나가지 않았다(확인창을 거친다)
    expect(screen.getByRole('textbox', { name: '유지 시간(초)' })).toHaveValue('600');
    expect(screen.getByRole('button', { name: '차단 요청' })).toBeEnabled();
  });

  it('같은 IP 를 다시 골라도 초안이 다시 채워진다', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    await user.click(await screen.findByRole('button', { name: '198.51.100.7 차단' }));
    await user.clear(screen.getByRole('textbox', { name: 'IP' }));
    await openTab(user, /탐지/);
    await user.click(await screen.findByRole('button', { name: '198.51.100.7 차단' }));
    expect(screen.getByRole('textbox', { name: 'IP' })).toHaveValue('198.51.100.7');
  });

  it('보고 전용 룰과 출발지 없는 인스턴스에는 차단 버튼이 없다', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    const report = await screen.findByRole('list', { name: 'R06 Distributed Probe 출발지' });
    expect(within(report).getByText('192.0.2.44')).toBeInTheDocument();
    expect(within(report).queryByRole('button')).not.toBeInTheDocument();
    expect(within(report).getByText('보고 전용 룰')).toBeInTheDocument();

    const pending = screen.getByRole('list', { name: 'R04 Sensitive Port Probe 출발지' });
    const items = within(pending).getAllByRole('listitem');
    expect(within(items[1]).getByText('출발지 없음')).toBeInTheDocument();
    expect(within(items[1]).queryByRole('button')).not.toBeInTheDocument();
  });

  it('이미 차단 중인 IP 는 버튼 대신 "차단 중"을 보여 준다', async () => {
    setup({ blocks: FIREWALL_BLOCKS_TWO });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    const list = await screen.findByRole('list', { name: 'R02 Vertical Port Scan 출발지' });
    // 발화 중인 172.28.10.66 이 차단 목록에 있다 (과거 출발지는 버튼·표시 모두 없다)
    await waitFor(() => expect(within(list).getAllByText('차단 중')).toHaveLength(1));
    expect(within(list).queryByRole('button')).not.toBeInTheDocument();
    // 차단 목록에 없는 출발지는 버튼이 그대로 있다
    expect(screen.getByRole('button', { name: '198.51.100.7 차단' })).toBeInTheDocument();
  });

  it('fwctl 에 연결할 수 없으면 차단 버튼이 비활성이다', async () => {
    setup({ status: FIREWALL_STATUS_UNREACHABLE });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    const top = await screen.findByRole('list', { name: '출발지 상위' });
    const buttons = screen.getAllByRole('button', { name: /^\d+\.\d+\.\d+\.\d+ 차단$/ });
    expect(buttons.length).toBeGreaterThan(2);
    for (const button of buttons) expect(button).toBeDisabled();
    expect(within(top).getByRole('button', { name: '172.28.10.66 차단' })).toBeDisabled();
  });

  it('차단 로그: 출발지 상위와 최근 로그를 보여 주고 프로토콜을 이름으로 표시한다', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    const top = await screen.findByRole('list', { name: '출발지 상위' });
    const topItems = within(top).getAllByRole('listitem');
    expect(topItems).toHaveLength(2);
    expect(within(topItems[0]).getByText('182건')).toBeInTheDocument();

    const table = screen.getByRole('table', { name: '최근 차단 로그' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText('TCP')).toBeInTheDocument();
    expect(within(rows[0]).getByText('22')).toBeInTheDocument();
    expect(within(rows[0]).getByText('정책 차단')).toBeInTheDocument();
    expect(within(rows[1]).getByText('UDP')).toBeInTheDocument();
    expect(within(rows[1]).getByText('차단 목록')).toBeInTheDocument();
    expect(within(rows[2]).getByText('ICMP')).toBeInTheDocument();
  });

  it('출발지 상위의 "이 IP 차단"은 건수를 사유 초안으로 넘긴다', async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    const top = await screen.findByRole('list', { name: '출발지 상위' });
    await user.click(within(top).getByRole('button', { name: '172.28.10.10 차단' }));
    expect(screen.getByRole('textbox', { name: 'IP' })).toHaveValue('172.28.10.10');
    expect(screen.getByRole('textbox', { name: '사유' })).toHaveValue('차단 로그 1시간 2건');
  });

  it('기간·구분을 바꾸면 허용 값만 쿼리로 보낸다', async () => {
    const rec = setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    await waitFor(() => expect(rec.eventQueries).toEqual([{ range: '1h', action: 'all' }]));
    await user.selectOptions(screen.getByRole('combobox', { name: '기간' }), '24h');
    await user.selectOptions(screen.getByRole('combobox', { name: '구분' }), 'block');
    await waitFor(() =>
      expect(rec.eventQueries[rec.eventQueries.length - 1]).toEqual({ range: '24h', action: 'block' }),
    );
    expect(
      within(screen.getByRole('combobox', { name: '기간' })).getAllByRole('option').map((o) => o.textContent),
    ).toEqual(['15분', '1시간', '6시간', '24시간']);
  });

  it('차단 로그가 없으면 빈 상태 문구', async () => {
    setup({ events: FIREWALL_EVENTS_EMPTY });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    expect(await screen.findByText('선택한 기간에 차단 로그가 없습니다.')).toBeInTheDocument();
  });

  it('Grafana 장애(503)는 탐지 탭에만 안내하고 현황 탭은 그대로 동작한다 (Plan SC-8)', async () => {
    setup({ blocks: FIREWALL_BLOCKS_TWO });
    const down = () =>
      HttpResponse.json(firewallError('GRAFANA_UNAVAILABLE', 'down'), { status: 503 });
    server.use(http.get(`${FW}/alerts`, down), http.get(`${FW}/events`, down));
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    const alerts = await screen.findAllByRole('alert');
    expect(alerts).toHaveLength(2);
    expect(alerts[0]).toHaveTextContent('Grafana에서 정보를 가져올 수 없습니다.');

    await openTab(user, /현황/);
    expect(await screen.findByText('현재 차단 목록 (2)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '차단 요청' })).toBeInTheDocument();
  });

  it('Grafana 미설정이면 조회하지 않고 설정 이름을 안내한다', async () => {
    const rec = setup({ status: FIREWALL_STATUS_NOT_CONFIGURED });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /탐지/);
    expect(screen.getByText('FIREWALL_ADMIN_GRAFANA_TOKEN')).toBeInTheDocument();
    expect(rec.eventQueries).toEqual([]);
  });
});

describe('감사 탭 (Plan FR-14, SC-4)', () => {
  it('이력을 표로 보여 주고 수행자를 관리자·에이전트로 구분한다', async () => {
    const rec = setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /감사/);

    const section = await screen.findByRole('region', { name: '감사 이력' });
    const rows = (await within(section).findAllByRole('row')).slice(1);
    expect(rows).toHaveLength(4);
    expect(rec.auditQueries[0]).toEqual({ range: '24h', event: 'all' });
    expect(within(section).getByText(/최근 7일까지 조회됩니다/)).toHaveTextContent('4건');

    // 에이전트(MCP 서버)
    expect(within(rows[0]).getByText('에이전트')).toBeInTheDocument();
    expect(within(rows[0]).getByText('mcp-firewall-server/local')).toBeInTheDocument();
    expect(within(rows[0]).getByText('900초')).toBeInTheDocument();
    // 해제: actor 가 없어 요청 ID 에서 관리자 ID 를 읽는다
    expect(within(rows[1]).getByText('해제')).toBeInTheDocument();
    expect(within(rows[1]).getByText('관리자')).toBeInTheDocument();
    expect(within(rows[1]).getByText('ID 7')).toBeInTheDocument();
    expect(within(rows[1]).queryByText('DRY-RUN')).not.toBeInTheDocument();
    // 거부된 차단
    expect(within(rows[2]).getByText('거부')).toBeInTheDocument();
    expect(within(rows[2]).getByText('FORBIDDEN_WHITELIST')).toBeInTheDocument();
    // 성공한 dry-run 차단
    expect(within(rows[3]).getByText('성공')).toBeInTheDocument();
    expect(within(rows[3]).getByText('DRY-RUN')).toBeInTheDocument();
    expect(within(rows[3]).getByText('R02 포트 스캔')).toBeInTheDocument();
    expect(within(rows[3]).getByText('ID 7')).toBeInTheDocument();
  });

  it('기간·이벤트는 바로, IP·수행자는 조회 버튼을 눌러야 반영된다', async () => {
    const rec = setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /감사/);
    await waitFor(() => expect(rec.auditQueries).toHaveLength(1));

    await user.selectOptions(screen.getByRole('combobox', { name: '기간' }), '7d');
    await user.selectOptions(screen.getByRole('combobox', { name: '이벤트' }), 'block');
    await waitFor(() =>
      expect(rec.auditQueries[rec.auditQueries.length - 1]).toEqual({ range: '7d', event: 'block' }),
    );
    const before = rec.auditQueries.length;

    await user.type(screen.getByRole('textbox', { name: 'IP 필터' }), ' 172.28.10.66 ');
    await user.type(screen.getByRole('textbox', { name: '수행자 필터' }), 'admin:7');
    expect(rec.auditQueries).toHaveLength(before);

    await user.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(() =>
      expect(rec.auditQueries[rec.auditQueries.length - 1]).toEqual({
        range: '7d', event: 'block', ip: '172.28.10.66', actor: 'admin:7',
      }),
    );
    expect(
      within(screen.getByRole('combobox', { name: '이벤트' })).getAllByRole('option').map((o) => o.textContent),
    ).toEqual(['전체', '차단', '해제']);
  });

  it('필터를 지우고 조회하면 키 자체를 보내지 않는다', async () => {
    const rec = setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /감사/);
    const ip = await screen.findByRole('textbox', { name: 'IP 필터' });
    await user.type(ip, '1.2.3.4');
    await user.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(() => expect(rec.auditQueries[rec.auditQueries.length - 1].ip).toBe('1.2.3.4'));
    await user.clear(ip);
    await user.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(() =>
      expect(rec.auditQueries[rec.auditQueries.length - 1]).toEqual({ range: '24h', event: 'all' }),
    );
  });

  it.each([
    ['IP 필터', '1.2.3', 'IPv4 주소 한 개를 입력하세요.'],
    ['수행자 필터', 'a" | line_format "x', /영문·숫자와 \. _ : \/ - 만 쓸 수 있고/],
    // 서버 규칙과 같게: 허용 문자만으로 된 정규식 조각(.*)도 거부 (Check D12)
    ['수행자 필터', '.*', /영문·숫자가 1자 이상/],
  ])('잘못된 %s 값은 보내지 않는다', async (field, value, message) => {
    const rec = setup();
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /감사/);
    await waitFor(() => expect(rec.auditQueries).toHaveLength(1));
    await user.type(await screen.findByRole('textbox', { name: field }), value);
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '조회' })).toBeDisabled();
    expect(rec.auditQueries).toHaveLength(1);
  });

  it('빈 결과와 오류 문구', async () => {
    setup({ audit: FIREWALL_AUDIT_EMPTY });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /감사/);
    expect(await screen.findByText('선택한 조건에 맞는 감사 이력이 없습니다.')).toBeInTheDocument();

    server.use(
      http.get(`${FW}/audit`, () =>
        HttpResponse.json(firewallError('GRAFANA_UNAVAILABLE', 'down'), { status: 503 }),
      ),
    );
    await user.click(screen.getByRole('button', { name: '새로고침' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Grafana에서 정보를 가져올 수 없습니다.',
    );
  });
});

describe('승인 탭 (Plan FR-22)', () => {
  it('승인 대기 건 중 block_ip·unblock_ip 요청만 보여 준다', async () => {
    const rec = setup({ approvals: FIREWALL_APPROVALS });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /승인/);

    const section = await screen.findByRole('region', { name: '승인 대기' });
    expect(await within(section).findByText('차단 요청 승인 대기 (2)')).toBeInTheDocument();
    const cards = within(section).getAllByRole('listitem');
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText(/차단 요청/)).toBeInTheDocument();
    expect(within(cards[0]).getByText('172.28.10.66 을 600초 차단 — R02 포트 스캔')).toBeInTheDocument();
    expect(within(cards[0]).getByText('방화벽 감시')).toBeInTheDocument();
    expect(within(cards[1]).getByText(/해제 요청/)).toBeInTheDocument();
    expect(within(section).queryByText('고객 안내 메일 발송')).not.toBeInTheDocument();
    expect(within(section).getByText(/내가 소유한 에이전트의 요청만 표시됩니다/)).toBeInTheDocument();
    expect(within(section).getByRole('link', { name: '작업함에서 보기' })).toHaveAttribute('href', '/jobs');
    // 대기(pending) 건만, 한 번에 100건
    expect(rec.approvalQueries[0]).toEqual({ status: 'pending', page: '1', size: '100' });
  });

  it('승인: 기존 approve API 를 한 번 부르고 목록에서 사라진다', async () => {
    const rec = setup({ approvals: FIREWALL_APPROVALS });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /승인/);
    await user.click(await screen.findByRole('button', { name: '방화벽 감시 차단 요청 승인' }));

    expect(await screen.findByText('승인 처리되었습니다.')).toBeInTheDocument();
    expect(rec.approved).toEqual(['ap-1']);
    await waitFor(() => expect(screen.getByText('차단 요청 승인 대기 (1)')).toBeInTheDocument());
    // 탭 배지도 같은 쿼리라 함께 줄어든다
    expect(screen.getByRole('tab', { name: /승인\s*1/ })).toBeInTheDocument();
  });

  it('거절: 사유를 입력해야 하고 기존 reject API 로 보낸다', async () => {
    const rec = setup({ approvals: FIREWALL_APPROVALS });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /승인/);
    await user.click(await screen.findByRole('button', { name: '방화벽 감시 해제 요청 거절' }));

    const dialog = screen.getByRole('dialog', { name: '거절 사유 입력' });
    const submit = within(dialog).getByRole('button', { name: '거절' });
    expect(submit).toBeDisabled();
    await user.type(within(dialog).getByRole('textbox', { name: '거절 사유' }), '아직 관찰이 필요합니다');
    await user.click(submit);

    expect(await screen.findByText('거절 처리되었습니다.')).toBeInTheDocument();
    expect(rec.rejected).toEqual([{ id: 'ap-2', body: { reason: '아직 관찰이 필요합니다' } }]);
    expect(rec.approved).toEqual([]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('이미 처리된 건(409)은 안내하고 목록을 다시 불러온다', async () => {
    const rec = setup({ approvals: FIREWALL_APPROVALS });
    server.use(
      http.post(`${APPROVALS}/:id/approve`, () =>
        HttpResponse.json({ detail: { code: 'APPROVAL_ALREADY_DECIDED', message: 'done' } }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /승인/);
    await user.click(await screen.findByRole('button', { name: '방화벽 감시 차단 요청 승인' }));
    expect(
      await screen.findByText('이미 처리된 요청입니다. 목록을 새로 불러왔습니다.'),
    ).toBeInTheDocument();
    await waitFor(() => expect(rec.approvalQueries.length).toBeGreaterThan(1));
  });

  it('응답을 받지 못하면 실패로 단정하지 않고, 목록을 다시 불러와 결과를 반영한다 (module-5 실측)', async () => {
    // 실측: 승인 API 가 에이전트 재개까지 기다려 30초를 넘겼고, 화면은 오류였지만 처리는 끝나 있었다.
    const rec = setup({ approvals: FIREWALL_APPROVALS });
    let handled = false;
    server.use(
      http.post(`${APPROVALS}/:id/approve`, () => {
        handled = true; // 서버에서는 처리됐다
        return HttpResponse.error(); // 그러나 응답은 오지 않는다
      }),
      http.get(APPROVALS, ({ request }) => {
        rec.approvalQueries.push(query(request.url));
        const data = handled ? FIREWALL_APPROVALS.slice(1) : FIREWALL_APPROVALS;
        return HttpResponse.json({ data, pagination: { total: data.length, page: 1, size: 100 } });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /승인/);
    await user.click(await screen.findByRole('button', { name: '방화벽 감시 차단 요청 승인' }));

    expect(await screen.findByText(/응답을 받지 못했습니다\. 요청은 처리됐을 수 있습니다/)).toBeInTheDocument();
    expect(screen.queryByText('알 수 없는 오류가 발생했습니다.')).not.toBeInTheDocument();
    // 목록을 직접 다시 불러와 처리된 건이 사라진다
    await waitFor(() => expect(screen.getByText('차단 요청 승인 대기 (1)')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '방화벽 감시 차단 요청 승인' })).not.toBeInTheDocument();
  });

  it('0건이면 빈 상태와 연동 준비 안내를 보여 준다', async () => {
    setup({ approvals: [FIREWALL_APPROVALS[2]] });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /승인/);
    expect(await screen.findByText('승인 대기 중인 차단 요청이 없습니다.')).toBeInTheDocument();
    expect(screen.getByText(/mcp-firewall-server/)).toBeInTheDocument();
    expect(screen.getByText(/block_ip 도구를 승인 필요로 지정/)).toBeInTheDocument();
  });

  it('대기 건이 한 번에 가져온 수보다 많으면 일부만 확인했다고 알린다', async () => {
    setup({ approvals: FIREWALL_APPROVALS, approvalTotal: 250 });
    const user = userEvent.setup();
    renderPage();
    await openTab(user, /승인/);
    expect(await screen.findByText(/승인 대기 건이 많아 일부만 확인했습니다/)).toBeInTheDocument();
  });
});
