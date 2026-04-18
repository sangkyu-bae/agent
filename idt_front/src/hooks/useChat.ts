import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { chatService } from '@/services/chatService';
import { queryKeys } from '@/lib/queryKeys';
import type {
  SendMessageRequest,
  ConversationChatRequest,
  GeneralChatRequest,
} from '@/types/chat';

/** 채팅 세션 목록 조회 */
export const useChatSessions = () =>
  useQuery({
    queryKey: queryKeys.chat.sessions(),
    queryFn: () => chatService.getSessions().then((r) => r.data),
  });

/** 메시지 전송 뮤테이션 (legacy) */
export const useSendMessage = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SendMessageRequest) =>
      chatService.sendMessage(payload).then((r) => r.data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.chat.session(variables.sessionId),
      });
    },
  });
};

/** CHAT-001: General Chat 뮤테이션 — onSuccess 시 history invalidate */
export const useGeneralChat = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: GeneralChatRequest) =>
      chatService.generalChat(payload).then((r) => r.data),
    onSuccess: (data, variables) => {
      const userId = variables.user_id;
      if (!userId) return;
      queryClient.invalidateQueries({
        queryKey: queryKeys.chat.history(userId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.chat.sessionMessages(data.session_id, userId),
      });
    },
  });
};

/** @deprecated Use useGeneralChat instead */
export const useConversationChat = () =>
  useMutation({
    mutationFn: (payload: ConversationChatRequest) =>
      chatService.conversationChat(payload).then((r) => r.data),
  });

/** CHAT-HIST-001: 사용자 대화 세션 목록 */
export const useConversationSessions = (userId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.chat.history(userId ?? ''),
    queryFn: () => chatService.getConversationSessions(userId as string),
    enabled: !!userId,
    staleTime: 60_000,
  });

/** CHAT-HIST-001: 특정 세션 메시지 (lazy) */
export const useSessionMessages = (
  sessionId: string | null,
  userId: string | undefined,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: queryKeys.chat.sessionMessages(sessionId ?? '', userId ?? ''),
    queryFn: () =>
      chatService.getSessionMessages(sessionId as string, userId as string),
    enabled: !!sessionId && !!userId && (options?.enabled ?? true),
    staleTime: 60_000,
  });
