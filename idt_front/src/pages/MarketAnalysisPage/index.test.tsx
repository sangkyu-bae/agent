// stock-analysis-agents module-9 — Design §13.4 L2 #1~7 + 권한·오류 경로.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { delay, http, HttpResponse } from 'msw';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import {
  MA_ACCESS_MANAGER,
  MA_ACCESS_NONE,
  MA_ACCESS_VIEWER,
  MA_DASHBOARD_OFF,
  MA_INDEX_CHART,
  MA_ROLE_AGENTS,
  MA_SETTINGS,
  marketAnalysisHandlers,
} from '@/__tests__/mocks/marketAnalysisMocks';
import MarketAnalysisPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// 현재 주소를 보이게 해 탭·상세가 URL 에 실리는지 확인한다 (G4)
const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
};

// 페이지 안의 Link(빌더 이동)에 라우터가 필요하다
const renderPage = (entry = '/market-analysis') =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <MarketAnalysisPage />
      <LocationProbe />
    </MemoryRouter>,
    { wrapper: createWrapper() },
  );

// MSW 는 먼저 넣은 핸들러가 이긴다 — 덮어쓸 응답을 기본 묶음보다 앞에 둔다
const use = (access = MA_ACCESS_MANAGER, ...overrides: Parameters<typeof server.use>) =>
  server.use(...overrides, ...marketAnalysisHandlers(access));

const openTab = async (user: ReturnType<typeof userEvent.setup>, name: string) => {
  await user.click(await screen.findByRole('tab', { name }));
};

