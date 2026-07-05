import { useQuery, useMutation } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { agentScheduleService } from '@/services/agentScheduleService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type {
  ScheduleCreateRequest,
  ScheduleUpdateRequest,
  ScheduleResponse,
  ScheduleRunResponse,
} from '@/types/agentSchedule';

// agent-schedule: 스케줄 CRUD/토글/실행 이력 훅

/** 서버 400 검증 메시지(detail)를 폼 에러로 그대로 표출하기 위한 추출기 */
export const extractScheduleError = (e: unknown): string => {
  if (e instanceof AxiosError) {
    const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === 'string') return detail;
  }
  return e instanceof Error ? e.message : '요청에 실패했습니다.';
};

const invalidateList = (agentId: string) =>
  queryClient.invalidateQueries({
    queryKey: queryKeys.agentSchedules.list(agentId),
  });

export const useAgentSchedules = (agentId: string | null) =>
  useQuery<ScheduleResponse[]>({
    queryKey: queryKeys.agentSchedules.list(agentId ?? ''),
    queryFn: () => agentScheduleService.list(agentId!).then((r) => r.data),
    enabled: !!agentId,
  });

export const useCreateSchedule = () =>
  useMutation<
    ScheduleResponse,
    Error,
    { agentId: string; data: ScheduleCreateRequest }
  >({
    mutationFn: ({ agentId, data }) =>
      agentScheduleService.create(agentId, data).then((r) => r.data),
    onSuccess: (_data, { agentId }) => invalidateList(agentId),
  });

export const useUpdateSchedule = () =>
  useMutation<
    ScheduleResponse,
    Error,
    { agentId: string; scheduleId: string; data: ScheduleUpdateRequest }
  >({
    mutationFn: ({ agentId, scheduleId, data }) =>
      agentScheduleService.update(agentId, scheduleId, data).then((r) => r.data),
    onSuccess: (_data, { agentId }) => invalidateList(agentId),
  });

export const useDeleteSchedule = () =>
  useMutation<void, Error, { agentId: string; scheduleId: string }>({
    mutationFn: ({ agentId, scheduleId }) =>
      agentScheduleService.remove(agentId, scheduleId).then(() => undefined),
    onSuccess: (_data, { agentId, scheduleId }) => {
      invalidateList(agentId);
      queryClient.invalidateQueries({
        queryKey: queryKeys.agentSchedules.runs(agentId, scheduleId),
      });
    },
  });

export const useToggleScheduleEnabled = () =>
  useMutation<
    ScheduleResponse,
    Error,
    { agentId: string; scheduleId: string; enabled: boolean }
  >({
    mutationFn: ({ agentId, scheduleId, enabled }) =>
      agentScheduleService
        .setEnabled(agentId, scheduleId, enabled)
        .then((r) => r.data),
    onSuccess: (_data, { agentId }) => invalidateList(agentId),
  });

/** 실행 이력 — 카드 확장 시에만 조회 (최근 20건) */
export const useScheduleRuns = (
  agentId: string | null,
  scheduleId: string | null,
  opts: { enabled: boolean },
) =>
  useQuery<ScheduleRunResponse[]>({
    queryKey: queryKeys.agentSchedules.runs(agentId ?? '', scheduleId ?? ''),
    queryFn: () =>
      agentScheduleService
        .listRuns(agentId!, scheduleId!, { limit: 20 })
        .then((r) => r.data),
    enabled: opts.enabled && !!agentId && !!scheduleId,
  });
