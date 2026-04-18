import apiClient from './api/client';
import authClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ChatSession,
  Message,
  SendMessageRequest,
  SendMessageResponse,
  ConversationChatRequest,
  ConversationChatResponse,
  GeneralChatRequest,
  GeneralChatResponse,
  SessionSummary,
  SessionSummaryListResponse,
  HistoryMessageItem,
  SessionMessagesResponse,
} from '@/types/chat';
import type { ApiResponse, PaginatedResponse } from '@/types/api';

const toChatSession = (summary: SessionSummary): ChatSession => ({
  id: summary.session_id,
  title: summary.last_message?.slice(0, 30) || '새 대화',
  messages: [],
  createdAt: summary.last_message_at,
  updatedAt: summary.last_message_at,
});

const toMessage = (item: HistoryMessageItem): Message => ({
  id: String(item.id),
  role: item.role,
  content: item.content,
  createdAt: item.created_at,
});

export const chatService = {
  /** CHAT-001: General Chat (LangGraph ReAct) — authClient 사용 */
  generalChat: (payload: GeneralChatRequest) =>
    authClient.post<GeneralChatResponse>(API_ENDPOINTS.GENERAL_CHAT, payload),

  /** CONV-001: 멀티턴 대화 API */
  conversationChat: (payload: ConversationChatRequest) =>
    apiClient.post<ConversationChatResponse>(API_ENDPOINTS.CONVERSATION_CHAT, payload),

  getSessions: () =>
    apiClient.get<PaginatedResponse<ChatSession>>(API_ENDPOINTS.CHAT_SESSIONS),

  sendMessage: (payload: SendMessageRequest) =>
    apiClient.post<ApiResponse<SendMessageResponse>>(API_ENDPOINTS.CHAT_MESSAGE, payload),

  getStreamUrl: (sessionId: string) =>
    `${API_ENDPOINTS.CHAT_STREAM}?sessionId=${sessionId}`,

  /** CHAT-HIST-001: 사용자 세션 목록 조회 */
  getConversationSessions: async (userId: string): Promise<ChatSession[]> => {
    const res = await apiClient.get<SessionSummaryListResponse>(
      API_ENDPOINTS.CONVERSATION_SESSIONS,
      { params: { user_id: userId } },
    );
    return res.data.sessions.map(toChatSession);
  },

  /** CHAT-HIST-001: 특정 세션 메시지 조회 */
  getSessionMessages: async (
    sessionId: string,
    userId: string,
  ): Promise<Message[]> => {
    const res = await apiClient.get<SessionMessagesResponse>(
      API_ENDPOINTS.CONVERSATION_SESSION_MESSAGES(sessionId),
      { params: { user_id: userId } },
    );
    return res.data.messages.map(toMessage);
  },
};
