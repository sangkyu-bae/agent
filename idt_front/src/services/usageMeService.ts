/**
 * My Usage service (M5).
 * /api/v1/usage/me, /usage/me/runs, /usage/me/timeseries HTTP 호출.
 * user_id 쿼리 파라미터는 절대 보내지 않는다 — 서버가 current_user.id 강제.
 */
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  MyRunsParams,
  MyRunsResponse,
  MyUsageParams,
  MyUsageResponse,
  MyUsageTimeseriesResponse,
} from '@/types/usageMe';

export const usageMeService = {
  /** 본인 LLM 모델별 집계 (M4 reuse) — 카드 데이터 합산에 사용 */
  getMyUsage: (params: MyUsageParams = {}) =>
    authApiClient
      .get<MyUsageResponse>(API_ENDPOINTS.USAGE_ME, { params })
      .then((r) => r.data),

  /** 본인 일자별 시계열 */
  getMyTimeseries: (params: MyUsageParams = {}) =>
    authApiClient
      .get<MyUsageTimeseriesResponse>(API_ENDPOINTS.USAGE_ME_TIMESERIES, {
        params,
      })
      .then((r) => r.data),

  /** 본인 Run 목록 — user_id 미포함 (서버 강제) */
  getMyRuns: (params: MyRunsParams = {}) =>
    authApiClient
      .get<MyRunsResponse>(API_ENDPOINTS.USAGE_ME_RUNS, { params })
      .then((r) => r.data),
};
