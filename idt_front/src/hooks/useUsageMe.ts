/**
 * My Usage hooks (M5).
 * 본인 사용량 데이터 fetch 훅 — service는 user_id 를 보내지 않으며
 * 서버가 current_user.id 를 강제 주입한다.
 */
import { useQuery } from '@tanstack/react-query';
import { usageMeService } from '@/services/usageMeService';
import { queryKeys } from '@/lib/queryKeys';
import type { MyRunsParams, MyUsageParams } from '@/types/usageMe';

/** 본인 LLM 모델별 집계 — 카드 합산 데이터 */
export const useMyUsage = (params: MyUsageParams = {}) =>
  useQuery({
    queryKey: queryKeys.usageMe.summary(params.from, params.to),
    queryFn: () => usageMeService.getMyUsage(params),
  });

/** 본인 일자별 시계열 */
export const useMyTimeseries = (params: MyUsageParams = {}) =>
  useQuery({
    queryKey: queryKeys.usageMe.timeseries(params.from, params.to),
    queryFn: () => usageMeService.getMyTimeseries(params),
  });

/** 본인 Run 목록 */
export const useMyRuns = (params: MyRunsParams = {}) =>
  useQuery({
    queryKey: queryKeys.usageMe.runs(params),
    queryFn: () => usageMeService.getMyRuns(params),
  });