describe('탭·리포트 주소 (G4)', () => {
  it('탭을 누르면 주소에 탭이 실리고, 리포트를 열면 리포트 번호도 실린다', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers());
    renderPage();
    await openTab(user, '리포트');
    expect(screen.getByTestId('location')).toHaveTextContent('/market-analysis?tab=reports');
    await user.click(await screen.findByRole('button', { name: 'SK하이닉스 리포트' }));
    expect(screen.getByTestId('location')).toHaveTextContent('tab=reports&report=11');
  });

  it('주소로 바로 들어오면 그 탭·리포트를 연다 (새로고침·링크 공유)', async () => {
    server.use(...marketAnalysisHandlers());
    renderPage('/market-analysis?tab=reports&report=11');
    expect(await screen.findByText('머리 사실 (도구 결과 그대로)')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '리포트' })).toHaveAttribute('aria-selected', 'true');
  });

  it('모르는 탭 값이면 대시보드', async () => {
    server.use(...marketAnalysisHandlers());
    renderPage('/market-analysis?tab=nope');
    expect(await screen.findByRole('tab', { name: '대시보드' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('공통 (L2 #1)', () => {
  it('면책 띠와 자동 분석 상태 칩을 보인다', async () => {
    server.use(...marketAnalysisHandlers());
    renderPage();
    expect(await screen.findByText('가상 계좌 시뮬레이션이며 투자 권유가 아닙니다.')).toBeInTheDocument();
    expect(await screen.findByText(/자동 분석 켜짐 · 다음/)).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(8);
  });

  it('스위치가 꺼져 있으면 꺼짐 칩', async () => {
    use(
      MA_ACCESS_MANAGER,
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_DASHBOARD}`, () => HttpResponse.json(MA_DASHBOARD_OFF)),
    );
    renderPage();
    expect(await screen.findByText('자동 분석 꺼짐')).toBeInTheDocument();
  });

  it('보기 권한이 없으면 안내만 보인다', async () => {
    server.use(...marketAnalysisHandlers(MA_ACCESS_NONE));
    renderPage();
    expect(await screen.findByText('권한이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  });

  it('모듈이 꺼져 404 면 권한 없음 안내', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ACCESS}`, () =>
        HttpResponse.json({ detail: 'Not Found' }, { status: 404 }),
      ),
    );
    renderPage();
    expect(await screen.findByText('권한이 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('시장 분석 기능이 꺼져 있습니다.')).toBeInTheDocument();
  });
});

describe('대시보드 (L2 #2)', () => {
  it('KPI 8개·최근 회차를 보인다', async () => {
    server.use(...marketAnalysisHandlers());
    renderPage();
    for (const label of ['보유 종목', '슬롯 사용', '청산 거래', '승률', '평균 수익률', '평균 보유일', '누적 실현 수익률', '시장 체제']) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('3/10')).toBeInTheDocument();
    expect(screen.getByText('+6.40%')).toBeInTheDocument();
    expect(screen.getByText('하락')).toBeInTheDocument(); // bear
    expect(screen.getByText('14 · 0 · 1')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /누적 수익률/ })).toBeInTheDocument();
  });
});

describe('올해 시장 카드 (market-index-ytd-chart §5.4)', () => {
  const chart = (body: unknown, status = 200) =>
    http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_INDEX_CHART}`, () => HttpResponse.json(body, { status }));
  const EMPTY_SERIES = { base_date: null, base_close: null, points: [] };

  it('지수별 최신 등락률·미확정·차트를 보인다', async () => {
    use();
    renderPage();
    const card = await screen.findByRole('region', { name: '올해 시장' });
    expect(await within(card).findByText('KOSPI +4.04%')).toBeInTheDocument();
    expect(within(card).getByText('KOSDAQ -1.20%')).toBeInTheDocument();
    expect(within(card).getByText('(11/27 미확정)')).toBeInTheDocument();
    expect(within(card).getByRole('img', { name: '올해 KOSPI·KOSDAQ 등락률' })).toBeInTheDocument();
    expect(within(card).getByText(/연초 첫 거래일 종가 대비 등락률입니다/)).toBeInTheDocument();
  });

  it('stale 이면 저장 데이터로 그리고 마지막 확정일로 안내한다 (G-M6)', async () => {
    use(MA_ACCESS_MANAGER, chart({ ...MA_INDEX_CHART, source_status: 'stale', source_error: 'SERVER_UNAVAILABLE' }));
    renderPage();
    const card = await screen.findByRole('region', { name: '올해 시장' });
    // 11/27 은 미확정 점이라 저장 데이터 기준일이 아니다
    expect(await within(card).findByText(/최신 시세를 받지 못해 11\/26까지의 저장 데이터로 표시합니다/)).toBeInTheDocument();
    expect(within(card).getByRole('img', { name: '올해 KOSPI·KOSDAQ 등락률' })).toBeInTheDocument();
  });

  it('한쪽 지수만 데이터가 있으면 빠진 지수를 밝힌다 (G-I1)', async () => {
    use(
      MA_ACCESS_MANAGER,
      chart({
        ...MA_INDEX_CHART,
        series: { KOSPI: MA_INDEX_CHART.series.KOSPI, KOSDAQ: EMPTY_SERIES },
        source_status: 'unavailable',
        source_error: 'RATE_LIMITED',
      }),
    );
    renderPage();
    const card = await screen.findByRole('region', { name: '올해 시장' });
    expect(await within(card).findByText('KOSDAQ 시세를 받지 못했습니다. 잠시 후 다시 확인하세요.')).toBeInTheDocument();
    expect(within(card).getByText('KOSPI +4.04%')).toBeInTheDocument();
    expect(within(card).getByRole('img', { name: '올해 KOSPI·KOSDAQ 등락률' })).toBeInTheDocument();
  });

  it('차트를 불러오는 동안 로딩 문구 (G-M5)', async () => {
    use(
      MA_ACCESS_MANAGER,
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_INDEX_CHART}`, async () => {
        await delay('infinite');
        return HttpResponse.json(MA_INDEX_CHART);
      }),
    );
    renderPage();
    const card = await screen.findByRole('region', { name: '올해 시장' });
    expect(within(card).getByText('지수 흐름을 불러오는 중…')).toBeInTheDocument();
  });

  it('unavailable 이면 KIS 설정 안내', async () => {
    use(
      MA_ACCESS_MANAGER,
      chart({
        ...MA_INDEX_CHART,
        series: { KOSPI: EMPTY_SERIES, KOSDAQ: EMPTY_SERIES },
        source_status: 'unavailable',
        source_error: 'KIS_NOT_CONFIGURED',
      }),
    );
    renderPage();
    const card = await screen.findByRole('region', { name: '올해 시장' });
    expect(await within(card).findByText('지수 시세를 받을 수 없습니다. KIS 서버 설정을 확인하세요.')).toBeInTheDocument();
    expect(within(card).queryByRole('img')).not.toBeInTheDocument();
  });

  it('올해 봉이 아직 없으면 빈 상태', async () => {
    use(MA_ACCESS_MANAGER, chart({ ...MA_INDEX_CHART, series: { KOSPI: EMPTY_SERIES, KOSDAQ: EMPTY_SERIES }, regimes: [] }));
    renderPage();
    const card = await screen.findByRole('region', { name: '올해 시장' });
    expect(await within(card).findByText('올해 첫 거래일 이후에 표시됩니다.')).toBeInTheDocument();
  });

  it('차트 조회가 실패해도 대시보드 나머지는 보인다', async () => {
    use(MA_ACCESS_MANAGER, chart({ detail: { code: 'MA_UNAVAILABLE', message: '준비 안 됨' } }, 503));
    renderPage();
    const card = await screen.findByRole('region', { name: '올해 시장' });
    expect(await within(card).findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('보유 종목')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /누적 수익률/ })).toBeInTheDocument();
  });
});

