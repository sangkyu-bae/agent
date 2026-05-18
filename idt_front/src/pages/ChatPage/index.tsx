import { useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import ChatHeader from '@/components/layout/ChatHeader';
import MessageList from '@/components/chat/MessageList';
import ChatInput from '@/components/chat/ChatInput';
import { useGeneralChat, useAgentChat, useAgentSessionMessages } from '@/hooks/useChat';
import { useAuthStore } from '@/store/authStore';
import { queryKeys } from '@/lib/queryKeys';
import type { Message } from '@/types/chat';
import type { AgentChatOutletContext, AgentSummary } from '@/types/agent';

interface EmptyAgentStateProps {
  agent: AgentSummary | null;
}

const EmptyAgentState = ({ agent }: EmptyAgentStateProps) => (
  <div className="flex flex-col items-center justify-center h-full">
    <img
      src="/logo.png"
      alt="상상인플러스저축은행"
      className="h-16 w-16 rounded-2xl shadow-lg mb-6 object-contain"
    />
    <h2 className="text-2xl font-bold text-violet-600 mb-2">
      {agent?.name ?? 'SUPER AI Agent'}와 대화하세요
    </h2>
    <p className="text-[14px] text-zinc-400">
      {agent?.description ?? 'Auto-routing meta agent for all your agents'}
    </p>
  </div>
);

const ChatPage = () => {
  const { selectedAgent, activeSessionId, setActiveSessionId, sessions, refetchSessions } =
    useOutletContext<AgentChatOutletContext>();

  const user = useAuthStore((s) => s.user);
  const userId = user?.id != null ? String(user.id) : undefined;
  const queryClient = useQueryClient();

  const [messagesBySession, setMessagesBySession] = useState<Record<string, Message[]>>({});
  const [useRag, setUseRag] = useState(true);

  const agentId = selectedAgent?.id ?? null;

  const draftSessionIds = useMemo(
    () => new Set(sessions.filter((s) => s.title === '새 대화' && s.messages.length === 0).map((s) => s.id)),
    [sessions],
  );
  const isDraftSession = draftSessionIds.has(activeSessionId ?? '');

  const { data: serverMessages } = useAgentSessionMessages(
    agentId,
    activeSessionId,
    userId,
    { enabled: !!activeSessionId && !isDraftSession },
  );

  const messages = useMemo<Message[]>(() => {
    const local = messagesBySession[activeSessionId ?? ''] ?? [];
    if (local.length > 0) return local;
    return serverMessages ?? [];
  }, [activeSessionId, messagesBySession, serverMessages]);

  const { mutate: sendGeneralChat, isPending: isGeneralPending } = useGeneralChat();
  const { mutate: sendAgentChat, isPending: isAgentPending } = useAgentChat();
  const isPending = isGeneralPending || isAgentPending;

  const addMessage = (sessionId: string, message: Message) => {
    setMessagesBySession((prev) => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] ?? []), message],
    }));
  };

  const syncSessionId = (clientId: string, serverId: string) => {
    if (clientId === serverId) return;
    setMessagesBySession((prev) => {
      const msgs = prev[clientId];
      if (!msgs) return prev;
      const next = { ...prev };
      delete next[clientId];
      next[serverId] = msgs;
      return next;
    });
    setActiveSessionId(serverId);
  };

  const handleSend = (content: string) => {
    if (!activeSessionId) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };
    addMessage(activeSessionId, userMessage);

    const currentSessionId = activeSessionId;

    const onError = () => {
      const errorMessage: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '죄송합니다. 응답을 받지 못했습니다. 잠시 후 다시 시도해주세요.',
        createdAt: new Date().toISOString(),
      };
      addMessage(currentSessionId, errorMessage);
    };

    if (selectedAgent) {
      sendAgentChat(
        {
          agentId: selectedAgent.id,
          query: content,
          user_id: userId ?? '',
          session_id: isDraftSession ? null : currentSessionId,
        },
        {
          onSuccess: (data) => {
            syncSessionId(currentSessionId, data.session_id);

            const assistantMessage: Message = {
              id: data.request_id,
              role: 'assistant',
              content: data.answer,
              createdAt: new Date().toISOString(),
            };
            addMessage(data.session_id, assistantMessage);

            if (userId) {
              queryClient.invalidateQueries({
                queryKey: queryKeys.chat.agentHistory(data.agent_id, userId),
              });
            }
          },
          onError,
        },
      );
    } else {
      sendGeneralChat(
        {
          user_id: userId ?? '',
          session_id: currentSessionId,
          message: content,
          top_k: useRag ? 5 : undefined,
        },
        {
          onSuccess: (data) => {
            syncSessionId(currentSessionId, data.session_id);

            const assistantMessage: Message = {
              id: data.request_id,
              role: 'assistant',
              content: data.answer,
              createdAt: new Date().toISOString(),
              sources: data.sources,
            };
            addMessage(data.session_id, assistantMessage);

            if (agentId && userId) {
              queryClient.invalidateQueries({
                queryKey: queryKeys.chat.agentHistory(agentId, userId),
              });
            }
          },
          onError,
        },
      );
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <ChatHeader
        title={selectedAgent?.name ?? 'SUPER AI Agent'}
        messageCount={messages.length}
      />

      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ maxWidth: '768px', margin: '0 auto', height: '100%' }}>
          {messages.length === 0 ? (
            <EmptyAgentState agent={selectedAgent} />
          ) : (
            <MessageList
              messages={messages}
              isStreaming={isPending}
              onSuggestionClick={handleSend}
            />
          )}
        </div>
      </div>

      <div style={{ background: '#fff' }}>
        <ChatInput
          onSend={handleSend}
          isLoading={isPending}
          useRag={useRag}
          onToggleRag={() => setUseRag((v) => !v)}
        />
      </div>
    </div>
  );
};

export default ChatPage;
