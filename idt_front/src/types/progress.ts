// progress-card: 공통 진행 상황 카드 도메인 타입.
// Design Ref: §3.1 — 컴포넌트 파일 co-locate 대신 types/로 분리
// (react-refresh/only-export-components 규칙 + 기존 types/ 상수 컨벤션 준수).
export const PROGRESS_STEP_STATUS = {
  COMPLETED: 'completed',
  IN_PROGRESS: 'in_progress',
  PENDING: 'pending',
  ERROR: 'error',
} as const;

export type ProgressStepStatus =
  (typeof PROGRESS_STEP_STATUS)[keyof typeof PROGRESS_STEP_STATUS];

export interface ProgressStep {
  /** 미지정 시 index를 key로 사용 */
  id?: string;
  /** 예: "Phase 1: 프로젝트 초기화" */
  label: string;
  status: ProgressStepStatus;
  /** 배지 기본 라벨(완료/진행중/대기중/실패) 오버라이드 */
  badgeLabel?: string;
}
