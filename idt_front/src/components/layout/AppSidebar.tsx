// Design Ref: ui-redesign-chat §5.5 — 256px 전체 / 64px 아이콘 레일. 접힌 상태에서도 모든 버튼은 aria-label로 접근 가능한 이름을 유지한다.
import { useMemo, type ButtonHTMLAttributes, type ComponentType } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  BarChart3,
  BookOpen,
  Clock,
  Folder,
  KeyRound,
  LayoutGrid,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  Star,
  Store,
  Wrench,
  type LucideProps,
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';
import { useLogout } from '@/hooks/useAuth';
import { ADMIN_ENTRY_PATH } from '@/constants/adminNav';
import { cn } from '@/utils/cn';
import type { MyAgent } from '@/types/agent';

interface AppSidebarProps {
  agents: MyAgent[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

type IconType = ComponentType<LucideProps>;

interface NavItem {
  id: string;
  label: string;
  path: string | null;
  icon: IconType;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'super', label: 'SUPER AI 에이전트', path: '/chatpage', icon: Sparkles },
  { id: 'agent-store', label: '에이전트 스토어', path: '/agent-store', icon: Store },
  { id: 'templates', label: '에이전트 템플릿', path: '/agent-builder', icon: LayoutGrid },
  { id: 'utility', label: '유틸리티', path: '/tool-connection', icon: Wrench },
  { id: 'tasks', label: '작업', path: '/jobs', icon: Clock },
  { id: 'eval', label: '평가', path: '/eval-dataset', icon: BarChart3 },
];

const BOTTOM_ITEMS: NavItem[] = [
  { id: 'favorites', label: '즐겨찾기', path: null, icon: Star },
  { id: 'roles', label: '역할설정', path: null, icon: KeyRound },
  { id: 'resources', label: '리소스', path: '/collections', icon: Folder },
  { id: 'kb', label: '지식베이스', path: '/knowledge-bases', icon: BookOpen },
  { id: 'settings', label: '환경설정', path: '/settings', icon: Settings },
];

const GROUP_CONFIG = [
  { key: 'pinned', label: '고정됨' },
  { key: 'owned', label: '내 에이전트' },
  { key: 'subscribed', label: '구독' },
  { key: 'forked', label: '포크' },
] as const;

interface SidebarItemProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  icon: IconType;
  collapsed: boolean;
  isActive?: boolean;
  /** 관리자 항목처럼 비활성 색을 brand 톤으로 */
  accent?: boolean;
}

