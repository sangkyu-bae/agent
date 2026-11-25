// firewall-agent design §4.1 — 에이전트 알림(Alertmanager 웹훅) 수신 설정

export interface AlertReceiverConfig {
  configured: boolean;
  enabled: boolean | null;
  skip_when_busy: boolean | null;
  instruction_prefix: string | null;
  token_hint: string | null;
  inbound_path: string | null;
  updated_at: string | null;
}

/** 보낸 필드만 바꾼다. 최초 생성 시 기본값: 꺼짐·바쁘면 건너뜀·앞머리 없음 */
export interface UpsertAlertReceiverRequest {
  enabled?: boolean;
  skip_when_busy?: boolean;
  instruction_prefix?: string;
}

export interface UpsertAlertReceiverResponse {
  config: AlertReceiverConfig;
  /** 최초 생성·재발급 응답에서만 평문 1회 */
  token: string | null;
}

export interface AlertReceipt {
  id: string;
  result: string;
  skip_reason: string | null;
  firing_count: number;
  job_id: string | null;
  received_at: string;
}

export const ALERT_INSTRUCTION_PREFIX_MAX = 300;
export const ALERT_RECEIPTS_SHOWN = 5;

export const ALERT_RECEIPT_RESULT_LABEL: Record<string, string> = {
  enqueued: '실행',
  duplicate: '중복 무시',
  resolved_only: '해소 알림',
  disabled: '꺼짐',
  skipped_busy: '건너뜀',
  invalid_payload: '형식 오류',
};
