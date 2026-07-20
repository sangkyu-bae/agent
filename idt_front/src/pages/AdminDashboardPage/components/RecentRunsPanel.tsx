import type { RunRow } from '@/types/agentRunAdmin';

interface Props {
  recentRows: RunRow[] | undefined;
  failedRows: RunRow[] | undefined;
  loading?: boolean;
  onRowClick?: (runId: string) => void;
}

function fmtDate(iso: string): string {
  return iso.slice(5, 16).replace('T', ' ');
}

const RunList = ({
  title,
  rows,
  emptyText,
  onRowClick,
}: {
  title: string;
  rows: RunRow[];
  emptyText: string;
  onRowClick?: (runId: string) => void;
}) => (
  <div className="flex-1 rounded-lg border border-zinc-100 bg-white">
    <h3 className="border-b border-zinc-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-400">
      {title}
    </h3>
    {rows.length === 0 ? (
      <p className="px-4 py-6 text-center text-sm text-zinc-400">{emptyText}</p>
    ) : (
      <ul>
        {rows.map((r) => (
          <li key={r.id} className="border-b border-zinc-50 last:border-0">
            <button
              type="button"
              onClick={() => onRowClick?.(r.id)}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-zinc-50"
            >
              <span
                className={[
                  'h-1.5 w-1.5 shrink-0 rounded-full',
                  r.status === 'SUCCESS'
                    ? 'bg-emerald-500'
                    : r.status === 'FAILED'
                      ? 'bg-red-500'
                      : 'bg-amber-400',
                ].join(' ')}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-zinc-700">
                  {r.error_message ?? `${r.agent_id} · ${r.user_id}`}
                </span>
                <span className="text-[11px] text-zinc-400">
                  {fmtDate(r.started_at)}
                  {r.latency_ms !== null && ` · ${r.latency_ms}ms`}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    )}
  </div>
);

/** 최근 질문/실패 목록 — 기존 /admin/runs 재사용 (D8) */
const RecentRunsPanel = ({
  recentRows,
  failedRows,
  loading,
  onRowClick,
}: Props) => {
  if (loading || !recentRows || !failedRows) {
    return (
      <div className="flex gap-4">
        <div className="h-48 flex-1 animate-pulse rounded-lg border border-zinc-100 bg-zinc-50" />
        <div className="h-48 flex-1 animate-pulse rounded-lg border border-zinc-100 bg-zinc-50" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <RunList
        title="최근 질문"
        rows={recentRows}
        emptyText="기간 내 질문이 없습니다"
        onRowClick={onRowClick}
      />
      <RunList
        title="최근 실패"
        rows={failedRows}
        emptyText="기간 내 실패가 없습니다"
        onRowClick={onRowClick}
      />
    </div>
  );
};

export default RecentRunsPanel;
