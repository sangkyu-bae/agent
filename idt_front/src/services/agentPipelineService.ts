/**
 * 에이전트 생성 파이프라인 API 호출.
 *
 * Design Ref: agent-create-wizard §4.1 / §9.1(Infrastructure).
 *
 * 동기 경로는 axios(`authApiClient`)를 쓰지만 **스트리밍은 raw fetch** 다:
 * 입력이 본문이라 EventSource 를 못 쓰고, axios 는 ReadableStream 을 브라우저에서
 * 노출하지 않는다. 그래서 인증 헤더를 직접 만들어야 하는데, 방식은
 * `authClient.ts` 의 요청 인터셉터와 **동일하게** Zustand 스토어를 읽는다.
 *
 * ⚠️ 한계: axios 응답 인터셉터의 401 자동 토큰 갱신은 이 경로에 적용되지 않는다.
 *    401 이면 훅이 그대로 실패로 처리하고 사용자가 재시도한다.
 */
import { API_BASE_URL, API_ENDPOINTS } from '@/constants/api';
import authApiClient from '@/services/api/authClient';
import { useAuthStore } from '@/store/authStore';
import { createEventFetchStream } from '@/utils/streamParser';
import type { NamedStreamEvent } from '@/utils/streamParser';
import type {
  AgentPipelineRequest,
  AgentPipelineResponse,
  AppendPromptVersionRequest,
  AppendPromptVersionResponse,
} from '@/types/agentPipeline';

/** 파이프라인 라우트가 서버 킬스위치로 꺼져 있을 때의 상태 코드. */
export const PIPELINE_DISABLED_STATUS = 404;

/** authClient 요청 인터셉터와 동일한 헤더 구성 (Bearer + X-User-Id). */
const authHeaders = (): Record<string, string> => {
  const { accessToken, user } = useAuthStore.getState();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (user?.id) headers['X-User-Id'] = String(user.id);
  return headers;
};

export interface PipelineStreamHandlers {
  /** 단계 시작 — 진행바를 in_progress 로 바꾼다. */
  onStageStarted?: (stage: string) => void;
  /** 단계 종료(정상/degraded/실패) — steps 를 누적한다. */
  onStageSettled?: (step: unknown) => void;
  /** 마지막 이벤트. 정확히 1회 온다. */
  onResult: (result: AgentPipelineResponse) => void;
}

export const agentPipelineService = {
  /** 동기 실행 — SSE 를 못 쓰는 환경의 폴백이자 테스트 편의 경로. */
  run: (body: AgentPipelineRequest) =>
    authApiClient.post<AgentPipelineResponse>(
      API_ENDPOINTS.AGENT_PIPELINE,
      body,
    ),

  /**
   * SSE 실행 — 단계 이벤트를 실시간으로 콜백에 밀어준다.
   *
   * @param signal 사용자가 이탈하면 중단한다. fetch 의 AbortSignal 을 그대로 전달.
   * @throws 스트림 개시 전 실패(401/404/422/5xx). `error.status` 로 구분한다.
   */
  stream: async (
    body: AgentPipelineRequest,
    handlers: PipelineStreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> => {
    await createEventFetchStream(
      `${API_BASE_URL}${API_ENDPOINTS.AGENT_PIPELINE_STREAM}`,
      {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
        signal,
      },
      (event: NamedStreamEvent) => {
        if (event.event === 'stage_started') {
          handlers.onStageStarted?.(
            (event.data as { stage: string }).stage,
          );
          return;
        }
        if (
          event.event === 'stage_completed' ||
          event.event === 'stage_failed'
        ) {
          handlers.onStageSettled?.(event.data);
          return;
        }
        if (event.event === 'pipeline_result') {
          handlers.onResult(event.data as AgentPipelineResponse);
        }
      },
      () => {},
    );
  },

  /** 사람이 편집한 프롬프트를 새 버전으로 저장 (prompt-composer §4.5). */
  appendPromptVersion: (
    sessionId: string,
    body: AppendPromptVersionRequest,
  ) =>
    authApiClient.post<AppendPromptVersionResponse>(
      API_ENDPOINTS.PROMPT_SESSION_VERSIONS(sessionId),
      body,
    ),

  /** 생성된 에이전트를 프롬프트 세션에 연결 (백필). */
  bindPromptSession: (sessionId: string, agentId: string) =>
    authApiClient.patch(API_ENDPOINTS.PROMPT_SESSION_BIND(sessionId), {
      agent_id: agentId,
    }),
};

export default agentPipelineService;
