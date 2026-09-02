// agent-model-benchmark: 모델 스윕 TanStack Query 훅.
// 폴링: pending/running 스윕이 있을 때만 3초 간격, 없으면 중단 (useEval 선례와 동형).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import sweepService from '@/services/sweepService';
import type {
  CreateSweepPayload,
  SweepDetail,
  SweepEstimatePayload,
  SweepSummary,
} from '@/types/sweep';
import type { Paginated } from '@/types/eval';

const SWEEP_POLL_INTERVAL_MS = 3000;

const isActive = (status?: string) =>
  status === 'pending' || status === 'running';

const hasActiveSweep = (data: Paginated<SweepSummary> | undefined) =>
  !!data?.items?.some((s) => isActive(s.status));

export const useSweeps = (params?: { limit?: number; offset?: number }) =>
  useQuery({
    queryKey: queryKeys.eval.sweeps(params),
    queryFn: () => sweepService.list(params),
    // 진행 중인 스윕이 없으면 폴링을 멈춘다 — 완료된 목록을 계속 두드리지 않는다.
    refetchInterval: (query) =>
      hasActiveSweep(query.state.data as Paginated<SweepSummary> | undefined)
        ? SWEEP_POLL_INTERVAL_MS
        : false,
  });

export const useSweepDetail = (sweepId: string | null) =>
  useQuery({
    queryKey: queryKeys.eval.sweepDetail(sweepId ?? ''),
    queryFn: () => sweepService.get(sweepId as string),
    enabled: !!sweepId,
    refetchInterval: (query) =>
      isActive((query.state.data as SweepDetail | undefined)?.status)
        ? SWEEP_POLL_INTERVAL_MS
        : false,
  });

/**
 * 예상 비용 추정. 조회지만 POST라 mutation으로 둔다 — 사용자가 버튼을 눌러
 * 명시적으로 실행하는 동작이고, 자동 재조회가 일어나면 안 되기 때문이다.
 */
export const useEstimateSweep = () =>
  useMutation({
    mutationFn: (payload: SweepEstimatePayload) => sweepService.estimate(payload),
  });

export const useCreateSweep = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateSweepPayload) => sweepService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.eval.all }),
  });
};

export const useDeleteSweep = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sweepId: string) => sweepService.remove(sweepId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.eval.all }),
  });
};
