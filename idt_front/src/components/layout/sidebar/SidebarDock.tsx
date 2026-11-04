// Design Ref: sidebar-agent-list §5.1 — 하단 보조 메뉴를 아이콘 한 줄 도크로 바꿔 목록 높이를 확보한다.
// 펼침: 6칸 한 줄 / 접힌 레일: 세로 한 열. 이름은 aria-label·title로 유지한다.
import type { ComponentType } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  BookOpen,
  Folder,
  KeyRound,
  LogOut,
  Settings,
  ShieldCheck,
  Star,
  type LucideProps,
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { useLogout } from '@/hooks/useAuth';
import { ADMIN_ENTRY_PATH } from '@/constants/adminNav';
import { cn } from '@/utils/cn';

interface SidebarDockProps {
  collapsed: boolean;
}

interface DockItem {
  id: string;
  label: string;
  path: string | null;
  icon: ComponentType<LucideProps>;
}

const DOCK_ITEMS: DockItem[] = [
  { id: 'favorites', label: '즐겨찾기', path: null, icon: Star },
  { id: 'roles', label: '역할설정', path: null, icon: KeyRound },
  { id: 'resources', label: '리소스', path: '/collections', icon: Folder },
  { id: 'kb', label: '지식베이스', path: '/knowledge-bases', icon: BookOpen },
  { id: 'settings', label: '환경설정', path: '/settings', icon: Settings },
];

interface DockButtonProps {
  label: string;
  icon: ComponentType<LucideProps>;
  isActive: boolean;
  accent?: boolean;
  disabledLook?: boolean;
  onClick: () => void;
}

const DockButton = ({ label, icon: Icon, isActive, accent = false, disabledLook = false, onClick }: DockButtonProps) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={label}
    title={label}
    aria-current={isActive ? 'page' : undefined}
    className={cn(
      'flex h-9 w-full items-center justify-center rounded-md transition-colors duration-150',
      isActive
        ? 'bg-sidebar-active text-sidebar-fg'
        : accent
          ? 'text-brand-300 hover:bg-sidebar-hover hover:text-brand-200'
          : 'text-sidebar-fg-muted hover:bg-sidebar-hover hover:text-sidebar-fg',
      disabledLook && 'cursor-default',
    )}
  >
    <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
  </button>
);

const SidebarDock = ({ collapsed }: SidebarDockProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuthStore();
  const { mutate: logout, isPending: isLoggingOut } = useLogout();

  const isActive = (path: string | null) =>
    !!path &&
    // kb-management-ui D7: 상세 라우트(/knowledge-bases/:kbId)에서도 활성 유지
    (path === '/knowledge-bases' ? location.pathname.startsWith(path) : location.pathname === path);

  return (
    <>
      <nav
        aria-label="보조 메뉴"
        className={cn(
          'grid gap-0.5 border-t border-sidebar-border py-2',
          collapsed ? 'grid-cols-1 px-3' : 'grid-cols-6 px-2.5',
        )}
      >
        {DOCK_ITEMS.map((item) => (
          <DockButton
            key={item.id}
            label={item.label}
            icon={item.icon}
            isActive={isActive(item.path)}
            disabledLook={!item.path}
            onClick={() => item.path && navigate(item.path)}
          />
        ))}
        {/* 관리자 진입 (role==='admin'일 때만 노출) */}
        {user?.role === 'admin' && (
          <DockButton
            label="관리자"
            icon={ShieldCheck}
            accent
            isActive={location.pathname.startsWith('/admin')}
            onClick={() => navigate(ADMIN_ENTRY_PATH)}
          />
        )}
      </nav>

      {/* Plan SC: FR-10 — 사용자 영역 1줄 (아바타 + 이메일 + 로그아웃) */}
      {user && (
        <div className={cn('border-t border-sidebar-border', collapsed ? 'px-3 py-3' : 'px-4 py-2.5')}>
          <div className={cn('flex items-center gap-3', collapsed && 'flex-col gap-2')}>
            <div
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-semibold text-white"
              title={collapsed ? user.email : undefined}
              aria-hidden={!collapsed}
            >
              {user.email[0].toUpperCase()}
            </div>
            {!collapsed && (
              <p className="min-w-0 flex-1 truncate text-sm font-medium text-sidebar-fg">{user.email}</p>
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
    </>
  );
};

export default SidebarDock;
