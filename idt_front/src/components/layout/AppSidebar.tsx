// Design Ref: ui-redesign-chat §5.5 — 256px 전체 / 64px 아이콘 레일. 접힌 상태에서도 모든 버튼은 aria-label로 접근 가능한 이름을 유지한다.
// Design Ref: sidebar-agent-list §2.1 — 에이전트 목록은 AgentList, 하단 메뉴·사용자는 SidebarDock으로 분리. props는 그대로.
import type { ButtonHTMLAttributes, ComponentType } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  BarChart3,
  Clock,
  LayoutGrid,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Sparkles,
  Store,
  Wrench,
  type LucideProps,
} from 'lucide-react';
import { useLayoutStore } from '@/store/layoutStore';
import { cn } from '@/utils/cn';
import AgentList from '@/components/layout/sidebar/AgentList';
import SidebarDock from '@/components/layout/sidebar/SidebarDock';
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
  const collapsed = useLayoutStore((s) => s.isSidebarCollapsed);
  const toggleSidebar = useLayoutStore((s) => s.toggleSidebar);
  const setSidebarCollapsed = useLayoutStore((s) => s.setSidebarCollapsed);

  const handleNavClick = (item: NavItem) => {
    if (item.id === 'super') {
      onSelectAgent('super');
    }
    if (item.path) navigate(item.path);
  };

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
          <AgentList
            agents={agents}
            selectedAgentId={selectedAgentId}
            onSelectAgent={onSelectAgent}
            isLoading={isLoading}
            isError={isError}
            onRetry={onRetry}
          />
        )}
      </div>

      {/* (f)(g) 하단 메뉴 도크 + 사용자 */}
      <SidebarDock collapsed={collapsed} />
    </aside>
  );
};

export default AppSidebar;
