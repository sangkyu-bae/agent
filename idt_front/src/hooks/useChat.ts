import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { chatService } from '@/services/chatService';
import { queryKeys } from '@/lib/queryKeys';
import { GENERAL_CHAT_AGENT_ID } from '@/constants/agent';
import {
  attachSessionSources,
  toSessionSourceMap,
  type SessionSourceMap,
} from '@/utils/sessionSources';
import {
  attachSessionToolTraces,
  toSessionToolTraceMap,
  type SessionToolTraceMap,
} from '@/utils/sessionToolTraces';
import type {
  SendMessageRequest,
  ConversationChatRequest,
  GeneralChatRequest,
  AgentChatRequest,
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

/** 에이전트 전용 채팅 뮤테이션 — POST /api/v1/agents/{agent_id}/run */
export const useAgentChat = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, ...payload }: AgentChatRequest & { agentId: string }) =>
      chatService.agentChat(agentId, payload).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.chat.agentHistory(data.agent_id, ''),
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

/** 에이전트별 세션 목록 (에이전트 전환 시 자동 재요청) */
export const useAgentSessions = (
  agentId: string | null,
  userId: string | undefined,
) =>
  useQuery({
    queryKey: queryKeys.chat.agentHistory(agentId ?? '', userId ?? ''),
    queryFn: () => chatService.getAgentSessions(agentId!, userId!),
    enabled: !!agentId && !!userId,
    staleTime: 60_000,
  });

/** 에이전트별 세션 메시지 */
export const useAgentSessionMessages = (
  agentId: string | null,
  sessionId: string | null,
  userId: string | undefined,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: queryKeys.chat.agentSessionMessages(
      agentId ?? '', sessionId ?? '', userId ?? '',
    ),
    queryFn: async () => {
      // agent-run-source-citations §6.1 — 근거는 부가 정보라 실패해도 메시지는 표시한다.
      // agent-run-tool-trace §6 — 도구 실행 내역도 부가 정보라 실패해도 메시지를 표시한다.
      const [messages, sources, traces] = await Promise.all([
        chatService.getAgentSessionMessages(agentId!, sessionId!, userId!),
        loadSessionSources(agentId!, sessionId!),
        loadSessionToolTraces(agentId!, sessionId!),
      ]);
      return attachSessionToolTraces(attachSessionSources(messages, sources), traces);
    },
    enabled: !!agentId && !!sessionId && !!userId && (options?.enabled ?? true),
    staleTime: 60_000,
  });

const loadSessionSources = async (
  agentId: string,
  sessionId: string,
): Promise<SessionSourceMap> => {
  // 일반 채팅은 에이전트 근거 계약의 범위 밖이다 (Plan §2.2).
  if (agentId === GENERAL_CHAT_AGENT_ID) return {};
  try {
    return toSessionSourceMap(await chatService.getAgentSessionSources(agentId, sessionId));
  } catch {
    return {};
  }
};

const loadSessionToolTraces = async (
  agentId: string,
  sessionId: string,
): Promise<SessionToolTraceMap> => {
  // 일반 채팅은 에이전트 내역 계약의 범위 밖이다 (Plan §2.2).
  if (agentId === GENERAL_CHAT_AGENT_ID) return {};
  try {
    return toSessionToolTraceMap(await chatService.getAgentSessionToolTraces(agentId, sessionId));
  } catch {
    return {};
  }
};
