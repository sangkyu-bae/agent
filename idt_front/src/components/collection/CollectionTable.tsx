import { useNavigate } from 'react-router-dom';
import type { CollectionInfo, CollectionScope } from '@/types/collection';
import {
  PROTECTED_COLLECTIONS,
  COLLECTION_STATUS_MAP,
  SCOPE_LABELS,
} from '@/types/collection';

interface CollectionTableProps {
  collections: CollectionInfo[];
  isLoading: boolean;
  isError: boolean;
  currentUserId: number | null;
  currentUserRole: string | null;
  onRefresh: () => void;
  onCreate: () => void;
  onRename: (name: string) => void;
  onDelete: (name: string) => void;
  onUpdateScope: (name: string) => void;
}

const isProtected = (name: string) =>
  (PROTECTED_COLLECTIONS as readonly string[]).includes(name);

const ScopeBadge = ({ scope }: { scope?: CollectionScope }) => {
  if (!scope) return <span className="text-[12px] text-zinc-400">&mdash;</span>;
  const info = SCOPE_LABELS[scope];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${info.bg} ${info.color}`}>
      {info.label}
    </span>
  );
};

const StatusBadge = ({ status }: { status: string }) => {
  const info =
    COLLECTION_STATUS_MAP[status as keyof typeof COLLECTION_STATUS_MAP];
  if (!info) return <span className="text-[12px] text-zinc-400">{status}</span>;

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${info.color}`} />
      <span className="text-[12px] text-zinc-600">{info.label}</span>
    </span>
  );
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

const CollectionTable = ({
  collections,
  isLoading,
  isError,
  currentUserId,
  currentUserRole,
  onRefresh,
  onCreate,
  onRename,
  onDelete,
  onUpdateScope,
}: CollectionTableProps) => {
  const navigate = useNavigate();
  const canManage = (col: CollectionInfo): boolean => {
    if (!currentUserId) return false;
    if (currentUserRole === 'admin') return true;
    return col.owner_id === currentUserId;
  };
  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <button
          onClick={onCreate}
          className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          <svg
            className="mr-1.5 h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 4.5v15m7.5-7.5h-15"
            />
          </svg>
          새 컬렉션
        </button>
        <button
          onClick={onRefresh}
          className="flex items-center rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
        >
          <svg
            className="mr-1.5 h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182"
            />
          </svg>
          새로고침
        </button>
      </div>

      {isError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
          <p className="text-[15px] text-red-600">
            컬렉션을 불러올 수 없습니다
          </p>
          <button
            onClick={onRefresh}
            className="mt-3 rounded-xl border border-red-200 bg-white px-4 py-2 text-[13.5px] font-medium text-red-600 transition-all hover:bg-red-50"
          >
            다시 시도
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-zinc-200">
          <table className="w-full">
            <thead>
              <tr className="bg-zinc-50">
                <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  Name
                </th>
                <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  Scope
                </th>
                <th className="px-4 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  Vectors
                </th>
                <th className="px-4 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  Points
                </th>
                <th className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  Status
                </th>
                <th className="px-4 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {isLoading ? (
                <SkeletonRows />
              ) : collections.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-[15px] text-zinc-400"
                  >
                    등록된 컬렉션이 없습니다
                  </td>
                </tr>
              ) : (
                collections.map((col) => (
                  <tr
                    key={col.name}
                    className="transition-colors hover:bg-zinc-50/50"
                  >
                    <td className="px-4 py-3 text-[13.5px] font-medium">
                      <button
                        onClick={() => navigate(`/collections/${col.name}/documents`)}
                        className="text-violet-600 transition-colors hover:text-violet-800 hover:underline"
                      >
                        {col.name}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <ScopeBadge scope={col.scope} />
                    </td>
                    <td className="px-4 py-3 text-right text-[13.5px] text-zinc-600">
                      {col.vectors_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right text-[13.5px] text-zinc-600">
                      {col.points_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={col.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      {isProtected(col.name) ? (
                        <span className="rounded-md bg-violet-50 px-2 py-0.5 text-[11.5px] font-semibold text-violet-500">
                          보호됨
                        </span>
                      ) : canManage(col) ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => onRename(col.name)}
                            className="rounded-xl border border-zinc-200 bg-white px-3 py-1.5 text-[12px] text-zinc-500 transition-all hover:border-zinc-300 hover:bg-zinc-100 hover:text-zinc-700"
                          >
                            이름변경
                          </button>
                          <button
                            onClick={() => onUpdateScope(col.name)}
                            className="rounded-xl border border-zinc-200 bg-white px-3 py-1.5 text-[12px] text-zinc-500 transition-all hover:border-violet-300 hover:bg-violet-50 hover:text-violet-600"
                          >
                            권한변경
                          </button>
                          <button
                            onClick={() => onDelete(col.name)}
                            className="rounded-xl border border-zinc-200 bg-white px-3 py-1.5 text-[12px] text-zinc-500 transition-all hover:border-red-200 hover:bg-red-50 hover:text-red-500"
                          >
                            삭제
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default CollectionTable;
