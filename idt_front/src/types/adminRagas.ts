export interface AdminRagasDashboard {
  total_runs: number;
  status_counts: Record<string, number>;
  target_type_counts: Record<string, number>;
  avg_metrics: Record<string, number>;
  recent_runs: EvalRunSummary[];
}

export interface EvalRunSummary {
  id: string;
  eval_type: string;
  target_type: string;
  status: string;
  total_cases: number;
  created_at: string;
  completed_at: string | null;
  summary: Record<string, number>;
}

export interface EvalRunDetail extends EvalRunSummary {
  config: Record<string, unknown>;
  results: EvalResultItem[];
  results_total: number;
}

export interface EvalResultItem {
  id: string;
  question: string;
  answer: string;
  ground_truth: string | null;
  contexts: string[];
  scores: Record<string, number>;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminRagasRunsParams {
  target_type?: string;
  eval_type?: string;
  status?: string;
  limit?: number;
  offset?: number;
}
