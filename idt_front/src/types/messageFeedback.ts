// agent-eval-gate: 답변 평가 타입. Mirror to backend src/application/eval/api_schemas.py.

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
