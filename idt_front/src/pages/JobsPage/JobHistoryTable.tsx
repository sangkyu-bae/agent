import StatusBadge from './StatusBadge';
import { agentDisplayName, formatJobDateTime } from '@/types/backgroundJob';
import type { JobHistoryItem } from '@/types/backgroundJob';

// jobs-page-revamp Design §5.1 — 시간/제목/상태/에이전트 4열 + 액션 열

interface JobHistoryTableProps {
  items: JobHistoryItem[];
  isLoading: boolean;
  onOpen: (item: JobHistoryItem) => void;
  onDelete: (item: JobHistoryItem) => void;
}

const TrashIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={1.7}
    stroke="currentColor"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
    />
  </svg>
);

const JobHistoryTable = ({
  items,
  isLoading,
  onOpen,
  onDelete,
}: JobHistoryTableProps) => {
  if (isLoading) {
    return (
      <p className="px-5 py-14 text-center text-[13.5px] text-zinc-400">
        불러오는 중…
      </p>
    );
  }
  if (items.length === 0) {
    return (
      <p className="px-5 py-14 text-center text-[13.5px] text-zinc-400">
        조건에 맞는 작업이 없습니다
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] table-fixed">
        <thead>
          <tr className="border-b border-zinc-200 text-left text-[13px] font-medium text-zinc-400">
            <th className="w-44 px-5 py-3 font-medium">시간</th>
            <th className="px-5 py-3 font-medium">제목</th>
            <th className="w-32 px-5 py-3 font-medium">상태</th>
            <th className="w-44 px-5 py-3 font-medium">에이전트</th>
            <th className="w-16 px-5 py-3" />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={`${item.type}-${item.id}`}
              className="border-b border-zinc-100 last:border-b-0 hover:bg-zinc-50"
            >
              <td className="px-5 py-4 text-[13.5px] text-zinc-500">
                {formatJobDateTime(item.occurred_at)}
              </td>
              <td className="px-5 py-4">
                <button
                  type="button"
                  onClick={() => onOpen(item)}
                  className="block max-w-full truncate text-left text-[14px] text-zinc-800 hover:text-violet-700"
                >
                  {item.title}
                </button>
                {item.status === 'failed' && item.error_message && (
                  <p className="mt-1 truncate text-[12.5px] text-red-500">
                    {item.error_message}
                  </p>
                )}
              </td>
              <td className="px-5 py-4">
                <StatusBadge status={item.status} />
              </td>
              <td className="px-5 py-4 truncate text-[13.5px] text-zinc-500">
                {agentDisplayName(item.agent_name, item.agent_id)}
              </td>
              <td className="px-5 py-4 text-right">
                {/* FR-11: 스케줄 실행 이력은 개별 삭제 대상이 아니라 아이콘을 숨긴다 */}
                {item.deletable && (
                  <button
                    type="button"
                    aria-label={`${item.title} 삭제`}
                    onClick={() => onDelete(item)}
                    className="rounded-lg p-1.5 text-zinc-400 transition-all hover:bg-red-50 hover:text-red-500"
                  >
                    <TrashIcon />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default JobHistoryTable;
