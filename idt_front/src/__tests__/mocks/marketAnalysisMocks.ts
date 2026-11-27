// stock-analysis-agents module-9 — 시장 분석 화면 테스트용 응답 (백엔드 module-8 형태 그대로).
import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  MarketAnalysisAccessResponse,
  MarketAnalysisDashboardResponse,
  MarketAnalysisPage,
  MarketAnalysisSettings,
  MarketDecision,
  MarketInsightsResponse,
  MarketPosition,
  MarketPositionDetail,
  MarketReport,
  MarketReportDetail,
  MarketRound,
  MarketRoundDetail,
  RoleAgentsResponse,
} from '@/types/marketAnalysis';

export const MA_ACCESS_MANAGER: MarketAnalysisAccessResponse = {
  enabled: true,
  can_view: true,
  can_manage: true,
};
export const MA_ACCESS_VIEWER: MarketAnalysisAccessResponse = {
  enabled: true,
  can_view: true,
  can_manage: false,
};
export const MA_ACCESS_NONE: MarketAnalysisAccessResponse = {
  enabled: true,
  can_view: false,
  can_manage: false,
};

export const MA_ROUND: MarketRound = {
  id: 41,
  trade_date: '2026-11-26',
  slot: '18:10',
  kind: 'close',
  trigger: 'auto',
  status: 'done',
  skip_reason: null,
  candidates: 30,
  signaled: 15,
  analyzed: 14,
  over_cap: 0,
  failed: 1,
  tokens: 120000,
  cost_usd: 3.12,
  error: null,
  started_at: '2026-11-26T09:10:00+00:00',
  finished_at: '2026-11-26T09:40:00+00:00',
};

export const MA_DASHBOARD: MarketAnalysisDashboardResponse = {
  as_of: '2026-11-26',
  switch: { enabled: true, next_round: '2026-11-27T01:00:00+00:00' },
  kpi: {
    open_positions: 3,
    used_slots: 3,
    slot_count: 10,
    closed_trades: 12,
    win_rate: 41.67,
    avg_profit_rate: 1.8,
    avg_holding_days: 4.2,
    realized_cum_rate: 6.4,
  },
  equity: [
    { date: '2026-11-25', portfolio: 5.9, kospi: 1.1, kosdaq: -0.4 },
    { date: '2026-11-26', portfolio: 6.4, kospi: 1.3, kosdaq: -0.2 },
  ],
  regime: { date: '2026-11-26', value: 'bear' },
  last_round: MA_ROUND,
};

export const MA_DASHBOARD_OFF: MarketAnalysisDashboardResponse = {
  ...MA_DASHBOARD,
  switch: { enabled: false, next_round: null },
};

const position = (over: Partial<MarketPosition>): MarketPosition => ({
  id: 1,
  symbol: '000660',
  name: 'SK하이닉스',
  sector: '반도체',
  status: 'open',
  slot_weight: 1,
  entry_price: 10000,
  entry_at: '2026-11-20T01:00:00+00:00',
  target_price: 12000,
  stop_loss: 9500,
  exit_price: null,
  exit_at: null,
  exit_reason: null,
  profit_rate: null,
  holding_days: null,
  buy_decision_id: 5,
  ...over,
});

export const MA_OPEN_POSITIONS: MarketAnalysisPage<MarketPosition> = {
  items: [
    position({ current_price: 10550, unrealized_rate: 5.5 }),
    position({ id: 2, symbol: '005930', name: '삼성전자', current_price: null, unrealized_rate: null }),
  ],
  total: 2,
  page: 1,
  size: 20,
};

export const MA_CLOSED_POSITIONS: MarketAnalysisPage<MarketPosition> = {
  items: [
    position({
      id: 3,
      status: 'closed',
      exit_price: 9400,
      exit_at: '2026-11-26T06:40:00+00:00',
      exit_reason: 'stop',
      profit_rate: -6,
      holding_days: 6,
    }),
  ],
  total: 1,
  page: 1,
  size: 20,
};

