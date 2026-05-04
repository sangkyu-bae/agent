export type AgentStatus = 'idle' | 'thinking' | 'tool_calling' | 'responding' | 'error';

// ── Agent Subscription ──────────────────────────

export type AgentSourceType = 'owned' | 'subscribed' | 'forked';
export type AgentVisibility = 'private' | 'public';

export interface MyAgent {
  agent_id: string;
  name: string;
  description: string;
  source_type: AgentSourceType;
  visibility: AgentVisibility;
  temperature: number;
  owner_user_id: string;
  forked_from: string | null;
  is_pinned: boolean;
  created_at: string;
}

export interface MyAgentsResponse {
  agents: MyAgent[];
  total: number;
  page: number;
  size: number;
}

export interface MyAgentsParams {
  filter?: 'all' | AgentSourceType;
  search?: string;
  page?: number;
  size?: number;
}

export interface SubscriptionResponse {
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
  workers: Array<{
    name: string;
    tool_type: string;
    config: Record<string, unknown>;
  }>;
  visibility: AgentVisibility;
  temperature: number;
  llm_model_id: string;
}

export interface AgentRun {
  id: string;
  status: AgentStatus;
  input: string;
  output?: string;
  steps: AgentStep[];
  createdAt: string;
  completedAt?: string;
}

export interface AgentStep {
  id: string;
  type: 'thought' | 'tool_call' | 'tool_result' | 'final_answer';
  content: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolOutput?: string;
  timestamp: string;
}

export interface RunAgentRequest {
  input: string;
  sessionId?: string;
  tools?: string[];
}

export interface RunAgentResponse {
  runId: string;
}

export interface AgentSummary {
  id: string;
  name: string;
  description: string;
  category: string;
  isDefault?: boolean;
}

export interface AgentChatOutletContext {
  selectedAgent: AgentSummary | null;
  activeSessionId: string | null;
  setActiveSessionId: (id: string) => void;
  handleNewChat: () => void;
  sessions: import('@/types/chat').ChatSession[];
}

