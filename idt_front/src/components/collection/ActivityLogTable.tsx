import type { ActivityLog } from '@/types/collection';

interface ActivityLogTableProps {
  logs: ActivityLog[];
  total: number;
  limit: number;
  offset: number;
  isLoading: boolean;
  isError: boolean;
  onPageChange: (newOffset: number) => void;
  onRetry: () => void;
}

const ACTION_BADGE: Record<string, string> = {
  CREATE: 'bg-emerald-50 text-emerald-600',
  DELETE: 'bg-red-50 text-red-600',
  SEARCH: 'bg-blue-50 text-blue-600',
  RENAME: 'bg-amber-50 text-amber-600',
};

const formatTime = (iso: string) => {
  const d = new Date(iso);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${mm}-${dd} ${hh}:${mi}`;
};

const truncateJson = (detail: Record<string, unknown> | null) => {
  if (!detail) return '-';
  const s = JSON.stringify(detail);
  return s.length > 50 ? s.slice(0, 47) + '...' : s;
};

const SkeletonRows = () => (
  <>
    {[1, 2, 3].map((i) => (
      <tr key={i}>
        {[1, 2, 3, 4, 5, 6].map((j) => (
          <td key={j} className="px-4 py-3">
            <div className="h-4 animate-pulse rounded bg-zinc-200" />
          </td>
        ))}
      </tr>
    ))}
  </>
);

const ActivityLogTable = ({
  logs,
  total,
  limit,
  offset,
  isLoading,
  isError,
  onPageChange,
  onRetry,
}: ActivityLogTableProps) => {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  if (isError) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-[15px] text-red-600">이력을 불러올 수 없습니다</p>
        <button
          onClick={onRetry}
          className="mt-3 rounded-xl border border-red-200 bg-white px-4 py-2 text-[13.5px] font-medium text-red-600 transition-all hover:bg-red-50"
        >
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="overflow-hidden rounded-2xl border border-zinc-200">
        <table className="w-full">
          <thead>
            <tr className="bg-zinc-50">
              <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                #
              </th>
              <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                Collection
              </th>
              <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                Action
              </th>
              <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                User
              </th>
              <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                Detail
              </th>
              <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                Time
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {isLoading ? (
              <SkeletonRows />
            ) : logs.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-12 text-center text-[15px] text-zinc-400"
                >
                  이력이 없습니다
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr
                  key={log.id}
                  className="transition-colors hover:bg-zinc-50/50"
                >
                  <td className="px-4 py-3 text-[13.5px] text-zinc-400">
                    {log.id}
                  </td>
                  <td className="px-4 py-3 text-[13.5px] font-medium text-zinc-700">
                    {log.collection_name}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${
                        ACTION_BADGE[log.action] ??
                        'bg-zinc-100 text-zinc-600'
                      }`}
                    >
                      {log.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[13.5px] text-zinc-600">
                    {log.user_id ?? '-'}
                  </td>
                  <td
                    className="max-w-[200px] truncate px-4 py-3 text-[12px] text-zinc-500"
                    title={
                      log.detail ? JSON.stringify(log.detail, null, 2) : ''
                    }
                  >
                    {truncateJson(log.detail)}
                  </td>
                  <td className="px-4 py-3 text-[12px] text-zinc-400">
                    {formatTime(log.created_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <button
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[13px] text-zinc-600 transition-all hover:bg-zinc-50 disabled:opacity-40"
          >
            이전
          </button>
          <span className="text-[13px] text-zinc-500">
            {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => onPageChange(offset + limit)}
            disabled={currentPage >= totalPages}
            className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[13px] text-zinc-600 transition-all hover:bg-zinc-50 disabled:opacity-40"
          >
            다음
          </button>
        </div>
      )}
    </div>
  );
};

export default ActivityLogTable;
