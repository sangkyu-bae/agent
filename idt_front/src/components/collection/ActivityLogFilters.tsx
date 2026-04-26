import type { ActivityLogFilters as Filters } from '@/types/collection';

interface ActivityLogFiltersProps {
  filters: Filters;
  collections: string[];
  onChange: (filters: Filters) => void;
}

const ACTION_OPTIONS = ['CREATE', 'DELETE', 'SEARCH', 'RENAME'] as const;

const ActivityLogFiltersPanel = ({
  filters,
  collections,
  onChange,
}: ActivityLogFiltersProps) => {
  const update = (patch: Partial<Filters>) =>
    onChange({ ...filters, ...patch, offset: 0 });

  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <select
        value={filters.collection_name ?? ''}
        onChange={(e) =>
          update({ collection_name: e.target.value || undefined })
        }
        className="rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13.5px] text-zinc-700 outline-none transition-all focus:border-violet-400"
      >
        <option value="">전체 컬렉션</option>
        {collections.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

      <select
        value={filters.action ?? ''}
        onChange={(e) => update({ action: e.target.value || undefined })}
        className="rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13.5px] text-zinc-700 outline-none transition-all focus:border-violet-400"
      >
        <option value="">전체 액션</option>
        {ACTION_OPTIONS.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>

      <input
        type="text"
        value={filters.user_id ?? ''}
        onChange={(e) => update({ user_id: e.target.value || undefined })}
        placeholder="사용자 ID"
        className="rounded-xl border border-zinc-300 px-3 py-2 text-[13.5px] text-zinc-700 placeholder-zinc-400 outline-none transition-all focus:border-violet-400"
      />

      <input
        type="date"
        value={filters.from_date ?? ''}
        onChange={(e) => update({ from_date: e.target.value || undefined })}
        className="rounded-xl border border-zinc-300 px-3 py-2 text-[13.5px] text-zinc-700 outline-none transition-all focus:border-violet-400"
      />
      <span className="text-[12px] text-zinc-400">~</span>
      <input
        type="date"
        value={filters.to_date ?? ''}
        onChange={(e) => update({ to_date: e.target.value || undefined })}
        className="rounded-xl border border-zinc-300 px-3 py-2 text-[13.5px] text-zinc-700 outline-none transition-all focus:border-violet-400"
      />
    </div>
  );
};

export default ActivityLogFiltersPanel;
