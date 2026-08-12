import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  BackgroundJob,
  EnqueueJobRequest,
  EnqueueJobResponse,
  MyScheduleRun,
  SeenAllResponse,
  UnseenCountResponse,
} from '@/types/backgroundJob';

// background-jobs: 작업 등록·조회·확인 처리 + 내 스케줄 실행 이력 (Design §5-1)
export const backgroundJobService = {
  enqueue: (agentId: string, data: EnqueueJobRequest) =>
    authApiClient.post<EnqueueJobResponse>(
      API_ENDPOINTS.AGENT_JOBS(agentId),
      data,
    ),

  list: (params?: { status?: string; limit?: number; offset?: number }) =>
    authApiClient.get<BackgroundJob[]>(API_ENDPOINTS.JOBS, { params }),

  get: (jobId: string) =>
    authApiClient.get<BackgroundJob>(API_ENDPOINTS.JOB_DETAIL(jobId)),

  unseenCount: () =>
    authApiClient.get<UnseenCountResponse>(API_ENDPOINTS.JOBS_UNSEEN_COUNT),

  markSeen: (jobId: string) =>
    authApiClient.post<void>(API_ENDPOINTS.JOB_SEEN(jobId)),

  markAllSeen: () =>
    authApiClient.post<SeenAllResponse>(API_ENDPOINTS.JOBS_SEEN_ALL),

  listMyScheduleRuns: (params?: { limit?: number; offset?: number }) =>
    authApiClient.get<MyScheduleRun[]>(API_ENDPOINTS.MY_SCHEDULE_RUNS, {
      params,
    }),
};
