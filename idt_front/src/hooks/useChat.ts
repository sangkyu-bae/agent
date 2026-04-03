import { useQuery, useMutation } from '@tanstack/react-query';
import { chatService } from '@/services/chatService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type { SendMessageRequest, ConversationChatRequest } from '@/types/chat';

/** 채팅 세션 목록 조회 */
export const useChatSessions = () =>
  useQuery({
    queryKey: queryKeys.chat.sessions(),
    queryFn: () => chatService.getSessions().then((r) => r.data),
  });

/** 메시지 전송 뮤테이션 (legacy) */
export const useSendMessage = () =>
  useMutation({
    mutationFn: (payload: SendMessageRequest) =>
      chatService.sendMessage(payload).then((r) => r.data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.chat.session(variables.sessionId),
      });
    },
  });

/** CONV-001: 멀티턴 대화 뮤테이션 */
export const useConversationChat = () =>
  useMutation({
    mutationFn: (payload: ConversationChatRequest) =>
      chatService.conversationChat(payload).then((r) => r.data),
  });
