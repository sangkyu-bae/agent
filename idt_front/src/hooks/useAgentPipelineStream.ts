/**
 * 파이프라인 SSE 소비 훅 — 단계 이벤트를 진행바 상태로 누적한다.
 *
 * Design Ref: agent-create-wizard §5.5 / FR-F09·F10.
 *
 * TanStack Query 를 쓰지 않는 이유: 이 호출은 캐시 대상이 아니고(매번 다른
 * 결과) 중간 이벤트를 소비해야 한다 — useMutation 은 최종값만 준다.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { agentPipelineService } from '@/services/agentPipelineService';
import { PIPELINE_DISABLED_STATUS } from '@/services/agentPipelineService';
import { PIPELINE_STAGE_STATUS } from '@/types/agentPipeline';
import type {
  AgentPipelineRequest,
  AgentPipelineResponse,
  PipelineStage,
  PipelineStepOut,
} from '@/types/agentPipeline';

/** 실패 분류 — 화면이 안내 문구를 고르는 기준이다. */
export const PIPELINE_ERROR = {
  /** 서버 킬스위치 off (404) — 위저드 자체가 불가능하다. */
  DISABLED: 'disabled',
  /** 인증 만료 (401). */
  UNAUTHORIZED: 'unauthorized',
  /** 그 외 — 네트워크 끊김·5xx·검증 실패. 재시도 가능. */
  FAILED: 'failed',
} as const;

export type PipelineErrorKind =
  (typeof PIPELINE_ERROR)[keyof typeof PIPELINE_ERROR];

export interface PipelineError {
  kind: PipelineErrorKind;
  message: string;
}

const classify = (error: unknown): PipelineError => {
  const status = (error as { status?: number } | null)?.status;
  if (status === PIPELINE_DISABLED_STATUS) {
    return {
      kind: PIPELINE_ERROR.DISABLED,
      message: '에이전트 생성 파이프라인이 비활성화되어 있습니다.',
    };
  }
  if (status === 401) {
    return {
      kind: PIPELINE_ERROR.UNAUTHORIZED,
      message: '로그인이 만료되었습니다. 다시 로그인해주세요.',
    };
  }
  return {
    kind: PIPELINE_ERROR.FAILED,
    message:
      error instanceof Error
        ? error.message
        : '요청을 처리하지 못했습니다.',
  };
};

export interface UseAgentPipelineStreamResult {
  /** 지금까지 확정된 단계 기록. 진행바 렌더에 그대로 넘긴다. */
  steps: PipelineStepOut[];
  /** 실행 중인 단계 (started 는 왔고 completed 는 아직). */
  activeStage: PipelineStage | null;
  isPending: boolean;
  error: PipelineError | null;
  /** 마지막 성공 결과. 다음 호출 시작 시 비워진다. */
  result: AgentPipelineResponse | null;
  send: (body: AgentPipelineRequest) => Promise<void>;
  /** 실패 안내를 닫을 때 사용. steps 는 유지한다. */
  clearError: () => void;
}

export const useAgentPipelineStream = (): UseAgentPipelineStreamResult => {
  const [steps, setSteps] = useState<PipelineStepOut[]>([]);
  const [activeStage, setActiveStage] = useState<PipelineStage | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<PipelineError | null>(null);
  const [result, setResult] = useState<AgentPipelineResponse | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      // 이탈 시 스트림을 끊는다 — 위저드는 create 에 도달하지 않으므로
      // 중단이 리소스를 남기지 않는다 (§6.3).
      abortRef.current?.abort();
    };
  }, []);

  const send = useCallback(async (body: AgentPipelineRequest) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsPending(true);
    setError(null);
    setResult(null);
    // 새 라운드는 진행바를 처음부터 다시 그린다 — 이전 라운드의 완료 표시가
    // 남으면 "이번에도 끝난 단계"로 오표시된다.
    setSteps([]);
    setActiveStage(null);

    // 실패 시 "어디서 끊겼는지"를 진행바에 남기기 위한 추적 (FR-F10).
    // state 가 아니라 지역 변수인 이유: catch 시점에 setState 반영을 기다릴 수
    // 없고, 이 값 자체는 렌더에 쓰이지 않는다.
    let inFlightStage: PipelineStage | null = null;

    try {
      await agentPipelineService.stream(
        body,
        {
          onStageStarted: (stage) => {
            inFlightStage = stage as PipelineStage;
            if (!mountedRef.current) return;
            setActiveStage(stage as PipelineStage);
          },
          onStageSettled: (step) => {
            const record = step as PipelineStepOut;
            // 종료된 단계는 더 이상 진행 중이 아니다 — 서버가 실어준 사유를
            // 아래 catch 의 합성 failed 가 덮어쓰지 않게 한다.
            if (inFlightStage === record.stage) inFlightStage = null;
            if (!mountedRef.current) return;
            setSteps((prev) => [
              ...prev.filter((s) => s.stage !== record.stage),
              record,
            ]);
            setActiveStage(null);
          },
          onResult: (payload) => {
            inFlightStage = null;
            if (!mountedRef.current) return;
            // 최종 payload 의 steps 가 진실이다 — 누적본을 덮어쓴다
            // (백엔드가 미도달 단계를 skipped 로 채워 5개를 보장한다).
            setSteps(payload.steps ?? []);
            setActiveStage(null);
            setResult(payload);
          },
        },
        controller.signal,
      );
    } catch (e) {
      if (controller.signal.aborted || !mountedRef.current) return;
      setActiveStage(null);
      // 끊긴 단계를 failed 로 남긴다 — 버리면 실패한 행이 '대기중'으로 되돌아가
      // 사용자가 어느 단계에서 틀렸는지 알 수 없다 (§6.1 / WHY).
      const brokenStage: PipelineStage | null = inFlightStage;
      if (brokenStage) {
        setSteps((prev) => [
          ...prev.filter((s) => s.stage !== brokenStage),
          {
            stage: brokenStage,
            status: PIPELINE_STAGE_STATUS.FAILED,
            reason: null,
            elapsed_ms: 0,
          },
        ]);
      }
      setError(classify(e));
    } finally {
      if (mountedRef.current && !controller.signal.aborted) {
        setIsPending(false);
      }
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    steps,
    activeStage,
    isPending,
    error,
    result,
    send,
    clearError,
  };
};

export default useAgentPipelineStream;
