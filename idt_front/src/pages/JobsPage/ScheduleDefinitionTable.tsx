import { agentDisplayName, formatJobDateTime } from '@/types/backgroundJob';
import { describeSpec } from '@/utils/scheduleCron';
import type { MySchedule } from '@/types/backgroundJob';

// jobs-page-revamp Design §5.4 — 스케줄 작업 탭: 등록된 스케줄 정의 목록 (FR-15)
// 토글·삭제는 기존 /agents/{agent_id}/schedules 계약을 그대로 쓴다.

interface ScheduleDefinitionTableProps {
  schedules: MySchedule[];
  isLoading: boolean;
  pendingId: string | null;
  onToggle: (schedule: MySchedule) => void;
  onDelete: (schedule: MySchedule) => void;
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

const ScheduleDefinitionTable = ({
  schedules,
  isLoading,
  pendingId,
  onToggle,
  onDelete,
}: ScheduleDefinitionTableProps) => {
  if (isLoading) {
    return (
      <p className="px-5 py-14 text-center text-[13.5px] text-zinc-400">
        불러오는 중…
      </p>
    );
  }
  if (schedules.length === 0) {
    return (
      <p className="px-5 py-14 text-center text-[13.5px] text-zinc-400">
        등록된 스케줄이 없습니다
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] table-fixed">
        <thead>
          <tr className="border-b border-zinc-200 text-left text-[13px] font-medium text-zinc-400">
            <th className="px-5 py-3 font-medium">스케줄명</th>
            <th className="w-40 px-5 py-3 font-medium">주기</th>
            <th className="w-44 px-5 py-3 font-medium">다음 실행</th>
            <th className="w-40 px-5 py-3 font-medium">에이전트</th>
            <th className="w-24 px-5 py-3 font-medium">활성</th>
            <th className="w-16 px-5 py-3" />
          </tr>
        </thead>
        <tbody>
          {schedules.map((schedule) => (
            <tr
              key={schedule.id}
              className="border-b border-zinc-100 last:border-b-0 hover:bg-zinc-50"
            >
              <td className="px-5 py-4 truncate text-[14px] text-zinc-800">
                {schedule.name}
              </td>
              <td className="px-5 py-4 truncate text-[13.5px] text-zinc-500">
                {describeSpec(schedule.spec)}
              </td>
              <td className="px-5 py-4 text-[13.5px] text-zinc-500">
                {/* 비활성 스케줄은 다음 실행이 없다 */}
                {schedule.enabled
                  ? formatJobDateTime(schedule.next_run_at)
                  : '—'}
              </td>
              <td className="px-5 py-4 truncate text-[13.5px] text-zinc-500">
                {agentDisplayName(schedule.agent_name, schedule.agent_id)}
              </td>
              <td className="px-5 py-4">
                <button
                  type="button"
                  role="switch"
                  aria-checked={schedule.enabled}
                  aria-label={`${schedule.name} 활성화`}
                  disabled={pendingId === schedule.id}
                  onClick={() => onToggle(schedule)}
                  className={`relative h-5 w-9 rounded-full transition-all disabled:opacity-50 ${
                    schedule.enabled ? 'bg-violet-500' : 'bg-zinc-300'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${
                      schedule.enabled ? 'left-4.5' : 'left-0.5'
                    }`}
                  />
                </button>
              </td>
              <td className="px-5 py-4 text-right">
                <button
                  type="button"
                  aria-label={`${schedule.name} 삭제`}
                  onClick={() => onDelete(schedule)}
                  className="rounded-lg p-1.5 text-zinc-400 transition-all hover:bg-red-50 hover:text-red-500"
                >
                  <TrashIcon />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ScheduleDefinitionTable;
