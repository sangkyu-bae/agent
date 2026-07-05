// fix-agent-composer: POST /api/v1/agents/compose 요청/응답 타입
// 백엔드 스키마 동기화: idt/src/application/agent_composer/schemas.py

/** 증분 수정용 현재 폼 스냅샷. 서버 스키마와 동일하게 모두 nullable. */
export interface ComposeCurrentConfig {
  name: string | null;
  system_prompt: string | null;
  tool_ids: string[];
  llm_model_id: string | null;
  temperature: number | null;
}

export interface ComposeHistoryTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface ComposeAgentRequest {
  user_request: string;
  name?: string | null;
  llm_model_id?: string | null;
  current_config?: ComposeCurrentConfig | null;
  history?: ComposeHistoryTurn[] | null;
}

export interface ComposeMissingCapability {
  capability: string;
  reason: string;
  suggestion: string;
}

export interface ComposeWorkerInfo {
  tool_id: string;
  worker_id: string;
  description: string;
  sort_order: number;
  tool_config: Record<string, unknown> | null;
  worker_type?: string;
  ref_agent_id?: string | null;
  ref_agent_name?: string | null;
  /** compose-tool-instructions: 도구별 사용 지침 (빈 문자열 가능) */
  instruction: string;
}

export type ComposeCoverage = 'full' | 'partial' | 'none';

export interface ComposeAgentDraftResponse {
  coverage: ComposeCoverage;
  name_suggestion: string;
  system_prompt: string;
  tool_ids: string[];
  workers: ComposeWorkerInfo[];
  flow_hint: string;
  llm_model_id: string;
  temperature: number;
  missing_capabilities: ComposeMissingCapability[];
  notes: string;
}

/** Fix 채팅 로컬 메시지 (서버 영속 아님). */
export interface FixChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  draft?: ComposeAgentDraftResponse;
  isError?: boolean;
  applied?: boolean;
}
