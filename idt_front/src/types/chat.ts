import type { ChartPayload } from './chart';
import type { SourceViewerRef } from './sourceViewer';
import type { ToolTrace } from './toolTrace';

export type MessageRole = 'user' | 'assistant' | 'tool';

/** agent-run-source-citations §3.2 — 에이전트 근거 종류 (백엔드 SourceKind wire 값) */
export const SOURCE_KIND = {
  DOCUMENT: 'document',
  WIKI: 'wiki',
  WEB: 'web',
  MCP: 'mcp',
} as const;
export type SourceKind = (typeof SOURCE_KIND)[keyof typeof SOURCE_KIND];

// answer-citation-verification §4.2 — 백엔드 계약: idt/src/application/answer_citation/enricher.py
/** 인용 검증 결과. verified=검증된 인용 있음, none=인용 없음(근거 확인 안 됨) */
export const CITATION_STATUS = {
  VERIFIED: 'verified',
  NONE: 'none',
} as const;
export type CitationStatus = (typeof CITATION_STATUS)[keyof typeof CITATION_STATUS];

/** 문서 칩에 실린 검증된 인용 1건 — no 는 본문 [n] 번호 */
export interface SourceCitationEntry {
  no: number;
  chunk_id: string | null;
  page: number | null;
  /** 청크 안 근거 문장. 청크에서 찾지 못했으면 null (원문 뷰어는 청크 전체 음영) */
  evidence: string | null;
}

export interface SourceCitationInfo {
  status: CitationStatus;
  /** 이 문서의 인용. 빈 배열이면 검색했지만 답변에 쓰지 않은 문서 */
  entries: SourceCitationEntry[];
}

/**
 * 답변 출처. 일반 채팅은 score 가 있고 kind 가 없다.
 * 에이전트 근거는 kind 가 있고, 검색 방식마다 점수 스케일이 달라 score 가 없다.
 */
export interface DocumentSource {
  content: string;
  source: string;
  chunk_id: string;
  score?: number;
  kind?: SourceKind;
  /** kind=web 전용 원문 링크 */
  url?: string;
  /** source-passage-viewer §3.3 — 원문 뷰어 진입 정보(KB 문서 칩 전용). 재진입 API 는 null 을 싣는다 */
  viewer?: SourceViewerRef | null;
  /** answer-citation-verification §4.2 — 인용 검증 결과(문서 칩 전용). 없으면 기존 칩 렌더 */
  citation?: SourceCitationInfo | null;
}

/** GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/sources 응답 */
export interface SessionSourcesResponse {
  session_id: string;
  items: { message_id: number; sources: DocumentSource[] }[];
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  isStreaming?: boolean;
  sources?: DocumentSource[];
  /** 차트 페이로드 (Chart.js config 패스스루). chat-chart-rendering */
  charts?: ChartPayload[];
  /**
   * agent-eval-gate — 평가(👍/👎) 대상 assistant 메시지 id.
   * placeholder(UUID) 메시지가 스트리밍 완료 시 ANSWER_COMPLETED의
   * assistant_message_id로 채워진다. 부재 시 평가 미노출.
   */
  feedbackMessageId?: number;
  /** chat-image-attachment §5.3 FR-17 — 전송한 이미지 썸네일(object URL, 세션 메모리). 히스토리 재조회 시 없음 */
  imagePreviews?: string[];
  /** agent-run-tool-trace — 답변별 도구 실행 내역. 도구 호출이 없으면 없다. */
  toolTrace?: ToolTrace;
  /** tool-access-control FR-11 — 권한이 없어 뺀 도구 (실시간 답변에만 존재, 히스토리 재조회 시 없음) */
  excludedTools?: import('./toolAccess').ExcludedTool[];
  /** agent-token-limit D11 — 한도 도달 사유 (실시간 답변에만 존재, 히스토리 재조회 시 없음) */
  limitReason?: import('./websocket').LimitReason;
}

/** @deprecated Use DocumentSource instead */
export interface SourceChunk {
  documentId: string;
  documentName: string;
  chunkIndex: number;
  content: string;
  score: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
}

export interface SendMessageRequest {
  sessionId: string;
  content: string;
  useRag?: boolean;
}

export interface SendMessageResponse {
  messageId: string;
  sessionId: string;
}

/** CONV-001: POST /api/v1/conversation/chat 요청 */
export interface ConversationChatRequest {
  user_id: string;
  session_id: string;
  message: string;
}

/** CONV-001: POST /api/v1/conversation/chat 응답 */
export interface ConversationChatResponse {
  user_id: string;
  session_id: string;
  answer: string;
  was_summarized: boolean;
  request_id: string;
}

/** CHAT-001: POST /api/v1/chat 요청 */
export interface GeneralChatRequest {
  user_id: string;
  session_id?: string;
  message: string;
  top_k?: number;
}

/** CHAT-001: POST /api/v1/chat 응답 */
export interface GeneralChatResponse {
  user_id: string;
  session_id: string;
  answer: string;
  tools_used: string[];
  sources: DocumentSource[];
  was_summarized: boolean;
  request_id: string;
}

/** CHAT-HIST-001: 세션 요약 (백엔드 응답 원본) */
export interface SessionSummary {
  session_id: string;
  message_count: number;
  last_message: string;
  last_message_at: string;
}

/** CHAT-HIST-001: GET /api/v1/conversations/sessions 응답 */
export interface SessionSummaryListResponse {
  user_id: string;
  sessions: SessionSummary[];
}

/** CHAT-HIST-001: 세션 내 메시지 항목 (백엔드 응답 원본) */
export interface HistoryMessageItem {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  turn_index: number;
  created_at: string;
  /** chat-chart-persistence: Chart.js config 배열 (없으면 null/생략) */
  charts?: ChartPayload[] | null;
}

/** CHAT-HIST-001: GET /api/v1/conversations/sessions/{session_id}/messages 응답 */
export interface SessionMessagesResponse {
  user_id: string;
  session_id: string;
  messages: HistoryMessageItem[];
}

/** AGENT-RUN: POST /api/v1/agents/{agent_id}/run 요청 */
export interface AgentChatRequest {
  query: string;
  user_id: string;
  session_id: string | null;
}

/** AGENT-RUN: POST /api/v1/agents/{agent_id}/run 응답 */
export interface AgentChatResponse {
  agent_id: string;
  query: string;
  answer: string;
  tools_used: string[];
  request_id: string;
  session_id: string;
}

/** 에이전트별 세션 목록 응답 */
export interface AgentSessionListResponse {
  user_id: string;
  agent_id: string;
  sessions: SessionSummary[];
}

/** 에이전트별 세션 메시지 응답 */
export interface AgentSessionMessagesResponse {
  user_id: string;
  agent_id: string;
  session_id: string;
  messages: HistoryMessageItem[];
}
