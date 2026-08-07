import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  UpdateWebhookRequest,
  WebhookConfig,
  WebhookDelivery,
  WebhookSecretIssue,
} from '@/types/agentWebhook';

// agent-webhook: 웹훅 채널 관리 (활성화/조회/재발급/토글/해제)
export const agentWebhookService = {
  get: (agentId: string) =>
    authApiClient.get<WebhookConfig>(API_ENDPOINTS.AGENT_WEBHOOK(agentId)),

  enable: (agentId: string) =>
    authApiClient.post<WebhookSecretIssue>(
      API_ENDPOINTS.AGENT_WEBHOOK(agentId),
    ),

  rotate: (agentId: string) =>
    authApiClient.post<WebhookSecretIssue>(
      API_ENDPOINTS.AGENT_WEBHOOK_ROTATE(agentId),
    ),

  update: (agentId: string, data: UpdateWebhookRequest) =>
    authApiClient.patch<WebhookConfig>(
      API_ENDPOINTS.AGENT_WEBHOOK(agentId),
      data,
    ),

  remove: (agentId: string) =>
    authApiClient.delete<void>(API_ENDPOINTS.AGENT_WEBHOOK(agentId)),

  listDeliveries: (agentId: string, limit = 20) =>
    authApiClient.get<WebhookDelivery[]>(
      API_ENDPOINTS.AGENT_WEBHOOK_DELIVERIES(agentId),
      { params: { limit } },
    ),
};
