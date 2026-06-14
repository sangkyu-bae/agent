import type { RunListResponse, RunRow } from '@/types/agentRunAdmin';

interface Props {
  data: RunListResponse | undefined;
  loading?: boolean;
  onRowClick: (runId: string) => void;
  onPageChange: (offset: number) => void;
}

const STATUS_COLORS: Record<string, string> = {
  RUNNING: 'bg-sky-50 text-sky-600',
  SUCCESS: 'bg-emerald-50 text-emerald-600',
  FAILED: 'bg-red-50 text-red-600',
  CANCELLED: 'bg-zinc-100 text-zinc-500',
};

function fmtCost(c: string | number): string {
  const v = typeof c === 'string' ? parseFloat(c) : c;
  if (Number.isNaN(v)) return '—';
  return `$${v.toFixed(4)}`;
}

function fmtDate(s: string | null): string {
  if (!s) return '—';
  return new Date(s).toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function fmtLatency(ms: number | null): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const RunListTable = ({ data, loading, onRowClick, onPageChange }: Props) => {
  if (loading || !data) {
    return (
      <div className="flex h-48 animate-pulse items-center justify-center rounded-lg border border-zinc-100 bg-zinc-50 text-sm text-zinc-400">
        Run 목록 로딩 중...
      </div>
    );
  }

  if (data.rows.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-zinc-100 bg-white text-sm text-zinc-400">
        조건에 맞는 Run이 없습니다
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(data.total / data.limit));
  const currentPage = Math.floor(data.offset / data.limit) + 1;

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="px-3 py-2 text-left">ID</th>
              <th className="px-3 py-2 text-left">User</th>
              <th className="px-3 py-2 text-left">Agent</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-right">Tokens</th>
              <th className="px-3 py-2 text-right">Cost</th>
              <th className="px-3 py-2 text-right">Latency</th>
              <th className="px-3 py-2 text-right">Started</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r: RunRow) => (
              <tr
                key={r.id}
                onClick={() => onRowClick(r.id)}
                className="cursor-pointer border-t border-zinc-100 hover:bg-zinc-50"
              >
                <td className="px-3 py-2 font-mono text-xs">
                  {r.id.slice(0, 8)}…
                </td>
                <td className="px-3 py-2 font-mono text-xs">{r.user_id}</td>
                <td className="px-3 py-2 font-mono text-xs">
                  {r.agent_id.slice(0, 8)}…
                </td>
                <td className="px-3 py-2">
                  <span
                    className={[
                      'rounded-full px-2 py-0.5 text-[11px] font-medium',
                      STATUS_COLORS[r.status] ?? 'bg-zinc-100 text-zinc-500',
                    ].join(' ')}
                  >
                    {r.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  {r.total_tokens.toLocaleString('ko-KR')}
                </td>
                <td className="px-3 py-2 text-right">{fmtCost(r.total_cost_usd)}</td>
                <td className="px-3 py-2 text-right">{fmtLatency(r.latency_ms)}</td>
                <td className="px-3 py-2 text-right text-xs text-zinc-500">
                  {fmtDate(r.started_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-zinc-500">
        <span>
          총 <b>{data.total.toLocaleString('ko-KR')}</b>건 · {currentPage} / {totalPages}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={data.offset === 0}
            onClick={() => onPageChange(Math.max(0, data.offset - data.limit))}
            className="rounded border border-zinc-200 px-2 py-1 disabled:opacity-40"
          >
            이전
          </button>
          <button
            type="button"
            disabled={data.offset + data.limit >= data.total}
            onClick={() => onPageChange(data.offset + data.limit)}
            className="rounded border border-zinc-200 px-2 py-1 disabled:opacity-40"
          >
            다음
          </button>
        </div>
      </div>
    </div>
  );
};

export default RunListTable;
