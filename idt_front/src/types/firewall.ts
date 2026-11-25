// firewall-admin-console Design §4.2 — 관리자 방화벽 API 계약
// (백엔드 idt/src/interfaces/schemas/firewall_admin.py 와 1:1).
import type { ApprovalStatus } from '@/types/approval';

export interface FirewallFwctlStatus {
  configured: boolean;
  reachable: boolean;
  dry_run: boolean | null;
  max_ttl_seconds: number | null;
  ipset_exists: boolean | null;
  version: string | null;
}

export interface FirewallGrafanaStatus {
  configured: boolean;
  dashboard_url: string | null;
}

export interface FirewallStatusResponse {
  enabled: true;
  fwctl: FirewallFwctlStatus;
  grafana: FirewallGrafanaStatus;
  default_ttl_seconds: number;
}

/** 백엔드 모듈이 꺼져 있을 때(status 404) 훅이 돌려주는 값 */
export interface FirewallDisabledStatus {
  enabled: false;
}

export type FirewallStatus = FirewallStatusResponse | FirewallDisabledStatus;

export interface FirewallBlockEntry {
  ip: string;
  ttl_remaining_seconds: number;
  packets: number;
  bytes: number;
}

export interface FirewallBlockListResponse {
  items: FirewallBlockEntry[];
  count: number;
  dry_run: boolean;
}

/** actor 는 서버가 채운다. 보내면 422 다. */
export interface FirewallBlockRequest {
  ip: string;
  ttl_seconds?: number;
  reason: string;
}

export interface FirewallBlockResponse {
  ip: string;
  ttl_seconds: number;
  expires_at: string;
  reason: string;
  dry_run: boolean;
  request_id: string;
}

export interface FirewallUnblockResponse {
  ip: string;
  removed: boolean;
  dry_run: boolean | null;
  already_absent: boolean;
  request_id: string;
}

/** module-4 탐지 탭이 차단 폼에 넘기는 초안. nonce 가 바뀔 때마다 폼에 반영한다. */
export interface FirewallBlockDraft {
  ip: string;
  reason: string;
  nonce: number;
}

export const FIREWALL_DISABLED_STATUS: FirewallDisabledStatus = { enabled: false };

export const FIREWALL_TABS = ['blocks', 'detection', 'audit', 'approvals'] as const;
export type FirewallTab = (typeof FIREWALL_TABS)[number];

export const FIREWALL_TAB_LABELS: Record<FirewallTab, string> = {
  blocks: '현황',
  detection: '탐지',
  audit: '감사',
  approvals: '승인',
};

export const FIREWALL_REASON_MAX_CHARS = 500;

/** 폴링 주기(ms) — Design §10.4 */
export const FIREWALL_STATUS_REFETCH_MS = 30_000;
export const FIREWALL_BLOCKS_REFETCH_MS = 10_000;

/** 오류 코드별 화면 문구 — Design §6.1. 없는 코드는 서버 메시지를 쓴다. */
export const FIREWALL_ERROR_MESSAGES: Record<string, string> = {
  AUTOMATION_NOT_CONFIGURED: '자동 점검 대상이 설정되지 않았습니다.',
  INVALID_IP: 'IPv4 주소 한 개를 입력하세요.',
  INVALID_REASON: '사유를 1~500자로 입력하세요.',
  FORBIDDEN_WHITELIST: '보호 대상 주소라 차단할 수 없습니다.',
  FWCTL_AUTH_FAILED: 'fwctl 인증에 실패했습니다. 서버 설정을 확인하세요.',
  FWCTL_AUDIT_ERROR:
    '차단은 적용됐지만 감사 기록에 실패했습니다. 운영자에게 알려 주세요.',
  FWCTL_UNAVAILABLE: 'fwctl에 연결할 수 없습니다.',
  FWCTL_TIMEOUT: 'fwctl 응답이 지연되고 있습니다.',
  // 탐지·감사 탭이 함께 쓰므로 탭 이름을 넣지 않는다
  GRAFANA_UNAVAILABLE: 'Grafana에서 정보를 가져올 수 없습니다. Grafana가 실행 중인지 확인하세요.',
  INVALID_FILTER: '조회 조건이 올바르지 않습니다.',
  INVALID_REQUEST: '요청 형식이 올바르지 않습니다.',
};

/** IPv4 단일 주소 (앞자리 0 불가). 차단 폼·감사 필터가 같이 쓴다 — 서버가 다시 검증한다. */
export const FIREWALL_IPV4_RE =
  /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;

// ── 탐지·감사·승인 탭 (Design §4.2 alerts/events/audit) ─────────────

export type FirewallAlertState = 'firing' | 'pending' | 'normal' | 'nodata' | 'error';

export interface FirewallAlertInstance {
  src_ip: string | null;
  state: FirewallAlertState;
  active_at: string | null;
  value: string | null;
}

export interface FirewallAlertRule {
  uid: string;
  name: string;
  rule_id: string;
  kind: string;
  severity: string;
  /** block | report | extend — report 는 차단 대상이 아니다 */
  action_hint: string;
  state: FirewallAlertState;
  description: string;
  last_evaluation: string | null;
  instances: FirewallAlertInstance[];
}

export interface FirewallAlertsResponse {
  rules: FirewallAlertRule[];
  firing_count: number;
  fetched_at: string;
}

export const FIREWALL_EVENT_RANGES = ['15m', '1h', '6h', '24h'] as const;
export type FirewallEventRange = (typeof FIREWALL_EVENT_RANGES)[number];

export const FIREWALL_EVENT_ACTIONS = ['all', 'drop', 'block'] as const;
export type FirewallEventAction = (typeof FIREWALL_EVENT_ACTIONS)[number];

