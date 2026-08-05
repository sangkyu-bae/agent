import { useNavigate, useLocation } from 'react-router-dom';
import { isAdminItemActive, type AdminNavGroup } from '@/constants/adminNav';

interface AdminSectionTabsProps {
  group: AdminNavGroup;
}

const AdminSectionTabs = ({ group }: AdminSectionTabsProps) => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div
      role="tablist"
      aria-label={`${group.label} 하위 메뉴`}
      className="flex shrink-0 items-center gap-1 border-b border-zinc-200 bg-white px-6"
    >
      {group.items.map((item) => {
        const isActive = isAdminItemActive(item, location.pathname);
        return (
          <button
            key={item.path}
            role="tab"
            aria-selected={isActive}
            onClick={() => navigate(item.path)}
            className={`-mb-px border-b-2 px-3.5 py-3 text-[13.5px] font-medium transition-all ${
              isActive
                ? 'border-violet-600 text-violet-700'
                : 'border-transparent text-zinc-500 hover:text-zinc-800'
            }`}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
};

export default AdminSectionTabs;
