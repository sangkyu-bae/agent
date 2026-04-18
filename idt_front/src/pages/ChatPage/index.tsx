import { useMemo, useState } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import ChatHeader from '@/components/layout/ChatHeader';
import MessageList from '@/components/chat/MessageList';
import ChatInput from '@/components/chat/ChatInput';
import {
  useGeneralChat,
  useConversationSessions,
  useSessionMessages,
} from '@/hooks/useChat';
import { useAuthStore } from '@/store/authStore';
import type { Message, ChatSession } from '@/types/chat';

const createDraftSession = (): ChatSession => ({
  id: crypto.randomUUID(),
  title: '새 대화',
  messages: [],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
});

const ChatPage = () => {
  const user = useAuthStore((s) => s.user);
  const userId = user?.id != null ? String(user.id) : undefined;

  const initialDraft = useState(() => createDraftSession())[0];
  const [draftSessions, setDraftSessions] = useState<ChatSession[]>([initialDraft]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(initialDraft.id);
  const [messagesBySession, setMessagesBySession] = useState<Record<string, Message[]>>({});
  const [useRag, setUseRag] = useState(true);

  const {
    data: serverSessions = [],
    isLoading: sessionsLoading,
    isError: sessionsError,
    refetch: refetchSessions,
  } = useConversationSessions(userId);

  const sessions = useMemo<ChatSession[]>(() => {
    const serverIds = new Set(serverSessions.map((s) => s.id));
    const drafts = draftSessions.filter((s) => !serverIds.has(s.id));
    return [...drafts, ...serverSessions];
  }, [draftSessions, serverSessions]);

  const isDraftSession = draftSessions.some((s) => s.id === activeSessionId);

  const { data: serverMessages } = useSessionMessages(
    activeSessionId,
    userId,
    { enabled: !!activeSessionId && !isDraftSession },
  );

  const messages = useMemo<Message[]>(() => {
    const local = messagesBySession[activeSessionId ?? ''] ?? [];
    if (local.length > 0) return local;
    return serverMessages ?? [];
  }, [activeSessionId, messagesBySession, serverMessages]);

  const activeSession = sessions.find((s) => s.id === activeSessionId);

  const { mutate: sendChat, isPending } = useGeneralChat();

  const addMessage = (sessionId: string, message: Message) => {
    setMessagesBySession((prev) => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] ?? []), message],
    }));
  };

  const syncSessionId = (clientId: string, serverId: string) => {
    if (clientId === serverId) return;
    setDraftSessions((prev) => prev.filter((s) => s.id !== clientId));
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
    sendChat(
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
        },
        onError: () => {
          const errorMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: '죄송합니다. 응답을 받지 못했습니다. 잠시 후 다시 시도해주세요.',
            createdAt: new Date().toISOString(),
          };
          addMessage(currentSessionId, errorMessage);
        },
      },
    );
  };

  const handleNewChat = () => {
    const newSession = createDraftSession();
    setDraftSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  };

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden', background: '#fff' }}>
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        isLoading={sessionsLoading}
        isError={sessionsError}
        onRetry={() => refetchSessions()}
      />

      <main style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', background: '#fff' }}>
        <ChatHeader
          title={activeSession?.title ?? '새 대화'}
          messageCount={messages.length}
        />

        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ maxWidth: '768px', margin: '0 auto', height: '100%' }}>
            <MessageList
              messages={messages}
              isStreaming={isPending}
              onSuggestionClick={handleSend}
            />
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
      </main>
    </div>
  );
};

export default ChatPage;
