import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  AdminRagasDashboard,
  EvalRunSummary,
  EvalRunDetail,
  PaginatedResponse,
  AdminRagasRunsParams,
} from '@/types/adminRagas';

export interface TestsetItem {
  id: string;
  name: string;
  description: string | null;
  case_count: number;
  created_at: string;
}

export const adminRagasService = {
  getDashboard: (recentLimit = 5) =>
    authApiClient
      .get<AdminRagasDashboard>(API_ENDPOINTS.ADMIN_RAGAS_DASHBOARD, {
        params: { recent_limit: recentLimit },
      })
      .then((r) => r.data),

  getRuns: (params: AdminRagasRunsParams = {}) =>
    authApiClient
      .get<PaginatedResponse<EvalRunSummary>>(API_ENDPOINTS.ADMIN_RAGAS_RUNS, { params })
      .then((r) => r.data),

  getRunDetail: (runId: string) =>
    authApiClient
      .get<EvalRunDetail>(API_ENDPOINTS.ADMIN_RAGAS_RUN_DETAIL(runId))
      .then((r) => r.data),

  getTestsets: (params: { limit?: number; offset?: number } = {}) =>
    authApiClient
      .get<PaginatedResponse<TestsetItem>>(API_ENDPOINTS.ADMIN_RAGAS_TESTSETS, { params })
      .then((r) => r.data),
};
