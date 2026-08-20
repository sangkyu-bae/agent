// agent-create-wizard §6.1 — SSE 끊김/실패 시 "어디서 끊겼는지"가 진행바에 남아야 한다.
//
// 이 훅이 실패 시점의 단계를 버리면 진행바가 '대기중'으로 회귀해 사용자는
// 어느 단계에서 틀렸는지 알 수 없다 (WHY: 블랙박스 제거).
//
// 서비스를 목으로 세운 이유: "스트림이 중간에 끊긴다"를 MSW 로 재현하면
// 인터셉터가 본문을 통째로 버퍼링해 앞 청크가 소비자에게 도달하지 않는다.
// 훅의 계약 상대는 `agentPipelineService.stream` 이므로 그 경계에서 검증한다.
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PIPELINE_STAGE_STATUS } from '@/types/agentPipeline';
import type { PipelineStreamHandlers } from '@/services/agentPipelineService';
import { pipelineStepsToProgress } from '@/utils/pipelineStepsToProgress';
import { PROGRESS_STEP_STATUS } from '@/types/progress';
import { PIPELINE_ERROR, useAgentPipelineStream } from './useAgentPipelineStream';

// vi.mock 은 파일 최상단으로 끌어올려지므로 목 함수도 함께 끌어올려야 한다
// (그렇지 않으면 팩토리가 TDZ 의 변수를 잡아 목이 조용히 어긋난다).
const { streamMock } = vi.hoisted(() => ({ streamMock: vi.fn() }));

vi.mock('@/services/agentPipelineService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/services/agentPipelineService')>();
  return {
    ...actual,
    agentPipelineService: { ...actual.agentPipelineService, stream: streamMock },
  };
});

beforeEach(() => streamMock.mockReset());

const httpError = (status: number) => {
  const error = new Error(`SSE request failed with status ${status}`);
  (error as Error & { status?: number }).status = status;
  return error;
};

/**
 * 주어진 이벤트를 흘린 뒤 끊기는 스트림.
 *
 * `handlers` 가드: 테스트 종료(언마운트) 뒤 잔여 호출이 인자 없이 한 번 더
 * 들어온다. 여기서 던지면 테스트와 무관한 unhandled rejection 이 된다.
 */
const brokenAfter = (
  emit: (handlers: PipelineStreamHandlers) => void,
  error: Error = new Error('network down'),
) =>
  streamMock.mockImplementation(
    async (_body: unknown, handlers?: PipelineStreamHandlers) => {
      if (!handlers) return;
      emit(handlers);
      throw error;
    },
  );

const send = async () => {
  const { result } = renderHook(() => useAgentPipelineStream());
  await result.current.send({ user_request: '문서 봇' });
  return result;
};

const okStep = (stage: string) => ({
  stage,
  status: PIPELINE_STAGE_STATUS.OK,
  reason: null,
  elapsed_ms: 3,
});

describe('useAgentPipelineStream — 실패 시 진행바', () => {
  it('진행 중이던 단계를 failed 로 남긴다', async () => {
    brokenAfter((h) => h.onStageStarted?.('intent'));

    const result = await send();

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.steps).toEqual([
      expect.objectContaining({
        stage: 'intent',
        status: PIPELINE_STAGE_STATUS.FAILED,
      }),
    ]);
    expect(result.current.activeStage).toBeNull();
  });

  it('완료된 단계는 유지하고 끊긴 단계만 failed 로 표시한다', async () => {
    brokenAfter((h) => {
      h.onStageStarted?.('intent');
      h.onStageSettled?.(okStep('intent'));
      h.onStageStarted?.('tools');
    });

    const result = await send();

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.steps).toEqual([
      expect.objectContaining({ stage: 'intent', status: 'ok' }),
      expect.objectContaining({
        stage: 'tools',
        status: PIPELINE_STAGE_STATUS.FAILED,
      }),
    ]);
  });

  it('진행바 어댑터가 끊긴 단계를 error 행으로 그린다', async () => {
    // 훅→어댑터 계약을 함께 잠근다 (어댑터 계약 자체는 변경하지 않는다).
    brokenAfter((h) => {
      h.onStageStarted?.('intent');
      h.onStageSettled?.(okStep('intent'));
      h.onStageStarted?.('tools');
    });

    const result = await send();
    await waitFor(() => expect(result.current.error).not.toBeNull());

    const rows = pipelineStepsToProgress(
      result.current.steps,
      result.current.activeStage,
    );
    expect(rows[0]).toMatchObject({
      id: 'intent',
      status: PROGRESS_STEP_STATUS.COMPLETED,
    });
    expect(rows[1]).toMatchObject({
      id: 'tools',
      status: PROGRESS_STEP_STATUS.ERROR,
      badgeLabel: '실패',
    });
    expect(rows[2]).toMatchObject({
      id: 'prompt',
      status: PROGRESS_STEP_STATUS.PENDING,
    });
  });

  it('stage_failed 이벤트가 이미 온 뒤 끊기면 사유를 덮어쓰지 않는다', async () => {
    brokenAfter((h) => {
      h.onStageStarted?.('prompt');
      h.onStageSettled?.({
        stage: 'prompt',
        status: PIPELINE_STAGE_STATUS.FAILED,
        reason: '버전 저장 실패',
        elapsed_ms: 7,
      });
    });

    const result = await send();

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.steps).toEqual([
      expect.objectContaining({
        stage: 'prompt',
        status: PIPELINE_STAGE_STATUS.FAILED,
        reason: '버전 저장 실패',
      }),
    ]);
  });

  it('연결 자체가 실패하면(500) 시작된 단계가 없으므로 steps 는 비어 있다', async () => {
    brokenAfter(() => {}, httpError(500));

    const result = await send();

    await waitFor(() =>
      expect(result.current.error?.kind).toBe(PIPELINE_ERROR.FAILED),
    );
    expect(result.current.steps).toEqual([]);
  });

  it('404 는 킬스위치로 분류한다', async () => {
    brokenAfter(() => {}, httpError(404));

    const result = await send();

    await waitFor(() =>
      expect(result.current.error?.kind).toBe(PIPELINE_ERROR.DISABLED),
    );
  });

  it('성공 응답은 서버 steps 로 덮어쓰고 실패 흔적을 남기지 않는다', async () => {
    streamMock.mockImplementation(
      async (_body: unknown, handlers?: PipelineStreamHandlers) => {
        if (!handlers) return;
        handlers.onStageStarted?.('intent');
        handlers.onResult({
          status: 'tools_proposed',
          round: 1,
          steps: [okStep('intent'), okStep('tools')],
          degraded_stages: [],
          questions: [],
          intent: null,
          recommended_tool_ids: [],
          final_tool_ids: [],
          unknown_tool_ids: [],
          session_id: null,
          version_id: null,
          agent_id: null,
          agent_name: null,
          assembled_prompt: null,
          suggested_name: null,
          prompt_clamp_reason: null,
          bind_ok: null,
        } as never);
      },
    );

    const result = await send();

    await waitFor(() => expect(result.current.result).not.toBeNull());
    expect(result.current.error).toBeNull();
    expect(
      result.current.steps.some(
        (s) => s.status === PIPELINE_STAGE_STATUS.FAILED,
      ),
    ).toBe(false);
  });
});
