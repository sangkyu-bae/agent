import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  BackgroundJob,
  CleanupJobsResponse,
  EnqueueJobRequest,
  EnqueueJobResponse,
  JobListResponse,
  MySchedule,
  SeenAllResponse,
  UnseenCountResponse,
} from '@/types/backgroundJob';

export interface JobListParams {
  status?: string;
  type?: string;
  period?: string;
  limit?: number;
  offset?: number;
}

// background-jobs: 작업 등록·조회·확인 처리 + 내 스케줄 실행 이력 (Design §5-1)
// jobs-page-revamp: list 는 통합 이력 {items,total}, 삭제·정리 추가 (Design §4.2)
export const backgroundJobService = {
  enqueue: (agentId: string, data: EnqueueJobRequest) =>
    authApiClient.post<EnqueueJobResponse>(
      API_ENDPOINTS.AGENT_JOBS(agentId),
      data,
    ),

  list: (params?: JobListParams) =>
    authApiClient.get<JobListResponse>(API_ENDPOINTS.JOBS, { params }),

  remove: (jobId: string) =>
    authApiClient.delete<void>(API_ENDPOINTS.JOB_DETAIL(jobId)),

  cleanup: () =>
    authApiClient.post<CleanupJobsResponse>(API_ENDPOINTS.JOBS_CLEANUP),

  get: (jobId: string) =>
    authApiClient.get<BackgroundJob>(API_ENDPOINTS.JOB_DETAIL(jobId)),

  unseenCount: () =>
    authApiClient.get<UnseenCountResponse>(API_ENDPOINTS.JOBS_UNSEEN_COUNT),

  markSeen: (jobId: string) =>
    authApiClient.post<void>(API_ENDPOINTS.JOB_SEEN(jobId)),

  markAllSeen: () =>
    authApiClient.post<SeenAllResponse>(API_ENDPOINTS.JOBS_SEEN_ALL),

  listMySchedules: () =>
    authApiClient.get<MySchedule[]>(API_ENDPOINTS.MY_SCHEDULES),
};
