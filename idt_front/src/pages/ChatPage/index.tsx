import { useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import ChatHeader from '@/components/layout/ChatHeader';
import MessageList from '@/components/chat/MessageList';
import ChatInput from '@/components/chat/ChatInput';
import ToolPreviewPanel from '@/components/chat/ToolPreviewPanel';
import { useAgentSessionMessages } from '@/hooks/useChat';
import { useChatStream } from '@/hooks/useChatStream';
import { useAgentRunStream } from '@/hooks/useAgentRunStream';
import { agentStepsToToolEvents } from '@/hooks/agentStepToToolEvent';
import { useAuthStore } from '@/store/authStore';
import { useChatPreferencesStore } from '@/store/chatPreferencesStore';
import agentAttachmentService from '@/services/agentAttachmentService';
import { queryKeys } from '@/lib/queryKeys';
import type { Message } from '@/types/chat';
import type { ChartPayload } from '@/types/chart';
import type { AgentAttachmentRef } from '@/types/agentAttachment';
import type { AgentChatOutletContext, AgentSummary } from '@/types/agent';
import type { ChatSource, ChatToolEvent } from '@/hooks/useChatStream';

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

// ws-agent-chat-streaming Design §3.1 — 단일 activeStream 상태(mutex).
// 한 번에 하나만 진행. handleSend가 isPending인 동안 무시.
// chatpage-rerequest-stale-state-fix Design §3.1 — 매 send 마다 streamId 발급.
type ActiveStream =
  | {
      kind: 'chat';
      streamId: string;
      sessionId: string;
      message: string;
      topK?: number;
      placeholderId: string;
    }
  | {
      kind: 'agent';
      streamId: string;
      runId: string;
      agentId: string;
      sessionId: string;
      message: string;
      placeholderId: string;
      // ws-agent-excel-attachment: 업로드된 엑셀 등 첨부 참조
      attachments?: AgentAttachmentRef[];
    };

interface NormalizedView {
  // chatpage-rerequest-stale-state-fix Design §3.4 — stale state 식별용
  streamId: string;
  tokens: string;
  answer: string | null;
  error: { code: string; message: string } | null;
  isDone: boolean;
  toolEvents: ChatToolEvent[];
  sources: ChatSource[];
  // supervisor-chart-builder-node: 답변과 함께 렌더할 Chart.js 페이로드.
  charts: ChartPayload[];
}

const ChatPage = () => {
  const { selectedAgent, activeSessionId, sessions } =
    useOutletContext<AgentChatOutletContext>();

  const user = useAuthStore((s) => s.user);
  const userId = user?.id != null ? String(user.id) : undefined;
  const queryClient = useQueryClient();

  const [messagesBySession, setMessagesBySession] = useState<Record<string, Message[]>>({});
  const [useRag, setUseRag] = useState(true);

  // ws-agent-excel-attachment: 전송 전 대기 중인 엑셀 첨부
  const [pendingAttachment, setPendingAttachment] = useState<
    { ref: AgentAttachmentRef; name: string } | null
  >(null);
  const [attachmentUploading, setAttachmentUploading] = useState(false);

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

  // Design §3.1 — 단일 ActiveStream 상태로 chat / agent stream을 mutually exclusive.
  const [activeStream, setActiveStream] = useState<ActiveStream | null>(null);

  const chatStream = useChatStream({
    streamId: activeStream?.kind === 'chat' ? activeStream.streamId : '',
    sessionId: activeStream?.kind === 'chat' ? activeStream.sessionId : '',
    message: activeStream?.kind === 'chat' ? activeStream.message : '',
    topK: activeStream?.kind === 'chat' ? activeStream.topK : undefined,
    enabled: activeStream?.kind === 'chat',
  });

  const agentRun = useAgentRunStream({
    streamId: activeStream?.kind === 'agent' ? activeStream.streamId : '',
    runId: activeStream?.kind === 'agent' ? activeStream.runId : '',
    agentId: activeStream?.kind === 'agent' ? activeStream.agentId : '',
    query: activeStream?.kind === 'agent' ? activeStream.message : '',
    sessionId: activeStream?.kind === 'agent' ? activeStream.sessionId : undefined,
    attachments: activeStream?.kind === 'agent' ? activeStream.attachments : undefined,
    enabled: activeStream?.kind === 'agent',
  });

  // Design §3.3 — 두 stream을 단일 view로 normalize.
  const view = useMemo<NormalizedView | null>(() => {
    if (activeStream?.kind === 'chat') {
      return {
        streamId: chatStream.streamId,
        tokens: chatStream.tokens,
        answer: chatStream.answer,
        error: chatStream.error,
        isDone: chatStream.isDone,
        toolEvents: chatStream.toolEvents,
        sources: chatStream.sources,
        charts: [],
      };
    }
    if (activeStream?.kind === 'agent') {
      return {
        streamId: agentRun.streamId,
        tokens: agentRun.tokens,
        answer: agentRun.answer,
        error: agentRun.error,
        isDone: agentRun.isDone,
        toolEvents: agentStepsToToolEvents(agentRun.steps),
        sources: [],
        charts: agentRun.charts,
      };
    }
    return null;
  }, [activeStream, chatStream, agentRun]);

  // chatpage-rerequest-stale-state-fix Design §3.4 — view 가 새 streamId 로 갱신되기 전에는 pending 유지.
  const isPending =
    activeStream !== null &&
    (view?.streamId !== activeStream.streamId || !view.isDone);

  const showToolPreview = useChatPreferencesStore((s) => s.showToolPreview);
  const setShowToolPreview = useChatPreferencesStore((s) => s.setShowToolPreview);

  const addMessage = (sessionId: string, message: Message) => {
    setMessagesBySession((prev) => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] ?? []), message],
    }));
  };

  const updateMessage = (sessionId: string, messageId: string, patch: Partial<Message>) => {
    setMessagesBySession((prev) => {
      const list = prev[sessionId];
      if (!list) return prev;
      return {
        ...prev,
        [sessionId]: list.map((m) => (m.id === messageId ? { ...m, ...patch } : m)),
      };
    });
  };

  // 토큰 누적 → placeholder content 갱신 (view 기반).
  // chatpage-rerequest-stale-state-fix Design §3.4 — streamId 일치 가드.
  useEffect(() => {
    if (!activeStream || !view) return;
    if (view.streamId !== activeStream.streamId) return;
    if (view.tokens) {
      updateMessage(activeStream.sessionId, activeStream.placeholderId, {
        content: view.tokens,
      });
    }
  }, [view?.streamId, view?.tokens, activeStream]);

  // CHAT_DONE / CHAT_FAILED / agent_run_completed / agent_run_failed 처리 (view 기반).
  // chatpage-rerequest-stale-state-fix Design §3.4 — streamId 일치 시에만 완료 처리.
  useEffect(() => {
    if (!activeStream || !view) return;
    if (view.streamId !== activeStream.streamId) return;
    if (!view.isDone) return;

    if (view.error) {
      updateMessage(activeStream.sessionId, activeStream.placeholderId, {
        content: `[${view.error.code}] ${view.error.message}`,
        isStreaming: false,
      });
    } else if (view.answer) {
      updateMessage(activeStream.sessionId, activeStream.placeholderId, {
        content: view.answer,
        sources: view.sources,
        charts: view.charts,
        isStreaming: false,
      });
      const historyAgentId =
        activeStream.kind === 'agent' ? activeStream.agentId : agentId;
      if (historyAgentId && userId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chat.agentHistory(historyAgentId, userId),
        });
      }
    }
    setActiveStream(null);
  }, [view?.streamId, view?.isDone, view?.answer, view?.error, view?.sources, view?.charts, activeStream, agentId, userId, queryClient]);

  // ws-agent-excel-attachment: 엑셀 업로드 → file_id 발급 후 대기 첨부로 보관.
  const handleAttachFile = async (file: File) => {
    setAttachmentUploading(true);
    try {
      const res = await agentAttachmentService.uploadExcel(file);
      setPendingAttachment({
        ref: { type: res.type, file_id: res.file_id },
        name: res.filename,
      });
    } catch {
      setPendingAttachment(null);
      // eslint-disable-next-line no-alert
      alert('엑셀 업로드에 실패했습니다. (.xlsx/.xls, 크기 제한 확인)');
    } finally {
      setAttachmentUploading(false);
    }
  };

  const handleSend = (content: string) => {
    if (!activeSessionId) return;
    if (isPending) return; // Q1 mutex: 진행 중이면 무시 (ChatInput isLoading도 차단함)

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };
    addMessage(activeSessionId, userMessage);

    const placeholderId = crypto.randomUUID();
    const placeholder: Message = {
      id: placeholderId,
      role: 'assistant',
      content: '',
      createdAt: new Date().toISOString(),
      isStreaming: true,
    };
    addMessage(activeSessionId, placeholder);

    // 사용자 정의 agent(UUID) → WS /ws/agent/{run_id}
    // general OR SUPER → WS /ws/chat/{session_id}
    // chatpage-rerequest-stale-state-fix Design §3.1 — 매 send 마다 새 streamId 발급.
    const streamId = crypto.randomUUID();
    if (selectedAgent && selectedAgent.id !== 'super') {
      setActiveStream({
        kind: 'agent',
        streamId,
        runId: crypto.randomUUID(),
        agentId: selectedAgent.id,
        sessionId: activeSessionId,
        message: content,
        placeholderId,
        attachments: pendingAttachment ? [pendingAttachment.ref] : undefined,
      });
      setPendingAttachment(null); // 전송과 함께 첨부 소진(run 1회성)
    } else {
      setActiveStream({
        kind: 'chat',
        streamId,
        sessionId: activeSessionId,
        message: content,
        topK: useRag ? 5 : undefined,
        placeholderId,
      });
    }
  };

  const toolEvents = view?.toolEvents ?? [];

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

      {toolEvents.length > 0 && (
        <div style={{ maxWidth: '768px', margin: '0 auto', width: '100%', padding: '0 16px 8px' }}>
          <ToolPreviewPanel
            events={toolEvents}
            visible={showToolPreview}
            onToggleVisible={setShowToolPreview}
          />
        </div>
      )}

      <div style={{ background: '#fff' }}>
        <ChatInput
          onSend={handleSend}
          isLoading={isPending}
          useRag={useRag}
          onToggleRag={() => setUseRag((v) => !v)}
          attachmentEnabled={!!selectedAgent && selectedAgent.id !== 'super'}
          attachmentName={pendingAttachment?.name ?? null}
          attachmentUploading={attachmentUploading}
          onAttachFile={handleAttachFile}
          onRemoveAttachment={() => setPendingAttachment(null)}
        />
      </div>
    </div>
  );
};

export default ChatPage;