describe('보유·거래 내역', () => {
  it('현재가가 없으면 0 이 아니라 "시세 없음"', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers());
    renderPage();
    await openTab(user, '보유');
    const table = await screen.findByRole('table', { name: '보유 종목' });
    expect(within(table).getByText('+5.50%')).toBeInTheDocument();
    expect(within(table).getByText('시세 없음')).toBeInTheDocument();
  });

  it('청산 행 → 포지션 상세 → 리포트로 이동', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers());
    renderPage();
    await openTab(user, '거래 내역');
    await user.click(await screen.findByRole('button', { name: 'SK하이닉스 상세' }));
    expect(await screen.findByText('갭 상승 추격 진입 후 손절')).toBeInTheDocument();
    expect(screen.getByText('추세 유지')).toBeInTheDocument();
    expect(screen.getByText(/게이트 통과 · 손익비 4.00/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '근거 리포트 보기' }));
    expect(await screen.findByText('투자 시나리오 본문')).toBeInTheDocument();
  });
});

describe('관심종목 (L2 #3)', () => {
  it('보류 사유를 한글로 풀어 보인다', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers());
    renderPage();
    await openTab(user, '관심종목');
    expect(await screen.findByText('거래량 부족')).toBeInTheDocument();
    expect(screen.getByText('판단 에이전트가 보류')).toBeInTheDocument();
    expect(screen.getByText('점수가 체제별 최소 점수보다 낮음 (6<7, bear)')).toBeInTheDocument();
    expect(screen.getByText('6 / 7')).toBeInTheDocument();
    expect(screen.getByText('미확정')).toBeInTheDocument();
  });
});

describe('리포트 (L2 #4)', () => {
  it('실패한 섹션은 "데이터 없음", 오류 근거는 표시', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers());
    renderPage();
    await openTab(user, '리포트');
    await user.click(await screen.findByRole('button', { name: 'SK하이닉스 리포트' }));
    const news = await screen.findByText('뉴스·촉매');
    expect(within(news.closest('summary') as HTMLElement).getByText('데이터 없음')).toBeInTheDocument();
    expect(screen.getByText('기술적 분석')).toBeInTheDocument();
    expect(screen.getByText('오류')).toBeInTheDocument();
    expect(screen.getByText('get_financials')).toBeInTheDocument();
  });

  it('머리 사실에 신호 값·방향·미확정을 보인다 (G3)', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers());
    renderPage();
    await openTab(user, '리포트');
    await user.click(await screen.findByRole('button', { name: 'SK하이닉스 리포트' }));
    const gap = await screen.findByText(/갭 ↑/);
    expect(gap).toHaveTextContent('change_pct 3.1');
    const spike = screen.getByText(/거래량 급증 ↑/);
    expect(spike).toHaveTextContent('ratio 2.5');
    expect(spike).toHaveTextContent('avg_volume 120,000');
    expect(spike).toHaveTextContent('미확정');
    expect(gap).not.toHaveTextContent('미확정');
  });
});