export interface FirewallEventsParams {
  range: FirewallEventRange;
  action: FirewallEventAction;
}

export interface FirewallSourceCount {
  src_ip: string;
  count: number;
}

export interface FirewallEvent {
  ts: string;
  action: string;
  src_ip: string | null;
  dest_ip: string | null;
  protocol: number | null;
  dport: number | null;
}

export interface FirewallEventsResponse {
  range: string;
  action: string;
  top_sources: FirewallSourceCount[];
  recent: FirewallEvent[];
  fetched_at: string;
}

export const FIREWALL_AUDIT_RANGES = ['1h', '6h', '24h', '7d'] as const;
export type FirewallAuditRange = (typeof FIREWALL_AUDIT_RANGES)[number];

export const FIREWALL_AUDIT_EVENTS = ['all', 'block', 'unblock'] as const;
export type FirewallAuditEvent = (typeof FIREWALL_AUDIT_EVENTS)[number];

export interface FirewallAuditParams {
  range: FirewallAuditRange;
  event: FirewallAuditEvent;
  ip?: string;
  actor?: string;
}

export interface FirewallAuditRecord {
  ts: string;
  request_id: string | null;
  event: string | null;
  actor: string | null;
  ip: string | null;
  ttl_seconds: number | null;
  reason: string | null;
  result: string | null;
  status: number | null;
  error_code: string | null;
  dry_run: boolean | null;
}

export interface FirewallAuditResponse {
  range: string;
  items: FirewallAuditRecord[];
  count: number;
  fetched_at: string;
}

export const FIREWALL_RANGE_LABELS: Record<FirewallEventRange | FirewallAuditRange, string> = {
  '15m': '15분',
  '1h': '1시간',
  '6h': '6시간',
  '24h': '24시간',
  '7d': '7일',
};

export const FIREWALL_EVENT_ACTION_LABELS: Record<FirewallEventAction, string> = {
  all: '전체',
  drop: '정책 차단',
  block: '차단 목록',
};

export const FIREWALL_AUDIT_EVENT_LABELS: Record<FirewallAuditEvent, string> = {
  all: '전체',
  block: '차단',
  unblock: '해제',
};

export const FIREWALL_ALERT_STATE_LABELS: Record<FirewallAlertState, string> = {
  firing: '발화',
  pending: '대기',
  normal: '정상',
  nodata: '데이터 없음',
  error: '오류',
};

export const FIREWALL_ACTION_HINT_LABELS: Record<string, string> = {
  block: '차단',
  report: '보고',
  extend: '연장',
};

export const FIREWALL_PROTOCOL_LABELS: Record<number, string> = {
  1: 'ICMP',
  6: 'TCP',
  17: 'UDP',
};

/** 탐지·로그 폴링 주기(ms) — Design §10.4 */
export const FIREWALL_OBSERVABILITY_REFETCH_MS = 30_000;

/** 승인 탭이 보여 주는 도구 — tool_id 의 마지막 구분(':' 뒤)이 이 이름인 건 (Design §5.4) */
export const FIREWALL_APPROVAL_TOOL_SUFFIXES = ['block_ip', 'unblock_ip'] as const;

/** 승인 탭이 보는 상태 — 사람의 결정을 기다리는 건만 */
export const FIREWALL_APPROVAL_STATUSES: ApprovalStatus[] = ['pending'];

/** 승인 탭이 한 번에 가져오는 건수 (백엔드 상한 100) */
export const FIREWALL_APPROVAL_FETCH_SIZE = 100;

/** fwctl 감사의 수행자 접두 — 관리자 화면 / MCP 서버(에이전트) */
export const FIREWALL_ACTOR_ADMIN_PREFIX = 'sangplusbot/admin:';
export const FIREWALL_ACTOR_AGENT_PREFIX = 'mcp-firewall-server';
/** 관리자 화면 요청 ID 형식 adm-<user_id>-<난수> — 해제는 actor 가 없어 여기서 사용자를 읽는다 */
export const FIREWALL_ADMIN_REQUEST_ID_RE = /^adm-(\d+)-/;


// ── 자동 점검 (firewall-agent design §4.4·§5.1) ──────────────────────────

export interface FirewallAutomationRun {
  status: string;
  skip_reason: string | null;
  started_at: string;
}

export interface FirewallAutomationSchedule {
  id: string;
  name: string;
  enabled: boolean;
  cron_expr: string | null;
  skip_when_busy: boolean;
  next_run_at: string | null;
  last_run: FirewallAutomationRun | null;
}

export interface FirewallAutomationAlert {
  configured: boolean;
  enabled: boolean | null;
  skip_when_busy: boolean | null;
  last_result: string | null;
  last_received_at: string | null;
}

export interface FirewallAutomationResponse {
  configured: boolean;
  reason: 'AGENT_NOT_SET' | 'AGENT_NOT_FOUND' | null;
  agent: { id: string; name: string } | null;
  schedules: FirewallAutomationSchedule[];
  alert_receiver: FirewallAutomationAlert | null;
}

export interface FirewallAutomationUpdate {
  schedule_enabled?: boolean;
  alert_enabled?: boolean;
}

export const FIREWALL_AUTOMATION_REFETCH_MS = 30_000;

/** 스케줄 회차 상태·알림 수신 결과 → 화면 문구 */
export const FIREWALL_AUTOMATION_RESULT_LABEL: Record<string, string> = {
  running: '실행 중',
  success: '성공',
  failed: '실패',
  skipped: '건너뜀',
  enqueued: '실행',
  duplicate: '중복 무시',
  resolved_only: '해소 알림',
  disabled: '꺼짐',
  skipped_busy: '건너뜀',
  invalid_payload: '형식 오류',
};
