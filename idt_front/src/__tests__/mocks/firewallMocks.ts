// firewall-admin-console — 테스트 응답 모음. Design §4.2 예시 JSON 과 같은 형태다
// (훅이 실제로 읽는 필드와 어긋나면 테스트가 조용히 통과하므로 형태를 그대로 맞춘다).
import type { ApprovalItem } from '@/types/approval';
import type {
  FirewallAlertRule,
  FirewallAlertsResponse,
  FirewallAuditResponse,
  FirewallAutomationResponse,
  FirewallBlockListResponse,
  FirewallEventsResponse,
  FirewallBlockResponse,
  FirewallStatusResponse,
  FirewallUnblockResponse,
} from '@/types/firewall';

export const FIREWALL_STATUS_DRY_RUN: FirewallStatusResponse = {
  enabled: true,
  fwctl: {
    configured: true,
    reachable: true,
    dry_run: true,
    max_ttl_seconds: 3600,
    ipset_exists: true,
    version: '0.1.0',
  },
  grafana: {
    configured: true,
    dashboard_url: 'http://127.0.0.1:3000/d/fireware-firewall-lab',
  },
  default_ttl_seconds: 600,
};

export const FIREWALL_STATUS_LIVE: FirewallStatusResponse = {
  ...FIREWALL_STATUS_DRY_RUN,
  fwctl: { ...FIREWALL_STATUS_DRY_RUN.fwctl, dry_run: false },
};

export const FIREWALL_STATUS_UNREACHABLE: FirewallStatusResponse = {
  ...FIREWALL_STATUS_DRY_RUN,
  fwctl: {
    configured: true,
    reachable: false,
    dry_run: null,
    max_ttl_seconds: null,
    ipset_exists: null,
    version: null,
  },
};

export const FIREWALL_STATUS_NOT_CONFIGURED: FirewallStatusResponse = {
  ...FIREWALL_STATUS_UNREACHABLE,
  fwctl: { ...FIREWALL_STATUS_UNREACHABLE.fwctl, configured: false },
  grafana: { configured: false, dashboard_url: null },
};

export const FIREWALL_BLOCKS_TWO: FirewallBlockListResponse = {
  items: [
    { ip: '172.28.10.66', ttl_remaining_seconds: 583, packets: 12, bytes: 720 },
    { ip: '203.0.113.9', ttl_remaining_seconds: 45, packets: 0, bytes: 0 },
  ],
  count: 2,
  dry_run: false,
};

export const FIREWALL_BLOCKS_EMPTY: FirewallBlockListResponse = {
  items: [],
  count: 0,
  dry_run: true,
};

export const FIREWALL_BLOCK_OK_DRY_RUN: FirewallBlockResponse = {
  ip: '172.28.10.66',
  ttl_seconds: 600,
  expires_at: '2026-11-23T12:10:01Z',
  reason: 'R02 포트 스캔',
  dry_run: true,
  request_id: 'adm-17-3f2a',
};

export const FIREWALL_BLOCK_OK_LIVE: FirewallBlockResponse = {
  ...FIREWALL_BLOCK_OK_DRY_RUN,
  dry_run: false,
};

export const FIREWALL_UNBLOCK_OK: FirewallUnblockResponse = {
  ip: '172.28.10.66',
  removed: true,
  dry_run: false,
  already_absent: false,
  request_id: 'adm-17-9c1e',
};

export const FIREWALL_UNBLOCK_ABSENT: FirewallUnblockResponse = {
  ip: '172.28.10.66',
  removed: false,
  dry_run: null,
  already_absent: true,
  request_id: 'adm-17-9c1f',
};

// ── 탐지·감사·승인 ──────────────────────────────────────────────────

const quietRule = (rule_id: string, name: string, action_hint = 'block'): FirewallAlertRule => ({
  uid: `fw-${rule_id.toLowerCase()}-${name.toLowerCase().replace(/[^a-z]+/g, '-')}`,
  name: `${rule_id} ${name}`,
  rule_id,
  kind: name.toLowerCase().replace(/ /g, '_'),
  severity: 'medium',
  action_hint,
  state: 'normal',
  description: `${name} 설명`,
  last_evaluation: '2026-11-23T11:39:50Z',
  instances: [],
});

