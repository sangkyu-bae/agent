// agent-webhook: 백엔드 idt/src/application/agent_webhook/schemas.py 미러

/** GET /agents/{id}/webhook — 미설정 시 configured=false, 나머지 null */
export interface WebhookConfig {
  configured: boolean;
  enabled: boolean | null;
  secret_hint: string | null;
  inbound_path: string | null;
  outbound_url: string | null;
  outbound_enabled: boolean | null;
  created_at: string | null;
}

/** POST /webhook · POST /webhook/rotate — secret 평문은 이 응답 1회만 */
export interface WebhookSecretIssue {
  secret: string;
  secret_hint: string;
  enabled: boolean;
  inbound_path: string;
  created_at: string;
}

/** PATCH body — 전 필드 optional (M2 D17). outbound_url: null 명시 = 해제 */
export interface UpdateWebhookRequest {
  enabled?: boolean;
  outbound_url?: string | null;
  outbound_enabled?: boolean;
}

/** GET /webhook/deliveries 행 — outbound 발송 이력 (M2) */
export interface WebhookDelivery {
  id: string;
  trigger_source: 'schedule' | 'webhook';
  success: boolean;
  status_code: number | null;
  attempts: number;
  error: string | null;
  duration_ms: number;
  created_at: string;
}
