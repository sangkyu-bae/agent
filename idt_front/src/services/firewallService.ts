import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  FirewallAlertsResponse,
  FirewallAuditParams,
  FirewallAuditResponse,
  FirewallBlockListResponse,
  FirewallBlockRequest,
  FirewallBlockResponse,
  FirewallEventsParams,
  FirewallEventsResponse,
  FirewallStatusResponse,
  FirewallUnblockResponse,
} from '@/types/firewall';

// firewall-admin-console §4 — 브라우저는 idt API 만 호출한다. fwctl·Grafana 토큰은 서버에만 있다.
export const firewallService = {
  getStatus: () =>
    authApiClient
      .get<FirewallStatusResponse>(API_ENDPOINTS.ADMIN_FIREWALL_STATUS)
      .then((r) => r.data),
  listBlocks: () =>
    authApiClient
      .get<FirewallBlockListResponse>(API_ENDPOINTS.ADMIN_FIREWALL_BLOCKS)
      .then((r) => r.data),
  block: (body: FirewallBlockRequest) =>
    authApiClient
      .post<FirewallBlockResponse>(API_ENDPOINTS.ADMIN_FIREWALL_BLOCKS, body)
      .then((r) => r.data),
  unblock: (ip: string) =>
    authApiClient
      .delete<FirewallUnblockResponse>(API_ENDPOINTS.ADMIN_FIREWALL_BLOCK_DETAIL(ip))
      .then((r) => r.data),

  // 조회 조건은 허용 값만 보낸다. LogQL 은 서버가 만든다 (Design §4.5).
  getAlerts: () =>
    authApiClient
      .get<FirewallAlertsResponse>(API_ENDPOINTS.ADMIN_FIREWALL_ALERTS)
      .then((r) => r.data),
  getEvents: (params: FirewallEventsParams) =>
    authApiClient
      .get<FirewallEventsResponse>(API_ENDPOINTS.ADMIN_FIREWALL_EVENTS, { params })
      .then((r) => r.data),
  getAudit: (params: FirewallAuditParams) =>
    authApiClient
      .get<FirewallAuditResponse>(API_ENDPOINTS.ADMIN_FIREWALL_AUDIT, {
        params: {
          range: params.range,
          event: params.event,
          // 빈 필터는 키 자체를 보내지 않는다
          ...(params.ip ? { ip: params.ip } : {}),
          ...(params.actor ? { actor: params.actor } : {}),
        },
      })
      .then((r) => r.data),
};
