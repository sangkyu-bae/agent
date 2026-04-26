import { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { useLogout } from '@/hooks/useAuth';

interface DropdownItem {
  label: string;
  path: string;
  icon: string;
  description: string;
}

interface NavMenu {
  label: string;
  items: DropdownItem[];
}

const NAV_MENUS: NavMenu[] = [
  {
    label: '데이터',
    items: [
      {
        label: '컬렉션 관리',
        path: '/collections',
        icon: 'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125',
        description: 'Qdrant 벡터 컬렉션을 관리하고 사용 이력을 확인합니다',
      },
    ],
  },
  {
    label: '에이전트',
    items: [
      {
        label: '에이전트 만들기',
        path: '/agent-builder',
        icon: 'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z',
        description: '새로운 AI 에이전트를 설계하고 구성합니다',
      },
      {
        label: '도구 연결',
        path: '/tool-connection',
        icon: 'M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z',
        description: '검색, 코드 실행, API 등 도구를 에이전트에 연결합니다',
      },
      {
        label: '워크플로우 설계',
        path: '/workflow-designer',
        icon: 'M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6',
        description: '에이전트 처리 단계를 시각적으로 설계합니다',
      },
      {
        label: '플로우 빌더',
        path: '/workflow-builder',
        icon: 'M7.5 3.75H6A2.25 2.25 0 0 0 3.75 6v1.5M16.5 3.75H18A2.25 2.25 0 0 1 20.25 6v1.5m0 9V18A2.25 2.25 0 0 1 18 20.25h-1.5m-9 0H6A2.25 2.25 0 0 1 3.75 18v-1.5M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
        description: '노드를 선으로 연결하여 에이전트 플로우를 직접 그립니다',
      },
      {
        label: '도구 관리',
        path: '/tool-admin',
        icon: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
        description: '에이전트에서 사용할 도구를 추가·수정·삭제합니다',
      },
    ],
  },
];

const TopNav = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const navRef = useRef<HTMLDivElement>(null);
  const { user } = useAuthStore();
  const { mutate: logout, isPending: isLoggingOut } = useLogout();

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenMenu(null);
        setUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNavigate = (path: string) => {
    navigate(path);
    setOpenMenu(null);
  };

  const isMenuActive = (menu: NavMenu) =>
    menu.items.some((item) => location.pathname === item.path);

  return (
    <nav
      ref={navRef}
      className="relative z-50 flex h-[52px] shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-4"
    >
      {/* 로고 */}
      <button
        onClick={() => navigate('/chatpage')}
        className="flex items-center gap-2.5 transition-opacity hover:opacity-80"
      >
        <div
          className="flex h-7 w-7 items-center justify-center rounded-lg"
          style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
        >
          <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
          </svg>
        </div>
        <span className="text-[13.5px] font-semibold text-zinc-900">IDT Platform</span>
      </button>

      {/* 메뉴 + 사용자 영역 */}
      <div className="flex items-center gap-1">
        {NAV_MENUS.map((menu) => {
          const isOpen = openMenu === menu.label;
          const isActive = isMenuActive(menu);

          return (
            <div key={menu.label} className="relative">
              <button
                onClick={() => setOpenMenu(isOpen ? null : menu.label)}
                className={`flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13.5px] font-medium transition-all ${
                  isActive || isOpen
                    ? 'bg-violet-50 text-violet-700'
                    : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900'
                }`}
              >
                {menu.label}
                <svg
                  className={`h-3.5 w-3.5 transition-transform duration-150 ${isOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2.5}
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
                </svg>
              </button>

              {/* 드롭다운 */}
              {isOpen && (
                <div className="absolute right-0 top-full mt-1.5 w-64 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-xl shadow-zinc-200/60">
                  <div className="p-1.5">
                    {menu.items.map((item) => {
                      const isItemActive = location.pathname === item.path;
                      return (
                        <button
                          key={item.path}
                          onClick={() => handleNavigate(item.path)}
                          className={`flex w-full items-start gap-3 rounded-xl px-3.5 py-3 text-left transition-all ${
                            isItemActive
                              ? 'bg-violet-50'
                              : 'hover:bg-zinc-50'
                          }`}
                        >
                          <div
                            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                            style={
                              isItemActive
                                ? { background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }
                                : { background: '#f4f4f5' }
                            }
                          >
                            <svg
                              className={`h-4 w-4 ${isItemActive ? 'text-white' : 'text-zinc-500'}`}
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={1.5}
                              stroke="currentColor"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                            </svg>
                          </div>
                          <div>
                            <p className={`text-[13.5px] font-medium ${isItemActive ? 'text-violet-700' : 'text-zinc-800'}`}>
                              {item.label}
                            </p>
                            <p className="mt-0.5 text-[11.5px] leading-tight text-zinc-400">
                              {item.description}
                            </p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {/* 사용자 아바타 + 드롭다운 */}
        {user && (
          <div className="relative ml-2">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-violet-600 text-[12px] font-semibold text-white transition-all hover:bg-violet-700 active:scale-95"
            >
              {user.email[0].toUpperCase()}
            </button>

            {userMenuOpen && (
              <div className="absolute right-0 top-full mt-1.5 w-52 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-xl shadow-zinc-200/60">
                {/* 사용자 정보 */}
                <div className="border-b border-zinc-100 px-4 py-3">
                  <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                    로그인 계정
                  </p>
                  <p className="mt-0.5 truncate text-[13px] text-zinc-700">{user.email}</p>
                </div>
                {/* 로그아웃 */}
                <div className="p-1.5">
                  <button
                    onClick={() => { logout(); setUserMenuOpen(false); }}
                    disabled={isLoggingOut}
                    className="flex w-full items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-left text-[13.5px] font-medium text-zinc-600 transition-all hover:bg-red-50 hover:text-red-500 disabled:opacity-50"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
                    </svg>
                    {isLoggingOut ? '로그아웃 중...' : '로그아웃'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </nav>
  );
};

export default TopNav;
