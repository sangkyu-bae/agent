/**
 * 에이전트 생성 파이프라인 API 계약.
 *
 * Design Ref: agent-create-wizard §3.5 — 백엔드
 * `src/interfaces/schemas/agent_pipeline.py` 와 1:1 대응한다.
 *
 * 상수 객체가 컴포넌트 파일이 아니라 여기 있는 이유(tsx-authoring-pitfalls 위키):
 * 컴포넌트 파일의 런타임 export 는 react-refresh 린트 위반이며, 이 프로젝트에서
 * 실제로 Do 단계 재작업을 유발한 함정이다.
 */

/** 고정 5단계. 화면은 항상 이 순서로 진행바를 렌더한다 (백엔드 STAGE_ORDER). */
export const PIPELINE_STAGE = {
  INTENT: 'intent',
  TOOLS: 'tools',
  PROMPT: 'prompt',
  CREATE: 'create',
  BIND: 'bind',
} as const;

export type PipelineStage =
  (typeof PIPELINE_STAGE)[keyof typeof PIPELINE_STAGE];

/** 화면이 렌더하는 순서. 백엔드 steps[] 순서와 동일하다. */
export const PIPELINE_STAGE_ORDER: readonly PipelineStage[] = [
  PIPELINE_STAGE.INTENT,
  PIPELINE_STAGE.TOOLS,
  PIPELINE_STAGE.PROMPT,
  PIPELINE_STAGE.CREATE,
  PIPELINE_STAGE.BIND,
] as const;

/** 단계 라벨 — 진행바 표기의 단일 소스. */
export const PIPELINE_STAGE_LABEL: Record<PipelineStage, string> = {
  [PIPELINE_STAGE.INTENT]: '의도 파악',
  [PIPELINE_STAGE.TOOLS]: '도구 추천',
  [PIPELINE_STAGE.PROMPT]: '프롬프트 생성',
  [PIPELINE_STAGE.CREATE]: '에이전트 생성',
  [PIPELINE_STAGE.BIND]: '프롬프트 연결',
};

export const PIPELINE_STAGE_STATUS = {
  OK: 'ok',
  DEGRADED: 'degraded',
  FAILED: 'failed',
  SKIPPED: 'skipped',
} as const;

export type PipelineStageStatus =
  (typeof PIPELINE_STAGE_STATUS)[keyof typeof PIPELINE_STAGE_STATUS];

/**
 * 응답 상태.
 * - `need_input` 되묻기 필요 · `tools_proposed` 도구 확인 대기
 * - `prompt_ready` 프롬프트 검토 대기 · `created` 논스톱 생성 완료
 * - `failed` 는 SSE 레이어가 합성하는 값이다(동기 경로에는 없다).
 */
export type PipelineStatus =
  | 'need_input'
  | 'tools_proposed'
  | 'prompt_ready'
  | 'created'
  | 'failed';

/** 위저드가 사용하는 정지 지점. create/bind 는 정지할 수 없다(서버 422). */
export const PIPELINE_STOP = {
  TOOLS: 'tools',
  PROMPT: 'prompt',
} as const;

export type PipelineStop = (typeof PIPELINE_STOP)[keyof typeof PIPELINE_STOP];

export interface PipelineStepOut {
  stage: PipelineStage;
  status: PipelineStageStatus;
  reason: string | null;
  elapsed_ms: number;
}

export interface PipelineQuestion {
  slot_key: string;
  question: string;
  options: string[];
  allow_free_text: boolean;
}

export interface PipelineIntentSummary {
  label: string | null;
  filled_slots: Record<string, string>;
  missing_slots: string[];
  degraded: boolean;
}

/** 되묻기 답변 에코백 1건 (stateless HITL). */
export interface PipelineAnswer {
  slot_key: string;
  value: string;
}

export interface PipelineHistoryTurn {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * 의도 에코백 (D2).
 * `complete`/`missing_slots` 는 **보내지 않는다** — 계산 필드는 서버가 재계산한다.
 */
export interface PipelineIntentEcho {
  label: string | null;
  filled_slots: Record<string, string>;
  degraded: boolean;
}

export interface AgentPipelineRequest {
  user_request: string;
  history?: PipelineHistoryTurn[];
  answers?: PipelineAnswer[];
  round?: number;
  tool_ids?: string[];
  name?: string | null;
  llm_model_id?: string | null;
  session_id?: string | null;
  /** 지정 단계 직후 정지. 미지정이면 서버가 생성까지 논스톱 실행한다. */
  stop_after?: PipelineStop | null;
  /** true 면 `tool_ids` 가 사용자 확정 목록이라 셀렉터를 돌리지 않는다 (D1). */
  tools_confirmed?: boolean;
  /** 확정된 의도 재사용 (D2). 서버가 spec 으로 재검증한다. */
  intent?: PipelineIntentEcho | null;
}

export interface AgentPipelineResponse {
  status: PipelineStatus;
  round: number;
  /** 항상 5개 — 미도달 단계는 `skipped` 로 채워져 온다. */
  steps: PipelineStepOut[];
  degraded_stages: string[];
  questions: PipelineQuestion[];
  intent: PipelineIntentSummary | null;
  recommended_tool_ids: string[];
  final_tool_ids: string[];
  /** 카탈로그에 없거나 비활성이라 반영되지 않은 tool_id 에코백. */
  unknown_tool_ids: string[];
  session_id: string | null;
  version_id: string | null;
  agent_id: string | null;
  agent_name: string | null;
  /** 4000자 clamp 가 적용된 값 — 화면에 보이는 것이 저장될 것이다 (D3). */
  assembled_prompt: string | null;
  suggested_name: string | null;
  /** 절단이 일어났을 때의 사유. null 이면 절단 없음. */
  prompt_clamp_reason: string | null;
  bind_ok: boolean | null;
  /** status='failed'(SSE 합성) 일 때만 존재한다. */
  error?: { message: string };
}

/** SSE 이벤트 이름 — 백엔드 `_sse()` 의 event 필드. */
export const PIPELINE_SSE_EVENT = {
  STAGE_STARTED: 'stage_started',
  STAGE_COMPLETED: 'stage_completed',
  STAGE_FAILED: 'stage_failed',
  RESULT: 'pipeline_result',
} as const;

export type PipelineSseEventName =
  (typeof PIPELINE_SSE_EVENT)[keyof typeof PIPELINE_SSE_EVENT];

export type PipelineSseEvent =
  | { event: 'stage_started'; data: { stage: PipelineStage } }
  | { event: 'stage_completed' | 'stage_failed'; data: PipelineStepOut }
  | { event: 'pipeline_result'; data: AgentPipelineResponse };

/** 사람이 편집한 프롬프트 버전 저장 (prompt-composer §4.5). */
export interface AppendPromptVersionRequest {
  assembled: string;
  tool_ids?: string[];
}

export interface AppendPromptVersionResponse {
  session_id: string;
  version_id: string;
  version_no: number;
  source: string;
}

/** `assembled` 상한 — 서버 CreateAgentRequest.system_prompt 와 동일해야 한다. */
export const MAX_ASSEMBLED_CHARS = 4000;

/** 설명 입력 상한 — 서버 `user_request` 와 동일. */
export const MAX_PIPELINE_USER_REQUEST_CHARS = 1000;
