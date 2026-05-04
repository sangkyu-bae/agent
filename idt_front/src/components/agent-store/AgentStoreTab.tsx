import type { MyAgentFilter } from '@/types/agentStore';

type StoreTab = 'public' | 'department' | 'my';

interface AgentStoreTabProps {
  activeTab: StoreTab;
  onTabChange: (tab: StoreTab) => void;
  myFilter?: MyAgentFilter;
  onMyFilterChange?: (filter: MyAgentFilter) => void;
}

const TABS: { key: StoreTab; label: string }[] = [
  { key: 'public', label: '전체 공개' },
  { key: 'department', label: '부서별' },
  { key: 'my', label: '내 에이전트' },
];

const MY_FILTERS: { key: MyAgentFilter; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'owned', label: '소유' },
  { key: 'subscribed', label: '구독' },
  { key: 'forked', label: '포크' },
];

const AgentStoreTab = ({
  activeTab,
  onTabChange,
  myFilter = 'all',
  onMyFilterChange,
}: AgentStoreTabProps) => {
  return (
    <div className="border-b border-zinc-200">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 sm:px-6">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className={`relative py-3 text-[13.5px] font-medium transition-colors ${
              activeTab === tab.key
                ? 'text-violet-600'
                : 'text-zinc-500 hover:text-zinc-700'
            }`}
          >
            {tab.label}
            {activeTab === tab.key && (
              <span className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-violet-600" />
            )}
          </button>
        ))}

        {activeTab === 'my' && onMyFilterChange && (
          <div className="ml-auto flex items-center gap-1">
            {MY_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => onMyFilterChange(f.key)}
                className={`rounded-lg px-2.5 py-1 text-[12px] font-medium transition-all ${
                  myFilter === f.key
                    ? 'bg-violet-100 text-violet-700'
                    : 'text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentStoreTab;
