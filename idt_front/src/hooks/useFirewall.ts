import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { approvalService } from '@/services/approvalService';
import type { ApprovalListResponse } from '@/types/approval';
import { firewallService } from '@/services/firewallService';
import { ApiError } from '@/services/api/ApiError';
import {
  FIREWALL_APPROVAL_FETCH_SIZE,
  FIREWALL_APPROVAL_STATUSES,
  FIREWALL_APPROVAL_TOOL_SUFFIXES,
  FIREWALL_BLOCKS_REFETCH_MS,
  FIREWALL_DISABLED_STATUS,
  FIREWALL_ERROR_MESSAGES,
  FIREWALL_OBSERVABILITY_REFETCH_MS,
  FIREWALL_STATUS_REFETCH_MS,
  type FirewallAuditParams,
  type FirewallBlockRequest,
  type FirewallEventsParams,
  type FirewallStatus,
} from '@/types/firewall';

// firewall-admin-console §10.4 — 서버 상태는 TanStack Query 폴링 (status 30초, blocks 10초).

/**
 * 모듈 상태. 백엔드에서 꺼져 있으면 라우터가 없어 404 가 오므로 `{ enabled: false }` 로 바꾼다.
 * 그 밖의 오류(권한·네트워크)는 그대로 error 로 둔다.
 */
export const useFirewallStatus = (
  options: {
    enabled?: boolean;
    /**
     * 주기 갱신 여부(기본 true). 메뉴처럼 모든 화면에 떠 있는 소비처는 false 로 둔다 —
     * 방화벽 페이지 밖에서도 30초마다 fwctl 상태를 묻게 되기 때문이다 (Check G5).
     */
    poll?: boolean;
  } = {},
) =>
  useQuery<FirewallStatus>({
    queryKey: queryKeys.admin.firewallStatus(),
    queryFn: async () => {
      try {
        return await firewallService.getStatus();
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return FIREWALL_DISABLED_STATUS;
        throw err;
      }
    },
    enabled: options.enabled ?? true,
    retry: false,
    staleTime: FIREWALL_STATUS_REFETCH_MS,
    // 꺼져 있으면 다시 묻지 않는다. 켜져 있을 때만 모드·연결 상태를 주기적으로 갱신한다.
    refetchInterval:
      options.poll === false
        ? false
        : (query) => (query.state.data?.enabled ? FIREWALL_STATUS_REFETCH_MS : false),
  });

export const useFirewallBlocks = (options: { enabled?: boolean } = {}) =>
  useQuery({
    queryKey: queryKeys.admin.firewallBlocks(),
    queryFn: firewallService.listBlocks,
    enabled: options.enabled ?? true,
    retry: false,
    refetchInterval: FIREWALL_BLOCKS_REFETCH_MS,
  });

export const useBlockIp = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: FirewallBlockRequest) => firewallService.block(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.firewallBlocks() });
    },
  });
};

export const useUnblockIp = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ip: string) => firewallService.unblock(ip),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.firewallBlocks() });
    },
  });
};

// ── 관측 (Grafana 경유) — 실패해도 현황 탭은 영향받지 않는다 (Plan SC-8) ──

export const useFirewallAlerts = (options: { enabled?: boolean } = {}) =>
  useQuery({
    queryKey: queryKeys.admin.firewallAlerts(),
    queryFn: firewallService.getAlerts,
    enabled: options.enabled ?? true,
    retry: false,
    refetchInterval: FIREWALL_OBSERVABILITY_REFETCH_MS,
  });

export const useFirewallEvents = (
  params: FirewallEventsParams,
  options: { enabled?: boolean } = {},
) =>
  useQuery({
    queryKey: queryKeys.admin.firewallEvents(params),
    queryFn: () => firewallService.getEvents(params),
    enabled: options.enabled ?? true,
    retry: false,
    refetchInterval: FIREWALL_OBSERVABILITY_REFETCH_MS,
  });

/** 감사 이력은 폴링하지 않는다. 필터를 바꾸거나 새로고침을 누를 때 조회한다. */
export const useFirewallAudit = (
  params: FirewallAuditParams,
  options: { enabled?: boolean } = {},
) =>
  useQuery({
    queryKey: queryKeys.admin.firewallAudit(params),
    queryFn: () => firewallService.getAudit(params),
    enabled: options.enabled ?? true,
    retry: false,
    // 감사 이력은 캐시된 값을 보여 주지 않는다 — 조건을 바꾸거나 탭에 들어올 때마다 새로 조회한다.
    staleTime: 0,
  });

/** tool_id(`mcp:{server}:{tool}`)의 도구 이름 부분 */
export const firewallToolName = (toolId: string): string => toolId.split(':').pop() ?? toolId;

/**
 * 승인 대기 건 중 방화벽 도구(block_ip·unblock_ip) 요청만.
 * 승인 API 는 고치지 않고 프론트에서 거른다 (Design §5.4). 목록은 "내가 소유한 에이전트" 범위다.
 * 페이지(탭 배지)와 승인 탭이 같은 쿼리를 공유한다.
 */
export const useFirewallApprovals = (options: { enabled?: boolean } = {}) => {
  const params = {
    statuses: FIREWALL_APPROVAL_STATUSES,
    page: 1,
    size: FIREWALL_APPROVAL_FETCH_SIZE,
  };
  // useApprovals 와 같은 키를 쓴다 — 승인·거절 후 approvals 전체 무효화에 함께 갱신된다.
  const query = useQuery<ApprovalListResponse>({
    queryKey: queryKeys.approvals.list(params),
    queryFn: () => approvalService.list(params).then((r) => r.data),
    enabled: options.enabled ?? true,
    retry: false,
    // 승인 대기는 캐시된 값을 믿지 않는다. 다른 화면·다른 사람이 처리했을 수 있고,
    // 승인 직후 갱신이 실패하면(백엔드가 에이전트 재개로 바쁠 때) 예전 값이 남는다.
    staleTime: 0,
    refetchInterval: FIREWALL_OBSERVABILITY_REFETCH_MS,
  });
  const items = useMemo(
    () =>
      (query.data?.data ?? []).filter((a) =>
        (FIREWALL_APPROVAL_TOOL_SUFFIXES as readonly string[]).includes(firewallToolName(a.tool_id)),
      ),
    [query.data],
  );
  // 한 번에 가져온 건수보다 대기 건이 많으면 일부만 본 것이다 — 화면에 알린다.
  const truncated = (query.data?.pagination.total ?? 0) > (query.data?.data.length ?? 0);
  return { ...query, items, truncated };
};

/** 오류 → 화면 문구. 코드별 문구가 있으면 그것을, 없으면 서버 메시지를 쓴다. */
export const firewallErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof ApiError) {
    if (err.code && FIREWALL_ERROR_MESSAGES[err.code]) return FIREWALL_ERROR_MESSAGES[err.code];
    if (err.message) return err.message;
  }
  return fallback;
};
