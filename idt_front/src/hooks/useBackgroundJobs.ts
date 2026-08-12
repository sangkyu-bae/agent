import { useMutation, useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { backgroundJobService } from '@/services/backgroundJobService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type {
  BackgroundJob,
  EnqueueJobRequest,
  EnqueueJobResponse,
  MyScheduleRun,
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

/** 내 작업 목록 — 진행중 항목이 있으면 폴링 유지, 없으면 중단 */
export const useJobList = (params?: {
  status?: string;
  limit?: number;
  offset?: number;
}) =>
  useQuery<BackgroundJob[]>({
    queryKey: queryKeys.backgroundJobs.list(params),
    queryFn: () => backgroundJobService.list(params).then((r) => r.data),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((j) => isJobActive(j.status))
        ? JOB_LIST_POLL_INTERVAL_MS
        : false,
  });

/** 작업 단건 조회 */
export const useJob = (jobId: string | null) =>
  useQuery<BackgroundJob>({
    queryKey: queryKeys.backgroundJobs.detail(jobId ?? ''),
    queryFn: () => backgroundJobService.get(jobId as string).then((r) => r.data),
    enabled: !!jobId,
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

/** 내 스케줄 실행 이력 (작업함 스케줄 탭, D9) */
export const useMyScheduleRuns = (params?: {
  limit?: number;
  offset?: number;
}) =>
  useQuery<MyScheduleRun[]>({
    queryKey: queryKeys.backgroundJobs.scheduleRuns(params),
    queryFn: () =>
      backgroundJobService.listMyScheduleRuns(params).then((r) => r.data),
  });
