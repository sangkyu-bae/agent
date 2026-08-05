// eval-hub: 평가 허브 API 서비스. 모든 호출은 authApiClient(Bearer) 경유.
import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  BatchEvalPayload,
  BatchEvalResponse,
  CreateTestsetPayload,
  EvalResultItem,
  EvalRun,
  GeneratedDraft,
  MetricInfo,
  Paginated,
  Testset,
  TestsetDetail,
} from '@/types/eval';

const evalService = {
  // ── 테스트셋 ──────────────────────────────────────────
  listTestsets: (params: { limit?: number; offset?: number } = {}) =>
    authApiClient
      .get<Paginated<Testset>>(API_ENDPOINTS.RAGAS_TESTSETS, { params })
      .then((r) => r.data),

  getTestset: (testsetId: string) =>
    authApiClient
      .get<TestsetDetail>(API_ENDPOINTS.RAGAS_TESTSET_DETAIL(testsetId))
      .then((r) => r.data),

  createTestset: (payload: CreateTestsetPayload) =>
    authApiClient
      .post<Testset>(API_ENDPOINTS.RAGAS_TESTSETS, payload)
      .then((r) => r.data),

  uploadTestset: (file: File, name: string, description = '') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    formData.append('description', description);
    return authApiClient
      .post<Testset>(API_ENDPOINTS.RAGAS_TESTSET_UPLOAD, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },

  generateDraft: (file: File, maxPairs = 10) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('max_pairs', String(maxPairs));
    return authApiClient
      .post<GeneratedDraft>(API_ENDPOINTS.RAGAS_TESTSET_GENERATE, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },

  deleteTestset: (testsetId: string) =>
    authApiClient
      .delete(API_ENDPOINTS.RAGAS_TESTSET_DETAIL(testsetId))
      .then(() => undefined),

  // ── 메트릭 카탈로그 ───────────────────────────────────
  listMetrics: () =>
    authApiClient
      .get<MetricInfo[]>(API_ENDPOINTS.RAGAS_METRICS)
      .then((r) => r.data),

  // ── 배치 평가 실행 ────────────────────────────────────
  startBatchEval: (payload: BatchEvalPayload) =>
    authApiClient
      .post<BatchEvalResponse>(API_ENDPOINTS.RAGAS_BATCH, payload)
      .then((r) => r.data),

  listRuns: (params: { limit?: number; offset?: number } = {}) =>
    authApiClient
      .get<Paginated<EvalRun>>(API_ENDPOINTS.RAGAS_RUNS, { params })
      .then((r) => r.data),

  getRun: (runId: string) =>
    authApiClient
      .get<EvalRun>(API_ENDPOINTS.RAGAS_RUN_DETAIL(runId))
      .then((r) => r.data),

  getRunResults: (runId: string, params: { limit?: number; offset?: number } = {}) =>
    authApiClient
      .get<Paginated<EvalResultItem>>(API_ENDPOINTS.RAGAS_RUN_RESULTS(runId), {
        params,
      })
      .then((r) => r.data),

  deleteRun: (runId: string) =>
    authApiClient
      .delete(API_ENDPOINTS.RAGAS_RUN_DETAIL(runId))
      .then(() => undefined),
};

export default evalService;
