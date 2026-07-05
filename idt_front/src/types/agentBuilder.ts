import type { RagToolConfig } from './ragToolConfig';
import type {
  DocumentExtractorDraft,
  DocumentTemplateRequest,
} from './documentExtractor';
import type { StagedSchedule } from './agentSchedule';

// ── Sub-Agent ──────────────────────────────────

/** 서버로 전송하는 서브에이전트 설정. */
export interface SubAgentConfigRequest {
  ref_agent_id: string;
  description: string;
}

/** 폼이 보유하는 서브에이전트 항목 (표시용 name 포함). */
export interface SubAgentConfig {
  ref_agent_id: string;
  name: string;
  description: string;
}

/** 사용 가능한 서브에이전트 후보 (GET /available-sub-agents). */
export interface SubAgentCandidate {
  agent_id: string;
  name: string;
  description: string;
  source_type: 'owned' | 'public' | 'department';
  tool_ids: string[];
  has_sub_agents: boolean;
  llm_model_id?: string | null;
  visibility?: string | null;
}

export interface AvailableSubAgentsResponse {
  agents: SubAgentCandidate[];
}

// ── Create ─────────────────────────────────────

export interface CreateBuilderAgentRequest {
  user_request: string;
  name: string;
  llm_model_id?: string;
  visibility?: 'private' | 'department' | 'public';
  department_id?: string;
  temperature?: number;
  tool_ids?: string[];
  tool_configs?: Record<string, RagToolConfig>;
  sub_agent_configs?: SubAgentConfigRequest[];
  // agent-skill-toggle: 등록 시점 부착 스킬(목표 상태)
  skill_ids?: string[];
  // document-template-extractor GA4: 확정 템플릿 (document_extractor 도구 필요)
  document_template?: DocumentTemplateRequest;
}

export interface CreateBuilderAgentResponse {
  agent_id: string;
  name: string;
  system_prompt: string;
  tool_ids: string[];
  workers: Array<{
    tool_id: string;
    worker_id: string;
    description: string;
    sort_order: number;
    tool_config: Record<string, unknown> | null;
  }>;
  flow_hint: string;
  llm_model_id: string;
  visibility: string;
  visibility_clamped: boolean;
  max_visibility: string | null;
  department_id: string | null;
  temperature: number;
  created_at: string;
}

// ── Update ─────────────────────────────────────

export interface UpdateBuilderAgentRequest {
  system_prompt?: string;
  name?: string;
  visibility?: 'private' | 'department' | 'public';
  department_id?: string;
  temperature?: number;
  // undefined = 변경 안 함, [] = 모든 서브에이전트 제거
  sub_agent_configs?: SubAgentConfigRequest[];
  // agent-skill-toggle: undefined = 변경 안 함, [] = 전부 해제, [...] = 목표 상태
  skill_ids?: string[];
  // document-template-extractor: undefined = 변경 안 함, 값 = 템플릿 교체
  document_template?: DocumentTemplateRequest;
}

export interface UpdateBuilderAgentResponse {
  agent_id: string;
  name: string;
  system_prompt: string;
  updated_at: string;
}

// ── Form (프론트엔드 전용) ─────────────────────

export interface AgentBuilderFormData {
  name: string;
  description: string;
  model: string;
  systemPrompt: string;
  tools: string[];
  temperature: number;
  toolConfigs: Record<string, RagToolConfig>;
  subAgents: SubAgentConfig[];
  // agent-skill-toggle: 부착 스킬 id 목록(단일 진실원, 저장 시 skill_ids로 전송)
  skills: string[];
  // document-template-extractor: 확정 전까지 프론트가 보유하는 드래프트 (R4)
  documentExtractorDraft?: DocumentExtractorDraft | null;
  // agent-schedule: 생성 모드 전용 staged 스케줄 (생성 성공 후 순차 POST, edit에선 미사용)
  schedules: StagedSchedule[];
}

// ── Studio UI (프론트엔드 전용) ────────────────
// agent-builder-studio-ui Design §3.1

/** 우측 패널 탭. 'test'/'skill'만 활성, 나머지는 비활성 placeholder. */
export type RightTabId =
  | 'test'
  | 'skill'
  | 'fix'
  | 'opener'
  | 'file'
  | 'schedule'
  | 'settings';

/** 좌측 폼/비주얼 탭. 'visual'은 비활성 placeholder. */
export type LeftTabId = 'form' | 'visual';

/** 테스트 패널의 로컬 대화 메시지 (서버 영속 아님). */
export interface TestChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

/**
 * 모델 설정 모달이 form에 적용하는 값.
 * maxTokens/topP/topK는 UI 표시 전용(미저장) — Design §3.1.
 */
export interface ModelSettingsValue {
  model: string;
  temperature: number;
}
