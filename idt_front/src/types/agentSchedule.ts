// agent-schedule: 에이전트 자동 실행 스케줄 (docs/api/agent-schedule.md)

export const SCHEDULE_TYPE = {
  ONCE: 'once',
  DAILY: 'daily',
  WEEKLY: 'weekly',
  CRON: 'cron',
} as const;
export type ScheduleType = (typeof SCHEDULE_TYPE)[keyof typeof SCHEDULE_TYPE];

export const SCHEDULE_RUN_STATUS = {
  RUNNING: 'running',
  SUCCESS: 'success',
  FAILED: 'failed',
} as const;
export type ScheduleRunStatus =
  (typeof SCHEDULE_RUN_STATUS)[keyof typeof SCHEDULE_RUN_STATUS];

export interface ScheduleSpecPayload {
  schedule_type: ScheduleType;
  /** once 전용 (YYYY-MM-DD, 미래 날짜) */
  run_date?: string | null;
  /** once/daily/weekly ("HH:MM") */
  time_of_day?: string | null;
  /** weekly 전용 (0=월 .. 6=일) — 조회 표시용, 이번 UI에서 생성하지 않음 */
  days_of_week?: number[] | null;
  /** cron 전용 (5필드, 최소 간격 10분) */
  cron_expr?: string | null;
}

export interface ScheduleCreateRequest {
  /** 1~200자 — 스펙 요약으로 자동 생성 */
  name: string;
  spec: ScheduleSpecPayload;
  /** 1~1,900자 — {today}/{now}/{weekday} 플레이스홀더 사용 가능 */
  instruction: string;
  /** 항상 'Asia/Seoul' 명시 전송 */
  timezone: string;
  enabled: boolean;
}

/** PUT은 생성과 동일 스키마 */
export type ScheduleUpdateRequest = ScheduleCreateRequest;

export interface ScheduleResponse {
  id: string;
  agent_id: string;
  name: string;
  spec: ScheduleSpecPayload;
  instruction: string;
  enabled: boolean;
  timezone: string;
  /** UTC ISO8601 */
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleRunResponse {
  id: string;
  schedule_id: string;
  status: ScheduleRunStatus;
  scheduled_for: string;
  started_at: string | null;
  finished_at: string | null;
  session_id: string | null;
  run_id: string | null;
  error_message: string | null;
}

/** 생성 모드 전용 — 에이전트 생성 성공 후 순차 POST될 로컬 항목 */
export interface StagedSchedule {
  localId: string;
  name: string;
  spec: ScheduleSpecPayload;
  instruction: string;
  timezone: string;
  enabled: boolean;
}

export const MAX_SCHEDULES_PER_AGENT = 10;
export const MAX_INSTRUCTION_LENGTH = 1900;
export const DEFAULT_SCHEDULE_TIMEZONE = 'Asia/Seoul';
