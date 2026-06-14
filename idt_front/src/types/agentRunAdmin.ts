/**
 * Agent Run Admin Dashboard 타입 (M5).
 * 백엔드 응답 스키마 1:1 매핑 — idt/src/interfaces/schemas/agent_run_response.py
 */

/** Run 상태 — RunStatus enum */
export type RunStatus = 'RUNNING' | 'SUCCESS' | 'FAILED' | 'CANCELLED';

/** Run 목록 한 행 (light — steps/tool_calls 미포함) */
export interface RunRow {
  id: string;
  user_id: string;
  agent_id: string;
  conversation_id: string;
  status: string;
  started_at: string; // ISO datetime
  ended_at: string | null;
  latency_ms: number | null;
  total_tokens: number;
  total_cost_usd: string | number; // Decimal serialized
  llm_call_count: number;
  error_message: string | null;
}

/** Run 목록 응답 (페이지네이션) */
export interface RunListResponse {
  from_dt: string | null;
  to_dt: string | null;
  limit: number;
  offset: number;
  total: number;
  rows: RunRow[];
}

/** Run 목록 조회 파라미터 */
export interface AdminRunsParams {
  from?: string;
  to?: string;
  user_id?: string;
  agent_id?: string;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}

/** 대시보드 카드 4종 요약 */
export interface UsageSummary {
  from_dt: string;
  to_dt: string;
  total_runs: number;
  success_runs: number;
  failed_runs: number;
  success_rate: number; // 0..1
  total_tokens: number;
  total_cost_usd: string | number;
}

/** 일자별 시계열 1포인트 */
export interface UsageTimeseriesPoint {
  bucket: string; // YYYY-MM-DD
  run_count: number;
  total_tokens: number;
  total_cost_usd: string | number;
}

/** 시계열 응답 */
export interface UsageTimeseriesResponse {
  from_dt: string;
  to_dt: string;
  bucket: 'day';
  points: UsageTimeseriesPoint[];
}

/** 기간 필터 (route 공통) */
export interface PeriodParams {
  from?: string;
  to?: string;
}

/** 사용자별 집계 행 (M4 reuse) */
export interface UsageByUserRow {
  user_id: string;
  total_tokens: number;
  total_cost_usd: string | number;
  call_count: number;
}

export interface UsageByUserResponse {
  from_dt: string;
  to_dt: string;
  rows: UsageByUserRow[];
}

/** LLM 모델별 집계 행 (M4 reuse) */
export interface UsageByLlmRow {
  llm_model_id: string | null;
  provider: string;
  model_name: string;
  total_tokens: number;
  total_cost_usd: string | number;
  call_count: number;
}

export interface UsageByLlmResponse {
  from_dt: string;
  to_dt: string;
  rows: UsageByLlmRow[];
}

/** 노드별 집계 행 (M4 reuse) */
export interface UsageByNodeRow {
  node_name: string;
  call_count: number;
  total_tokens: number;
  total_cost_usd: string | number;
}

export interface UsageByNodeResponse {
  from_dt: string;
  to_dt: string;
  rows: UsageByNodeRow[];
}

/** Run 상세 응답 (기존 M4 schema 기반) */
export interface TokenUsageDto {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface CostUsdDto {
  input_usd: string | number;
  output_usd: string | number;
  total_usd: string | number;
}

export interface RetrievalDto {
  id: string;
  collection_name: string;
  document_id: string | null;
  chunk_id: string | null;
  score: number | null;
  rank_index: number | null;
  content_preview: string | null;
  created_at: string;
}

export interface LlmCallDto {
  id: string;
  purpose: string | null;
  provider: string;
  model_name: string;
  llm_model_id: string | null;
  token_usage: TokenUsageDto;
  cost_usd: CostUsdDto;
  latency_ms: number | null;
  status: string;
  created_at: string;
}

export interface ToolCallDto {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown> | null;
  result_summary: string | null;
  latency_ms: number | null;
  status: string;
  retrievals: RetrievalDto[];
  llm_calls: LlmCallDto[];
}

export interface StepDto {
  id: string;
  step_index: number;
  node_name: string;
  node_type: string;
  status: string;
  input_summary: string | null;
  output_summary: string | null;
  started_at: string;
  ended_at: string | null;
  latency_ms: number | null;
  error_text: string | null;
  llm_calls: LlmCallDto[];
  tool_calls: ToolCallDto[];
}

export interface RunDto {
  id: string;
  status: string;
  user_id: string;
  agent_id: string;
  conversation_id: string;
  llm_model_id: string | null;
  langgraph_thread_id: string;
  langsmith_trace_id: string | null;
  langsmith_run_url: string | null;
  token_usage: TokenUsageDto;
  cost_usd: CostUsdDto;
  llm_call_count: number;
  started_at: string;
  ended_at: string | null;
  latency_ms: number | null;
  error_message: string | null;
}

export interface RunDetailResponse {
  run: RunDto;
  steps: StepDto[];
  orphan_llm_calls: LlmCallDto[];
}
