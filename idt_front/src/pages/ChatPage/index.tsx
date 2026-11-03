import { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import ChatHeader from '@/components/layout/ChatHeader';
import MessageList, { SuggestionCards, type Suggestion } from '@/components/chat/MessageList';
import ChatInput from '@/components/chat/ChatInput';
import ToolPreviewPanel from '@/components/chat/ToolPreviewPanel';
import ExcelPreviewModal from '@/components/chat/ExcelPreviewModal';
import EmptyState from '@/components/ui/EmptyState';
import { AlertTriangle, Loader2, MessageSquare } from 'lucide-react';
import { useAgentSessionMessages } from '@/hooks/useChat';
import { useChatStream } from '@/hooks/useChatStream';
import { useAgentRunStream } from '@/hooks/useAgentRunStream';
import { agentStepsToToolEvents } from '@/hooks/agentStepToToolEvent';
import { useAuthStore } from '@/store/authStore';
import { useChatPreferencesStore } from '@/store/chatPreferencesStore';
import {
  extractJobError,
  isJobConflictError,
  useEnqueueJob,
  useJobHistory,
} from '@/hooks/useBackgroundJobs';
import { isJobActive } from '@/types/backgroundJob';
import agentAttachmentService from '@/services/agentAttachmentService';
import { ApiError } from '@/services/api/ApiError';
import { useLlmModels } from '@/hooks/useLlmModels';
import { queryKeys } from '@/lib/queryKeys';
import type { DocumentSource, Message } from '@/types/chat';
import type { ChartPayload } from '@/types/chart';
import {
  ATTACHMENT_ERROR_MESSAGES,
  VISION_DISABLED_REASON,
  type AgentAttachmentRef,
  type AttachmentErrorCode,
  type PendingAttachment,
} from '@/types/agentAttachment';
import {
  isExcelFile,
  isImageFile,
  rejectReasonMessage,
  validateImageFiles,
} from '@/utils/imageAttachmentValidators';
import type { AgentChatOutletContext, AgentSummary } from '@/types/agent';
import type { ChatToolEvent } from '@/hooks/useChatStream';

interface EmptyAgentStateProps {
  agent: AgentSummary | null;
  onSuggestionClick?: (text: string) => void;
}

// chat-image-attachment §6.1 (Analysis G-I6): 업로드 오류를 코드·상태별 안내로 바꾼다.
const uploadErrorMessage = (e: unknown): string => {
  if (e instanceof ApiError) {
    if (e.code === 'ATTACHMENT_TOO_LARGE' || e.status === 413) {
      return '파일이 너무 큽니다. 이미지는 장당 10MB, 엑셀도 10MB 이하여야 합니다.';
    }
    if (e.code === 'INVALID_ATTACHMENT' || e.status === 400) {
      return '지원하지 않는 파일입니다. 이미지는 png/jpg/webp, 엑셀은 xlsx/xls 만 첨부할 수 있습니다.';
    }
  }
  return '첨부 업로드에 실패했습니다. 형식과 크기 제한을 확인해 주세요.';
};

// agent-opener §5.2: 에이전트 오프너 → 제안 카드 항목. super·없음이면 undefined(고정 4종 유지)
const openerSuggestions = (agent: AgentSummary | null): Suggestion[] | undefined => {
  if (!agent || agent.id === 'super' || !agent.openers || agent.openers.length === 0) {
    return undefined;
  }
  return agent.openers.map((text) => ({ label: text, text, icon: MessageSquare }));
};

// Design Ref: ui-redesign-chat §5.4 — ui/EmptyState 1종 + 제안 카드 (G-01)
const EmptyAgentState = ({ agent, onSuggestionClick }: EmptyAgentStateProps) => (
  <div className="flex h-full items-center justify-center pb-16">
    <EmptyState
      icon={
        <img
          src="/logo.png"
          alt="상상인플러스저축은행"
          className="h-14 w-14 rounded-xl object-contain shadow-sm"
        />
      }
      iconUnstyled
      title={`${agent?.name ?? 'SUPER AI Agent'}와 대화하세요`}
      description={agent?.description ?? 'Auto-routing meta agent for all your agents'}
      className="w-full max-w-xl"
    >
      <SuggestionCards onSuggestionClick={onSuggestionClick} items={openerSuggestions(agent)} />
    </EmptyState>
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
  // agent-run-source-citations: 에이전트 근거는 kind·url 이 있고 score 가 없다.
  sources: DocumentSource[];
  // supervisor-chart-builder-node: 답변과 함께 렌더할 Chart.js 페이로드.
  charts: ChartPayload[];
  // agent-eval-gate: 저장된 assistant 메시지 id (평가 대상). 부재 시 null.
  assistantMessageId: number | null;
}

const ChatPage = () => {
  const { selectedAgent, activeSessionId, sessions } =
    useOutletContext<AgentChatOutletContext>();

  const user = useAuthStore((s) => s.user);
  const userId = user?.id != null ? String(user.id) : undefined;
  const queryClient = useQueryClient();

  const [messagesBySession, setMessagesBySession] = useState<Record<string, Message[]>>({});
  const [useRag, setUseRag] = useState(true);

  // ws-agent-excel-attachment / chat-image-attachment §5.3: 전송 전 대기 첨부 (엑셀 1 + 이미지 N)
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [attachmentUploading, setAttachmentUploading] = useState(false);
  const [attachmentNotice, setAttachmentNotice] = useState<string | null>(null);
  // 서버가 첨부를 거절하면(비전 미지원·장수 초과) 재시도할 수 있게 되돌린다 (§5.2)
  const lastSentAttachmentsRef = useRef<PendingAttachment[]>([]);

  const agentId = selectedAgent?.id ?? null;

  // chat-image-attachment D-09: 비전 여부 안내 — 모델 목록에서 찾았고 supports_vision=false 일 때만 비활성.
  // 목록 미로드·미발견은 허용(권위는 서버 precheck).
  const { data: llmModels } = useLlmModels();
  const visionSupported = useMemo(() => {
    const model = llmModels?.find((m) => m.id === selectedAgent?.llmModelId);
    return model ? model.supports_vision !== false : true;
  }, [llmModels, selectedAgent?.llmModelId]);

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

  // background-jobs S9: 현재 세션의 진행중 백그라운드 작업 가드 (D5 프론트 축)
  // jobs-page-revamp: 목록이 통합 이력으로 바뀌었다. 서버의 세션 중복 가드는
  // agent_background_job 만 보므로 여기서도 수동 작업의 진행중 건만 받는다.
  const { data: myJobs } = useJobHistory({ type: 'manual', status: 'running' });
  const enqueueJob = useEnqueueJob();
  const [bgNotice, setBgNotice] = useState<string | null>(null);
  // G-07: 오류 안내는 danger 톤으로 구분 (표현 분기만, 로직 동일)
  const [bgNoticeIsError, setBgNoticeIsError] = useState(false);
  const activeSessionJob = useMemo(
    () =>
      (myJobs?.items ?? []).find(
        (j) => j.session_id === activeSessionId && isJobActive(j.status),
      ) ?? null,
    [myJobs, activeSessionId],
  );

  // 진행중이던 job이 종료되면 세션 이력을 재조회해 결과를 표시한다 (FR-13)
  const prevActiveJobIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (activeSessionJob) {
      prevActiveJobIdRef.current = activeSessionJob.id;
      return;
    }
    if (prevActiveJobIdRef.current !== null) {
      prevActiveJobIdRef.current = null;
      setBgNotice(null);
      if (agentId && userId && activeSessionId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chat.agentSessionMessages(
            agentId,
            activeSessionId,
            userId,
          ),
        });
        queryClient.invalidateQueries({
          queryKey: queryKeys.chat.agentHistory(agentId, userId),
        });
      }
    }
  }, [activeSessionJob, agentId, userId, activeSessionId, queryClient]);

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
        assistantMessageId: chatStream.assistantMessageId,
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
        // agent-run-source-citations FR-13: ANSWER_COMPLETED 의 근거를 그대로 쓴다.
        sources: agentRun.sources,
        charts: agentRun.charts,
        // agent-run-feedback-wiring D-07: ANSWER_COMPLETED 의 assistant_message_id 로
        // 일반 채팅과 같은 feedbackMessageId 경로를 탄다 (없으면 평가 미노출).
        assistantMessageId: agentRun.assistantMessageId,
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
      // chat-image-attachment §6.1: 첨부 거절 코드는 안내 문구로 바꾸고 첨부를 되돌린다
      const friendly = ATTACHMENT_ERROR_MESSAGES[view.error.code as AttachmentErrorCode];
      if (friendly && lastSentAttachmentsRef.current.length > 0) {
        setPendingAttachments(lastSentAttachmentsRef.current);
        setAttachmentNotice(friendly);
      }
      updateMessage(activeStream.sessionId, activeStream.placeholderId, {
        content: friendly ?? `[${view.error.code}] ${view.error.message}`,
        isStreaming: false,
      });
    } else if (view.answer) {
      updateMessage(activeStream.sessionId, activeStream.placeholderId, {
        content: view.answer,
        sources: view.sources,
        charts: view.charts,
        isStreaming: false,
        // agent-eval-gate — 저장된 assistant 메시지 id를 부여해 평가 버튼 노출
        feedbackMessageId: view.assistantMessageId ?? undefined,
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

  // ws-agent-excel-attachment: 엑셀 업로드 → file_id 발급 후 대기 첨부로 보관 (턴당 1건, 교체).
  const uploadExcel = async (file: File) => {
    const res = await agentAttachmentService.uploadExcel(file);
    setPendingAttachments((prev) => [
      ...prev.filter((a) => a.ref.type !== 'excel'),
      { id: res.file_id, ref: { type: res.type, file_id: res.file_id }, name: res.filename },
    ]);
  };

  // chat-image-attachment §5.2: 사전 검증 → 순차 업로드 → 썸네일 칩. 실패 항목은 안내만.
  const uploadImages = async (files: File[]) => {
    const imageCount = pendingAttachments.filter((a) => a.ref.type === 'image').length;
    const { accepted, rejected } = validateImageFiles(files, imageCount);
    if (rejected.length > 0) setAttachmentNotice(rejectReasonMessage(rejected[0].reason));
    for (const file of accepted) {
      const res = await agentAttachmentService.uploadImage(file);
      setPendingAttachments((prev) => [
        ...prev,
        {
          id: res.file_id,
          ref: { type: res.type, file_id: res.file_id },
          name: res.filename,
          previewUrl: URL.createObjectURL(file),
        },
      ]);
    }
  };

  const handleAttachFiles = async (files: File[]) => {
    if (files.length === 0) return;
    setAttachmentNotice(null);
    setAttachmentUploading(true);
    try {
      const excel = files.find(isExcelFile);
      const images = files.filter(isImageFile);
      if (excel) await uploadExcel(excel);
      if (images.length > 0) {
        if (!visionSupported) setAttachmentNotice(VISION_DISABLED_REASON);
        else await uploadImages(images);
      }
      if (!excel && images.length === 0) {
        setAttachmentNotice('엑셀(.xlsx/.xls) 또는 이미지(png/jpg/webp)만 첨부할 수 있습니다.');
      }
    } catch (e) {
      setAttachmentNotice(uploadErrorMessage(e));
    } finally {
      setAttachmentUploading(false);
    }
  };

  const handleRemoveAttachment = (id: string) => {
    setPendingAttachments((prev) => {
      const target = prev.find((a) => a.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((a) => a.id !== id);
    });
  };

  const handleSend = (content: string) => {
    if (!activeSessionId) return;
    if (isPending) return; // Q1 mutex: 진행 중이면 무시 (ChatInput isLoading도 차단함)

    const isAgentMode = !!selectedAgent && selectedAgent.id !== 'super';
    const sentAttachments = isAgentMode ? pendingAttachments : [];
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
      // chat-image-attachment FR-17: 말풍선 썸네일 (object URL 은 세션 동안 유지)
      imagePreviews: sentAttachments.flatMap((a) => (a.previewUrl ? [a.previewUrl] : [])),
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
        attachments:
          sentAttachments.length > 0
            ? sentAttachments.map((a): AgentAttachmentRef => a.ref)
            : undefined,
      });
      lastSentAttachmentsRef.current = sentAttachments;
      setPendingAttachments([]); // 전송과 함께 첨부 소진(run 1회성)
      setAttachmentNotice(null);
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

  // background-jobs S9: 현재 질문을 백그라운드 작업으로 등록 (agent 모드 전용)
  const handleSendBackground = (content: string) => {
    if (!activeSessionId || isPending) return;
    if (!selectedAgent || selectedAgent.id === 'super') return;
    enqueueJob.mutate(
      {
        agentId: selectedAgent.id,
        data: { query: content, session_id: activeSessionId, source: 'chat' },
      },
      {
        onSuccess: () => {
          setBgNoticeIsError(false);
          setBgNotice(
            '백그라운드에서 실행 중입니다 — 채팅방을 나가도 계속 실행되며, 완료되면 상단 알림과 작업함에서 확인할 수 있어요.',
          );
        },
        onError: (e) => {
          setBgNoticeIsError(true);
          setBgNotice(
            isJobConflictError(e)
              ? '이미 이 대화에서 진행 중인 백그라운드 작업이 있어요. 완료된 뒤 다시 시도해 주세요.'
              : extractJobError(e),
          );
        },
      },
    );
  };

  const backgroundBlocked = activeSessionJob !== null;

  const toolEvents = view?.toolEvents ?? [];

  return (
    // Design Ref: ui-redesign-chat §5.3 — CLAUDE.md 패턴 A(고정 헤더 + 스크롤 바디)를 클래스로
    <div className="flex h-full flex-col">
      {/* excel-preview Design §5.3: 모달은 페이지 레벨 1회 마운트 (상태는 스토어 소유) */}
      <ExcelPreviewModal />
      <ChatHeader
        title={selectedAgent?.name ?? 'SUPER AI Agent'}
        messageCount={messages.length}
        agentId={selectedAgent && selectedAgent.id !== 'super' ? selectedAgent.id : undefined}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto h-full w-full max-w-3xl">
          {messages.length === 0 ? (
            <EmptyAgentState agent={selectedAgent} onSuggestionClick={handleSend} />
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
        <div className="mx-auto w-full max-w-3xl px-4 pb-2 sm:px-6">
          <ToolPreviewPanel
            events={toolEvents}
            visible={showToolPreview}
            onToggleVisible={setShowToolPreview}
          />
        </div>
      )}

      <div className="bg-surface">
        {/* background-jobs S9: 진행중 배너 + 접수 안내 */}
        {(backgroundBlocked || bgNotice) && (
          <div className="mx-auto max-w-3xl px-4 pb-1 sm:px-6">
            <div
              role={bgNotice && bgNoticeIsError ? 'alert' : 'status'}
              className={
                bgNotice && bgNoticeIsError
                  ? 'flex items-center gap-2 rounded-xl border border-danger-border bg-danger-bg px-4 py-2.5 text-sm text-danger'
                  : 'flex items-center gap-2 rounded-xl border border-info-border bg-info-bg px-4 py-2.5 text-sm text-info'
              }
            >
              {bgNotice && bgNoticeIsError ? (
                <AlertTriangle className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden="true" />
              ) : (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin" strokeWidth={2} aria-hidden="true" />
              )}
              <span>
                {/* 에러/접수 안내(bgNotice) 우선 — 진행중 배너가 409 안내를 가리지 않는다 */}
                {bgNotice ??
                  '이 대화에서 백그라운드 작업이 실행 중입니다. 완료되면 답변이 여기에 표시돼요.'}
              </span>
            </div>
          </div>
        )}
        <ChatInput
          onSend={handleSend}
          isLoading={isPending || backgroundBlocked}
          useRag={useRag}
          onToggleRag={() => setUseRag((v) => !v)}
          attachmentEnabled={!!selectedAgent && selectedAgent.id !== 'super'}
          attachments={pendingAttachments}
          attachmentUploading={attachmentUploading}
          onAttachFiles={handleAttachFiles}
          onRemoveAttachment={handleRemoveAttachment}
          imageAttachmentEnabled={visionSupported}
          imageDisabledReason={visionSupported ? null : VISION_DISABLED_REASON}
          attachmentNotice={attachmentNotice}
          backgroundEnabled={!!selectedAgent && selectedAgent.id !== 'super'}
          onSendBackground={handleSendBackground}
        />
      </div>
    </div>
  );
};

export default ChatPage;
