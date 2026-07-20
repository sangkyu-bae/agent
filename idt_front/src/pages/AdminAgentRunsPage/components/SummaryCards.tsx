interface CardProps {
  label: string;
  value: string;
  hint?: string;
  accent?: 'violet' | 'emerald' | 'amber' | 'sky';
}

const ACCENT_CLASSES: Record<NonNullable<CardProps['accent']>, string> = {
  violet: 'border-violet-200 bg-violet-50 text-violet-700',
  emerald: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  amber: 'border-amber-200 bg-amber-50 text-amber-700',
  sky: 'border-sky-200 bg-sky-50 text-sky-700',
};

/** 범용 스탯 카드 — 운영 대시보드(admin-dashboard D6) 등 cross-page 재사용 */
export const Card = ({ label, value, hint, accent = 'violet' }: CardProps) => (
  <div
    className={[
      'flex flex-col rounded-lg border p-4',
      ACCENT_CLASSES[accent],
    ].join(' ')}
  >
    <span className="text-[11px] font-semibold uppercase tracking-widest opacity-70">
      {label}
    </span>
    <span className="mt-2 text-2xl font-semibold">{value}</span>
    {hint && <span className="mt-1 text-xs opacity-70">{hint}</span>}
  </div>
);

interface Props {
  totalRuns: number | undefined;
  successRate: number | undefined; // 0..1
  totalTokens: number | undefined;
  totalCostUsd: string | number | undefined;
  loading?: boolean;
}

function fmtNumber(n: number | undefined): string {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString('ko-KR');
}

function fmtCost(c: string | number | undefined): string {
  if (c === undefined || c === null) return '—';
  const v = typeof c === 'string' ? parseFloat(c) : c;
  if (Number.isNaN(v)) return '—';
  return `$${v.toFixed(4)}`;
}

function fmtRate(r: number | undefined): string {
  if (r === undefined || r === null) return '—';
  return `${(r * 100).toFixed(1)}%`;
}

const SummaryCards = ({
  totalRuns,
  successRate,
  totalTokens,
  totalCostUsd,
  loading,
}: Props) => {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg border border-zinc-100 bg-zinc-50"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card
        label="총 Run"
        value={fmtNumber(totalRuns)}
        accent="violet"
      />
      <Card
        label="성공률"
        value={fmtRate(successRate)}
        accent="emerald"
      />
      <Card
        label="총 토큰"
        value={fmtNumber(totalTokens)}
        accent="sky"
      />
      <Card
        label="총 비용"
        value={fmtCost(totalCostUsd)}
        accent="amber"
      />
    </div>
  );
};

export default SummaryCards;
