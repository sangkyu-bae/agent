import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import {
  ALERT_RECEIPTS_SHOWN,
  type AlertReceipt,
  type AlertReceiverConfig,
  type UpsertAlertReceiverRequest,
  type UpsertAlertReceiverResponse,
} from '@/types/alertReceiver';

// firewall-agent design §4.1 — 알림 수신 설정 (소유자 전용). 토큰 평문은 생성·재발급 응답 1회만.
export const alertReceiverService = {
  get: (agentId: string) =>
    authApiClient
      .get<AlertReceiverConfig>(API_ENDPOINTS.AGENT_ALERT_RECEIVER(agentId))
      .then((r) => r.data),
  upsert: (agentId: string, body: UpsertAlertReceiverRequest) =>
    authApiClient
      .put<UpsertAlertReceiverResponse>(API_ENDPOINTS.AGENT_ALERT_RECEIVER(agentId), body)
      .then((r) => r.data),
  rotate: (agentId: string) =>
    authApiClient
      .post<UpsertAlertReceiverResponse>(API_ENDPOINTS.AGENT_ALERT_RECEIVER_TOKEN(agentId))
      .then((r) => r.data),
  receipts: (agentId: string) =>
    authApiClient
      .get<AlertReceipt[]>(API_ENDPOINTS.AGENT_ALERT_RECEIVER_RECEIPTS(agentId), {
        params: { limit: ALERT_RECEIPTS_SHOWN },
      })
      .then((r) => r.data),
};
