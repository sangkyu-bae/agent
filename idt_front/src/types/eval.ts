// eval-hub: 평가 허브 타입 — 백엔드 /api/ragas 응답과 snake_case 그대로 동기화
// (idt/src/api/routes/ragas_router.py 스키마 대응)

export type EvalTargetType = 'rag' | 'agent' | 'retrieval';
export type EvalRunStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface TestCaseItem {
  question: string;
  ground_truth: string | null;
}

export interface Testset {
  id: string;
  name: string;
  description: string;
  case_count: number;
  created_at: string;
  user_id: string | null;
}

export interface TestsetDetail extends Testset {
  cases: TestCaseItem[];
}

export interface CreateTestsetPayload {
  name: string;
  description: string;
  cases: TestCaseItem[];
}

export interface GeneratedDraft {
  source_filename: string;
  items: TestCaseItem[];
}

export interface MetricInfo {
  key: string;
  name: string;
  description: string;
  target_types: EvalTargetType[];
  requires_ground_truth: boolean;
}

export interface EvalRun {
  id: string;
  eval_type: string;
  target_type: EvalTargetType;
  status: EvalRunStatus;
  total_cases: number;
  created_at: string;
  completed_at: string | null;
  summary: Record<string, number>;
  error_message: string | null;
  config: Record<string, unknown>;
  /** agent-model-benchmark: 스윕 소속 식별. 단독 실행이면 null (목록에선 제외됨) */
  sweep_id?: string | null;
  llm_model_id?: string | null;
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

export interface BatchEvalPayload {
  target_type: EvalTargetType;
  metrics: string[];
  testset_id: string;
  top_k?: number;
  sample_ratio?: number;
  llm_model?: string;
  agent_id?: string;
  collection_name?: string;
}

export interface BatchEvalResponse {
  run_id: string;
  status: string;
  total_cases: number;
  message: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
