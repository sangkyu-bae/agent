import type { KbBreakdownRow } from '@/types/adminDashboard';

interface Props {
  rows: KbBreakdownRow[] | undefined;
  loading?: boolean;
}

const SCOPE_LABELS: Record<string, string> = {
  PERSONAL: '개인',
  DEPARTMENT: '부서',
  PUBLIC: '전체 공개',
};

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  return iso.slice(0, 16).replace('T', ' ');
}

/** KB별 문서/청크 현황 — 문서 0건 KB 포함 (D4) */
const KbBreakdownTable = ({ rows, loading }: Props) => {
  if (loading || !rows) {
    return (
      <div className="h-48 animate-pulse rounded-lg border border-zinc-100 bg-zinc-50" />
    );
  }

  if (rows.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-zinc-100 bg-white text-sm text-zinc-400">
        등록된 지식 베이스가 없습니다
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-100 bg-white">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-100 text-[11px] uppercase tracking-wider text-zinc-400">
            <th className="px-4 py-2.5 font-semibold">KB</th>
            <th className="px-4 py-2.5 font-semibold">범위</th>
            <th className="px-4 py-2.5 text-right font-semibold">문서</th>
            <th className="px-4 py-2.5 text-right font-semibold">청크</th>
            <th className="px-4 py-2.5 font-semibold">최근 업로드</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.kb_id} className="border-b border-zinc-50 last:border-0">
              <td className="px-4 py-2.5">
                <span className="font-medium text-zinc-800">{r.name}</span>
                {r.status !== 'active' && (
                  <span className="ml-2 rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-500">
                    {r.status}
                  </span>
                )}
              </td>
              <td className="px-4 py-2.5 text-zinc-500">
                {SCOPE_LABELS[r.scope] ?? r.scope}
              </td>
              <td
                className={[
                  'px-4 py-2.5 text-right tabular-nums',
                  r.document_count === 0
                    ? 'text-zinc-300'
                    : 'text-zinc-700',
                ].join(' ')}
              >
                {r.document_count.toLocaleString('ko-KR')}
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums text-zinc-700">
                {r.chunk_count.toLocaleString('ko-KR')}
              </td>
              <td className="px-4 py-2.5 text-xs text-zinc-500">
                {fmtDate(r.last_uploaded_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default KbBreakdownTable;
