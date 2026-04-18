import { useNavigate, useLocation } from 'react-router-dom';
import type { ChatSession } from '@/types/chat';
import { formatDate } from '@/utils/formatters';

interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

const NAV_ITEMS = [
  {
    path: '/documents',
    icon: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
    label: '문서 관리',
  },
  {
    path: '/agent-builder',
    icon: 'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z',
    label: '에이전트 만들기',
  },
  {
    path: '/tool-connection',
    icon: 'M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z',
    label: '도구 연결',
  },
  {
    path: '/workflow-designer',
    icon: 'M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6',
    label: '워크플로우 설계',
  },
  {
    path: '/eval-dataset',
    icon: 'M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 0 1-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0 1 12 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h1.5a1.125 1.125 0 0 1 1.125 1.125v1.5a1.125 1.125 0 0 1-1.125 1.125h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a1.125 1.125 0 0 1 1.125-1.125Zm-17.25 0h1.5a1.125 1.125 0 0 1 1.125 1.125v1.5a1.125 1.125 0 0 1-1.125 1.125h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a1.125 1.125 0 0 1 1.125-1.125Z',
    label: '평가 데이터셋',
  },
  {
    path: '/settings',
    icon: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
    label: '설정',
  },
];

const Sidebar = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  isLoading = false,
  isError = false,
  onRetry,
}: SidebarProps) => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside
      className="flex h-full w-64 shrink-0 flex-col"
      style={{ background: '#0f0f0f' }}
    >
      {/* 로고 */}
      <div className="flex items-center gap-3 px-5 py-5">
        <img
          src="https://m.sangsanginplussb.com/mob/img/ssiplus_logo.png"
          alt="상상인플러스저축은행"
          className="h-8 w-auto object-contain brightness-0 invert"
        />
      </div>

      {/* 새 대화 버튼 */}
      <div className="px-3 pb-5">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-3 rounded-xl border border-white/10 px-4 py-2.5 text-[13.5px] font-medium text-white/60 transition-all hover:bg-white/[0.08] hover:text-white"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          새 대화
        </button>
      </div>

      {/* 구분선 */}
      <div className="mx-4 mb-4 border-t border-white/[0.06]" />

      {/* 세션 목록 */}
      <div className="flex-1 overflow-y-auto px-3 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {isError ? (
          <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-center">
            <p className="text-[12.5px] text-red-300">⚠ 대화 내역을 불러오지 못했습니다</p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="mt-2 rounded-lg border border-white/15 px-3 py-1 text-[11.5px] text-white/70 hover:bg-white/[0.08] hover:text-white"
              >
                다시 시도
              </button>
            )}
          </div>
        ) : isLoading && sessions.length === 0 ? (
          <div>
            <p className="mb-2 px-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-white/20">
              최근 대화
            </p>
            <div className="space-y-1" aria-label="불러오는 중" role="status">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="flex w-full flex-col items-start rounded-xl px-4 py-3"
                >
                  <span className="h-3 w-3/4 animate-pulse rounded bg-white/10" />
                  <span className="mt-2 h-2 w-1/3 animate-pulse rounded bg-white/5" />
                </div>
              ))}
            </div>
          </div>
        ) : sessions.length > 0 ? (
          <div>
            <p className="mb-2 px-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-white/20">
              최근 대화
            </p>
            <div className="space-y-0.5">
              {sessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  aria-current={activeSessionId === session.id ? 'true' : undefined}
                  className={`group relative flex w-full flex-col items-start rounded-xl px-4 py-3 text-left transition-all duration-150 ${
                    activeSessionId === session.id
                      ? 'bg-white/[0.12] text-white'
                      : 'text-white/45 hover:bg-white/[0.07] hover:text-white/80'
                  }`}
                >
                  {activeSessionId === session.id && (
                    <span
                      className="absolute left-1 top-1/2 h-6 w-0.5 -translate-y-1/2 rounded-full"
                      style={{ background: 'linear-gradient(135deg, #7c3aed, #4f46e5)' }}
                    />
                  )}
                  <span className="w-full truncate text-[13.5px] font-medium leading-snug">
                    {session.title}
                  </span>
                  <span className="mt-1 text-[11px] text-white/25 group-hover:text-white/35">
                    {formatDate(session.updatedAt)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-12 text-center">
            <p className="text-[12.5px] text-white/20">대화 내역이 없습니다</p>
          </div>
        )}
      </div>

      {/* 하단 네비게이션 */}
      <div className="border-t border-white/[0.06] px-3 py-3 space-y-0.5">
        {NAV_ITEMS.map(({ path, icon, label }) => {
          const isActive = location.pathname === path;
          return (
            <button
              key={path}
              onClick={() => navigate(path)}
              className={`flex w-full items-center gap-3 rounded-xl px-4 py-2.5 text-[13px] transition-all ${
                isActive
                  ? 'bg-white/[0.12] text-white'
                  : 'text-white/30 hover:bg-white/[0.07] hover:text-white/65'
              }`}
            >
              {isActive && (
                <span
                  className="absolute left-1 h-5 w-0.5 rounded-full"
                  style={{ background: 'linear-gradient(135deg, #7c3aed, #4f46e5)' }}
                />
              )}
              <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d={icon} />
              </svg>
              {label}
            </button>
          );
        })}
      </div>
    </aside>
  );
};

export default Sidebar;
