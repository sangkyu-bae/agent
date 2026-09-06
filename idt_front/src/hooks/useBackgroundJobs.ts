import { useMutation, useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { backgroundJobService } from '@/services/backgroundJobService';
import type { JobListParams } from '@/services/backgroundJobService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
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
import {
  JOB_LIST_POLL_INTERVAL_MS,
  UNSEEN_COUNT_POLL_INTERVAL_MS,
  isJobActive,
} from '@/types/backgroundJob';

// background-jobs: 작업 등록·작업함·벨 배지 훅 (Design §5-1)

export const extractJobError = (e: unknown): string => {
  if (e instanceof AxiosError) {
    const detail = (e.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === 'string') return detail;
  }
  return e instanceof Error ? e.message : '요청에 실패했습니다.';
};

export const isJobConflictError = (e: unknown): boolean =>
  e instanceof AxiosError && e.response?.status === 409;

const invalidateJobs = () =>
  queryClient.invalidateQueries({ queryKey: queryKeys.backgroundJobs.all });

/**
 * 통합 작업 이력 — 진행중 항목이 있으면 폴링 유지, 없으면 중단.
 * Design Ref: §4.2 — 응답이 {items,total} 이므로 total 이 필요한 화면은 그대로 쓴다.
 */
export const useJobHistory = (params?: JobListParams) =>
  useQuery<JobListResponse>({
    queryKey: queryKeys.backgroundJobs.list(params),
    queryFn: () => backgroundJobService.list(params).then((r) => r.data),
    refetchInterval: (query) =>
      (query.state.data?.items ?? []).some((j) => isJobActive(j.status))
        ? JOB_LIST_POLL_INTERVAL_MS
        : false,
  });

export const useDeleteJob = () =>
  useMutation<void, Error, { jobId: string }>({
    mutationFn: ({ jobId }) =>
      backgroundJobService.remove(jobId).then(() => undefined),
    // 삭제된 작업은 미확인 배지에서도 빠져야 한다 (FR-16)
    onSuccess: () => invalidateJobs(),
  });

export const useCleanupJobs = () =>
  useMutation<CleanupJobsResponse, Error, void>({
    mutationFn: () => backgroundJobService.cleanup().then((r) => r.data),
    onSuccess: () => invalidateJobs(),
  });

/** 작업 단건 조회 */
export const useJob = (jobId: string | null) =>
  useQuery<BackgroundJob>({
    queryKey: queryKeys.backgroundJobs.detail(jobId ?? ''),
    queryFn: () => backgroundJobService.get(jobId as string).then((r) => r.data),
    enabled: !!jobId,
  });

/** 미확인 수 무효화 — 새로고침 버튼이 목록과 배지를 함께 갱신하도록 (FR-13) */
export const invalidateUnseenCount = () =>
  queryClient.invalidateQueries({
    queryKey: queryKeys.backgroundJobs.unseenCount(),
  });

/** 미확인 완료/실패 카운트 — 벨 배지 폴링 (D11) */
export const useUnseenCount = () =>
  useQuery<UnseenCountResponse>({
    queryKey: queryKeys.backgroundJobs.unseenCount(),
    queryFn: () => backgroundJobService.unseenCount().then((r) => r.data),
    refetchInterval: UNSEEN_COUNT_POLL_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });

export const useEnqueueJob = () =>
  useMutation<
    EnqueueJobResponse,
    Error,
    { agentId: string; data: EnqueueJobRequest }
  >({
    mutationFn: ({ agentId, data }) =>
      backgroundJobService.enqueue(agentId, data).then((r) => r.data),
    onSuccess: () => invalidateJobs(),
  });

export const useMarkSeen = () =>
  useMutation<void, Error, { jobId: string }>({
    mutationFn: ({ jobId }) =>
      backgroundJobService.markSeen(jobId).then(() => undefined),
    onSuccess: () => invalidateJobs(),
  });

export const useMarkAllSeen = () =>
  useMutation<SeenAllResponse, Error, void>({
    mutationFn: () => backgroundJobService.markAllSeen().then((r) => r.data),
    onSuccess: () => invalidateJobs(),
  });

/** 내 스케줄 정의 (작업함 스케줄 작업 탭, FR-15) */
export const useMySchedules = () =>
  useQuery<MySchedule[]>({
    queryKey: queryKeys.backgroundJobs.mySchedules(),
    queryFn: () => backgroundJobService.listMySchedules().then((r) => r.data),
  });

/**
 * 스케줄 정의 목록 무효화 — 토글·삭제는 기존 useAgentSchedules 훅을 쓰는데,
 * 그 훅은 이 화면의 캐시 키를 모르므로 호출측에서 직접 무효화한다.
 */
export const invalidateMySchedules = () =>
  queryClient.invalidateQueries({
    queryKey: queryKeys.backgroundJobs.mySchedules(),
  });
