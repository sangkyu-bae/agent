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

/** fix-agent-planner-hitl: HITL 질문 답변. answer===''는 무응답(부분 답변 허용).
 * question 텍스트는 stateless 재구성용 에코백(D8). */
export interface ClarificationAnswer {
  question_id: string;
  question: string;
  answer: string;
}

/** fix-agent-planner-hitl: 구조화 질문 — 선택지+자유 입력 허용 플래그. */
export interface ClarifyingQuestion {
  id: string;
  question: string;
  options: string[];
  allow_free_text: boolean;
}

export type ComposeStatus = 'draft' | 'needs_clarification';

export interface ComposeAgentRequest {
  user_request: string;
  name?: string | null;
  llm_model_id?: string | null;
  current_config?: ComposeCurrentConfig | null;
  history?: ComposeHistoryTurn[] | null;
  /** fix-agent-planner-hitl: HITL 왕복 (미전송 시 기존 동작과 동일) */
  clarification_answers?: ClarificationAnswer[] | null;
  clarification_round?: number;
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
  /** fix-agent-planner-hitl: 미수신(구 응답) 시 'draft'로 간주 */
  status?: ComposeStatus;
  /** status==='needs_clarification'일 때만 채워짐 */
  questions?: ClarifyingQuestion[];
  /** Planner 계획 요약 — 초안 카드 "빌드 계획" 섹션에 표시 */
  plan_summary?: string;
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
  /** fix-agent-planner-hitl: HITL 질문 카드 메시지 */
  questions?: ClarifyingQuestion[];
  planSummary?: string;
  answered?: boolean;
}