describe('인사이트 (L2 #7)', () => {
  it('manage 는 원칙을 켜면 PATCH 한다', async () => {
    const user = userEvent.setup();
    const patches: unknown[] = [];
    server.use(
      ...marketAnalysisHandlers(),
      http.patch('*/api/v1/market-analysis/principles/:id', async ({ request, params }) => {
        patches.push({ id: params.id, body: await request.json() });
        return HttpResponse.json({ id: 1, is_active: true });
      }),
    );
    renderPage();
    await openTab(user, '인사이트');
    await user.click(await screen.findByRole('checkbox', { name: /갭 상승 다음 날 원칙 켜기/ }));
    await waitFor(() => expect(patches).toEqual([{ id: '1', body: { is_active: true } }]));
  });

  it('view 는 토글이 비활성', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers(MA_ACCESS_VIEWER));
    renderPage();
    await openTab(user, '인사이트');
    expect(await screen.findByRole('checkbox', { name: /원칙 켜기/ })).toBeDisabled();
  });
});

describe('실행 현황', () => {
  it('지금 실행 → 확인창 → POST, 409 는 문구로', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      ...marketAnalysisHandlers(),
      http.post(`*${API_ENDPOINTS.MARKET_ANALYSIS_RUN_NOW}`, () => {
        calls += 1;
        return HttpResponse.json(
          { detail: { code: 'MA_ROUND_RUNNING', message: 'busy' } },
          { status: 409 },
        );
      }),
    );
    renderPage();
    await openTab(user, '실행 현황');
    expect(await screen.findByText('휴장')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '지금 실행' }));
    await user.click(await screen.findByRole('button', { name: '실행' }));
    expect(await screen.findByText('실행 중인 회차가 있습니다. 끝난 뒤 다시 시도하세요.')).toBeInTheDocument();
    expect(calls).toBe(1);
  });

  it('view 에게는 지금 실행 버튼이 없다', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers(MA_ACCESS_VIEWER));
    renderPage();
    await openTab(user, '실행 현황');
    await screen.findByText('휴장');
    expect(screen.queryByRole('button', { name: '지금 실행' })).not.toBeInTheDocument();
  });
});

describe('설정 (L2 #5·#6)', () => {
  it('스위치를 끌 때 확인창을 거쳐 PUT 한다', async () => {
    const user = userEvent.setup();
    const bodies: unknown[] = [];
    server.use(
      ...marketAnalysisHandlers(),
      http.put(`*${API_ENDPOINTS.MARKET_ANALYSIS_SETTINGS_ENABLED}`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ enabled: false });
      }),
    );
    renderPage();
    await openTab(user, '설정');
    await user.click(await screen.findByRole('button', { name: '자동 분석 끄기' }));
    expect(bodies).toEqual([]); // 확인 전에는 보내지 않는다
    await user.click(await screen.findByRole('button', { name: '끄기' }));
    await waitFor(() => expect(bodies).toEqual([{ enabled: false }]));
  });

  it('view 권한이면 입력이 비활성', async () => {
    const user = userEvent.setup();
    server.use(...marketAnalysisHandlers(MA_ACCESS_VIEWER));
    renderPage();
    await openTab(user, '설정');
    expect(await screen.findByText('보기 권한만 있어 설정을 바꿀 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '회차 시각' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '자동 분석 끄기' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '설정 저장' })).not.toBeInTheDocument();
  });

  it('저장 422 는 필드별 사유를 보인다', async () => {
    const user = userEvent.setup();
    let sent: Record<string, unknown> | null = null;
    server.use(
      ...marketAnalysisHandlers(),
      http.get('*/api/v1/mcp-registry', () => HttpResponse.json({ items: [], total: 0 })),
      http.put(`*${API_ENDPOINTS.MARKET_ANALYSIS_SETTINGS}`, async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            detail: {
              code: 'MA_INVALID_SETTING',
              message: '설정 값을 확인하세요.',
              errors: { max_per_round: '1~200 사이여야 합니다' },
            },
          },
          { status: 422 },
        );
      }),
    );
    renderPage();
    await openTab(user, '설정');
    const times = await screen.findByRole('textbox', { name: '회차 시각' });
    await user.clear(times);
    await user.type(times, '09:30, 15:40');
    await user.click(screen.getByRole('button', { name: '설정 저장' }));
    expect(await screen.findByText('1~200 사이여야 합니다')).toBeInTheDocument();
    expect(sent).toMatchObject({ round_times: ['09:30', '15:40'], kis_server_id: MA_SETTINGS.kis_server_id });
    // 스위치는 PUT /settings/enabled 만 바꾼다 — 설정 저장 본문에는 싣지 않는다 (G9)
    expect(sent).not.toHaveProperty('enabled');
  });

  it('역할 매핑 표: 미지정 표시와 기본 에이전트 만들기', async () => {
    const user = userEvent.setup();
    let boots = 0;
    server.use(
      ...marketAnalysisHandlers(),
      http.post(`*${API_ENDPOINTS.MARKET_ANALYSIS_BOOTSTRAP}`, () => {
        boots += 1;
        return HttpResponse.json({
          items: [{ role: 'sell_judge', status: 'created', agent_id: 's1', error: null }],
        });
      }),
    );
    renderPage();
    await openTab(user, '설정');
    const table = await screen.findByRole('table', { name: '역할별 에이전트' });
    expect(within(table).getByText('미지정')).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: '지침 편집' })).toHaveAttribute(
      'href',
      '/agent-builder?edit=a1&returnTo=%2Fmarket-analysis',
    );
    await user.click(screen.getByRole('button', { name: '기본 에이전트 만들기' }));
    expect(await screen.findByText('매도 판단: 새로 만듦')).toBeInTheDocument();
    expect(boots).toBe(1);
  });
});

