/**
 * Agent Run Admin Dashboard service (M5).
 * /api/v1/admin/{runs, usage/*} + /api/v1/agents/runs/{id} HTTP 호출.
 */
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  AdminRunsParams,
  PeriodParams,
  RunDetailResponse,
  RunListResponse,
  UsageByLlmResponse,
  UsageByNodeResponse,
  UsageByUserResponse,
  UsageSummary,
  UsageTimeseriesResponse,
} from '@/types/agentRunAdmin';

export const agentRunAdminService = {
  /** 대시보드 카드 4종 */
  getSummary: (params: PeriodParams = {}) =>
    authApiClient
      .get<UsageSummary>(API_ENDPOINTS.ADMIN_USAGE_SUMMARY, { params })
      .then((r) => r.data),

  /** 일자별 시계열 */
  getTimeseries: (params: PeriodParams = {}) =>
    authApiClient
      .get<UsageTimeseriesResponse>(API_ENDPOINTS.ADMIN_USAGE_TIMESERIES, {
        params,
      })
      .then((r) => r.data),

  /** Run 목록 (페이지네이션 + 필터) */
  getRuns: (params: AdminRunsParams = {}) =>
    authApiClient
      .get<RunListResponse>(API_ENDPOINTS.ADMIN_AGENT_RUNS, { params })
      .then((r) => r.data),

  /** Run 상세 (M4 reuse) */
  getRunDetail: (runId: string) =>
    authApiClient
      .get<RunDetailResponse>(API_ENDPOINTS.ADMIN_AGENT_RUN_DETAIL(runId))
      .then((r) => r.data),

  /** 사용자별 집계 (M4 reuse) */
  getUsageByUser: (params: PeriodParams = {}) =>
    authApiClient
      .get<UsageByUserResponse>(API_ENDPOINTS.ADMIN_USAGE_BY_USER, { params })
      .then((r) => r.data),

  /** LLM별 집계 (M4 reuse) */
  getUsageByLlm: (params: PeriodParams = {}) =>
    authApiClient
      .get<UsageByLlmResponse>(API_ENDPOINTS.ADMIN_USAGE_BY_LLM, { params })
      .then((r) => r.data),

  /** 노드별 집계 (M4 reuse) */
  getUsageByNode: (params: PeriodParams = {}) =>
    authApiClient
      .get<UsageByNodeResponse>(API_ENDPOINTS.ADMIN_USAGE_BY_NODE, { params })
      .then((r) => r.data),
};
