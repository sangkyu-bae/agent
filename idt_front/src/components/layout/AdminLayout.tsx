import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import TopNav from '@/components/layout/TopNav';

interface AdminSidebarItem {
  label: string;
  path: string;
  icon: string;
}

const ADMIN_SIDEBAR_ITEMS: AdminSidebarItem[] = [
  {
    label: '사용자 관리',
    path: '/admin/users',
    icon: 'M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128H5.228A2 2 0 0 1 3.22 17.07a8.632 8.632 0 0 1 2.026-4.564c1.128-1.188 2.714-1.927 4.504-1.927 1.79 0 3.375.739 4.504 1.927M12 9.75a3.75 3.75 0 1 0 0-7.5 3.75 3.75 0 0 0 0 7.5Z',
  },
  {
    label: '부서 관리',
    path: '/admin/departments',
    icon: 'M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21',
  },
];

const AdminLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <TopNav />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Sidebar */}
        <nav
          aria-label="관리 메뉴"
          className="flex w-56 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50"
        >
          <div className="flex-1 px-3 py-4">
            <p className="mb-3 px-3 text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
              Admin
            </p>
            <ul className="space-y-1">
              {ADMIN_SIDEBAR_ITEMS.map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <li key={item.path}>
                    <button
                      onClick={() => navigate(item.path)}
                      className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13.5px] font-medium transition-all ${
                        isActive
                          ? 'bg-violet-50 font-semibold text-violet-700'
                          : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900'
                      }`}
                    >
                      <svg
                        className="h-[18px] w-[18px] shrink-0"
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={1.5}
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                      </svg>
                      {item.label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* 하단 복귀 링크 */}
          <div className="border-t border-zinc-200 px-3 py-3">
            <button
              onClick={() => navigate('/chatpage')}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-[13px] text-zinc-400 transition-all hover:bg-zinc-100 hover:text-zinc-600"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
              </svg>
              메인으로 돌아가기
            </button>
          </div>
        </nav>

        {/* 본문 */}
        <main style={{ flex: 1, overflowY: 'auto', background: '#fff' }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default AdminLayout;
