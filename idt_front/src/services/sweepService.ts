// agent-model-benchmark: 모델 스윕 API 서비스. authApiClient(Bearer) 경유.
import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { Paginated } from '@/types/eval';
import type {
  CreateSweepPayload,
  CreateSweepResponse,
  SweepDetail,
  SweepEstimate,
  SweepEstimatePayload,
  SweepSummary,
} from '@/types/sweep';

const sweepService = {
  /** 실행 전 예상 비용. 부수효과 없음 — 사용자가 금액을 보고 결정한다. */
  estimate: (payload: SweepEstimatePayload) =>
    authApiClient
      .post<SweepEstimate>(API_ENDPOINTS.RAGAS_SWEEP_ESTIMATE, payload)
      .then((r) => r.data),

  create: (payload: CreateSweepPayload) =>
    authApiClient
      .post<CreateSweepResponse>(API_ENDPOINTS.RAGAS_SWEEPS, payload)
      .then((r) => r.data),

  list: (params: { limit?: number; offset?: number } = {}) =>
    authApiClient
      .get<Paginated<SweepSummary>>(API_ENDPOINTS.RAGAS_SWEEPS, { params })
      .then((r) => r.data),

  get: (sweepId: string) =>
    authApiClient
      .get<SweepDetail>(API_ENDPOINTS.RAGAS_SWEEP_DETAIL(sweepId))
      .then((r) => r.data),

  remove: (sweepId: string) =>
    authApiClient
      .delete<void>(API_ENDPOINTS.RAGAS_SWEEP_DETAIL(sweepId))
      .then((r) => r.data),
};

export default sweepService;
