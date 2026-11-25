import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { ApiError } from '@/services/api/ApiError';
import { alertReceiverService } from '@/services/alertReceiverService';
import type { UpsertAlertReceiverRequest } from '@/types/alertReceiver';

// firewall-agent design §5.2 — 빌더 설정 탭 "알림 수신". 토큰 평문은 캐시에 넣지 않는다
// (호출측 로컬 상태로만 1회 표시 — WebhookSection 과 같은 규칙).

export const alertReceiverErrorMessage = (e: unknown): string => {
  if (e instanceof ApiError && e.message) return e.message;
  return e instanceof Error && e.message ? e.message : '요청에 실패했습니다.';
};

export const useAlertReceiver = (agentId: string | null) =>
  useQuery({
    queryKey: queryKeys.agentAlertReceiver.config(agentId ?? ''),
    queryFn: () => alertReceiverService.get(agentId!),
    enabled: !!agentId,
  });

export const useAlertReceipts = (agentId: string | null, options: { enabled?: boolean } = {}) =>
  useQuery({
    queryKey: queryKeys.agentAlertReceiver.receipts(agentId ?? ''),
    queryFn: () => alertReceiverService.receipts(agentId!),
    enabled: !!agentId && (options.enabled ?? true),
    staleTime: 0,
  });

const useConfigWriter = <V,>(
  mutationFn: (vars: V & { agentId: string }) => ReturnType<typeof alertReceiverService.rotate>,
) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (data, vars) => {
      // config 만 캐시에 넣는다 — token 평문은 넣지 않는다
      queryClient.setQueryData(queryKeys.agentAlertReceiver.config(vars.agentId), data.config);
    },
  });
};

export const useUpsertAlertReceiver = () =>
  useConfigWriter<{ data: UpsertAlertReceiverRequest }>(({ agentId, data }) =>
    alertReceiverService.upsert(agentId, data),
  );

export const useRotateAlertToken = () =>
  useConfigWriter<object>(({ agentId }) => alertReceiverService.rotate(agentId));
