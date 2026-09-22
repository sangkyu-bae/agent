import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ApprovalGateConfig,
  ApprovalGateSettings,
  ApprovalDecisionResponse,
  ApprovalDetail,
  ApprovalListResponse,
  ApprovalStatus,
  RejectApprovalRequest,
} from '@/types/approval';

export interface ApprovalListParams {
  statuses?: ApprovalStatus[];
  page?: number;
  size?: number;
}

// approval-gate: 승인 대기 조회·결정 (Design §4.1)
// 컴포넌트는 axios 를 직접 부르지 않는다 — 모든 호출이 이 레이어를 거친다.
export const approvalService = {
  list: (params: ApprovalListParams = {}) =>
    authApiClient.get<ApprovalListResponse>(API_ENDPOINTS.APPROVALS, {
      params: {
        // 백엔드는 쉼표 구분 문자열을 받는다. 미지정이면 서버 기본값
        // (pending,scheduled)을 쓰도록 키 자체를 보내지 않는다.
        ...(params.statuses?.length
          ? { status: params.statuses.join(',') }
          : {}),
        page: params.page ?? 1,
        size: params.size ?? 20,
      },
    }),

  detail: (approvalId: string) =>
    authApiClient.get<ApprovalDetail>(
      API_ENDPOINTS.APPROVAL_DETAIL(approvalId),
    ),

  /**
   * 승인. executeOnly 는 에이전트 구성이 변경돼 재개가 불가할 때
   * "집행만 진행" 을 선택하는 경로다 (백엔드 FR-14).
   */
  approve: (approvalId: string, executeOnly = false) =>
    authApiClient.post<ApprovalDecisionResponse>(
      API_ENDPOINTS.APPROVAL_APPROVE(approvalId),
      undefined,
      { params: executeOnly ? { execute_only: true } : undefined },
    ),

  reject: (approvalId: string, body: RejectApprovalRequest) =>
    authApiClient.post<ApprovalDecisionResponse>(
      API_ENDPOINTS.APPROVAL_REJECT(approvalId),
      body,
    ),

  markSeen: (approvalId: string) =>
    authApiClient.post<void>(API_ENDPOINTS.APPROVAL_SEEN(approvalId)),

  /** 에이전트별 게이트 설정 (Check G3) */
  getGateSettings: (agentId: string) =>
    authApiClient.get<ApprovalGateSettings>(
      API_ENDPOINTS.AGENT_APPROVAL_GATE(agentId),
    ),

  saveGateSettings: (agentId: string, config: ApprovalGateConfig) =>
    authApiClient.put<ApprovalGateSettings>(
      API_ENDPOINTS.AGENT_APPROVAL_GATE(agentId),
      config,
    ),
};
