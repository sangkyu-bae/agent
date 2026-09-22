// approval-gate: 승인 게이트 타입 (백엔드 src/interfaces/schemas/approval.py 1:1 대응)
// Design Ref: §4 (API), §5 (UI)

export const APPROVAL_STATUSES = [
  'pending',
  'approved',
  'scheduled',
  'executed',
  'rejected',
  'expired',
  'failed',
] as const;

export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number];

/** 사람이 아직 볼 이유가 있는 상태 — 목록 기본 필터 (백엔드 DEFAULT_STATUSES 와 일치) */
export const ACTIVE_APPROVAL_STATUSES: ApprovalStatus[] = [
  'pending',
  'scheduled',
];

export const APPROVAL_STATUS_LABELS: Record<ApprovalStatus, string> = {
  pending: '승인 대기',
  approved: '승인됨',
  scheduled: '집행 예정',
  executed: '집행 완료',
  rejected: '거절됨',
  expired: '만료됨',
  failed: '집행 실패',
};

/** 상태 배지 색 — 디자인 토큰(CLAUDE.md UI 섹션) 범위 안에서 */
export const APPROVAL_STATUS_TONES: Record<ApprovalStatus, string> = {
  pending: 'bg-violet-50 text-violet-600 border-violet-200',
  approved: 'bg-zinc-50 text-zinc-600 border-zinc-200',
  scheduled: 'bg-blue-50 text-blue-600 border-blue-200',
  executed: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  rejected: 'bg-zinc-100 text-zinc-500 border-zinc-300',
  expired: 'bg-zinc-100 text-zinc-400 border-zinc-200',
  failed: 'bg-red-50 text-red-500 border-red-200',
};

/** 백엔드 Design §6.1 에러 코드 — 화면 문구 매핑의 단일 출처 */
export const APPROVAL_ERROR_MESSAGES: Record<string, string> = {
  APPROVAL_NOT_FOUND: '이미 삭제되었거나 존재하지 않는 요청입니다.',
  APPROVAL_FORBIDDEN: '이 요청을 승인할 권한이 없습니다.',
  APPROVAL_NOT_PENDING: '이미 처리된 요청입니다. 목록을 새로고침했습니다.',
  APPROVAL_EXPIRED: '만료된 요청입니다.',
  APPROVAL_INVALID_WINDOW:
    '집행 예정 시각이 만료 시각보다 늦습니다. 에이전트 설정을 확인하세요.',
  APPROVAL_AGENT_CHANGED:
    '에이전트 구성이 변경되어 이어서 진행할 수 없습니다. 집행만 진행할 수 있습니다.',
};

export const APPROVAL_PAGE_SIZE = 20;

export interface ApprovalItem {
  id: string;
  agent_id: string;
  agent_name: string | null;
  tool_id: string;
  draft_preview: string;
  status: ApprovalStatus;
  execute_after: string | null;
  expires_at: string;
  seen_at: string | null;
  created_at: string;
}

export interface ApprovalDetail extends ApprovalItem {
  draft: string;
  tool_args: Record<string, unknown>;
  worker_id: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_reason: string | null;
  executed_at: string | null;
  error_message: string | null;
}

export interface ApprovalListResponse {
  data: ApprovalItem[];
  pagination: { total: number; page: number; size: number };
}

export interface ApprovalDecisionResponse {
  id: string;
  status: ApprovalStatus;
  execute_after: string | null;
  message: string;
}

export interface RejectApprovalRequest {
  reason: string;
}

/** 에이전트별 승인 게이트 설정 (백엔드 Design §3.4 config 스키마) */
export interface ApprovalGateConfig {
  mode: 'always' | 'off';
  execute_after: string | null;
  expires_hours: number;
  on_expire: 'expire';
  /** Check G13: cron 해석 기준 타임존. 미지정이면 서버 기본 Asia/Seoul */
  timezone?: string;
}

/** GET/PUT /api/v1/agents/{id}/approval-gate 응답 (Check G3) */
export interface ApprovalGateSettings {
  /** 관리자가 카탈로그에서 승인 게이트를 활성화했는가 */
  available: boolean;
  /** 이 에이전트에 적용 중인가 (강제 포함) */
  enabled: boolean;
  /** 관리자 강제 — 소유자가 끌 수 없다 */
  is_enforced: boolean;
  config: ApprovalGateConfig;
}

/** 전용 API 가 소유해 일반 미들웨어 목록에서 감추는 타입 (백엔드 SEPARATELY_MANAGED 와 일치) */
export const SEPARATELY_MANAGED_MIDDLEWARE_TYPES: readonly string[] = [
  'approval_gate',
];

export const DEFAULT_GATE_TIMEZONE = 'Asia/Seoul';

export const DEFAULT_APPROVAL_GATE_CONFIG: ApprovalGateConfig = {
  mode: 'always',
  execute_after: null,
  expires_hours: 168,
  on_expire: 'expire',
};

export const GATE_EXPIRES_HOURS_MIN = 1;
export const GATE_EXPIRES_HOURS_MAX = 720;

/** 종료 상태 — 목록에서 액션 버튼을 감출 판정 */
export const isApprovalTerminal = (status: ApprovalStatus): boolean =>
  status === 'executed' ||
  status === 'rejected' ||
  status === 'expired' ||
  status === 'failed';

/** 승인·거절 가능 여부. scheduled 는 이미 결정된 건이라 재결정 대상이 아니다. */
export const isApprovalActionable = (status: ApprovalStatus): boolean =>
  status === 'pending';