const decision = (over: Partial<MarketDecision>): MarketDecision => ({
  id: 5,
  kind: 'buy',
  symbol: '000660',
  name: 'SK하이닉스',
  decision: 'enter',
  score: 8,
  confidence: null,
  target_price: 12000,
  stop_loss: 9500,
  investment_period: '단기',
  sector: '반도체',
  rationale: '수급 개선',
  skip_reason: null,
  gate: { passed: true, reasons: [], price: '10000', rr: '4.00', stop_pct: '5.00' },
  principles_used: [],
  price_at_decision: 10000,
  regime: 'bull',
  provisional: false,
  report_id: 11,
  position_id: 1,
  run_id: 'run-1',
  created_at: '2026-11-20T01:00:00+00:00',
  ...over,
});

export const MA_POSITION_DETAIL: MarketPositionDetail = {
  ...MA_CLOSED_POSITIONS.items[0],
  buy_decision: decision({}),
  sell_decisions: [
    decision({
      id: 9,
      kind: 'sell',
      decision: 'hold',
      score: null,
      confidence: 6,
      rationale: '추세 유지',
      created_at: '2026-11-24T06:40:00+00:00',
    }),
  ],
  journal: {
    id: 1,
    position_id: 3,
    one_line: '갭 상승 추격 진입 후 손절',
    situation: '상황',
    evaluation: '평가',
    lessons: ['갭 추격 금지'],
    tags: ['gap'],
    raw_answer: null,
    created_at: '2026-11-26T06:41:00+00:00',
  },
  report_id: 11,
};

export const MA_WATCHLIST: MarketAnalysisPage<MarketDecision> = {
  items: [
    decision({
      id: 21,
      symbol: '005930',
      name: '삼성전자',
      decision: 'skip',
      score: 6,
      regime: 'bear',
      provisional: true,
      skip_reason: '거래량 부족 · GATE: DECISION_SKIP, SCORE_BELOW_MIN(6<7, bear)',
      created_at: new Date().toISOString(),
    }),
  ],
  total: 1,
  page: 1,
  size: 20,
};

export const MA_REPORTS: MarketAnalysisPage<MarketReport> = {
  items: [
    {
      id: 11,
      symbol: '000660',
      name: 'SK하이닉스',
      trade_date: '2026-11-26',
      round_id: 41,
      provisional: true,
      signals: [
        { rule: 'gap', direction: 'up', provisional: false, values: { change_pct: 3.1 } },
        { rule: 'volume_spike', direction: 'up', provisional: true, values: { ratio: 2.5, avg_volume: 120000 } },
      ],
      regime: 'bull',
      status: 'partial',
      summary: '요약',
      tokens: 800,
      cost_usd: 0.3,
      created_at: '2026-11-26T01:10:00+00:00',
    },
  ],
  total: 1,
  page: 1,
  size: 20,
};

export const MA_REPORT_DETAIL: MarketReportDetail = {
  ...MA_REPORTS.items[0],
  header_facts: { price: '10000', change: '200', change_rate: '2.04', volume: 1234, as_of: 't' },
  strategy: '투자 시나리오 본문',
  sections: [
    { role: 'section_technical', status: 'done', content: '기술적 분석 본문', run_id: 'r1', tokens: 100, cost_usd: 0.01 },
    { role: 'section_news', status: 'failed', content: '', run_id: null, tokens: 0, cost_usd: 0 },
  ],
  evidence: [
    { source: 'kis', tool: 'get_quote', args: { symbol: '000660' }, payload: '{"price":"10000"}', is_error: false, fetched_at: '2026-11-26T01:05:00+00:00' },
    { source: 'dart', tool: 'get_financials', args: {}, payload: 'DART_UNAVAILABLE: x', is_error: true, fetched_at: '2026-11-26T01:05:00+00:00' },
  ],
  decisions: [decision({})],
};

