import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import TopNav from '@/components/layout/TopNav';
import AdminSectionTabs from '@/components/layout/AdminSectionTabs';
import { ADMIN_NAV_GROUPS, findAdminGroupByPath } from '@/constants/adminNav';

const AdminLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const activeGroup = findAdminGroupByPath(location.pathname);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <TopNav />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Sidebar — 그룹 단위 네비게이션 */}
        <nav
          aria-label="관리 메뉴"
          className="flex w-56 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50"
        >
          <div className="flex-1 px-3 py-4">
            <p className="mb-3 px-3 text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
              Admin
            </p>
            <ul className="space-y-1">
              {ADMIN_NAV_GROUPS.map((group) => {
                const isActive = group.key === activeGroup?.key;
                return (
                  <li key={group.key}>
                    <button
                      onClick={() => navigate(group.items[0].path)}
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
                        <path strokeLinecap="round" strokeLinejoin="round" d={group.icon} />
                      </svg>
                      {group.label}
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

        {/* 본문 — 2차 탭 바(고정) + 스크롤 영역 */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          {activeGroup && <AdminSectionTabs group={activeGroup} />}
          <main style={{ flex: 1, overflowY: 'auto', background: '#fff' }}>
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
};

export default AdminLayout;
