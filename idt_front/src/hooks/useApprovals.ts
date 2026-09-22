import { useMutation, useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { approvalService } from '@/services/approvalService';
import type { ApprovalListParams } from '@/services/approvalService';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import {
  APPROVAL_ERROR_MESSAGES,
  type ApprovalDecisionResponse,
  type ApprovalGateConfig,
  type ApprovalGateSettings,
  type ApprovalListResponse,
} from '@/types/approval';

// approval-gate: 승인 대기 조회·결정 훅 (Design §4, §5)

/** 백엔드 detail 은 {code, message} 객체다 (Design §6.1). */
const errorPayload = (
  e: unknown,
): { code?: string; message?: string } | undefined => {
  if (!(e instanceof AxiosError)) return undefined;
  const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
  return detail && typeof detail === 'object'
    ? (detail as { code?: string; message?: string })
    : undefined;
};

export const extractApprovalErrorCode = (e: unknown): string | undefined =>
  errorPayload(e)?.code;

/**
 * 화면 문구. 알려진 코드는 사용자 언어로, 모르는 코드는 서버 메시지를 쓴다.
 * 코드→문구 매핑을 types/approval.ts 에 두는 이유: 컴포넌트마다 다른 문구를
 * 쓰면 같은 오류가 화면마다 달라 보인다.
 */
export const extractApprovalError = (e: unknown): string => {
  const payload = errorPayload(e);
  if (payload?.code && APPROVAL_ERROR_MESSAGES[payload.code]) {
    return APPROVAL_ERROR_MESSAGES[payload.code];
  }
  if (payload?.message) return payload.message;
  return e instanceof Error ? e.message : '요청에 실패했습니다.';
};

/** 이미 처리된 건 — 중복 클릭의 정상 응답이다. 목록만 새로고침하면 된다. */
export const isApprovalConflict = (e: unknown): boolean =>
  e instanceof AxiosError && e.response?.status === 409;

export const invalidateApprovals = () =>
  queryClient.invalidateQueries({ queryKey: queryKeys.approvals.all });

/** 벨 배지는 jobs 쪽 unseen-count 가 승인 건수를 합산하므로 함께 무효화한다. */
export const invalidateApprovalBadges = () => {
  void invalidateApprovals();
  void queryClient.invalidateQueries({
    queryKey: queryKeys.backgroundJobs.unseenCount(),
  });
};

export const useApprovals = (params: ApprovalListParams = {}) =>
  useQuery<ApprovalListResponse>({
    queryKey: queryKeys.approvals.list({
      statuses: params.statuses,
      page: params.page,
      size: params.size,
    }),
    queryFn: () => approvalService.list(params).then((r) => r.data),
  });

export const useApprovalDetail = (approvalId: string | null) =>
  useQuery({
    queryKey: queryKeys.approvals.detail(approvalId ?? ''),
    queryFn: () => approvalService.detail(approvalId!).then((r) => r.data),
    enabled: Boolean(approvalId),
  });

export const useApproveApproval = () =>
  useMutation<
    ApprovalDecisionResponse,
    unknown,
    { approvalId: string; executeOnly?: boolean }
  >({
    mutationFn: ({ approvalId, executeOnly }) =>
      approvalService.approve(approvalId, executeOnly).then((r) => r.data),
    // 성공·실패 모두 무효화한다: 409(이미 처리됨)는 목록이 낡았다는 뜻이라
    // 새로고침이 곧 해결이다.
    onSettled: invalidateApprovalBadges,
  });

export const useRejectApproval = () =>
  useMutation<
    ApprovalDecisionResponse,
    unknown,
    { approvalId: string; reason: string }
  >({
    mutationFn: ({ approvalId, reason }) =>
      approvalService.reject(approvalId, { reason }).then((r) => r.data),
    onSettled: invalidateApprovalBadges,
  });

export const useMarkApprovalSeen = () =>
  useMutation<void, unknown, string>({
    mutationFn: (approvalId) =>
      approvalService.markSeen(approvalId).then(() => undefined),
    onSettled: invalidateApprovalBadges,
  });

/** 에이전트별 게이트 설정 조회 (Check G3). agentId 가 없으면(생성 모드) 비활성. */
export const useApprovalGateSettings = (agentId: string | null | undefined) =>
  useQuery<ApprovalGateSettings>({
    queryKey: queryKeys.approvals.gateSettings(agentId ?? ''),
    queryFn: () => approvalService.getGateSettings(agentId!).then((r) => r.data),
    enabled: Boolean(agentId),
  });

export const useSaveApprovalGateSettings = (agentId: string) =>
  useMutation<ApprovalGateSettings, unknown, ApprovalGateConfig>({
    mutationFn: (config) =>
      approvalService.saveGateSettings(agentId, config).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.approvals.gateSettings(agentId), data);
    },
  });
