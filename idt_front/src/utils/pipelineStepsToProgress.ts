/**
 * 백엔드 `steps[]` → 공통 `ProgressCard` 의 `ProgressStep[]` 매핑.
 *
 * Design Ref: agent-create-wizard §5.5 — **이 변환의 단일 소스**다.
 * 화면마다 따로 매핑하면 degraded 표기가 갈린다.
 *
 * 상태 매핑 (§5.5 표):
 *   ok       → completed
 *   degraded → completed + badgeLabel(사유 요약)   ← ProgressStepStatus 미확장
 *   failed   → error
 *   skipped  → pending
 *   미도착   → pending (activeStage 면 in_progress)
 */
import {
  PIPELINE_STAGE_LABEL,
  PIPELINE_STAGE_ORDER,
  PIPELINE_STAGE_STATUS,
} from '@/types/agentPipeline';
import type { PipelineStage, PipelineStepOut } from '@/types/agentPipeline';
import { PROGRESS_STEP_STATUS } from '@/types/progress';
import type { ProgressStep, ProgressStepStatus } from '@/types/progress';

/** degraded 배지 최대 길이 — 진행바 한 줄을 넘기지 않는다. */
const BADGE_MAX_CHARS = 12;
const DEGRADED_FALLBACK_BADGE = '일부 제한';
const FAILED_BADGE = '실패';

const summarize = (reason: string | null): string => {
  const text = (reason ?? '').trim();
  if (!text) return DEGRADED_FALLBACK_BADGE;
  return text.length > BADGE_MAX_CHARS
    ? `${text.slice(0, BADGE_MAX_CHARS)}…`
    : text;
};

const toStatus = (status: PipelineStepOut['status']): ProgressStepStatus => {
  switch (status) {
    case PIPELINE_STAGE_STATUS.OK:
    case PIPELINE_STAGE_STATUS.DEGRADED:
      return PROGRESS_STEP_STATUS.COMPLETED;
    case PIPELINE_STAGE_STATUS.FAILED:
      return PROGRESS_STEP_STATUS.ERROR;
    default:
      return PROGRESS_STEP_STATUS.PENDING;
  }
};

const toBadge = (step: PipelineStepOut): string | undefined => {
  if (step.status === PIPELINE_STAGE_STATUS.DEGRADED) {
    return summarize(step.reason);
  }
  if (step.status === PIPELINE_STAGE_STATUS.FAILED) return FAILED_BADGE;
  // skipped 의 reason(stopped_for_review)은 내부 사유다 — 노출하지 않는다.
  return undefined;
};

/**
 * @param steps 서버 응답의 `steps[]`. 빈 배열이어도 5단계가 나온다.
 * @param activeStage SSE `stage_started` 는 왔지만 `stage_completed` 가 아직
 *   안 온 단계. 해당 단계를 `in_progress` 로 덮어쓴다. 단, 이미 완료로 확정된
 *   단계는 되돌리지 않는다(늦게 도착한 started 이벤트로 진행바가 역행하는 것 방지).
 */
export const pipelineStepsToProgress = (
  steps: PipelineStepOut[],
  activeStage?: PipelineStage | null,
): ProgressStep[] => {
  const byStage = new Map(steps.map((step) => [step.stage, step]));

  return PIPELINE_STAGE_ORDER.map((stage) => {
    const step = byStage.get(stage);
    const status = step
      ? toStatus(step.status)
      : PROGRESS_STEP_STATUS.PENDING;

    if (status === PROGRESS_STEP_STATUS.PENDING && activeStage === stage) {
      return {
        id: stage,
        label: PIPELINE_STAGE_LABEL[stage],
        status: PROGRESS_STEP_STATUS.IN_PROGRESS,
      };
    }

    return {
      id: stage,
      label: PIPELINE_STAGE_LABEL[stage],
      status,
      ...(step && toBadge(step) ? { badgeLabel: toBadge(step) } : {}),
    };
  });
};
