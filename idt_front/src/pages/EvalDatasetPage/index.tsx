// eval-hub: 평가 허브 — 데이터셋/평가 실행/평가기/대시보드 4탭 (revlu 시안)
import { useSearchParams } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import DatasetsTab from './DatasetsTab';
import RunsTab from './RunsTab';
import EvaluatorsTab from './EvaluatorsTab';
import DashboardTab from './DashboardTab';

const TABS = [
  { key: 'datasets', label: '데이터셋' },
  { key: 'runs', label: '평가 실행' },
  { key: 'evaluators', label: '평가기' },
  { key: 'dashboard', label: '대시보드', adminOnly: true },
] as const;

type TabKey = (typeof TABS)[number]['key'];

const EvalDatasetPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin');

  const visibleTabs = TABS.filter((t) => !('adminOnly' in t && t.adminOnly) || isAdmin);
  const requested = searchParams.get('tab') as TabKey | null;
  const activeTab: TabKey = visibleTabs.some((t) => t.key === requested)
    ? (requested as TabKey)
    : 'datasets';

  const selectTab = (key: TabKey) => {
    setSearchParams({ tab: key });
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-white">
      <header className="shrink-0 border-b border-zinc-200 px-6 py-4">
        <h1 className="text-[20px] font-semibold text-violet-600">평가</h1>
        <p className="mt-0.5 text-[12.5px] text-zinc-500">
          평가 데이터셋, 실행, 평가기를 관리합니다
        </p>
      </header>

      <div className="shrink-0 border-b border-zinc-100 px-6 py-3">
        <div role="tablist" className="inline-flex items-center gap-1 rounded-xl bg-zinc-100 p-1">
          {visibleTabs.map((tab) => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => selectTab(tab.key)}
              className={`rounded-lg px-4 py-1.5 text-[13px] font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-zinc-900 text-white shadow-sm'
                  : 'text-zinc-600 hover:text-zinc-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {activeTab === 'datasets' && <DatasetsTab />}
        {activeTab === 'runs' && <RunsTab />}
        {activeTab === 'evaluators' && <EvaluatorsTab />}
        {activeTab === 'dashboard' && isAdmin && <DashboardTab />}
      </div>
    </div>
  );
};

export default EvalDatasetPage;
