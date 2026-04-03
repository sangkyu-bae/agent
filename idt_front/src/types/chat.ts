export type MessageRole = 'user' | 'assistant' | 'tool';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  isStreaming?: boolean;
  sources?: SourceChunk[];
}

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
