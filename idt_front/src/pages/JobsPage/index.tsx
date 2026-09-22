import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import JobFilterBar from './JobFilterBar';
import JobHistoryTable from './JobHistoryTable';
import JobPagination from './JobPagination';
import ScheduleDefinitionTable from './ScheduleDefinitionTable';
import ApprovalTable from './ApprovalTable';
import {
  extractJobError,
  invalidateMySchedules,
  invalidateUnseenCount,
  useCleanupJobs,
  useDeleteJob,
  useJobHistory,
  useMarkSeen,
  useMySchedules,
} from '@/hooks/useBackgroundJobs';
import {
  useDeleteSchedule,
  useToggleScheduleEnabled,
} from '@/hooks/useAgentSchedules';
import { useApprovals } from '@/hooks/useApprovals';
import { ACTIVE_APPROVAL_STATUSES } from '@/types/approval';
import {
  DEFAULT_JOB_FILTERS,
  JOB_PAGE_SIZE,
  chatSessionPath,
  isJobFinished,
} from '@/types/backgroundJob';
import type {
  JobHistoryFilters,
  JobHistoryItem,
  MySchedule,
} from '@/types/backgroundJob';

// jobs-page-revamp S2: 작업함 — 통합 작업 기록 테이블 + 필터 + 정리 (Design §5)
// Design Ref: §2.0 Option C — 정렬·페이징·총건수는 서버가 계산하고 여기선 그린다.

type TabKey = 'history' | 'schedules' | 'approvals';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'history', label: '작업 기록' },
  { key: 'schedules', label: '스케줄 작업' },
  // approval-gate Design §5.1: 사람이 결정해야 할 것 — 배지로 건수 노출
  { key: 'approvals', label: '승인 대기' },
];

