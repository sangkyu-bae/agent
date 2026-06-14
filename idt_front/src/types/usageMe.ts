/**
 * My Usage 타입 (M5).
 * /usage/me/runs, /usage/me/timeseries 응답 타입.
 * 응답 스키마는 admin과 동일 — 권한 강제만 다름.
 */
export type {
  RunListResponse as MyRunsResponse,
  UsageTimeseriesResponse as MyUsageTimeseriesResponse,
  UsageByLlmResponse as MyUsageResponse, // /usage/me는 M4 LLM별 집계 그대로
  PeriodParams as MyUsageParams,
  RunStatus,
} from './agentRunAdmin';

import type { PeriodParams, RunStatus } from './agentRunAdmin';

/** My Runs 조회 파라미터 — user_id 미수용 (서버 강제) */
export interface MyRunsParams extends PeriodParams {
  agent_id?: string;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}
