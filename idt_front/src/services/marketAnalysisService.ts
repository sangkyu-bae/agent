import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  BootstrapResponse,
  MarketAnalysisAccessResponse,
  MarketAnalysisDashboardResponse,
  MarketAnalysisPage,
  MarketAnalysisSettings,
  MarketAnalysisSettingsUpdate,
  MarketDecision,
  MarketInsightsResponse,
  MarketPosition,
  MarketPositionDetail,
  MarketReport,
  MarketReportDetail,
  MarketRound,
  MarketRoundDetail,
  PrinciplePatchRequest,
  RoleAgentsResponse,
  RoleAgentsUpdateResponse,
  RunNowResponse,
} from '@/types/marketAnalysis';

// stock-analysis-agents §5.1 — 조회는 view, 변경은 manage 권한. 오류는 detail.code(MA_*)로 온다.
export const marketAnalysisService = {
  getAccess: () =>
    authApiClient
      .get<MarketAnalysisAccessResponse>(API_ENDPOINTS.MARKET_ANALYSIS_ACCESS)
      .then((r) => r.data),
  getDashboard: () =>
    authApiClient
      .get<MarketAnalysisDashboardResponse>(API_ENDPOINTS.MARKET_ANALYSIS_DASHBOARD)
      .then((r) => r.data),
  listPositions: (params: { status: 'open' | 'closed'; page: number; size: number }) =>
    authApiClient
      .get<MarketAnalysisPage<MarketPosition>>(API_ENDPOINTS.MARKET_ANALYSIS_POSITIONS, {
        params,
      })
      .then((r) => r.data),
  getPosition: (id: number) =>
    authApiClient
      .get<MarketPositionDetail>(API_ENDPOINTS.MARKET_ANALYSIS_POSITION(id))
      .then((r) => r.data),
  listDecisions: (params: { kind: string; decision: string; page: number; size: number }) =>
    authApiClient
      .get<MarketAnalysisPage<MarketDecision>>(API_ENDPOINTS.MARKET_ANALYSIS_DECISIONS, {
        params,
      })
      .then((r) => r.data),
  listReports: (params: { symbol?: string; date?: string; page: number; size: number }) =>
    authApiClient
      .get<MarketAnalysisPage<MarketReport>>(API_ENDPOINTS.MARKET_ANALYSIS_REPORTS, {
        params: {
          page: params.page,
          size: params.size,
          // 빈 필터는 키 자체를 보내지 않는다
          ...(params.symbol ? { symbol: params.symbol } : {}),
          ...(params.date ? { date: params.date } : {}),
        },
      })
      .then((r) => r.data),
  getReport: (id: number) =>
    authApiClient
      .get<MarketReportDetail>(API_ENDPOINTS.MARKET_ANALYSIS_REPORT(id))
      .then((r) => r.data),
  getInsights: () =>
    authApiClient
      .get<MarketInsightsResponse>(API_ENDPOINTS.MARKET_ANALYSIS_INSIGHTS)
      .then((r) => r.data),
  patchPrinciple: (id: number, body: PrinciplePatchRequest) =>
    authApiClient
      .patch(API_ENDPOINTS.MARKET_ANALYSIS_PRINCIPLE(id), body)
      .then((r) => r.data),
  listRounds: (params: { page: number; size: number }) =>
    authApiClient
      .get<MarketAnalysisPage<MarketRound>>(API_ENDPOINTS.MARKET_ANALYSIS_ROUNDS, { params })
      .then((r) => r.data),
  getRound: (id: number) =>
    authApiClient
      .get<MarketRoundDetail>(API_ENDPOINTS.MARKET_ANALYSIS_ROUND(id))
      .then((r) => r.data),
  // 종류는 보내지 않는다 — 서버가 서울 시각으로 정한다 (15:30 이후 장 마감)
  runNow: () =>
    authApiClient
      .post<RunNowResponse>(API_ENDPOINTS.MARKET_ANALYSIS_RUN_NOW, {})
      .then((r) => r.data),
  getSettings: () =>
    authApiClient
      .get<MarketAnalysisSettings>(API_ENDPOINTS.MARKET_ANALYSIS_SETTINGS)
      .then((r) => r.data),
  putSettings: (body: MarketAnalysisSettingsUpdate) =>
    authApiClient
      .put<MarketAnalysisSettings>(API_ENDPOINTS.MARKET_ANALYSIS_SETTINGS, body)
      .then((r) => r.data),
  putEnabled: (enabled: boolean) =>
    authApiClient
      .put<{ enabled: boolean }>(API_ENDPOINTS.MARKET_ANALYSIS_SETTINGS_ENABLED, { enabled })
      .then((r) => r.data),
  getRoleAgents: () =>
    authApiClient
      .get<RoleAgentsResponse>(API_ENDPOINTS.MARKET_ANALYSIS_ROLE_AGENTS)
      .then((r) => r.data),
  putRoleAgents: (mapping: Record<string, string>) =>
    authApiClient
      .put<RoleAgentsUpdateResponse>(API_ENDPOINTS.MARKET_ANALYSIS_ROLE_AGENTS, { mapping })
      .then((r) => r.data),
  bootstrapAgents: () =>
    authApiClient
      .post<BootstrapResponse>(API_ENDPOINTS.MARKET_ANALYSIS_BOOTSTRAP)
      .then((r) => r.data),
};
