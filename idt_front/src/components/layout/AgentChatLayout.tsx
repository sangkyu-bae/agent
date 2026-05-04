import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import AppSidebar from '@/components/layout/AppSidebar';
import ChatHistoryPanel from '@/components/layout/ChatHistoryPanel';
import { useLayoutStore } from '@/store/layoutStore';
import { useAuthStore } from '@/store/authStore';
import { useConversationSessions } from '@/hooks/useChat';
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

  const initialDraft = useState(() => createDraftSession())[0];
  const [draftSessions, setDraftSessions] = useState<ChatSession[]>([initialDraft]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(initialDraft.id);

  const {
    data: serverSessions = [],
    isLoading: sessionsLoading,
    isError: sessionsError,
    refetch: refetchSessions,
  } = useConversationSessions(userId);

  const {
    data: myAgentsData,
    isLoading: agentsLoading,
    isError: agentsError,
    refetch: refetchAgents,
  } = useMyAgents();

  const myAgents = useMemo(() => myAgentsData?.agents ?? [], [myAgentsData]);

  useEffect(() => {
    if (myAgents.length > 0 && !myAgents.find((a) => a.agent_id === selectedAgentId)) {
      selectAgent(myAgents[0].agent_id);
    }
  }, [myAgents, selectedAgentId, selectAgent]);

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
