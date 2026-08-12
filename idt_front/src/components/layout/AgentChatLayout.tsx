import { useEffect, useMemo, useRef, useState } from 'react';
import { Outlet, useLocation, useSearchParams } from 'react-router-dom';
import AppSidebar from '@/components/layout/AppSidebar';
import ChatHistoryPanel from '@/components/layout/ChatHistoryPanel';
import { useLayoutStore } from '@/store/layoutStore';
import { useAuthStore } from '@/store/authStore';
import { useAgentSessions } from '@/hooks/useChat';
import { useMyAgents } from '@/hooks/useAgentSubscription';
import { toAgentSummary } from '@/services/agentSubscriptionService';
import type { AgentSummary, AgentChatOutletContext } from '@/types/agent';
import type { ChatSession } from '@/types/chat';

const createDraftSession = (): ChatSession => ({
  id: crypto.randomUUID(),
  title: '새 대화',
  messages: [],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
});

const AgentChatLayout = () => {
  const location = useLocation();
  const isChatRoute = location.pathname === '/chatpage';

  const {
    isChatPanelOpen,
    selectedAgentId,
    toggleChatPanel,
    selectAgent,
  } = useLayoutStore();

  const user = useAuthStore((s) => s.user);
  const userId = user?.id != null ? String(user.id) : undefined;

  const [draftSessions, setDraftSessions] = useState<ChatSession[]>(() => [createDraftSession()]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(draftSessions[0]?.id ?? null);

  const prevAgentIdRef = useRef(selectedAgentId);

  // background-jobs: 작업함/벨 딥링크(?agentId=&sessionId=) 소비 —
  // 에이전트 전환이 필요한 경우 전환 리셋 effect 가 draft 대신 이 세션을 선택한다
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkSessionRef = useRef<string | null>(null);
  useEffect(() => {
    const qAgentId = searchParams.get('agentId');
    const qSessionId = searchParams.get('sessionId');
    if (!qAgentId || !qSessionId) return;
    if (qAgentId !== selectedAgentId) {
      deepLinkSessionRef.current = qSessionId;
      selectAgent(qAgentId);
    } else {
      setActiveSessionId(qSessionId);
    }
    setSearchParams({}, { replace: true });
  }, [searchParams, selectedAgentId, selectAgent, setSearchParams]);

  const {
    data: serverSessions = [],
    isLoading: sessionsLoading,
    isError: sessionsError,
    refetch: refetchSessions,
  } = useAgentSessions(selectedAgentId, userId);

  const {
    data: myAgentsData,
    isLoading: agentsLoading,
    isError: agentsError,
    refetch: refetchAgents,
  } = useMyAgents();

  const myAgents = useMemo(() => myAgentsData?.agents ?? [], [myAgentsData]);

  // 에이전트 전환 시 세션 초기화 (딥링크 전환이면 해당 세션 선택)
  useEffect(() => {
    if (prevAgentIdRef.current !== selectedAgentId) {
      prevAgentIdRef.current = selectedAgentId;
      if (deepLinkSessionRef.current) {
        setDraftSessions([]);
        setActiveSessionId(deepLinkSessionRef.current);
        deepLinkSessionRef.current = null;
        return;
      }
      const newDraft = createDraftSession();
      setDraftSessions([newDraft]);
      setActiveSessionId(newDraft.id);
    }
  }, [selectedAgentId]);

  // 서버 세션 로드 완료 후 → 서버 세션 있으면 첫 번째 선택
  useEffect(() => {
    if (serverSessions.length > 0) {
      const isDraft = draftSessions.some((d) => d.id === activeSessionId);
      if (isDraft) {
        setActiveSessionId(serverSessions[0].id);
      }
    }
  }, [serverSessions]);

  const sessions = useMemo<ChatSession[]>(() => {
    const serverIds = new Set(serverSessions.map((s) => s.id));
    const drafts = draftSessions.filter((s) => !serverIds.has(s.id));
    return [...drafts, ...serverSessions];
  }, [draftSessions, serverSessions]);

  const handleNewChat = () => {
    const newSession = createDraftSession();
    setDraftSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  };

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
  };

  const selectedAgent: AgentSummary | null = (() => {
    if (selectedAgentId === 'super') {
      return {
        id: 'super',
        name: 'SUPER AI Agent',
        description: 'Auto-routing meta agent for all your agents',
        category: 'system',
        isDefault: true,
      };
    }
    const found = myAgents.find((a) => a.agent_id === selectedAgentId);
    if (found) return toAgentSummary(found);
    if (myAgents.length > 0) return toAgentSummary(myAgents[0]);
    return null;
  })();

  const outletContext: AgentChatOutletContext = {
    selectedAgent,
    activeSessionId,
    setActiveSessionId,
    handleNewChat,
    sessions,
    refetchSessions: () => refetchSessions(),
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      <AppSidebar
        agents={myAgents}
        selectedAgentId={selectedAgentId}
        onSelectAgent={selectAgent}
        isLoading={agentsLoading}
        isError={agentsError}
        onRetry={() => refetchAgents()}
      />

      {isChatRoute && (
        <ChatHistoryPanel
          isOpen={isChatPanelOpen}
          onToggle={toggleChatPanel}
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          isLoading={sessionsLoading}
          isError={sessionsError}
          onRetry={() => refetchSessions()}
        />
      )}

      <main style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', background: '#fff' }}>
        <Outlet context={outletContext} />
      </main>
    </div>
  );
};

export default AgentChatLayout;
