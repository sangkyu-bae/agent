// eval-hub: 평가 허브 TanStack Query 훅.
// runs 폴링: pending/running이 있을 때만 5초 간격, 없으면 중단.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import evalService from '@/services/evalService';
import { adminRagasService } from '@/services/adminRagasService';
import { queryKeys } from '@/lib/queryKeys';
import type {
  BatchEvalPayload,
  CreateTestsetPayload,
  EvalRun,
  Paginated,
} from '@/types/eval';

const RUN_POLL_INTERVAL_MS = 5000;

const hasActiveRun = (runs: EvalRun[] | undefined) =>
  !!runs?.some((r) => r.status === 'pending' || r.status === 'running');

// ── 테스트셋 ────────────────────────────────────────────

export const useTestsets = (params?: { limit?: number; offset?: number }) =>
  useQuery({
    queryKey: queryKeys.eval.testsets(params),
    queryFn: () => evalService.listTestsets(params),
  });

export const useTestsetDetail = (testsetId: string | null) =>
  useQuery({
    queryKey: queryKeys.eval.testsetDetail(testsetId ?? ''),
    queryFn: () => evalService.getTestset(testsetId as string),
    enabled: !!testsetId,
  });

export const useCreateTestset = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateTestsetPayload) =>
      evalService.createTestset(payload),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.eval.all }),
  });
};

export const useUploadTestset = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      name,
      description,
    }: {
      file: File;
      name: string;
      description?: string;
    }) => evalService.uploadTestset(file, name, description),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.eval.all }),
  });
};

export const useGenerateDraft = () =>
  useMutation({
    mutationFn: ({ file, maxPairs }: { file: File; maxPairs?: number }) =>
      evalService.generateDraft(file, maxPairs),
  });

export const useDeleteTestset = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (testsetId: string) => evalService.deleteTestset(testsetId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.eval.all }),
  });
};

// ── 메트릭 카탈로그 ─────────────────────────────────────

export const useEvalMetrics = () =>
  useQuery({
    queryKey: queryKeys.eval.metrics(),
    queryFn: evalService.listMetrics,
    staleTime: 30 * 60 * 1000, // 정적 카탈로그
  });

// ── 배치 평가 실행 ──────────────────────────────────────

export const useStartBatchEval = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: BatchEvalPayload) =>
      evalService.startBatchEval(payload),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.eval.all }),
  });
};

export const useEvalRuns = (params?: { limit?: number; offset?: number }) =>
  useQuery({
    queryKey: queryKeys.eval.runs(params),
    queryFn: () => evalService.listRuns(params),
    refetchInterval: (query) => {
      const data = query.state.data as Paginated<EvalRun> | undefined;
      return hasActiveRun(data?.items) ? RUN_POLL_INTERVAL_MS : false;
    },
  });

export const useEvalRunDetail = (runId: string | null) =>
  useQuery({
    queryKey: queryKeys.eval.runDetail(runId ?? ''),
    queryFn: () => evalService.getRun(runId as string),
    enabled: !!runId,
    refetchInterval: (query) => {
      const data = query.state.data as EvalRun | undefined;
      return data && (data.status === 'pending' || data.status === 'running')
        ? RUN_POLL_INTERVAL_MS
        : false;
    },
  });

export const useEvalRunResults = (
  runId: string | null,
  params?: { limit?: number; offset?: number },
) =>
  useQuery({
    queryKey: queryKeys.eval.runResults(runId ?? '', params),
    queryFn: () => evalService.getRunResults(runId as string, params),
    enabled: !!runId,
  });

export const useDeleteEvalRun = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => evalService.deleteRun(runId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.eval.all }),
  });
};

// ── 관리자 대시보드 (기존 adminRagasService 재사용) ─────

export const useAdminRagasDashboard = (enabled: boolean) =>
  useQuery({
    queryKey: queryKeys.eval.adminDashboard(),
    queryFn: () => adminRagasService.getDashboard(),
    enabled,
  });
