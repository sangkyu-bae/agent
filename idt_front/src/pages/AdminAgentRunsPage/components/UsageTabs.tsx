import type {
  UsageByLlmResponse,
  UsageByNodeResponse,
  UsageByUserResponse,
} from '@/types/agentRunAdmin';

function fmtCost(c: string | number): string {
  const v = typeof c === 'string' ? parseFloat(c) : c;
  if (Number.isNaN(v)) return '—';
  return `$${v.toFixed(4)}`;
}

function fmtNumber(n: number): string {
  return n.toLocaleString('ko-KR');
}

interface SectionProps {
  data: UsageByUserResponse | UsageByLlmResponse | UsageByNodeResponse | undefined;
  loading?: boolean;
  emptyHint: string;
  children: (
    rows: (
      | UsageByUserResponse['rows'][number]
      | UsageByLlmResponse['rows'][number]
      | UsageByNodeResponse['rows'][number]
    )[],
  ) => React.ReactNode;
}

const TableShell = ({ data, loading, emptyHint, children }: SectionProps) => {
  if (loading || !data) {
    return (
      <div className="flex h-32 animate-pulse items-center justify-center rounded-lg border border-zinc-100 bg-zinc-50 text-sm text-zinc-400">
        로딩 중...
      </div>
    );
  }
  if (data.rows.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-zinc-100 bg-white text-sm text-zinc-400">
        {emptyHint}
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
      {children(data.rows)}
    </div>
  );
};

// ── 사용자별 ────────────────────────────────────────────

export const UsageByUserTab = ({
  data,
  loading,
}: {
  data: UsageByUserResponse | undefined;
  loading?: boolean;
}) => (
  <TableShell data={data} loading={loading} emptyHint="사용자별 사용량 데이터가 없습니다">
    {(rows) => (
      <table className="w-full text-sm">
        <thead className="bg-zinc-50 text-xs uppercase tracking-wider text-zinc-500">
          <tr>
            <th className="px-3 py-2 text-left">User ID</th>
            <th className="px-3 py-2 text-right">Calls</th>
            <th className="px-3 py-2 text-right">Tokens</th>
            <th className="px-3 py-2 text-right">Cost</th>
          </tr>
        </thead>
        <tbody>
          {(rows as UsageByUserResponse['rows']).map((r) => (
            <tr key={r.user_id} className="border-t border-zinc-100">
              <td className="px-3 py-2 font-mono text-xs">{r.user_id}</td>
              <td className="px-3 py-2 text-right">{fmtNumber(r.call_count)}</td>
              <td className="px-3 py-2 text-right">{fmtNumber(r.total_tokens)}</td>
              <td className="px-3 py-2 text-right">{fmtCost(r.total_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </TableShell>
);

// ── LLM별 ─────────────────────────────────────────────

export const UsageByLlmTab = ({
  data,
  loading,
}: {
  data: UsageByLlmResponse | undefined;
  loading?: boolean;
}) => (
  <TableShell data={data} loading={loading} emptyHint="LLM별 사용량 데이터가 없습니다">
    {(rows) => (
      <table className="w-full text-sm">
        <thead className="bg-zinc-50 text-xs uppercase tracking-wider text-zinc-500">
          <tr>
            <th className="px-3 py-2 text-left">Provider</th>
            <th className="px-3 py-2 text-left">Model</th>
            <th className="px-3 py-2 text-right">Calls</th>
            <th className="px-3 py-2 text-right">Tokens</th>
            <th className="px-3 py-2 text-right">Cost</th>
          </tr>
        </thead>
        <tbody>
          {(rows as UsageByLlmResponse['rows']).map((r, i) => (
            <tr
              key={`${r.llm_model_id ?? 'null'}-${i}`}
              className="border-t border-zinc-100"
            >
              <td className="px-3 py-2">{r.provider}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.model_name}</td>
              <td className="px-3 py-2 text-right">{fmtNumber(r.call_count)}</td>
              <td className="px-3 py-2 text-right">{fmtNumber(r.total_tokens)}</td>
              <td className="px-3 py-2 text-right">{fmtCost(r.total_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </TableShell>
);

// ── 노드별 ─────────────────────────────────────────────

export const UsageByNodeTab = ({
  data,
  loading,
}: {
  data: UsageByNodeResponse | undefined;
  loading?: boolean;
}) => (
  <TableShell data={data} loading={loading} emptyHint="노드별 사용량 데이터가 없습니다">
    {(rows) => (
      <table className="w-full text-sm">
        <thead className="bg-zinc-50 text-xs uppercase tracking-wider text-zinc-500">
          <tr>
            <th className="px-3 py-2 text-left">Node</th>
            <th className="px-3 py-2 text-right">Calls</th>
            <th className="px-3 py-2 text-right">Tokens</th>
            <th className="px-3 py-2 text-right">Cost</th>
          </tr>
        </thead>
        <tbody>
          {(rows as UsageByNodeResponse['rows']).map((r) => (
            <tr key={r.node_name} className="border-t border-zinc-100">
              <td className="px-3 py-2 font-mono text-xs">{r.node_name}</td>
              <td className="px-3 py-2 text-right">{fmtNumber(r.call_count)}</td>
              <td className="px-3 py-2 text-right">{fmtNumber(r.total_tokens)}</td>
              <td className="px-3 py-2 text-right">{fmtCost(r.total_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </TableShell>
);
