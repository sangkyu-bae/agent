/**
 * 운영 대시보드 service (admin-dashboard).
 * /api/v1/admin/dashboard/* HTTP 호출 — 기간 지표는 agentRunAdminService 재사용.
 */
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  DashboardStats,
  KbBreakdownResponse,
  RecentDocumentsResponse,
  StorageHealthResponse,
} from '@/types/adminDashboard';

export const adminDashboardService = {
  /** KB/문서/청크/사용자 누적 현황 (기간 무관) */
  getStats: () =>
    authApiClient
      .get<DashboardStats>(API_ENDPOINTS.ADMIN_DASHBOARD_STATS)
      .then((r) => r.data),

  /** KB별 문서/청크 현황 — 문서 0건 KB 포함 */
  getKbBreakdown: () =>
    authApiClient
      .get<KbBreakdownResponse>(API_ENDPOINTS.ADMIN_DASHBOARD_KB_BREAKDOWN)
      .then((r) => r.data),

  /** 최근 적재 문서 */
  getRecentDocuments: (limit = 10) =>
    authApiClient
      .get<RecentDocumentsResponse>(
        API_ENDPOINTS.ADMIN_DASHBOARD_RECENT_DOCUMENTS,
        { params: { limit } },
      )
      .then((r) => r.data),

  /** 저장소 헬스 (MySQL/Qdrant/ES) — 부분 실패 포함 200 */
  getHealth: () =>
    authApiClient
      .get<StorageHealthResponse>(API_ENDPOINTS.ADMIN_DASHBOARD_HEALTH)
      .then((r) => r.data),
};
