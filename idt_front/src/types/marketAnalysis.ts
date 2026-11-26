// stock-analysis-agents Design §5 · §7.5 — 시장 분석 API 계약.
// 백엔드 idt/src/api/routes/market_analysis_router.py ·
// application/market_analysis/queries.py · infrastructure/market_analysis/query_repository.py 와 1:1.
// 시각은 UTC ISO(+00:00), 거래일은 YYYY-MM-DD, 금액·비율은 number.

// ── 공통 ──────────────────────────────────────────────────────────────────

export interface MarketAnalysisAccessResponse {
  enabled: boolean;
  can_view: boolean;
  can_manage: boolean;
}

export interface MarketAnalysisPage<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface MarketAnalysisErrorDetail {
  code: string;
  message: string;
  errors?: Record<string, string>;
  roles?: string[];
}

export const REGIMES = ['strong_bull', 'bull', 'neutral', 'bear', 'strong_bear'] as const;
export type Regime = (typeof REGIMES)[number];

export const REGIME_LABELS: Record<string, string> = {
  strong_bull: '강한 상승',
  bull: '상승',
  neutral: '중립',
  bear: '하락',
  strong_bear: '강한 하락',
};

// ── 대시보드 ──────────────────────────────────────────────────────────────

export interface MarketAnalysisKpi {
  open_positions: number;
  used_slots: number;
  slot_count: number;
  closed_trades: number;
  win_rate: number;
  avg_profit_rate: number;
  avg_holding_days: number;
  realized_cum_rate: number;
}

export interface EquityPoint {
  date: string;
  portfolio: number | null;
  kospi: number | null;
  kosdaq: number | null;
  open_positions?: number;
}

export interface RegimeSnapshot {
  date: string;
  value: string;
  kospi_close?: number | null;
  kosdaq_close?: number | null;
  basis?: Record<string, unknown> | null;
}

