// background-jobs: 백그라운드 작업 큐·작업함 (Design §5-1)
import type { ScheduleSpecPayload } from '@/types/agentSchedule';

export const JOB_STATUS = {
  QUEUED: 'queued',
  RUNNING: 'running',
  SUCCESS: 'success',
  FAILED: 'failed',
} as const;
export type JobStatus = (typeof JOB_STATUS)[keyof typeof JOB_STATUS];

export interface EnqueueJobRequest {
  query: string;
  session_id?: string | null;
  source?: 'chat' | 'api';
}

export interface EnqueueJobResponse {
  job_id: string;
  status: JobStatus;
  request_id: string;
}

export interface BackgroundJob {
  id: string;
  agent_id: string;
  /** 작업함 표시용 에이전트명 (에이전트 삭제 시 null) */
  agent_name: string | null;
  source: string;
  query: string;
  session_id: string | null;
  run_id: string | null;
  status: JobStatus;
  error_message: string | null;
  /** null=미확인 (벨 배지 기준) */
  seen_at: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
}

// ── jobs-page-revamp: 통합 작업 이력 + 필터 (Design §3.1, §4.2) ──────

export const JOB_HISTORY_TYPE = {
  MANUAL: 'manual',
  SCHEDULE: 'schedule',
} as const;
export type JobHistoryType =
  (typeof JOB_HISTORY_TYPE)[keyof typeof JOB_HISTORY_TYPE];

/**
 * 작업 기록 한 행 — 수동 job 과 스케줄 실행을 서버가 하나로 정규화한 형태.
 * 제목은 수동=질문 원문, 스케줄=스케줄명이다.
 */
export interface JobHistoryItem {
  id: string;
  type: JobHistoryType;
  /** 정렬 기준 — 수동=등록 시각, 스케줄=예정 시각 */
  occurred_at: string;
  title: string;
  status: JobStatus;
  agent_id: string;
  /** 에이전트 삭제 시 null */
  agent_name: string | null;
  session_id: string | null;
  error_message: string | null;
  /** null=미확인. 스케줄 행은 항상 null */
  seen_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  /** 휴지통 노출 기준 — 스케줄 실행 이력은 개별 삭제 불가 */
  deletable: boolean;
}

export interface JobListResponse {
  items: JobHistoryItem[];
  total: number;
}

export interface CleanupJobsResponse {
  deleted: number;
}

/** 상태 그룹 — 서버의 4개 상태를 사용자가 고르는 3개 묶음으로 접는다 */
export const JOB_STATUS_GROUP = {
  ALL: 'all',
  RUNNING: 'running',
  DONE: 'done',
} as const;
export type JobStatusGroup =
  (typeof JOB_STATUS_GROUP)[keyof typeof JOB_STATUS_GROUP];

export const JOB_PERIOD = {
  ALL: 'all',
  HOUR: '1h',
  TODAY: 'today',
  WEEK: 'week',
} as const;
export type JobPeriod = (typeof JOB_PERIOD)[keyof typeof JOB_PERIOD];

export interface JobHistoryFilters {
  status: JobStatusGroup;
  type: JobHistoryType | 'all';
  period: JobPeriod;
}

export const DEFAULT_JOB_FILTERS: JobHistoryFilters = {
  status: 'all',
  type: 'all',
  period: 'all',
};

/** 작업 기록 페이지 크기 */
export const JOB_PAGE_SIZE = 20;

export const JOB_STATUS_GROUP_OPTIONS = [
  { value: JOB_STATUS_GROUP.ALL, label: '전체' },
  { value: JOB_STATUS_GROUP.RUNNING, label: '진행중' },
  { value: JOB_STATUS_GROUP.DONE, label: '완료됨' },
] as const;

export const JOB_TYPE_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: JOB_HISTORY_TYPE.MANUAL, label: '수동' },
  { value: JOB_HISTORY_TYPE.SCHEDULE, label: '스케줄' },
] as const;

export const JOB_PERIOD_OPTIONS = [
  { value: JOB_PERIOD.ALL, label: '전체' },
  { value: JOB_PERIOD.HOUR, label: '1시간' },
  { value: JOB_PERIOD.TODAY, label: '오늘' },
  { value: JOB_PERIOD.WEEK, label: '이번 주' },
] as const;

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  queued: '대기 중',
  running: '실행 중',
  success: '완료',
  failed: '실패',
};

export interface UnseenCountResponse {
  /** 총 미확인 건수 (작업 + 승인). 기존 소비자는 이 값만 읽어도 된다. */
  count: number;
  /** approval-gate Design §5.5: 분해 필드 — 필요한 화면만 나눠 표시한다. */
  jobs?: number;
  approvals?: number;
}

export interface SeenAllResponse {
  updated: number;
}

/**
 * 작업함 '스케줄 작업' 탭 — 내 스케줄 정의 (jobs-page-revamp FR-15).
 * 관리(토글·삭제)는 기존 /agents/{agent_id}/schedules 계약을 그대로 쓴다.
 */
export interface MySchedule {
  id: string;
  agent_id: string;
  /** 에이전트 삭제 시 null */
  agent_name: string | null;
  name: string;
  spec: ScheduleSpecPayload;
  instruction: string;
  enabled: boolean;
  timezone: string;
  next_run_at: string | null;
  last_run_at: string | null;
}

/** 진행중 여부 (폴링 지속 판단) */
export const isJobActive = (status: JobStatus): boolean =>
  status === JOB_STATUS.QUEUED || status === JOB_STATUS.RUNNING;

/** 종결 여부 (벨 드롭다운·새 결과 표시 기준) */
export const isJobFinished = (status: JobStatus): boolean =>
  status === JOB_STATUS.SUCCESS || status === JOB_STATUS.FAILED;

/** 결과 세션 딥링크 — 쿼리 파라미터는 AgentChatLayout 이 소비한다 */
export const chatSessionPath = (agentId: string, sessionId: string): string =>
  `/chatpage?agentId=${encodeURIComponent(agentId)}&sessionId=${encodeURIComponent(sessionId)}`;

/** 벨 배지 폴링 주기 (ms) — Design D11 */
export const UNSEEN_COUNT_POLL_INTERVAL_MS = 15_000;

/** 작업함 진행중 항목 폴링 주기 (ms) */
export const JOB_LIST_POLL_INTERVAL_MS = 5_000;

/** 시간 열 표기 — 서버는 UTC naive 로 주므로 Z 를 붙여 로컬(KST)로 변환한다 */
export const formatJobDateTime = (iso: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/** 에이전트 표시명 — 이름이 없으면(삭제된 에이전트) id 앞 8자로 대체 */
export const agentDisplayName = (
  agentName: string | null,
  agentId: string,
): string => agentName ?? agentId.slice(0, 8);
