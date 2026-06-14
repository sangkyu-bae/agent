import type { RagToolConfig } from './ragToolConfig';

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
}