export interface MarketRound {
  id: number;
  trade_date: string;
  slot: string;
  kind: 'intraday' | 'close';
  trigger: 'auto' | 'manual';
  status: string;
  skip_reason: string | null;
  candidates: number;
  signaled: number;
  analyzed: number;
  over_cap: number;
  failed: number;
  tokens: number;
  cost_usd: number | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface MarketAnalysisDashboardResponse {
  as_of: string;
  switch: { enabled: boolean; next_round: string | null };
  kpi: MarketAnalysisKpi;
  equity: EquityPoint[];
  regime: RegimeSnapshot | null;
  last_round: MarketRound | null;
}

// ── 포지션 · 판단 · 저널 ───────────────────────────────────────────────────

export interface MarketPosition {
  id: number;
  symbol: string;
  name: string | null;
  sector: string | null;
  status: 'open' | 'closed';
  slot_weight: number | null;
  entry_price: number | null;
  entry_at: string | null;
  target_price: number | null;
  stop_loss: number | null;
  exit_price: number | null;
  exit_at: string | null;
  exit_reason: string | null;
  profit_rate: number | null;
  holding_days: number | null;
  buy_decision_id: number | null;
  /** 보유 목록에만 — 시세가 없으면 null (0 이 아니다) */
  current_price?: number | null;
  unrealized_rate?: number | null;
}

export interface MarketDecision {
  id: number;
  kind: 'buy' | 'sell';
  symbol: string;
  name: string | null;
  decision: string;
  score: number | null;
  confidence: number | null;
  target_price: number | null;
  stop_loss: number | null;
  investment_period: string | null;
  sector: string | null;
  rationale: string | null;
  skip_reason: string | null;
  gate: {
    passed?: boolean;
    reasons?: string[];
    price?: string;
    rr?: string | null;
    stop_pct?: string | null;
    exit?: string;
  } | null;
  principles_used: number[];
  price_at_decision: number | null;
  regime: string | null;
  provisional: boolean;
  report_id: number | null;
  position_id: number | null;
  run_id: string | null;
  created_at: string | null;
}

export interface MarketJournal {
  id: number;
  position_id: number;
  one_line: string | null;
  situation: string | null;
  evaluation: string | null;
  lessons: string[];
  tags: string[];
  raw_answer: string | null;
  created_at: string | null;
  symbol?: string;
  name?: string | null;
  profit_rate?: number | null;
  exit_reason?: string | null;
}

export interface MarketPositionDetail extends MarketPosition {
  buy_decision: MarketDecision | null;
  sell_decisions: MarketDecision[];
  journal: MarketJournal | null;
  report_id: number | null;
}

// ── 리포트 ────────────────────────────────────────────────────────────────

export interface MarketSignal {
  rule?: string;
  direction?: string;
  provisional?: boolean;
  values?: Record<string, unknown>;
}

export interface MarketReport {
  id: number;
  symbol: string;
  name: string | null;
  trade_date: string;
  round_id: number | null;
  provisional: boolean;
  signals: MarketSignal[];
  regime: string | null;
  status: 'running' | 'done' | 'partial' | 'failed';
  summary: string | null;
  tokens: number;
  cost_usd: number | null;
  created_at: string | null;
}

export interface MarketReportSection {
  role: string;
  status: string;
  content: string | null;
  run_id: string | null;
  tokens: number;
  cost_usd: number | null;
}

export interface MarketEvidence {
  source: string;
  tool: string;
  args: Record<string, unknown> | null;
  payload: string | null;
  is_error: boolean;
  fetched_at: string | null;
}

export interface MarketReportDetail extends MarketReport {
  header_facts: {
    price?: string;
    change?: string;
    change_rate?: string;
    volume?: number | null;
    as_of?: string;
    signals?: MarketSignal[];
  } | null;
  strategy: string | null;
  sections: MarketReportSection[];
  evidence: MarketEvidence[];
  decisions: MarketDecision[];
}

// ── 회차 ──────────────────────────────────────────────────────────────────

export interface MarketRoundItem {
  id: number;
  symbol: string;
  name: string | null;
  signals: MarketSignal[];
  status: string;
  error: string | null;
  report_id: number | null;
  tokens: number;
  cost_usd: number | null;
}

export interface MarketRoundDetail extends MarketRound {
  items: MarketRoundItem[];
}

// ── 인사이트 ──────────────────────────────────────────────────────────────

export interface MarketPrinciple {
  id: number;
  condition: string;
  action: string;
  reason: string | null;
  scope: 'buy' | 'sell' | 'all';
  priority: 'high' | 'medium' | 'low';
  confidence: number;
  supporting_count: number;
  is_active: boolean;
  source_journal_id: number | null;
  updated_by: string | null;
  updated_at: string | null;
}

export interface RulePerformance {
  rule: string;
  trades: number;
  win_rate: number;
  avg_profit_rate: number;
}

export interface MarketInsightsResponse {
  principles: MarketPrinciple[];
  journals: MarketJournal[];
  rule_performance: RulePerformance[];
}

export interface PrinciplePatchRequest {
  is_active: boolean;
  priority?: string | null;
}

// ── 설정 · 역할 · 운영 ─────────────────────────────────────────────────────

export interface MarketAnalysisSettings {
  enabled: boolean;
  round_times: string[];
  max_per_round: number;
  max_per_day: number;
  max_concurrent_stocks: number;
  max_concurrent_runs: number;
  signal_rules: string[];
  rule_params: Record<string, unknown> | null;
  ranking_kinds: string[];
  ranking_limit: number;
  condition_seqs: string[];
  intraday_entry_allowed: boolean;
  slot_count: number;
  min_score_by_regime: Record<string, number>;
  min_rr: number;
  max_stop_pct: number;
  min_stop_pct: number;
  max_principles: number;
  principle_auto_activate: boolean;
  run_as_user_id: string | null;
  kis_server_id: string | null;
  dart_server_id: string | null;
  perplexity_server_id: string | null;
}

export interface RoleAgentRow {
  role: string;
  name: string;
  agent_id: string | null;
}

export interface RoleAgentsResponse {
  roles: RoleAgentRow[];
}

export interface RoleAgentsUpdateResponse {
  mapping: Record<string, string>;
}

export interface BootstrapItem {
  role: string;
  status: 'created' | 'kept' | 'failed';
  agent_id: string | null;
  error: string | null;
}

export interface BootstrapResponse {
  items: BootstrapItem[];
}

export interface RunNowResponse {
  round_id: number;
}

// ── 화면 상수 ─────────────────────────────────────────────────────────────

export const MARKET_ANALYSIS_TABS = [
  'dashboard',
  'positions',
  'history',
  'watchlist',
  'reports',
  'insights',
  'rounds',
  'settings',
] as const;
export type MarketAnalysisTab = (typeof MARKET_ANALYSIS_TABS)[number];

export const MARKET_ANALYSIS_TAB_LABELS: Record<MarketAnalysisTab, string> = {
  dashboard: '대시보드',
  positions: '보유',
  history: '거래 내역',
  watchlist: '관심종목',
  reports: '리포트',
  insights: '인사이트',
  rounds: '실행 현황',
  settings: '설정',
};

export const MARKET_ANALYSIS_DISCLAIMER = '가상 계좌 시뮬레이션이며 투자 권유가 아닙니다.';

/** mcp-kis-server scan_signals 규칙 7종 (백엔드 DEFAULT_SIGNAL_RULES 와 같다) */
export const SIGNAL_RULES = [
  'ma_cross',
  'rsi_threshold',
  'bollinger_break',
  'macd_cross',
  'volume_spike',
  'gap',
  'closing_strength',
] as const;

export const SIGNAL_RULE_LABELS: Record<string, string> = {
  ma_cross: '이동평균 교차',
  rsi_threshold: 'RSI 임계',
  bollinger_break: '볼린저 이탈',
  macd_cross: 'MACD 교차',
  volume_spike: '거래량 급증',
  gap: '갭',
  closing_strength: '종가 강도',
};

export const RANKING_KINDS = ['volume', 'fluctuation', 'volume_power'] as const;
export const RANKING_KIND_LABELS: Record<string, string> = {
  volume: '거래량',
  fluctuation: '등락률',
  volume_power: '체결강도',
};

export const EXIT_REASON_LABELS: Record<string, string> = {
  target: '목표가 도달',
  stop: '손절가 도달',
  judge: '매도 판단',
};

export const REPORT_STATUS_LABELS: Record<string, string> = {
  running: '작성 중',
  done: '완료',
  partial: '일부',
  failed: '실패',
};

export const DECISION_LABELS: Record<string, string> = {
  enter: '진입',
  skip: '보류',
  hold: '보유',
  sell: '매도',
  adjust: '가격 조정',
};

export const ROUND_STATUS_LABELS: Record<string, string> = {
  running: '실행 중',
  done: '완료',
  skipped: '건너뜀',
  failed: '실패',
  abandoned: '중단됨',
};

// 키는 서버 SkipReason 값 그대로(대문자) — domain/market_analysis/round.py
export const ROUND_SKIP_LABELS: Record<string, string> = {
  DISABLED: '자동 분석 꺼짐',
  WEEKEND: '주말',
  HOLIDAY: '휴장',
  BUSY: '앞 회차 실행 중',
};

export const ROUND_KIND_LABELS: Record<string, string> = {
  intraday: '장중',
  close: '장 마감',
};

export const ITEM_STATUS_LABELS: Record<string, string> = {
  queued: '대기',
  analyzing: '분석 중',
  done: '완료',
  failed: '실패',
  over_cap: '상한 초과',
  duplicate: '오늘 분석함',
  held: '보유 중',
};

export const PRIORITY_LABELS: Record<string, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
};

