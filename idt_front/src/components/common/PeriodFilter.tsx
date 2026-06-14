import { useMemo } from 'react';

export type PeriodPreset = 'today' | '7d' | '30d' | 'custom';

export interface PeriodValue {
  preset: PeriodPreset;
  from?: string; // ISO datetime
  to?: string;
}

interface Props {
  value: PeriodValue;
  onChange: (next: PeriodValue) => void;
}

function isoForDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString();
}

function isoNow(): string {
  return new Date().toISOString();
}

/** preset 선택 시 from/to 를 자동 계산하여 반환 */
export function resolvePeriod(preset: PeriodPreset): {
  from?: string;
  to?: string;
} {
  switch (preset) {
    case 'today':
      return { from: isoForDaysAgo(0), to: isoNow() };
    case '7d':
      return { from: isoForDaysAgo(7), to: isoNow() };
    case '30d':
      return { from: isoForDaysAgo(30), to: isoNow() };
    case 'custom':
      return {};
  }
}

const PRESETS: Array<{ label: string; value: PeriodPreset }> = [
  { label: '오늘', value: 'today' },
  { label: '7일', value: '7d' },
  { label: '30일', value: '30d' },
  { label: '사용자 지정', value: 'custom' },
];

const PeriodFilter = ({ value, onChange }: Props) => {
  const isCustom = value.preset === 'custom';

  const fromDate = useMemo(
    () => (value.from ? value.from.slice(0, 10) : ''),
    [value.from],
  );
  const toDate = useMemo(
    () => (value.to ? value.to.slice(0, 10) : ''),
    [value.to],
  );

  const handlePreset = (preset: PeriodPreset) => {
    const { from, to } = resolvePeriod(preset);
    onChange({ preset, from, to });
  };

  const handleCustomDate = (which: 'from' | 'to', dateStr: string) => {
    const iso = dateStr ? new Date(dateStr).toISOString() : undefined;
    onChange({ ...value, preset: 'custom', [which]: iso });
  };

  return (
    <div className="flex items-center gap-3">
      <div className="inline-flex overflow-hidden rounded-md border border-zinc-200 bg-white">
        {PRESETS.map((p) => {
          const active = value.preset === p.value;
          return (
            <button
              key={p.value}
              type="button"
              onClick={() => handlePreset(p.value)}
              className={[
                'px-3 py-1.5 text-xs font-medium transition',
                active
                  ? 'bg-violet-600 text-white'
                  : 'bg-white text-zinc-600 hover:bg-zinc-50',
              ].join(' ')}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      {isCustom && (
        <div className="flex items-center gap-2 text-xs text-zinc-600">
          <input
            type="date"
            value={fromDate}
            onChange={(e) => handleCustomDate('from', e.target.value)}
            className="rounded-md border border-zinc-200 px-2 py-1"
            aria-label="시작 날짜"
          />
          <span>~</span>
          <input
            type="date"
            value={toDate}
            onChange={(e) => handleCustomDate('to', e.target.value)}
            className="rounded-md border border-zinc-200 px-2 py-1"
            aria-label="종료 날짜"
          />
        </div>
      )}
    </div>
  );
};

export default PeriodFilter;
