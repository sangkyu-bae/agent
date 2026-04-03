import apiClient from './api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ChatSession,
  SendMessageRequest,
  SendMessageResponse,
  ConversationChatRequest,
  ConversationChatResponse,
} from '@/types/chat';
import type { ApiResponse, PaginatedResponse } from '@/types/api';

export const chatService = {
  /** CONV-001: 멀티턴 대화 API */
  conversationChat: (payload: ConversationChatRequest) =>
    apiClient.post<ConversationChatResponse>(API_ENDPOINTS.CONVERSATION_CHAT, payload),

  getSessions: () =>
    apiClient.get<PaginatedResponse<ChatSession>>(API_ENDPOINTS.CHAT_SESSIONS),

  sendMessage: (payload: SendMessageRequest) =>
    apiClient.post<ApiResponse<SendMessageResponse>>(API_ENDPOINTS.CHAT_MESSAGE, payload),

  getStreamUrl: (sessionId: string) =>
    `${API_ENDPOINTS.CHAT_STREAM}?sessionId=${sessionId}`,
};