export const SCOPE_LABELS: Record<string, string> = {
  buy: '매수',
  sell: '매도',
  all: '전체',
};

/** 결정론 게이트·보류 사유 코드 → 한글 (Design §6 EntryGatePolicy, §7.3) */
export const SKIP_REASON_LABELS: Record<string, string> = {
  DECISION_SKIP: '판단 에이전트가 보류',
  SCORE_BELOW_MIN: '점수가 체제별 최소 점수보다 낮음',
  PRICE_LEVELS_MISSING: '목표가·손절가 없음',
  LEVELS_INVALID: '손절가 < 현재가 < 목표가가 아님',
  STOP_TOO_WIDE: '손절폭이 너무 큼',
  STOP_TOO_TIGHT: '손절폭이 너무 작음',
  RR_BELOW_MIN: '손익비 부족',
  NO_SLOT: '남은 슬롯 없음',
  ALREADY_HELD: '이미 보유 중',
  INTRADAY_ENTRY_OFF: '장중 진입 꺼짐',
  REPORT_INCOMPLETE: '리포트 미완성(전략·요약 없음)',
  ROLE_UNMAPPED: '판단 에이전트 미지정',
  JUDGE_FAILED: '판단 에이전트 실행 실패',
  PARSE_FAILED: '판단 결과를 읽지 못함',
  QUOTE_UNAVAILABLE: '현재가 조회 실패',
  ENTRY_FAILED: '포지션 생성 실패',
  ADJUST_REJECTED: '가격 조정 거부(현재가 범위 밖)',
};

export const WATCHLIST_PERIODS = ['today', '7d', '30d'] as const;
export type WatchlistPeriod = (typeof WATCHLIST_PERIODS)[number];
export const WATCHLIST_PERIOD_LABELS: Record<WatchlistPeriod, string> = {
  today: '오늘',
  '7d': '7일',
  '30d': '30일',
};

export const MARKET_ANALYSIS_PAGE_SIZE = 20;
export const MARKET_ANALYSIS_ROUNDS_REFETCH_MS = 15_000;

/** 리포트 섹션 역할 → 제목 (백엔드 SECTION_TITLES 와 같다) */
export const SECTION_ROLE_LABELS: Record<string, string> = {
  section_technical: '기술적 분석',
  section_flow: '수급',
  section_financial: '재무',
  section_company: '기업·산업',
  section_news: '뉴스·촉매',
  section_market: '시장·섹터',
};

export const EVIDENCE_SOURCE_LABELS: Record<string, string> = {
  kis: 'KIS',
  dart: 'DART',
  perplexity: 'Perplexity',
  tavily: '뉴스 검색',
};