export const MA_INSIGHTS: MarketInsightsResponse = {
  principles: [
    {
      id: 1,
      condition: '갭 상승 다음 날',
      action: '진입하지 않는다',
      reason: '손절 2건',
      scope: 'buy',
      priority: 'high',
      confidence: 6,
      supporting_count: 2,
      is_active: false,
      source_journal_id: 1,
      updated_by: null,
      updated_at: null,
    },
  ],
  journals: [MA_POSITION_DETAIL.journal!],
  rule_performance: [{ rule: 'gap', trades: 2, win_rate: 50, avg_profit_rate: 1.5 }],
};

export const MA_ROUNDS: MarketAnalysisPage<MarketRound> = {
  items: [
    MA_ROUND,
    { ...MA_ROUND, id: 40, slot: '14:00', kind: 'intraday', status: 'skipped', skip_reason: 'HOLIDAY', analyzed: 0 },
  ],
  total: 2,
  page: 1,
  size: 20,
};

export const MA_ROUND_DETAIL: MarketRoundDetail = {
  ...MA_ROUND,
  items: [
    { id: 1, symbol: '000660', name: 'SK하이닉스', signals: [{ rule: 'gap' }], status: 'done', error: null, report_id: 11, tokens: 800, cost_usd: 0.3 },
    { id: 2, symbol: '005930', name: '삼성전자', signals: [], status: 'failed', error: 'REPORT_FAILED', report_id: null, tokens: 0, cost_usd: 0 },
  ],
};

export const MA_SETTINGS: MarketAnalysisSettings = {
  enabled: true,
  round_times: ['10:00', '14:00', '18:10'],
  max_per_round: 20,
  max_per_day: 50,
  max_concurrent_stocks: 2,
  max_concurrent_runs: 4,
  signal_rules: ['ma_cross', 'gap'],
  rule_params: null,
  ranking_kinds: ['volume'],
  ranking_limit: 30,
  condition_seqs: [],
  intraday_entry_allowed: true,
  slot_count: 10,
  min_score_by_regime: { strong_bull: 5, bull: 6, neutral: 6, bear: 7, strong_bear: 8 },
  min_rr: 2,
  max_stop_pct: 7,
  min_stop_pct: 2,
  max_principles: 10,
  principle_auto_activate: false,
  run_as_user_id: '7',
  kis_server_id: 'kis-1',
  dart_server_id: null,
  perplexity_server_id: null,
};

export const MA_ROLE_AGENTS: RoleAgentsResponse = {
  roles: [
    { role: 'buy_judge', name: '매수 판단', agent_id: 'a1' },
    { role: 'sell_judge', name: '매도 판단', agent_id: null },
  ],
};

/** 페이지 전체를 그릴 때 쓰는 기본 핸들러 묶음 — 테스트가 필요한 것만 server.use 로 덮어쓴다 */
export const marketAnalysisHandlers = (access: MarketAnalysisAccessResponse = MA_ACCESS_MANAGER) => [
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ACCESS}`, () => HttpResponse.json(access)),
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_DASHBOARD}`, () => HttpResponse.json(MA_DASHBOARD)),
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_POSITIONS}`, ({ request }) =>
    HttpResponse.json(
      new URL(request.url).searchParams.get('status') === 'closed'
        ? MA_CLOSED_POSITIONS
        : MA_OPEN_POSITIONS,
    ),
  ),
  http.get(`*/api/v1/market-analysis/positions/:id`, () => HttpResponse.json(MA_POSITION_DETAIL)),
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_DECISIONS}`, () => HttpResponse.json(MA_WATCHLIST)),
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_REPORTS}`, () => HttpResponse.json(MA_REPORTS)),
  http.get(`*/api/v1/market-analysis/reports/:id`, () => HttpResponse.json(MA_REPORT_DETAIL)),
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_INSIGHTS}`, () => HttpResponse.json(MA_INSIGHTS)),
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ROUNDS}`, () => HttpResponse.json(MA_ROUNDS)),
  http.get(`*/api/v1/market-analysis/rounds/:id`, () => HttpResponse.json(MA_ROUND_DETAIL)),
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_SETTINGS}`, () => HttpResponse.json(MA_SETTINGS)),
  http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ROLE_AGENTS}`, () => HttpResponse.json(MA_ROLE_AGENTS)),
];
