import { describe, expect, it } from 'vitest';
import { pipelineStepsToProgress } from './pipelineStepsToProgress';
import { PIPELINE_STAGE, PIPELINE_STAGE_STATUS } from '@/types/agentPipeline';
import type { PipelineStepOut } from '@/types/agentPipeline';
import { PROGRESS_STEP_STATUS } from '@/types/progress';

const step = (
  stage: PipelineStepOut['stage'],
  status: PipelineStepOut['status'],
  reason: string | null = null,
): PipelineStepOut => ({ stage, status, reason, elapsed_ms: 0 });

const ALL_SKIPPED: PipelineStepOut[] = [
  step(PIPELINE_STAGE.INTENT, PIPELINE_STAGE_STATUS.SKIPPED),
  step(PIPELINE_STAGE.TOOLS, PIPELINE_STAGE_STATUS.SKIPPED),
  step(PIPELINE_STAGE.PROMPT, PIPELINE_STAGE_STATUS.SKIPPED),
  step(PIPELINE_STAGE.CREATE, PIPELINE_STAGE_STATUS.SKIPPED),
  step(PIPELINE_STAGE.BIND, PIPELINE_STAGE_STATUS.SKIPPED),
];

describe('pipelineStepsToProgress', () => {
  it('항상 5단계를 고정 순서로 반환한다', () => {
    const result = pipelineStepsToProgress([]);
    expect(result).toHaveLength(5);
    expect(result.map((s) => s.id)).toEqual([
      'intent',
      'tools',
      'prompt',
      'create',
      'bind',
    ]);
  });

  it('서버가 일부 단계만 보내도 5개를 채운다', () => {
    // 방어 코드가 아니라 계약이다 — 백엔드 finalize_steps 가 5개를 보장하지만
    // 화면은 응답 도착 전에도 진행바를 렌더해야 한다.
    const result = pipelineStepsToProgress([
      step(PIPELINE_STAGE.INTENT, PIPELINE_STAGE_STATUS.OK),
    ]);
    expect(result).toHaveLength(5);
    expect(result[0].status).toBe(PROGRESS_STEP_STATUS.COMPLETED);
    expect(result[1].status).toBe(PROGRESS_STEP_STATUS.PENDING);
  });

  it('한국어 라벨을 붙인다', () => {
    expect(pipelineStepsToProgress([]).map((s) => s.label)).toEqual([
      '의도 파악',
      '도구 추천',
      '프롬프트 생성',
      '에이전트 생성',
      '프롬프트 연결',
    ]);
  });

  it('ok 는 completed 로 매핑한다', () => {
    const result = pipelineStepsToProgress([
      step(PIPELINE_STAGE.INTENT, PIPELINE_STAGE_STATUS.OK),
    ]);
    expect(result[0].status).toBe(PROGRESS_STEP_STATUS.COMPLETED);
    expect(result[0].badgeLabel).toBeUndefined();
  });

  it('degraded 는 completed + 사유 배지로 매핑한다', () => {
    // ProgressStepStatus 에 degraded 를 추가하지 않는다 (Design A-4) —
    // 공통 컴포넌트 계약을 이 사이클 요구로 바꾸지 않는다.
    const result = pipelineStepsToProgress([
      step(
        PIPELINE_STAGE.PROMPT,
        PIPELINE_STAGE_STATUS.DEGRADED,
        'LLM 시간 초과 — 규칙기반 폴백',
      ),
    ]);
    expect(result[2].status).toBe(PROGRESS_STEP_STATUS.COMPLETED);
    expect(result[2].badgeLabel).toBeTruthy();
  });

  it('degraded 배지는 길이를 제한한다', () => {
    const result = pipelineStepsToProgress([
      step(PIPELINE_STAGE.PROMPT, PIPELINE_STAGE_STATUS.DEGRADED, '가'.repeat(80)),
    ]);
    expect(result[2].badgeLabel!.length).toBeLessThanOrEqual(13);
  });

  it('사유 없는 degraded 에도 기본 배지를 붙인다', () => {
    const result = pipelineStepsToProgress([
      step(PIPELINE_STAGE.TOOLS, PIPELINE_STAGE_STATUS.DEGRADED),
    ]);
    expect(result[1].badgeLabel).toBe('일부 제한');
  });

  it('failed 는 error 로 매핑한다', () => {
    const result = pipelineStepsToProgress([
      step(PIPELINE_STAGE.PROMPT, PIPELINE_STAGE_STATUS.FAILED, '저장 실패'),
    ]);
    expect(result[2].status).toBe(PROGRESS_STEP_STATUS.ERROR);
    expect(result[2].badgeLabel).toBe('실패');
  });

  it('skipped 는 pending 으로 매핑한다', () => {
    const result = pipelineStepsToProgress(ALL_SKIPPED);
    expect(result.every((s) => s.status === PROGRESS_STEP_STATUS.PENDING)).toBe(
      true,
    );
  });

  it('skipped 에는 배지를 붙이지 않는다', () => {
    // stopped_for_review 를 배지로 노출하면 "대기중"에 내부 사유가 새어나온다.
    const result = pipelineStepsToProgress([
      step(PIPELINE_STAGE.CREATE, PIPELINE_STAGE_STATUS.SKIPPED, 'stopped_for_review'),
    ]);
    expect(result[3].badgeLabel).toBeUndefined();
  });

  it('activeStage 는 in_progress 로 덮어쓴다', () => {
    const result = pipelineStepsToProgress([], PIPELINE_STAGE.TOOLS);
    expect(result[1].status).toBe(PROGRESS_STEP_STATUS.IN_PROGRESS);
  });

  it('activeStage 가 이미 완료된 단계면 완료를 유지한다', () => {
    // stage_completed 가 도착한 뒤 activeStage 가 남아 있어도 되돌리지 않는다.
    const result = pipelineStepsToProgress(
      [step(PIPELINE_STAGE.INTENT, PIPELINE_STAGE_STATUS.OK)],
      PIPELINE_STAGE.INTENT,
    );
    expect(result[0].status).toBe(PROGRESS_STEP_STATUS.COMPLETED);
  });

  it('실행 중 단계 이후는 대기 상태로 남는다', () => {
    const result = pipelineStepsToProgress(
      [step(PIPELINE_STAGE.INTENT, PIPELINE_STAGE_STATUS.OK)],
      PIPELINE_STAGE.TOOLS,
    );
    expect(result.map((s) => s.status)).toEqual([
      PROGRESS_STEP_STATUS.COMPLETED,
      PROGRESS_STEP_STATUS.IN_PROGRESS,
      PROGRESS_STEP_STATUS.PENDING,
      PROGRESS_STEP_STATUS.PENDING,
      PROGRESS_STEP_STATUS.PENDING,
    ]);
  });

  it('알 수 없는 stage 는 무시한다', () => {
    const result = pipelineStepsToProgress([
      { stage: 'ghost', status: 'ok', reason: null, elapsed_ms: 0 } as never,
    ]);
    expect(result).toHaveLength(5);
    expect(result.every((s) => s.status === PROGRESS_STEP_STATUS.PENDING)).toBe(
      true,
    );
  });
});