/** 룰 8개 — 발화 2(R02 차단 권고, R06 보고 전용), 대기 1(R04). 서버가 정렬해 준 순서다. */
export const FIREWALL_ALERTS: FirewallAlertsResponse = {
  rules: [
    {
      uid: 'fw-r02-port-scan',
      name: 'R02 Vertical Port Scan',
      rule_id: 'R02',
      kind: 'port_scan',
      severity: 'high',
      action_hint: 'block',
      state: 'firing',
      description: '같은 출발지가 여러 포트를 두드림',
      last_evaluation: '2026-11-23T11:39:50Z',
      instances: [
        { src_ip: '172.28.10.66', state: 'firing', active_at: '2026-11-23T11:31:50Z', value: '41' },
        { src_ip: '203.0.113.9', state: 'nodata', active_at: '2026-11-22T09:00:00Z', value: null },
      ],
    },
    {
      uid: 'fw-r06-distributed-probe',
      name: 'R06 Distributed Probe',
      rule_id: 'R06',
      kind: 'distributed_probe',
      severity: 'medium',
      action_hint: 'report',
      state: 'firing',
      description: '여러 출발지가 같은 포트를 두드림',
      last_evaluation: '2026-11-23T11:39:50Z',
      instances: [
        { src_ip: '192.0.2.44', state: 'firing', active_at: '2026-11-23T11:35:00Z', value: '7' },
      ],
    },
    {
      uid: 'fw-r04-sensitive-port',
      name: 'R04 Sensitive Port Probe',
      rule_id: 'R04',
      kind: 'sensitive_port',
      severity: 'medium',
      action_hint: 'block',
      state: 'pending',
      description: '관리 포트 접근 시도',
      last_evaluation: '2026-11-23T11:39:50Z',
      instances: [
        { src_ip: '198.51.100.7', state: 'pending', active_at: '2026-11-23T11:39:00Z', value: '12' },
        { src_ip: null, state: 'pending', active_at: null, value: null },
      ],
    },
    quietRule('R01', 'Drop Burst'),
    { ...quietRule('R01', 'Drop Burst high'), severity: 'high' },
    quietRule('R03', 'Horizontal Host Scan'),
    quietRule('R07', 'Long-window Repetition'),
    quietRule('R08', 'Repeat Offender', 'extend'),
  ],
  firing_count: 2,
  fetched_at: '2026-11-23T11:40:02Z',
};

export const FIREWALL_ALERTS_QUIET: FirewallAlertsResponse = {
  ...FIREWALL_ALERTS,
  rules: FIREWALL_ALERTS.rules.map((r) => ({ ...r, state: 'normal', instances: [] })),
  firing_count: 0,
};

export const FIREWALL_EVENTS: FirewallEventsResponse = {
  range: '1h',
  action: 'all',
  top_sources: [
    { src_ip: '172.28.10.66', count: 182 },
    { src_ip: '172.28.10.10', count: 2 },
  ],
  recent: [
    { ts: '2026-11-23T11:39:41Z', action: 'drop', src_ip: '172.28.10.66', dest_ip: '172.28.20.10', protocol: 6, dport: 22 },
    { ts: '2026-11-23T11:39:40Z', action: 'block', src_ip: '172.28.10.66', dest_ip: '172.28.20.10', protocol: 17, dport: 53 },
    { ts: '2026-11-23T11:39:39Z', action: 'drop', src_ip: '172.28.10.10', dest_ip: '172.28.20.10', protocol: 1, dport: null },
  ],
  fetched_at: '2026-11-23T11:40:02Z',
};

export const FIREWALL_EVENTS_EMPTY: FirewallEventsResponse = {
  ...FIREWALL_EVENTS,
  top_sources: [],
  recent: [],
};