const JobsPage = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>('history');
  const [filters, setFilters] = useState<JobHistoryFilters>(
    DEFAULT_JOB_FILTERS,
  );
  const [offset, setOffset] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<JobHistoryItem | null>(null);
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [scheduleTarget, setScheduleTarget] = useState<MySchedule | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  // approval-gate Design §5.4: 탭 배지 건수. 목록과 같은 쿼리라
  // 탭을 열면 캐시가 재사용된다.
  const { data: approvalPage } = useApprovals({
    statuses: ACTIVE_APPROVAL_STATUSES,
  });
  const approvalCount = approvalPage?.pagination.total ?? 0;

  const params = useMemo(
    () => ({ ...filters, limit: JOB_PAGE_SIZE, offset }),
    [filters, offset],
  );
  const {
    data: history,
    isLoading,
    refetch,
  } = useJobHistory(params);
  const { data: schedules, isLoading: schedulesLoading } = useMySchedules();
  const markSeen = useMarkSeen();
  const deleteJob = useDeleteJob();
  const cleanupJobs = useCleanupJobs();
  const toggleSchedule = useToggleScheduleEnabled();
  const deleteSchedule = useDeleteSchedule();

  const items = history?.items ?? [];
  const total = history?.total ?? 0;

  // 필터를 바꾸면 현재 offset 이 범위를 벗어날 수 있어 첫 페이지로 되돌린다
  const changeFilters = (next: JobHistoryFilters) => {
    setFilters(next);
    setOffset(0);
  };

  const openItem = (item: JobHistoryItem) => {
    if (item.type === 'manual' && item.seen_at === null && isJobFinished(item.status)) {
      markSeen.mutate({ jobId: item.id });
    }
    if (item.session_id) {
      navigate(chatSessionPath(item.agent_id, item.session_id));
    }
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteJob.mutate(
      { jobId: deleteTarget.id },
      {
        onSuccess: () => {
          setDeleteTarget(null);
          setNotice('작업을 삭제했습니다');
        },
      },
    );
  };

  const confirmCleanup = () => {
    cleanupJobs.mutate(undefined, {
      onSuccess: (res) => {
        setCleanupOpen(false);
        setNotice(`완료된 작업 ${res.deleted}건을 정리했습니다`);
      },
    });
  };

  // Plan SC: FR-13 — 새로고침은 목록과 미확인 수를 함께 재조회한다.
  // refetch() 만으로는 벨 배지가 15초 폴링 주기까지 옛 값을 유지한다.
  const refreshAll = () => {
    refetch();
    invalidateUnseenCount();
  };

  const toggleScheduleEnabled = (schedule: MySchedule) => {
    setTogglingId(schedule.id);
    toggleSchedule.mutate(
      {
        agentId: schedule.agent_id,
        scheduleId: schedule.id,
        enabled: !schedule.enabled,
      },
      {
        onSettled: () => setTogglingId(null),
        onSuccess: invalidateMySchedules,
      },
    );
  };

  const confirmScheduleDelete = () => {
    if (!scheduleTarget) return;
    deleteSchedule.mutate(
      { agentId: scheduleTarget.agent_id, scheduleId: scheduleTarget.id },
      {
        onSuccess: () => {
          invalidateMySchedules();
          setScheduleTarget(null);
          setNotice('스케줄을 삭제했습니다');
        },
      },
    );
  };

  return (
    <div className="h-full overflow-y-auto bg-zinc-50">
      {/* 폭 제한 없이 네비바 옆 영역을 꽉 채운다 — 테이블 열이 넓어야 읽힌다 */}
      <div className="px-6 py-6">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[20px] font-bold text-violet-700">
              백그라운드 작업
            </h1>
            <p className="mt-1 text-[13px] text-zinc-500">
              백그라운드 작업을 모니터링하고 관리하세요
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setCleanupOpen(true)}
              className="rounded-xl bg-violet-600 px-3.5 py-2 text-[12.5px] font-medium text-white transition-all hover:bg-violet-700"
            >
              정리
            </button>
            <button
              type="button"
              onClick={refreshAll}
              className="rounded-xl border border-zinc-200 bg-white px-3.5 py-2 text-[12.5px] font-medium text-zinc-600 transition-all hover:bg-zinc-100"
            >
              새로고침
            </button>
          </div>
        </div>

        {/* 전체 폭에서 flex-1 로 늘리면 탭이 화면 끝까지 벌어진다 — 내용 폭 유지 */}
        <div className="mb-4 inline-flex gap-1 rounded-xl bg-zinc-100 p-1">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={tab === key}
              onClick={() => setTab(key)}
              className={`rounded-lg px-4 py-2 text-[13.5px] font-medium transition-all ${
                tab === key
                  ? 'bg-white text-violet-700 shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-700'
              }`}
            >
              {label}
              {key === 'approvals' && approvalCount > 0 && (
                <span
                  className="ml-1.5 rounded-full bg-violet-600 px-1.5 py-0.5 text-[11px] font-semibold text-white"
                  aria-label={`승인 대기 ${approvalCount}건`}
                >
                  {approvalCount}
                </span>
              )}
            </button>
          ))}
        </div>

        {notice && (
          <p
            role="status"
            className="mb-3 rounded-xl bg-violet-50 px-4 py-2.5 text-[13px] text-violet-700"
          >
            {notice}
          </p>
        )}

        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
          {tab === 'approvals' ? (
            <div className="p-4">
              <ApprovalTable />
            </div>
          ) : tab === 'history' ? (
            <>
              <JobFilterBar filters={filters} onChange={changeFilters} />
              <JobHistoryTable
                items={items}
                isLoading={isLoading}
                onOpen={openItem}
                onDelete={setDeleteTarget}
              />
              <JobPagination
                total={total}
                pageSize={JOB_PAGE_SIZE}
                offset={offset}
                onOffsetChange={setOffset}
              />
            </>
          ) : (
            <ScheduleDefinitionTable
              schedules={schedules ?? []}
              isLoading={schedulesLoading}
              pendingId={togglingId}
              onToggle={toggleScheduleEnabled}
              onDelete={setScheduleTarget}
            />
          )}
        </div>
      </div>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="작업 삭제"
        description={
          <>
            <span className="font-semibold">{deleteTarget?.title}</span> 작업을
            삭제하시겠습니까?
          </>
        }
        confirmLabel="삭제"
        variant="danger"
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        isPending={deleteJob.isPending}
        error={deleteJob.isError ? extractJobError(deleteJob.error) : null}
      />

      <ConfirmDialog
        isOpen={cleanupOpen}
        title="완료된 작업 정리"
        description="완료·실패한 작업을 모두 정리합니다. 진행 중인 작업은 남습니다."
        confirmLabel="정리하기"
        variant="danger"
        onClose={() => setCleanupOpen(false)}
        onConfirm={confirmCleanup}
        isPending={cleanupJobs.isPending}
        error={cleanupJobs.isError ? extractJobError(cleanupJobs.error) : null}
      />

      <ConfirmDialog
        isOpen={!!scheduleTarget}
        title="스케줄 삭제"
        description={
          <>
            <span className="font-semibold">{scheduleTarget?.name}</span>{' '}
            스케줄을 삭제하시겠습니까?
            <br />
            실행 이력도 함께 삭제되며 되돌릴 수 없습니다.
          </>
        }
        confirmLabel="스케줄 삭제"
        variant="danger"
        onClose={() => setScheduleTarget(null)}
        onConfirm={confirmScheduleDelete}
        isPending={deleteSchedule.isPending}
        error={
          deleteSchedule.isError ? extractJobError(deleteSchedule.error) : null
        }
      />
    </div>
  );
};

export default JobsPage;
