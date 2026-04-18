export type MessageRole = 'user' | 'assistant' | 'tool';

/** General Chat API 문서 출처 */
export interface DocumentSource {
  content: string;
  source: string;
  chunk_id: string;
  score: number;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  isStreaming?: boolean;
  sources?: DocumentSource[];
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
}

/** CHAT-HIST-001: GET /api/v1/conversations/sessions/{session_id}/messages 응답 */
export interface SessionMessagesResponse {
  user_id: string;
  session_id: string;
  messages: HistoryMessageItem[];
}
