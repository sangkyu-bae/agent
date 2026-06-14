/**
 * Frontend WebSocket message types.
 *
 * Mirror of backend `src/domain/agent_run/value_objects.py::AgentRunEventType`
 * via the WS adapter `src/infrastructure/agent_run/ws_adapter.py`.
 *
 * Design fe-websocket-integration-guide §3.3.
 */

import type { ChartPayload } from './chart';

export interface WSEnvelope<T = unknown> {
  type: string;
  data: T;
  timestamp?: string;
  metadata?: { seq?: number; ts?: string; [k: string]: unknown };
}

// ── Agent run message payloads ───────────────────────────────────────────

export interface AgentRunStartedData {
  run_id: string | null;
  session_id: string;
  agent_id: string;
}

export interface AgentNodeStartedData {
  node_name: string;
  node_type: string;
}

export interface AgentNodeCompletedData {
  node_name: string;
  duration_ms: number;
}

// agent-chat-reasoning-display Design §3.3
export interface AgentStepReasoningData {
  step_name: string;
  reasoning: string;
  next_worker: string;
}

export interface AgentToolStartedData {
  tool_name: string;
  tool_call_id: string;
  input_preview: string;
}

export interface AgentToolCompletedData {
  tool_name: string;
  tool_call_id: string;
  output_preview: string;
  duration_ms: number;
}

export interface AgentTokenData {
  chunk: string;
  node_name: string;
}

export interface AgentAnswerCompletedData {
  answer: string;
  tools_used: string[];
  /**
   * 차트 페이로드 (Chart.js config 패스스루). supervisor-chart-builder-node.
   * 필드 부재 시 차트 미표시(하위호환).
   */
  charts?: ChartPayload[];
}

export interface AgentRunCompletedData {
  run_id: string | null;
  langsmith_run_url: string | null;
}

export interface AgentRunFailedData {
  code: string;
  message: string;
}

// ── Discriminated union ──────────────────────────────────────────────────

export type AgentRunMessage =
  | (WSEnvelope<AgentRunStartedData>     & { type: 'agent_run_started' })
  | (WSEnvelope<AgentNodeStartedData>    & { type: 'agent_node_started' })
  | (WSEnvelope<AgentNodeCompletedData>  & { type: 'agent_node_completed' })
  | (WSEnvelope<AgentStepReasoningData>  & { type: 'agent_step_reasoning' })
  | (WSEnvelope<AgentToolStartedData>    & { type: 'agent_tool_started' })
  | (WSEnvelope<AgentToolCompletedData>  & { type: 'agent_tool_completed' })
  | (WSEnvelope<AgentTokenData>          & { type: 'agent_token' })
  | (WSEnvelope<AgentAnswerCompletedData> & { type: 'agent_answer_completed' })
  | (WSEnvelope<AgentRunCompletedData>   & { type: 'agent_run_completed' })
  | (WSEnvelope<AgentRunFailedData>      & { type: 'agent_run_failed' });

// ── Outbound (client → server) ───────────────────────────────────────────

export interface SubscribeAgentRunPayload {
  type: 'subscribe';
  agent_id: string;
  query: string;
  session_id?: string;
}

// ── General Chat stream message payloads ────────────────────────────────
// Mirror of backend `src/domain/general_chat/value_objects.py::ChatEventType`
// via the adapter `src/infrastructure/general_chat/ws_adapter.py`.
// ws-chat-streaming Design §3.6.

export interface ChatSource {
  content: string;
  source: string;
  chunk_id: string;
  score: number;
}

export interface ChatStartedData {
  session_id: string;
}

export interface ChatTokenData {
  chunk: string;
}

// agent-chat-reasoning-display Design §3.3
export interface ChatStepReasoningData {
  step_name: string;
  reasoning: string;
  tool_calls: string[];
}

export interface ChatToolStartedData {
  tool_name: string;
  tool_call_id: string;
  input_preview: string;
}

export interface ChatToolCompletedData {
  tool_name: string;
  tool_call_id: string;
  output_preview: string;
  duration_ms: number;
}

export interface ChatAnswerCompletedData {
  answer: string;
  tools_used: string[];
  sources: ChatSource[];
  was_summarized: boolean;
  /**
   * 차트 페이로드 (Chart.js config 패스스루). chat-chart-rendering.
   * 백엔드 협의 후 연동 — 필드 부재 시 차트 미표시(하위호환).
   */
  charts?: ChartPayload[];
}

export interface ChatDoneData {
  session_id: string;
}

export interface ChatFailedData {
  code: string;
  message: string;
}

export type ChatMessage =
  | (WSEnvelope<ChatStartedData>          & { type: 'chat_started' })
  | (WSEnvelope<ChatTokenData>            & { type: 'chat_token' })
  | (WSEnvelope<ChatStepReasoningData>    & { type: 'chat_step_reasoning' })
  | (WSEnvelope<ChatToolStartedData>      & { type: 'chat_tool_started' })
  | (WSEnvelope<ChatToolCompletedData>    & { type: 'chat_tool_completed' })
  | (WSEnvelope<ChatAnswerCompletedData>  & { type: 'chat_answer_completed' })
  | (WSEnvelope<ChatDoneData>             & { type: 'chat_done' })
  | (WSEnvelope<ChatFailedData>           & { type: 'chat_failed' });

export interface SubscribeChatPayload {
  type: 'subscribe';
  message: string;
  top_k?: number;
  llm_model_id?: string;
}