/** 다크 사이드바 전용 항목 버튼. 접히면 아이콘만 남고 라벨은 aria-label·title로 유지된다. */
const SidebarItem = ({
  label,
  icon: Icon,
  collapsed,
  isActive = false,
  accent = false,
  className,
  type = 'button',
  ...rest
}: SidebarItemProps) => (
  <button
    type={type}
    aria-label={label}
    title={collapsed ? label : undefined}
    aria-current={isActive ? 'page' : undefined}
    className={cn(
      'relative flex w-full items-center rounded-md text-sm transition-colors duration-150 disabled:opacity-50',
      collapsed ? 'h-10 justify-center' : 'gap-3 px-3 py-2.5',
      isActive
        ? 'bg-sidebar-active text-sidebar-fg'
        : accent
          ? 'text-brand-300 hover:bg-sidebar-hover hover:text-brand-200'
          : 'text-sidebar-fg-muted hover:bg-sidebar-hover hover:text-sidebar-fg',
      className,
    )}
    {...rest}
  >
    {isActive && (
      <span
        aria-hidden="true"
        className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-linear-to-b from-brand-500 to-brand-800"
      />
    )}
    <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
    {!collapsed && <span className="truncate">{label}</span>}
  </button>
);

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
  const collapsed = useLayoutStore((s) => s.isSidebarCollapsed);
  const toggleSidebar = useLayoutStore((s) => s.toggleSidebar);
  const setSidebarCollapsed = useLayoutStore((s) => s.setSidebarCollapsed);

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

  const handleNavClick = (item: NavItem) => {
    if (item.id === 'super') {
      onSelectAgent('super');
    }
    if (item.path) navigate(item.path);
  };

  const isBottomActive = (path: string | null) =>
    !!path &&
    // kb-management-ui D7: 상세 라우트(/knowledge-bases/:kbId)에서도 활성 유지
    (path === '/knowledge-bases' ? location.pathname.startsWith(path) : location.pathname === path);

  return (
    <aside
      aria-label="주 메뉴"
      data-collapsed={collapsed || undefined}
      className={cn(
        'flex h-full shrink-0 flex-col bg-sidebar transition-[width] duration-200',
        collapsed ? 'w-16' : 'w-64',
      )}
    >
      {/* (a) 토글 + 로고 */}
      <div className={cn('flex items-center', collapsed ? 'flex-col gap-2 px-3 pt-3 pb-2' : 'gap-2 px-3 pt-3 pb-2')}>
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
          title={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
          aria-expanded={!collapsed}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-sidebar-fg-muted transition-colors duration-150 hover:bg-sidebar-hover hover:text-sidebar-fg"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
          ) : (
            <PanelLeftClose className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
          )}
        </button>
        <div className={cn('flex min-w-0 items-center gap-2', collapsed && 'justify-center')}>
          <img
            src="/logo.png"
            alt="상상인플러스저축은행"
            className="h-8 w-8 shrink-0 rounded-md object-contain"
          />
          {!collapsed && (
            <span className="truncate text-sm font-semibold leading-tight text-sidebar-fg">상상인플러스저축은행</span>
          )}
        </div>
      </div>

      {/* (b) 새 에이전트
          agent-create-entry FR-01: 사이드바 진입점만 생성 화면으로 보낸다.
          목록 헤더·빈 상태 버튼은 기존대로 빈 스튜디오 직행 (Design §5.4). */}
      <div className="px-3 pb-2">
        <button
          type="button"
          onClick={() => navigate('/agent-builder/new')}
          aria-label="새 에이전트"
          title={collapsed ? '새 에이전트' : undefined}
          className={cn(
            'flex w-full items-center rounded-md border border-sidebar-border text-sm text-sidebar-fg-muted transition-colors duration-150 hover:bg-sidebar-hover hover:text-sidebar-fg',
            collapsed ? 'h-10 justify-center' : 'gap-2 px-3 py-2.5',
          )}
        >
          <Plus className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden="true" />
          {!collapsed && '새 에이전트'}
        </button>
      </div>

      {/* (d) 내비게이션 */}
      <nav aria-label="기본 메뉴" className="space-y-0.5 px-3">
        {NAV_ITEMS.map((item) => (
          <SidebarItem
            key={item.id}
            label={item.label}
            icon={item.icon}
            collapsed={collapsed}
            isActive={location.pathname === item.path}
            onClick={() => handleNavClick(item)}
          />
        ))}
      </nav>

      {/* (e) 에이전트 목록 — 접힌 상태에서는 아이콘 1개로 대체(클릭 시 펼침) */}
      <div className="mt-2 flex-1 overflow-y-auto border-t border-sidebar-border pt-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {collapsed ? (
          <div className="px-3">
            <SidebarItem
              label="에이전트 목록"
              icon={Sparkles}
              collapsed
              onClick={() => setSidebarCollapsed(false)}
            />
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between px-4 py-1">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-brand-400" strokeWidth={1.75} aria-hidden="true" />
                <span className="text-sm font-medium text-sidebar-fg">에이전트</span>
              </div>
            </div>

            <div className="mt-1 px-3">
              {isError ? (
                <div className="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-center">
                  <p className="text-xs text-danger-border">에이전트 목록을 불러오지 못했습니다</p>
                  {onRetry && (
                    <button
                      type="button"
                      onClick={onRetry}
                      className="mt-2 rounded-md border border-sidebar-border px-3 py-1 text-xs text-sidebar-fg-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-fg"
                    >
                      다시 시도
                    </button>
                  )}
                </div>
              ) : isLoading ? (
                <div className="space-y-1" aria-label="불러오는 중" role="status">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="flex w-full flex-col items-start rounded-md px-3 py-2">
                      <span className="h-3 w-3/4 animate-pulse rounded-md bg-sidebar-active" />
                      <span className="mt-2 h-2 w-1/2 animate-pulse rounded-md bg-sidebar-hover" />
                    </div>
                  ))}
                </div>
              ) : agents.length === 0 ? (
                <div className="mt-6 text-center">
                  <p className="text-xs text-sidebar-fg-muted">등록된 에이전트가 없습니다</p>
                  <button
                    type="button"
                    onClick={() => navigate('/agent-builder')}
                    className="mt-3 rounded-md border border-brand-500/40 px-3 py-1.5 text-xs text-brand-300 transition-colors hover:bg-brand-500/10"
                  >
                    에이전트 만들기
                  </button>
                </div>
              ) : (
                groups.map((group) => (
                  <div key={group.key} className="mb-2">
                    <div className="mb-1 px-1">
                      <span className="text-xs font-medium text-sidebar-fg-muted">
                        {group.label} ({group.agents.length})
                      </span>
                    </div>
                    {group.agents.map((agent) => {
                      const isSelected = agent.agent_id === selectedAgentId;
                      return (
                        <button
                          key={agent.agent_id}
                          type="button"
                          onClick={() => {
                            onSelectAgent(agent.agent_id);
                            navigate('/chatpage');
                          }}
                          aria-current={isSelected ? 'true' : undefined}
                          className={cn(
                            'w-full rounded-md px-3 py-2 text-left transition-colors duration-150',
                            isSelected
                              ? 'bg-sidebar-active text-sidebar-fg'
                              : 'text-sidebar-fg-muted hover:bg-sidebar-hover hover:text-sidebar-fg',
                          )}
                        >
                          <div className="flex items-center justify-between">
                            <p className="flex-1 truncate text-sm font-medium">{agent.name}</p>
                            {agent.is_pinned && (
                              <Star
                                className="ml-1 h-3 w-3 shrink-0 fill-current text-brand-400"
                                aria-label="고정됨"
                              />
                            )}
                          </div>
                          <p className="mt-0.5 truncate text-xs opacity-70">{agent.description}</p>
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>

      {/* (f) 하단 메뉴 */}
      <nav aria-label="보조 메뉴" className="space-y-0.5 border-t border-sidebar-border px-3 py-2">
        {BOTTOM_ITEMS.map((item) => (
          <SidebarItem
            key={item.id}
            label={item.label}
            icon={item.icon}
            collapsed={collapsed}
            isActive={isBottomActive(item.path)}
            onClick={() => item.path && navigate(item.path)}
            className={!item.path ? 'cursor-default' : undefined}
          />
        ))}

        {/* 관리자 진입 (role==='admin'일 때만 노출) */}
        {user?.role === 'admin' && (
          <SidebarItem
            label="관리자"
            icon={ShieldCheck}
            collapsed={collapsed}
            accent
            isActive={location.pathname.startsWith('/admin')}
            onClick={() => navigate(ADMIN_ENTRY_PATH)}
          />
        )}
      </nav>

      {/* (g) 사용자 + 로그아웃 */}
      {user && (
        <div className={cn('border-t border-sidebar-border', collapsed ? 'px-3 py-3' : 'px-4 py-3')}>
          <div className={cn('flex items-center gap-3', collapsed && 'flex-col gap-2')}>
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-semibold text-white"
              title={collapsed ? user.email : undefined}
              aria-hidden={!collapsed}
            >
              {user.email[0].toUpperCase()}
            </div>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-sidebar-fg">{user.email}</p>
                <p className="truncate text-xs text-sidebar-fg-muted">{user.email}</p>
              </div>
            )}
            <button
              type="button"
              onClick={() => logout()}
              disabled={isLoggingOut}
              aria-label="로그아웃"
              title="로그아웃"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-sidebar-fg-muted transition-colors duration-150 hover:bg-sidebar-hover hover:text-danger-border disabled:opacity-50"
            >
              <LogOut className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </aside>
  );
};

export default AppSidebar;
