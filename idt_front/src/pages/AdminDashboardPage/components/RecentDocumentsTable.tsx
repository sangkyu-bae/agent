import type { RecentDocumentRow } from '@/types/adminDashboard';

interface Props {
  rows: RecentDocumentRow[] | undefined;
  loading?: boolean;
}

function fmtDate(iso: string): string {
  return iso.slice(0, 16).replace('T', ' ');
}

/** 최근 적재 문서 목록 (D9) */
const RecentDocumentsTable = ({ rows, loading }: Props) => {
  if (loading || !rows) {
    return (
      <div className="h-48 animate-pulse rounded-lg border border-zinc-100 bg-zinc-50" />
    );
  }

  if (rows.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-zinc-100 bg-white text-sm text-zinc-400">
        적재된 문서가 없습니다
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-100 bg-white">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-100 text-[11px] uppercase tracking-wider text-zinc-400">
            <th className="px-4 py-2.5 font-semibold">파일명</th>
            <th className="px-4 py-2.5 font-semibold">KB</th>
            <th className="px-4 py-2.5 text-right font-semibold">청크</th>
            <th className="px-4 py-2.5 font-semibold">전략</th>
            <th className="px-4 py-2.5 font-semibold">적재 시각</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.document_id}
              className="border-b border-zinc-50 last:border-0"
            >
              <td
                className="max-w-[200px] truncate px-4 py-2.5 font-medium text-zinc-800"
                title={r.filename}
              >
                {r.filename}
              </td>
              <td className="px-4 py-2.5 text-zinc-500">
                {r.kb_name ?? (
                  <span className="text-zinc-300">일반 업로드</span>
                )}
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums text-zinc-700">
                {r.chunk_count.toLocaleString('ko-KR')}
              </td>
              <td className="px-4 py-2.5 text-xs text-zinc-500">
                {r.chunk_strategy}
              </td>
              <td className="px-4 py-2.5 text-xs text-zinc-500">
                {fmtDate(r.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default RecentDocumentsTable;
