// agent-model-benchmark: 모델 스윕 타입 — 백엔드 /api/ragas/sweeps 응답과
// snake_case 그대로 동기화 (idt/src/application/eval_sweep/schemas.py 대응).

export type SweepStatus = 'pending' | 'running' | 'completed' | 'failed';

/** 스윕당 모델 상한 — 백엔드 SweepPolicy.MAX_MODELS와 같은 값이어야 한다. */
export const SWEEP_MAX_MODELS = 5;

/** 재현성을 위해 서버가 0으로 고정한다 (Design D9). 화면은 읽기전용으로 표시만 한다. */
export const SWEEP_FIXED_TEMPERATURE = 0;

/**
 * 스윕은 agent 대상 전용이라 RAGAS 메트릭이 3개로 제한된다.
 * (idt/src/domain/ragas/policies.py TARGET_METRICS['agent'])
 * faithfulness·context_* 를 보내면 백엔드가 422로 거절한다.
 */
export const SWEEP_AVAILABLE_METRICS = [
  { key: 'answer_relevancy', label: '답변 관련성' },
  { key: 'answer_correctness', label: '답변 정확성' },
  { key: 'answer_similarity', label: '답변 유사도' },
] as const;

/** 매트릭스 표에서 값이 클수록 좋은 지표 / 작을수록 좋은 지표 구분. */
export const SWEEP_LOWER_IS_BETTER = ['cost_usd', 'latency_p50_ms', 'latency_p95_ms'] as const;

export interface PerModelEstimate {
  llm_model_id: string;
  display_name: string;
  estimated_cost_usd: string;
}

export interface SweepEstimate {
  case_count: number;
  model_count: number;
  total_calls: number;
  estimated_cost_usd: string;
  estimated_minutes: number;
  basis: {
    source?: string;
    avg_prompt_tokens?: number;
    avg_completion_tokens?: number;
    sample_size?: number;
    judge_cost_usd?: string;
  };
  per_model: PerModelEstimate[];
}

export interface SweepEstimatePayload {
  agent_id: string;
  testset_id: string;
  model_ids: string[];
  judge_llm_model_id: string | null;
  metrics: string[];
}

export interface CreateSweepPayload extends SweepEstimatePayload {
  name: string;
}

export interface CreateSweepResponse {
  sweep_id: string;
  status: SweepStatus;
  total_runs: number;
  estimated_cost_usd: string | null;
  message: string;
}

/** 매트릭스 한 행 = 모델 1개. 측정 불가 지표는 null(N/A) — 0과 구분해야 한다. */
export interface SweepRow {
  run_id: string;
  llm_model_id: string | null;
  llm_model_name: string | null;
  status: SweepStatus;
  quality: Record<string, number | null>;
  cost_usd: string | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  tool_f1: number | null;
  measured_cases: number;
  failed_cases: number;
  error_message: string | null;
}

export interface SweepSummary {
  id: string;
  name: string;
  agent_id: string;
  testset_id: string;
  judge_llm_model_id: string | null;
  temperature: number;
  status: SweepStatus;
  total_runs: number;
  completed_runs: number;
  estimated_cost_usd: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface SweepDetail extends SweepSummary {
  model_ids: string[];
  metrics: string[];
  rows: SweepRow[];
  /** 실험 조건 — 어떤 에이전트·테스트셋이었는지 (G-2) */
  agent_name: string | null;
  testset_name: string | null;
  case_count: number;
  /** 실제 지출 합계. 측정된 행이 없으면 null(N/A) (G-1) */
  actual_cost_usd: string | null;
}

export const SWEEP_STATUS_BADGE: Record<
  SweepStatus,
  { label: string; cls: string }
> = {
  pending: { label: '대기', cls: 'bg-zinc-100 text-zinc-500' },
  running: { label: '실행 중', cls: 'bg-blue-50 text-blue-600' },
  completed: { label: '완료', cls: 'bg-emerald-50 text-emerald-600' },
  failed: { label: '실패', cls: 'bg-red-50 text-red-600' },
};
