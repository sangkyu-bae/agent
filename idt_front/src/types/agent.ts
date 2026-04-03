export type AgentStatus = 'idle' | 'thinking' | 'tool_calling' | 'responding' | 'error';

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