/** 실제 fwctl 감사 형태: 관리자 차단 2(성공·거부), 관리자 해제 1(actor 없음), 에이전트 차단 1 */
export const FIREWALL_AUDIT: FirewallAuditResponse = {
  range: '24h',
  items: [
    {
      ts: '2026-11-23T12:44:00Z', request_id: 'it-9f', event: 'block',
      actor: 'mcp-firewall-server/local', ip: '198.51.100.7', ttl_seconds: 900,
      reason: 'agent decision', result: 'ok', status: 201, error_code: null, dry_run: true,
    },
    {
      ts: '2026-11-23T12:43:10Z', request_id: 'adm-7-50ef44708adf478bb182c652', event: 'unblock',
      actor: null, ip: '172.28.10.66', ttl_seconds: null,
      reason: null, result: 'ok', status: 200, error_code: null, dry_run: false,
    },
    {
      ts: '2026-11-23T12:42:54Z', request_id: 'adm-7-ba1a6ae516744f9b9968f96a', event: 'block',
      actor: 'sangplusbot/admin:7', ip: '172.28.10.10', ttl_seconds: 600,
      reason: 'whitelist check', result: 'rejected', status: 403,
      error_code: 'FORBIDDEN_WHITELIST', dry_run: true,
    },
    {
      ts: '2026-11-23T12:42:36Z', request_id: 'adm-7-ad2733bbc6174c0eae75787c', event: 'block',
      actor: 'sangplusbot/admin:7', ip: '172.28.10.66', ttl_seconds: 600,
      reason: 'R02 포트 스캔', result: 'ok', status: 201, error_code: null, dry_run: true,
    },
  ],
  count: 4,
  fetched_at: '2026-11-23T12:45:00Z',
};

export const FIREWALL_AUDIT_EMPTY: FirewallAuditResponse = {
  ...FIREWALL_AUDIT,
  items: [],
  count: 0,
};

const approval = (id: string, tool_id: string, draft_preview: string): ApprovalItem => ({
  id,
  agent_id: 'agent-fw',
  agent_name: '방화벽 감시',
  tool_id,
  draft_preview,
  status: 'pending',
  execute_after: null,
  expires_at: '2026-11-24T12:00:00Z',
  seen_at: null,
  created_at: '2026-11-23T12:00:00Z',
  edited: false,
});

const MCP = 'mcp:7f3c0000-0000-0000-0000-000000000001';

/** 승인 대기 3건 — 방화벽 도구 2건(block_ip·unblock_ip) + 다른 도구 1건 */
export const FIREWALL_APPROVALS: ApprovalItem[] = [
  approval('ap-1', `${MCP}:block_ip`, '172.28.10.66 을 600초 차단 — R02 포트 스캔'),
  approval('ap-2', `${MCP}:unblock_ip`, '203.0.113.9 차단 해제'),
  approval('ap-3', 'mcp:9a000000-0000-0000-0000-000000000002:send_mail', '고객 안내 메일 발송'),
];

/** 백엔드 오류 본문 — HTTPException(detail={code, message, ...}) */
export const firewallError = (code: string, message: string, details?: unknown) => ({
  detail: { code, message, request_id: 'adm-17-err', ...(details ? { details } : {}) },
});

// ── firewall-agent: 자동 점검 ────────────────────────────────────────────

export const FIREWALL_AUTOMATION_NOT_SET: FirewallAutomationResponse = {
  configured: false,
  reason: 'AGENT_NOT_SET',
  agent: null,
  schedules: [],
  alert_receiver: null,
};

export const FIREWALL_AUTOMATION_ON: FirewallAutomationResponse = {
  configured: true,
  reason: null,
  agent: { id: 'agent-fw', name: '방화벽 보안 에이전트' },
  schedules: [
    {
      id: 'sch-1',
      name: '10분 점검',
      enabled: true,
      cron_expr: '*/10 * * * *',
      skip_when_busy: true,
      next_run_at: '2026-11-24T05:20:00',
      last_run: {
        status: 'skipped',
        skip_reason: 'approval_pending',
        started_at: '2026-11-24T05:10:00',
      },
    },
  ],
  alert_receiver: {
    configured: true,
    enabled: true,
    skip_when_busy: true,
    last_result: 'enqueued',
    last_received_at: '2026-11-24T05:12:00',
  },
};
