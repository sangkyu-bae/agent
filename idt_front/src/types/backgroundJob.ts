// background-jobs: 백그라운드 작업 큐·작업함 (Design §5-1)

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

export interface UnseenCountResponse {
  count: number;
}

export interface SeenAllResponse {
  updated: number;
}

/** 작업함 스케줄 실행 탭 (D9) */
export interface MyScheduleRun {
  id: string;
  schedule_id: string;
  schedule_name: string;
  agent_id: string;
  /** 작업함 표시용 에이전트명 (에이전트 삭제 시 null) */
  agent_name: string | null;
  status: 'running' | 'success' | 'failed';
  scheduled_for: string;
  started_at: string;
  finished_at: string | null;
  session_id: string | null;
  error_message: string | null;
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
