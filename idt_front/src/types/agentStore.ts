export type AgentScope = 'all' | 'public' | 'department' | 'mine';

export interface AgentListParams {
  scope: AgentScope;
  search?: string;
  page?: number;
  size?: number;
}

export interface StoreAgentSummary {
  agent_id: string;
  name: string;
  description: string;
  visibility: 'private' | 'department' | 'public';
  department_name: string | null;
  owner_user_id: string;
  owner_email: string | null;
  temperature: number;
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
}

export interface AgentListResponse {
  agents: StoreAgentSummary[];
  total: number;
  page: number;
  size: number;
}

export interface WorkerInfo {
  tool_id: string;
  worker_id: string;
  description: string;
  sort_order: number;
  tool_config: Record<string, unknown> | null;
}

export interface AgentDetail {
  agent_id: string;
  name: string;
  description: string;
  system_prompt: string;
  tool_ids: string[];
  workers: WorkerInfo[];
  flow_hint: string;
  llm_model_id: string;
  status: string;
  visibility: 'private' | 'department' | 'public';
  department_id: string | null;
  department_name: string | null;
  temperature: number;
  owner_user_id: string;
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
}

export interface SubscribeResponse {
  subscription_id: string;
  agent_id: string;
  agent_name: string;
  is_pinned: boolean;
  subscribed_at: string;
}

export interface UpdateSubscriptionRequest {
  is_pinned: boolean;
}

export interface ForkAgentRequest {
  name?: string;
}

export interface ForkAgentResponse {
  agent_id: string;
  name: string;
  forked_from: string;
  forked_at: string;
  system_prompt: string;
  workers: WorkerInfo[];
  visibility: string;
  temperature: number;
  llm_model_id: string;
}

export type MyAgentFilter = 'all' | 'owned' | 'subscribed' | 'forked';

export interface MyAgentListParams {
  filter: MyAgentFilter;
  search?: string;
  page?: number;
  size?: number;
}

export interface MyAgentSummary {
  agent_id: string;
  name: string;
  description: string;
  source_type: 'owned' | 'subscribed' | 'forked';
  visibility: 'private' | 'department' | 'public';
  temperature: number;
  owner_user_id: string;
  forked_from: string | null;
  is_pinned: boolean;
  created_at: string;
}

export interface MyAgentListResponse {
  agents: MyAgentSummary[];
  total: number;
  page: number;
  size: number;
}

export interface ForkStatsResponse {
  agent_id: string;
  fork_count: number;
  subscriber_count: number;
}

export interface PublishAgentRequest {
  visibility: 'public' | 'department';
  department_id?: string;
}
