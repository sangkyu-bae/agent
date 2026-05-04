import { useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { useLogout } from '@/hooks/useAuth';
import type { MyAgent } from '@/types/agent';

interface AppSidebarProps {
  agents: MyAgent[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

const NAV_ITEMS = [
  { id: 'super-ai', label: 'SUPER AI 에이전트', path: '/chatpage', iconPath: 'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z' },
  { id: 'templates', label: '에이전트 템플릿', path: '/agent-builder', iconPath: 'M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z' },
  { id: 'utility', label: '유틸리티', path: '/tool-connection', iconPath: 'M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z' },
  { id: 'tasks', label: '작업', path: '/workflow-designer', iconPath: 'M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z' },
  { id: 'eval', label: '평가', path: '/eval-dataset', iconPath: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z' },
];

const BOTTOM_ITEMS = [
  { label: '즐겨찾기', path: null, iconPath: 'M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z' },
  { label: '역할설정', path: null, iconPath: 'M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z' },
  { label: '리소스', path: '/collections', iconPath: 'M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z' },
  { label: '환경설정', path: '/settings', iconPath: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z' },
];

const GROUP_CONFIG = [
  { key: 'pinned', label: '고정됨' },
  { key: 'owned', label: '내 에이전트' },
  { key: 'subscribed', label: '구독' },
  { key: 'forked', label: '포크' },
] as const;

const AppSidebar = ({
  agents,
  selectedAgentId,
  onSelectAgent,
  isLoading = false,
  isError = false,
  onRetry,
}: AppSidebarProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuthStore();
  const { mutate: logout, isPending: isLoggingOut } = useLogout();

  const groups = useMemo(() => {
    const pinned = agents.filter((a) => a.is_pinned);
    const owned = agents.filter((a) => a.source_type === 'owned' && !a.is_pinned);
    const subscribed = agents.filter((a) => a.source_type === 'subscribed' && !a.is_pinned);
    const forked = agents.filter((a) => a.source_type === 'forked' && !a.is_pinned);

    return GROUP_CONFIG
      .map((cfg) => {
        const items =
          cfg.key === 'pinned' ? pinned :
          cfg.key === 'owned' ? owned :
          cfg.key === 'subscribed' ? subscribed :
          forked;
        return { ...cfg, agents: items };
      })
      .filter((g) => g.agents.length > 0);
  }, [agents]);

  const handleNavClick = (path: string) => {
    navigate(path);
  };

  return (
    <aside
      className="flex h-full w-64 shrink-0 flex-col"
      style={{ background: '#0f0f0f' }}
    >
      {/* (a) Logo */}
      <div className="flex items-center gap-3 px-5 py-5">
        <img
          src="/logo.png"
          alt="상상인플러스저축은행"
          className="h-8 w-8 rounded-lg object-contain"
        />
        <span className="text-[13px] font-semibold text-white leading-tight">상상인플러스저축은행</span>
      </div>

      {/* (b) New agent button */}
      <div className="px-3 pb-2">
        <button
          onClick={() => navigate('/agent-builder')}
          className="flex w-full items-center gap-2 rounded-xl border border-white/10 px-3 py-2.5 text-[13px] text-white/60 hover:bg-white/[0.08] transition-all"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          새 에이전트
        </button>
      </div>

      {/* (d) Navigation */}
      <div className="px-3 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <button
              key={item.id}
              onClick={() => handleNavClick(item.path)}
              className={`relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] transition-all duration-150 ${
                isActive
                  ? 'bg-white/[0.12] text-white'
                  : 'text-white/40 hover:bg-white/[0.07] hover:text-white/70'
              }`}
            >
              {isActive && (
                <span
                  className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full"
                  style={{ background: 'linear-gradient(135deg, #7c3aed, #4f46e5)' }}
                />
              )}
              <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d={item.iconPath} />
              </svg>
              {item.label}
            </button>
          );
        })}
      </div>

      {/* (e) Agent section */}
      <div className="mt-2 border-t border-white/[0.06] pt-3 flex-1 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex items-center justify-between px-4 py-1">
          <div className="flex items-center gap-2">
            <svg className="h-4 w-4 text-violet-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
            </svg>
            <span className="text-[13px] font-medium text-white">에이전트</span>
          </div>
        </div>

        <div className="mt-1 px-3">
          {isError ? (
            <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-center">
              <p className="text-[12.5px] text-red-300">에이전트 목록을 불러오지 못했습니다</p>
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="mt-2 rounded-lg border border-white/15 px-3 py-1 text-[11.5px] text-white/70 hover:bg-white/[0.08] hover:text-white"
                >
                  다시 시도
                </button>
              )}
            </div>
          ) : isLoading ? (
            <div className="space-y-1" aria-label="불러오는 중" role="status">
              {[0, 1, 2].map((i) => (
                <div key={i} className="flex w-full flex-col items-start rounded-xl px-3 py-2">
                  <span className="h-3 w-3/4 animate-pulse rounded bg-white/10" />
                  <span className="mt-2 h-2 w-1/2 animate-pulse rounded bg-white/5" />
                </div>
              ))}
            </div>
          ) : agents.length === 0 ? (
            <div className="mt-6 text-center">
              <p className="text-[12.5px] text-white/20">등록된 에이전트가 없습니다</p>
              <button
                onClick={() => navigate('/agent-builder')}
                className="mt-3 rounded-lg border border-violet-500/30 px-3 py-1.5 text-[11.5px] text-violet-400 hover:bg-violet-500/10 transition-all"
              >
                에이전트 만들기
              </button>
            </div>
          ) : (
            groups.map((group) => (
              <div key={group.key} className="mb-2">
                <div className="mb-1 px-1">
                  <span className="text-[11px] font-medium text-white/20">
                    {group.label} ({group.agents.length})
                  </span>
                </div>
                {group.agents.map((agent) => {
                  const isSelected = agent.agent_id === selectedAgentId;
                  return (
                    <button
                      key={agent.agent_id}
                      onClick={() => onSelectAgent(agent.agent_id)}
                      className={`w-full rounded-lg px-3 py-2 text-left transition-all duration-150 ${
                        isSelected
                          ? 'bg-white/[0.12] text-white'
                          : 'text-white/45 hover:bg-white/[0.06] hover:text-white/70'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <p className="text-[13px] font-medium truncate flex-1">{agent.name}</p>
                        {agent.is_pinned && (
                          <svg className="h-3 w-3 shrink-0 text-violet-400 ml-1" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z" />
                          </svg>
                        )}
                      </div>
                      <p className="text-[11px] text-white/25 truncate mt-0.5">{agent.description}</p>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>

      {/* (f) Bottom menu */}
      <div className="border-t border-white/[0.06] px-3 py-2 space-y-0.5">
        {BOTTOM_ITEMS.map(({ label, path, iconPath }) => {
          const isActive = path && location.pathname === path;
          return (
            <button
              key={label}
              onClick={() => path && navigate(path)}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-[12.5px] transition-all ${
                isActive
                  ? 'bg-white/[0.12] text-white'
                  : 'text-white/30 hover:bg-white/[0.07] hover:text-white/60'
              } ${!path ? 'cursor-default' : ''}`}
            >
              <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d={iconPath} />
              </svg>
              {label}
            </button>
          );
        })}
      </div>

      {/* (g) User profile + logout */}
      {user && (
        <div className="border-t border-white/[0.06] px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-violet-600 text-[11px] font-semibold text-white">
              {user.email[0].toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-white">{user.email}</p>
              <p className="truncate text-[11px] text-white/30">{user.email}</p>
            </div>
            <button
              onClick={() => logout()}
              disabled={isLoggingOut}
              title="로그아웃"
              className="flex h-7 w-7 items-center justify-center rounded-lg text-white/25 hover:bg-white/[0.08] hover:text-red-400 transition-all disabled:opacity-50"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </aside>
  );
};

export default AppSidebar;
