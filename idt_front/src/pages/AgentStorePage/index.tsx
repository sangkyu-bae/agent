import { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import AgentStoreTab from '@/components/agent-store/AgentStoreTab';
import AgentStoreCard from '@/components/agent-store/AgentStoreCard';
import AgentDetailModal from '@/components/agent-store/AgentDetailModal';
import PublishAgentModal from '@/components/agent-store/PublishAgentModal';
import {
  useAgentList,
  useMyAgents,
  useSubscribeAgent,
  useForkAgent,
} from '@/hooks/useAgentStore';
import type { AgentScope, MyAgentFilter, StoreAgentSummary } from '@/types/agentStore';

type StoreTab = 'public' | 'department' | 'my';

const TAB_TO_SCOPE: Record<StoreTab, AgentScope> = {
  public: 'public',
  department: 'department',
  my: 'mine',
};

const PAGE_SIZE = 20;

const AgentStorePage = () => {
  const [activeTab, setActiveTab] = useState<StoreTab>('public');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [myFilter, setMyFilter] = useState<MyAgentFilter>('all');
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [showPublishModal, setShowPublishModal] = useState(false);

  const searchTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(value);
      setPage(1);
    }, 300);
  }, []);

  useEffect(() => {
    return () => clearTimeout(searchTimerRef.current);
  }, []);

  const handleTabChange = (tab: StoreTab) => {
    setActiveTab(tab);
    setPage(1);
    setSearch('');
    setDebouncedSearch('');
  };

  const agentListQuery = useAgentList({
    scope: TAB_TO_SCOPE[activeTab],
    search: debouncedSearch || undefined,
    page,
    size: PAGE_SIZE,
  });

  const myAgentsQuery = useMyAgents({
    filter: myFilter,
    search: debouncedSearch || undefined,
    page,
    size: PAGE_SIZE,
  });

  const subscribeMutation = useSubscribeAgent();
  const forkMutation = useForkAgent();

  const isMyTab = activeTab === 'my';
  const query = isMyTab ? myAgentsQuery : agentListQuery;
  const agents: StoreAgentSummary[] = isMyTab
    ? (myAgentsQuery.data?.agents ?? []).map((a) => ({
        agent_id: a.agent_id,
        name: a.name,
        description: a.description,
        visibility: a.visibility,
        department_name: null,
        owner_user_id: a.owner_user_id,
        owner_email: null,
        temperature: a.temperature,
        can_edit: a.source_type === 'owned',
        can_delete: a.source_type === 'owned',
        created_at: a.created_at,
      }))
    : agentListQuery.data?.agents ?? [];
  const total = isMyTab
    ? (myAgentsQuery.data?.total ?? 0)
    : (agentListQuery.data?.total ?? 0);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const EMPTY_MESSAGES: Record<StoreTab, { text: string; link?: { label: string; path: string } }> = {
    public: {
      text: '공개된 에이전트가 없습니다',
      link: { label: '에이전트 만들기', path: '/agent-builder' },
    },
    department: { text: '부서에 공개된 에이전트가 없습니다' },
    my: {
      text: '에이전트가 없습니다',
      link: { label: '에이전트 만들기', path: '/agent-builder' },
    },
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div className="shrink-0 border-b border-zinc-200 px-4 py-5 sm:px-6">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-xl shadow-md"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 21v-7.5a.75.75 0 0 1 .75-.75h3a.75.75 0 0 1 .75.75V21m-4.5 0H2.36m11.14 0H18m0 0h3.64m-1.39 0V9.349M3.75 21V9.349m0 0a3.001 3.001 0 0 0 3.75-.615A2.993 2.993 0 0 0 9.75 9.75c.896 0 1.7-.393 2.25-1.016a2.993 2.993 0 0 0 2.25 1.016c.896 0 1.7-.393 2.25-1.015a3.001 3.001 0 0 0 3.75.614m-16.5 0a3.004 3.004 0 0 1-.621-4.72l1.189-1.19A1.5 1.5 0 0 1 5.378 3h13.243a1.5 1.5 0 0 1 1.06.44l1.19 1.189a3 3 0 0 1-.621 4.72M6.75 18h3.75a.75.75 0 0 0 .75-.75V13.5a.75.75 0 0 0-.75-.75H6.75a.75.75 0 0 0-.75.75v3.75c0 .414.336.75.75.75Z" />
              </svg>
            </div>
            <div>
              <h1 className="text-[18px] font-bold text-zinc-900">에이전트 스토어</h1>
              <p className="text-[12px] text-zinc-400">공개 에이전트를 탐색하고 구독하세요</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative">
              <svg
                className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="에이전트 검색..."
                className="w-56 rounded-xl border border-zinc-200 bg-zinc-50 py-2 pl-9 pr-3 text-[13px] text-zinc-800 outline-none transition-all placeholder:text-zinc-400 focus:border-violet-400 focus:bg-white focus:shadow-sm"
              />
            </div>

            {/* Publish button */}
            <button
              onClick={() => setShowPublishModal(true)}
              className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              등록
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <AgentStoreTab
        activeTab={activeTab}
        onTabChange={handleTabChange}
        myFilter={myFilter}
        onMyFilterChange={setMyFilter}
      />

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
          {/* Loading skeleton */}
          {query.isLoading && (
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="animate-pulse rounded-2xl border border-zinc-100 bg-white p-4"
                >
                  <div className="flex items-start gap-3">
                    <div className="h-10 w-10 rounded-xl bg-zinc-100" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-32 rounded bg-zinc-100" />
                      <div className="h-3 w-24 rounded bg-zinc-100" />
                    </div>
                  </div>
                  <div className="mt-4 space-y-2">
                    <div className="h-3 w-full rounded bg-zinc-100" />
                    <div className="h-3 w-2/3 rounded bg-zinc-100" />
                  </div>
                  <div className="mt-4 h-8 w-24 rounded bg-zinc-100" />
                </div>
              ))}
            </div>
          )}

          {/* Empty state */}
          {!query.isLoading && agents.length === 0 && (
            <div className="flex flex-col items-center gap-3 py-20 text-center">
              <svg className="h-12 w-12 text-zinc-200" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5m6 4.125 2.25 2.25m0 0 2.25 2.25M12 13.875l2.25-2.25M12 13.875l-2.25 2.25M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z" />
              </svg>
              {debouncedSearch ? (
                <p className="text-[14px] text-zinc-500">
                  &apos;{debouncedSearch}&apos;에 대한 결과가 없습니다
                </p>
              ) : (
                <>
                  <p className="text-[14px] text-zinc-500">
                    {EMPTY_MESSAGES[activeTab].text}
                  </p>
                  {EMPTY_MESSAGES[activeTab].link && (
                    <Link
                      to={EMPTY_MESSAGES[activeTab].link!.path}
                      className="text-[13px] font-medium text-violet-600 hover:text-violet-700"
                    >
                      {EMPTY_MESSAGES[activeTab].link!.label} &rarr;
                    </Link>
                  )}
                </>
              )}
            </div>
          )}

          {/* Card grid */}
          {!query.isLoading && agents.length > 0 && (
            <>
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
                {agents.map((agent) => (
                  <AgentStoreCard
                    key={agent.agent_id}
                    agent={agent}
                    onClick={(id) => setSelectedAgentId(id)}
                    onSubscribe={(id) => subscribeMutation.mutate(id)}
                    onFork={(id) => forkMutation.mutate({ agentId: id })}
                    isSubscribing={subscribeMutation.isPending}
                    isForking={forkMutation.isPending}
                  />
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="mt-8 flex items-center justify-center gap-3">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[13px] text-zinc-600 transition-all hover:bg-zinc-50 disabled:opacity-40"
                  >
                    이전
                  </button>
                  <span className="text-[13px] text-zinc-500">
                    {page} / {totalPages}
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[13px] text-zinc-600 transition-all hover:bg-zinc-50 disabled:opacity-40"
                  >
                    다음
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      <AgentDetailModal
        agentId={selectedAgentId}
        isOpen={!!selectedAgentId}
        onClose={() => setSelectedAgentId(null)}
      />
      <PublishAgentModal
        isOpen={showPublishModal}
        onClose={() => setShowPublishModal(false)}
      />
    </div>
  );
};

export default AgentStorePage;
