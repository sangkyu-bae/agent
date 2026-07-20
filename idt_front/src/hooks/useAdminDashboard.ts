/**
 * 운영 대시보드 hooks (admin-dashboard).
 * 수동 새로고침 정책(D7) — refetchInterval 없음, invalidate로만 갱신.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { adminDashboardService } from '@/services/adminDashboardService';
import { queryKeys } from '@/lib/queryKeys';

/** 적재/사용자 누적 현황 (기간 무관) */
export const useDashboardStats = () =>
  useQuery({
    queryKey: queryKeys.adminDashboard.stats(),
    queryFn: () => adminDashboardService.getStats(),
  });

/** KB별 현황 테이블 */
export const useKbBreakdown = () =>
  useQuery({
    queryKey: queryKeys.adminDashboard.kbBreakdown(),
    queryFn: () => adminDashboardService.getKbBreakdown(),
  });

/** 최근 적재 문서 */
export const useRecentDocuments = (limit = 10) =>
  useQuery({
    queryKey: queryKeys.adminDashboard.recentDocuments(limit),
    queryFn: () => adminDashboardService.getRecentDocuments(limit),
  });

/** 저장소 헬스 */
export const useStorageHealth = () =>
  useQuery({
    queryKey: queryKeys.adminDashboard.health(),
    queryFn: () => adminDashboardService.getHealth(),
  });

/** 새로고침 — 대시보드 도메인 + 기간 지표(agentRunAdmin) 전체 invalidate */
export const useDashboardRefresh = () => {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({
      queryKey: queryKeys.adminDashboard.all,
    });
    queryClient.invalidateQueries({
      queryKey: queryKeys.agentRunAdmin.all,
    });
  };
};
