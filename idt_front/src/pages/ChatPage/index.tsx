import { useState, useRef, useEffect } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import ChatHeader from '@/components/layout/ChatHeader';
import MessageList from '@/components/chat/MessageList';
import ChatInput from '@/components/chat/ChatInput';
import { useConversationChat } from '@/hooks/useChat';
import type { Message, ChatSession } from '@/types/chat';

/** 브라우저 세션 동안 유지되는 익명 user_id */
const getUserId = (): string => {
  const key = 'idt_user_id';
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
};

const createSession = (): ChatSession => ({
  id: crypto.randomUUID(),
  title: '새 대화',
  messages: [],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
});

const ChatPage = () => {
  const userId = useRef(getUserId()).current;

  const [sessions, setSessions] = useState<ChatSession[]>(() => [createSession()]);
  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    const first = createSession();
    return first.id;
  });
  const [messagesBySession, setMessagesBySession] = useState<Record<string, Message[]>>({});
  const [useRag, setUseRag] = useState(true);

  // 첫 세션 id를 sessions 초기값과 동기화
  useEffect(() => {
    setActiveSessionId(sessions[0].id);
  }, []);

  const { mutate: sendChat, isPending } = useConversationChat();

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const messages = messagesBySession[activeSessionId] ?? [];

  const addMessage = (sessionId: string, message: Message) => {
    setMessagesBySession((prev) => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] ?? []), message],
    }));
  };

  const updateSessionTitle = (sessionId: string, title: string) => {
    setSessions((prev) =>
      prev.map((s) => (s.id === sessionId ? { ...s, title } : s)),
    );
  };

  const handleSend = (content: string) => {
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };
    addMessage(activeSessionId, userMessage);

    // 첫 메시지로 세션 제목 설정
    if ((messagesBySession[activeSessionId] ?? []).length === 0) {
      updateSessionTitle(activeSessionId, content.slice(0, 30));
    }

    sendChat(
      { user_id: userId, session_id: activeSessionId, message: content },
      {
        onSuccess: (data) => {
          const assistantMessage: Message = {
            id: data.request_id,
            role: 'assistant',
            content: data.answer,
            createdAt: new Date().toISOString(),
          };
          addMessage(activeSessionId, assistantMessage);
        },
        onError: () => {
          const errorMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: '죄송합니다. 응답을 받지 못했습니다. 잠시 후 다시 시도해주세요.',
            createdAt: new Date().toISOString(),
          };
          addMessage(activeSessionId, errorMessage);
        },
      },
    );
  };

  const handleNewChat = () => {
    const newSession = createSession();
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden', background: '#fff' }}>
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={setActiveSessionId}
        onNewChat={handleNewChat}
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
