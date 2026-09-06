import {
  JOB_PERIOD_OPTIONS,
  JOB_STATUS_GROUP_OPTIONS,
  JOB_TYPE_OPTIONS,
} from '@/types/backgroundJob';
import type { JobHistoryFilters } from '@/types/backgroundJob';

// jobs-page-revamp Design §5.4 — 상태·유형·기간 3단 필터 (FR-07~09)
// 필터가 바뀌면 페이지를 0으로 되돌리는 책임은 상위(JobsPage)에 있다.

interface FilterGroupProps {
  label: string;
  options: readonly { readonly value: string; readonly label: string }[];
  value: string;
  onChange: (value: string) => void;
}

const FilterGroup = ({ label, options, value, onChange }: FilterGroupProps) => (
  <div className="flex items-center gap-1" role="group" aria-label={label}>
    {options.map((opt) => (
      <button
        key={opt.value}
        type="button"
        aria-pressed={value === opt.value}
        onClick={() => onChange(opt.value)}
        className={`rounded-lg px-3 py-1.5 text-[13px] font-medium transition-all ${
          value === opt.value
            ? 'bg-zinc-900 text-white'
            : 'text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700'
        }`}
      >
        {opt.label}
      </button>
    ))}
  </div>
);

interface JobFilterBarProps {
  filters: JobHistoryFilters;
  onChange: (next: JobHistoryFilters) => void;
}

const JobFilterBar = ({ filters, onChange }: JobFilterBarProps) => (
  <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 px-5 py-3">
    <FilterGroup
      label="상태 필터"
      options={JOB_STATUS_GROUP_OPTIONS}
      value={filters.status}
      onChange={(v) =>
        onChange({ ...filters, status: v as JobHistoryFilters['status'] })
      }
    />
    <FilterGroup
      label="유형 필터"
      options={JOB_TYPE_OPTIONS}
      value={filters.type}
      onChange={(v) =>
        onChange({ ...filters, type: v as JobHistoryFilters['type'] })
      }
    />
    <FilterGroup
      label="기간 필터"
      options={JOB_PERIOD_OPTIONS}
      value={filters.period}
      onChange={(v) =>
        onChange({ ...filters, period: v as JobHistoryFilters['period'] })
      }
    />
  </div>
);

export default JobFilterBar;
