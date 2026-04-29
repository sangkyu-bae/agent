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

export const MOCK_AGENTS: AgentSummary[] = [
  {
    id: 'super-ai',
    name: 'SUPER AI Agent',
    description: 'Auto-routing meta agent for all your agents',
    category: '기본',
    isDefault: true,
  },
  {
    id: 'doc-rag',
    name: '사내 문서 RAG 챗봇',
    description: '업로드된 사내 문서를 기반으로 정보를 검색합니다',
    category: '미분류',
  },
  {
    id: 'trading-assistant',
    name: 'AI 트레이딩 어시스턴트',
    description: '시장 데이터, 기술적 분석, 뉴스 및 트렌드를 기반으로 투자 인사이트를 제공합니다',
    category: '미분류',
  },
  {
    id: 'doc-rag-2',
    name: '사내 문서 RAG 챗봇',
    description: '업로드된 사내 문서를 기반으로 정보를 검색합니다',
    category: '미분류',
  },
];
