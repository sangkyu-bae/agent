import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { marketAnalysisService } from '@/services/marketAnalysisService';
import { ApiError } from '@/services/api/ApiError';
import {
  INDEX_CHART_STALE_MS,
  MARKET_ANALYSIS_PAGE_SIZE,
  MARKET_ANALYSIS_ROUNDS_REFETCH_MS,
  type MarketAnalysisAccessResponse,
  type MarketAnalysisSettingsUpdate,
  type PrinciplePatchRequest,
} from '@/types/marketAnalysis';

// stock-analysis-agents §9 — 서버 상태는 TanStack Query. 쓰기 뒤에는 관련 조회를 무효화한다.

const NO_ACCESS: MarketAnalysisAccessResponse = {
  enabled: false,
  can_view: false,
  can_manage: false,
};

/**
 * 메뉴·페이지 진입 판단. 백엔드 모듈이 꺼져 있으면 라우터가 없어 404 → 권한 없음과 같게 본다.
 * 사이드바처럼 모든 화면에 떠 있는 소비처가 쓰므로 주기 갱신하지 않는다.
 */
export const useMarketAnalysisAccess = (options: { enabled?: boolean } = {}) =>
  useQuery<MarketAnalysisAccessResponse>({
    queryKey: queryKeys.marketAnalysis.access(),
    queryFn: async () => {
      try {
        return await marketAnalysisService.getAccess();
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return NO_ACCESS;
        throw err;
      }
    },
    enabled: options.enabled ?? true,
    retry: false,
    staleTime: 5 * 60_000,
  });

export const useMarketDashboard = (enabled = true) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.dashboard(),
    queryFn: marketAnalysisService.getDashboard,
    enabled,
    retry: false,
  });

/**
 * 올해 KOSPI·KOSDAQ 등락률 (market-index-ytd-chart §5.3).
 * 대시보드와 따로 불러 첫 조회의 연초 적재가 대시보드를 막지 않게 한다.
 * 백엔드 장중 봉 캐시(5분)와 같은 주기로 다시 묻는다.
 */
export const useIndexChart = (enabled = true) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.indexChart(),
    queryFn: marketAnalysisService.getIndexChart,
    enabled,
    retry: false,
    staleTime: INDEX_CHART_STALE_MS,
  });

export const useMarketPositions = (status: 'open' | 'closed', page: number) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.positions({ status, page }),
    queryFn: () =>
      marketAnalysisService.listPositions({ status, page, size: MARKET_ANALYSIS_PAGE_SIZE }),
    placeholderData: keepPreviousData,
    retry: false,
  });

export const useMarketPosition = (id: number | null) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.position(id ?? 0),
    queryFn: () => marketAnalysisService.getPosition(id as number),
    enabled: id !== null,
    retry: false,
  });

export const useMarketWatchlist = (page: number) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.decisions({ kind: 'buy', decision: 'skip', page }),
    queryFn: () =>
      marketAnalysisService.listDecisions({
        kind: 'buy',
        decision: 'skip',
        page,
        size: MARKET_ANALYSIS_PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
    retry: false,
  });

export const useMarketReports = (params: { symbol?: string; date?: string; page: number }) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.reports(params),
    queryFn: () =>
      marketAnalysisService.listReports({ ...params, size: MARKET_ANALYSIS_PAGE_SIZE }),
    placeholderData: keepPreviousData,
    retry: false,
  });

export const useMarketReport = (id: number | null) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.report(id ?? 0),
    queryFn: () => marketAnalysisService.getReport(id as number),
    enabled: id !== null,
    retry: false,
  });

export const useMarketInsights = () =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.insights(),
    queryFn: marketAnalysisService.getInsights,
    retry: false,
  });

export const usePatchPrinciple = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: PrinciplePatchRequest }) =>
      marketAnalysisService.patchPrinciple(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.marketAnalysis.insights() });
    },
  });
};

/** 실행 중인 회차가 있으면 목록을 주기 갱신한다 */
export const useMarketRounds = (page: number) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.rounds(page),
    queryFn: () =>
      marketAnalysisService.listRounds({ page, size: MARKET_ANALYSIS_PAGE_SIZE }),
    placeholderData: keepPreviousData,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => r.status === 'running')
        ? MARKET_ANALYSIS_ROUNDS_REFETCH_MS
        : false,
  });

export const useMarketRound = (id: number | null) =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.round(id ?? 0),
    queryFn: () => marketAnalysisService.getRound(id as number),
    enabled: id !== null,
    retry: false,
  });

export const useRunNow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => marketAnalysisService.runNow(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.marketAnalysis.all });
    },
  });
};

export const useMarketSettings = () =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.settings(),
    queryFn: marketAnalysisService.getSettings,
    retry: false,
  });

const useInvalidateSettings = () => {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.marketAnalysis.settings() });
    queryClient.invalidateQueries({ queryKey: queryKeys.marketAnalysis.dashboard() });
  };
};

export const useSaveSettings = () => {
  const invalidate = useInvalidateSettings();
  return useMutation({
    mutationFn: (body: MarketAnalysisSettingsUpdate) => marketAnalysisService.putSettings(body),
    onSuccess: invalidate,
  });
};

export const useSetEnabled = () => {
  const invalidate = useInvalidateSettings();
  return useMutation({
    mutationFn: (enabled: boolean) => marketAnalysisService.putEnabled(enabled),
    onSuccess: invalidate,
  });
};

export const useRoleAgents = () =>
  useQuery({
    queryKey: queryKeys.marketAnalysis.roleAgents(),
    queryFn: marketAnalysisService.getRoleAgents,
    retry: false,
  });

export const useSaveRoleAgents = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mapping: Record<string, string>) => marketAnalysisService.putRoleAgents(mapping),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.marketAnalysis.roleAgents() });
    },
  });
};

export const useBootstrapAgents = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: marketAnalysisService.bootstrapAgents,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.marketAnalysis.roleAgents() });
    },
  });
};
