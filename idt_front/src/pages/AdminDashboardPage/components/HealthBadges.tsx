import type { HealthComponent } from '@/types/adminDashboard';

interface Props {
  components: HealthComponent[] | undefined;
  loading?: boolean;
}

const LABELS: Record<string, string> = {
  mysql: 'MySQL',
  qdrant: 'Qdrant',
  elasticsearch: 'Elasticsearch',
};

/** 저장소 헬스 배지 — 부분 실패 격리 표시 (D5) */
const HealthBadges = ({ components, loading }: Props) => {
  if (loading || !components) {
    return (
      <div className="flex gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="h-7 w-28 animate-pulse rounded-full border border-zinc-100 bg-zinc-50"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {components.map((c) => {
        const ok = c.status === 'ok';
        return (
          <span
            key={c.name}
            title={c.error ?? undefined}
            className={[
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium',
              ok
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-red-200 bg-red-50 text-red-700',
            ].join(' ')}
          >
            <span
              className={[
                'h-1.5 w-1.5 rounded-full',
                ok ? 'bg-emerald-500' : 'bg-red-500',
              ].join(' ')}
            />
            {LABELS[c.name] ?? c.name}
            {ok && c.latency_ms !== null && (
              <span className="opacity-60">{c.latency_ms}ms</span>
            )}
            {!ok && <span className="opacity-70">{c.error}</span>}
          </span>
        );
      })}
    </div>
  );
};

export default HealthBadges;
