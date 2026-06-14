/**
 * Agent Run Admin Dashboard hooks (M5).
 * TanStack Query 래퍼 — 캐싱·invalidation을 관리한다.
 */
import { useQuery } from '@tanstack/react-query';
import { agentRunAdminService } from '@/services/agentRunAdminService';
import { queryKeys } from '@/lib/queryKeys';
import type {
  AdminRunsParams,
  PeriodParams,
} from '@/types/agentRunAdmin';

/** 카드 4종 요약 */
export const useAdminUsageSummary = (params: PeriodParams = {}) =>
  useQuery({
    queryKey: queryKeys.agentRunAdmin.summary(params.from, params.to),
    queryFn: () => agentRunAdminService.getSummary(params),
  });

/** 일자별 시계열 */
export const useAdminUsageTimeseries = (params: PeriodParams = {}) =>
  useQuery({
    queryKey: queryKeys.agentRunAdmin.timeseries(params.from, params.to),
    queryFn: () => agentRunAdminService.getTimeseries(params),
  });

/** Run 목록 (필터·페이지네이션) */
export const useAdminRuns = (params: AdminRunsParams = {}) =>
  useQuery({
    queryKey: queryKeys.agentRunAdmin.runs(params),
    queryFn: () => agentRunAdminService.getRuns(params),
  });

/** Run 상세 */
export const useAgentRunDetail = (runId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.agentRunAdmin.runDetail(runId ?? ''),
    queryFn: () => agentRunAdminService.getRunDetail(runId!),
    enabled: Boolean(runId),
  });

/** 사용자별 집계 */
export const useUsageByUser = (params: PeriodParams = {}) =>
  useQuery({
    queryKey: queryKeys.agentRunAdmin.byUser(params.from, params.to),
    queryFn: () => agentRunAdminService.getUsageByUser(params),
  });

/** LLM별 집계 */
export const useUsageByLlm = (params: PeriodParams = {}) =>
  useQuery({
    queryKey: queryKeys.agentRunAdmin.byLlm(params.from, params.to),
    queryFn: () => agentRunAdminService.getUsageByLlm(params),
  });

/** 노드별 집계 */
export const useUsageByNode = (params: PeriodParams = {}) =>
  useQuery({
    queryKey: queryKeys.agentRunAdmin.byNode(params.from, params.to),
    queryFn: () => agentRunAdminService.getUsageByNode(params),
  });