// 실화면 결함 (module-9 화면 확인): 저장·생성 뒤 다시 불러온 값이 달라지면 폼이 새로 그려지며
// 성공 문구가 사라졌다 — 다시 불러온 응답이 바뀌는 상황을 그대로 만든다.
describe('저장 뒤 다시 불러와도 결과 문구가 남는다', () => {
  it('설정 저장 → "저장했습니다"', async () => {
    const user = userEvent.setup();
    let saved = MA_SETTINGS;
    use(
      MA_ACCESS_MANAGER,
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_SETTINGS}`, () => HttpResponse.json(saved)),
      http.put(`*${API_ENDPOINTS.MARKET_ANALYSIS_SETTINGS}`, async ({ request }) => {
        saved = (await request.json()) as typeof MA_SETTINGS;
        return HttpResponse.json(saved);
      }),
      http.get('*/api/v1/mcp-registry', () => HttpResponse.json({ items: [], total: 0 })),
    );
    renderPage();
    await openTab(user, '설정');
    const runAs = await screen.findByRole('textbox', { name: '실행 사용자 ID' });
    await user.clear(runAs);
    await user.type(runAs, '9');
    await user.click(screen.getByRole('button', { name: '설정 저장' }));
    await waitFor(() => expect(saved.run_as_user_id).toBe('9'));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '실행 사용자 ID' })).toHaveValue('9');
  });

  it('기본 에이전트 만들기 → 결과가 남는다(매핑이 바뀌어도)', async () => {
    const user = userEvent.setup();
    let roles = MA_ROLE_AGENTS;
    use(
      MA_ACCESS_MANAGER,
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ROLE_AGENTS}`, () => HttpResponse.json(roles)),
      http.post(`*${API_ENDPOINTS.MARKET_ANALYSIS_BOOTSTRAP}`, () => {
        roles = {
          roles: roles.roles.map((r) => ({ ...r, agent_id: r.agent_id ?? 'new-1' })),
        };
        return HttpResponse.json({
          items: [{ role: 'sell_judge', status: 'created', agent_id: 'new-1', error: null }],
        });
      }),
    );
    renderPage();
    await openTab(user, '설정');
    await user.click(await screen.findByRole('button', { name: '기본 에이전트 만들기' }));
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: '매도 판단 에이전트 ID' })).toHaveValue('new-1'),
    );
    expect(screen.getByText('매도 판단: 새로 만듦')).toBeInTheDocument();
  });
});
