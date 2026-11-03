// agent-eval-gate: 답변 평가 타입. Mirror to backend src/application/eval/api_schemas.py.
import type { RetrievalDto } from '@/types/agentRunAdmin';

export type Rating = 'up' | 'down';

export interface MyFeedback {
  message_id: number;
  rating: Rating | null; // null = 평가 없음/취소됨
  comment?: string | null;
}

export interface AgentEvalStat {
  agent_id: string;
  up: number;
  down: number;
  satisfaction: number | null; // 0건이면 null
}

export interface RecentNegativeItem {
  message_id: number;
  agent_id: string;
  comment?: string | null;
  created_at?: string | null;
}

// negative-feedback-drilldown: Mirror to backend src/interfaces/schemas/eval_drilldown_response.py.
export interface QueryRetrievalGroup {
  search_query: string | null;
  query_source: string | null;
  search_mode: string | null;
  sources: RetrievalDto[];
}

export interface MessageRunRetrievals {
  run_id: string;
  agent_id: string;
  langsmith_run_url: string | null;
  groups: QueryRetrievalGroup[];
}

export interface NegativeDrilldown {
  message_id: number;
  agent_id: string;
  question: string | null; // null = 질문 복원 실패
  answer: string;
  runs: MessageRunRetrievals[];
}
