import { useMutation, useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { agentWebhookService } from '@/services/agentWebhookService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type {
  UpdateWebhookRequest,
  WebhookConfig,
  WebhookDelivery,
  WebhookSecretIssue,
} from '@/types/agentWebhook';

// agent-webhook: 웹훅 설정 조회 + 활성화/재발급/토글/해제 훅.
// enable/rotate 응답의 secret 평문은 캐시에 넣지 않는다 — 호출측 로컬 상태(모달)로만 소비.

export const extractWebhookError = (e: unknown): string => {
  if (e instanceof AxiosError) {
    const detail = (e.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === 'string') return detail;
  }
  return e instanceof Error ? e.message : '요청에 실패했습니다.';
};

const invalidateConfig = (agentId: string) =>
  queryClient.invalidateQueries({
    queryKey: queryKeys.agentWebhook.config(agentId),
  });

export const useAgentWebhook = (agentId: string | null) =>
  useQuery<WebhookConfig>({
    queryKey: queryKeys.agentWebhook.config(agentId ?? ''),
    queryFn: () => agentWebhookService.get(agentId!).then((r) => r.data),
    enabled: !!agentId,
  });

export const useEnableWebhook = () =>
  useMutation<WebhookSecretIssue, Error, { agentId: string }>({
    mutationFn: ({ agentId }) =>
      agentWebhookService.enable(agentId).then((r) => r.data),
    onSuccess: (_data, { agentId }) => invalidateConfig(agentId),
  });

export const useRotateWebhookSecret = () =>
  useMutation<WebhookSecretIssue, Error, { agentId: string }>({
    mutationFn: ({ agentId }) =>
      agentWebhookService.rotate(agentId).then((r) => r.data),
    onSuccess: (_data, { agentId }) => invalidateConfig(agentId),
  });

export const useUpdateWebhook = () =>
  useMutation<
    WebhookConfig,
    Error,
    { agentId: string; data: UpdateWebhookRequest }
  >({
    mutationFn: ({ agentId, data }) =>
      agentWebhookService.update(agentId, data).then((r) => r.data),
    onSuccess: (_data, { agentId }) => invalidateConfig(agentId),
  });

export const useDeleteWebhook = () =>
  useMutation<void, Error, { agentId: string }>({
    mutationFn: ({ agentId }) =>
      agentWebhookService.remove(agentId).then(() => undefined),
    onSuccess: (_data, { agentId }) => invalidateConfig(agentId),
  });

/** outbound 발송 이력 — 펼침 시에만 조회 (M2 D21, useScheduleRuns 선례) */
export const useWebhookDeliveries = (
  agentId: string | null,
  opts: { enabled: boolean },
) =>
  useQuery<WebhookDelivery[]>({
    queryKey: queryKeys.agentWebhook.deliveries(agentId ?? ''),
    queryFn: () =>
      agentWebhookService.listDeliveries(agentId!).then((r) => r.data),
    enabled: opts.enabled && !!agentId,
  });
