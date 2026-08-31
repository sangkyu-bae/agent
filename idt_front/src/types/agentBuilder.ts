import type { RagToolConfig } from './ragToolConfig';
import type {
  DocumentExtractorDraft,
  DocumentTemplateRequest,
} from './documentExtractor';
import type {
  DocumentGenerationTypeRequest,
  DocumentGeneratorDraft,
} from './documentGenerator';
import type { StagedSchedule } from './agentSchedule';
import type {
  PresentationGeneratorConfigRequest,
  PresentationGeneratorDraft,
} from './presentationGenerator';

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
  // agent-instruction-required: 지침 필수 — 비우면 백엔드 422
  system_prompt: string;
  llm_model_id?: string;
  visibility?: 'private' | 'department' | 'public';
  department_id?: string;
  temperature?: number;
  tool_ids?: string[];
  tool_configs?: Record<string, RagToolConfig>;
  sub_agent_configs?: SubAgentConfigRequest[];
  // builtin-tools D5: 빌트인 수동 opt-out (생성 폼 전용 — 카탈로그/저장 형식 모두 수용)
  exclude_builtin_tool_ids?: string[];
  // builtin-middleware D5: 빌트인 미들웨어 수동 opt-out (생성 폼 전용)
  exclude_builtin_middleware_types?: string[];
  // agent-skill-toggle: 등록 시점 부착 스킬(목표 상태)
  skill_ids?: string[];
  // document-template-extractor GA4: 확정 템플릿 (document_extractor 도구 필요)
  document_template?: DocumentTemplateRequest;
  // doc-generator: 문서 유형 (document_generator 도구 필요)
  document_generation_type?: DocumentGenerationTypeRequest;
  // golden-sample-blueprint D7: 발표자료 설정 (presentation_generator 도구 필요)
  presentation_generator?: PresentationGeneratorConfigRequest;
  // agent-settings-tab D5: supervisor 반복 한도 (백엔드 기본 25, 범위 10~1000)
  max_iterations?: number;
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
  // doc-generator: undefined = 변경 안 함, 값 = 문서 유형 교체
  document_generation_type?: DocumentGenerationTypeRequest;
  // golden-sample-blueprint D7: 발표자료 설정 (presentation_generator 도구 필요)
  presentation_generator?: PresentationGeneratorConfigRequest;
  // agent-builder-edit-mapping FR-5: undefined = 모델 변경 안 함
  llm_model_id?: string;
  // builtin-middleware D5: undefined = 변경 안 함, [] = 전부 해제, [...] = 전체 교체
  middleware_types?: string[];
  // agent-settings-tab D5: undefined = 변경 안 함 (폼은 프라임 값 기반으로 항상 전송)
  max_iterations?: number;
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
  // doc-generator: 문서 유형 드래프트 (저장 시 document_generation_type으로 전송)
  documentGeneratorDraft?: DocumentGeneratorDraft | null;
  // golden-sample-blueprint: 발표자료 설정 드래프트 (저장 시 presentation_generator로 전송)
  presentationGeneratorDraft?: PresentationGeneratorDraft | null;
  // agent-schedule: 생성 모드 전용 staged 스케줄 (생성 성공 후 순차 POST, edit에선 미사용)
  schedules: StagedSchedule[];
  // builtin-tools D8: 수동 해제된 빌트인 도구(카탈로그 형식) — ToolPickerModal에서만
  // 토글되며 Fix 초안 적용이 건드리지 않는다 (채팅 경로 빌트인 제거 차단의 프론트 절반)
  excludedBuiltinTools: string[];
  // builtin-middleware D10: 수동 해제된 빌트인 미들웨어 타입 (create 전용 —
  // Fix 초안 적용이 건드리지 않는다, excludedBuiltinTools 패턴 대칭)
  excludedBuiltinMiddlewares: string[];
  // builtin-middleware D10: 적용 미들웨어 타입 (edit 전용 — detail 프리필 후 전체 교체 전송)
  middlewares: string[];
  // agent-settings-tab: supervisor 반복 한도 (설정 탭 — 저장 시 max_iterations로 전송)
  maxIterations: number;
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
