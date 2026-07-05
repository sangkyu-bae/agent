import { useState } from 'react';
import type {
  ScheduleCreateRequest,
  ScheduleResponse,
  ScheduleRunStatus,
  StagedSchedule,
} from '@/types/agentSchedule';
import {
  MAX_SCHEDULES_PER_AGENT,
  SCHEDULE_TYPE,
} from '@/types/agentSchedule';
import {
  useAgentSchedules,
  useCreateSchedule,
  useUpdateSchedule,
  useDeleteSchedule,
  useToggleScheduleEnabled,
  useScheduleRuns,
  extractScheduleError,
} from '@/hooks/useAgentSchedules';
import { describeSpec } from '@/utils/scheduleCron';
import { formatDate } from '@/utils/formatters';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import ScheduleForm from './ScheduleForm';

interface SchedulePanelProps {
  mode: 'create' | 'edit';
  agentId: string | null;
  /** 생성 모드 전용 — 로컬 staged 목록 */
  stagedSchedules: StagedSchedule[];
  onStagedAdd: (item: StagedSchedule) => void;
  onStagedRemove: (localId: string) => void;
}

const RUN_STATUS_BADGE: Record<ScheduleRunStatus, { label: string; className: string }> = {
  running: { label: '실행중', className: 'bg-amber-100 text-amber-700 animate-pulse' },
  success: { label: '성공', className: 'bg-emerald-100 text-emerald-700' },
  failed: { label: '실패', className: 'bg-red-100 text-red-600' },
};

const EmptyState = () => (
  <div className="flex flex-col items-center justify-center py-20 text-center">
    <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-zinc-100">
      <svg className="h-6 w-6 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
      </svg>
    </div>
    <p className="text-[14px] font-medium text-zinc-700">등록된 스케줄이 없습니다</p>
    <p className="mt-1 text-[12.5px] text-zinc-400">첫 번째 스케줄을 추가해보세요</p>
  </div>
);

/**
 * 스케줄 탭 콘텐츠 — agent-schedule Design §4.2.
 * edit: 서버 직결 CRUD (추가 POST / 수정 PUT / 토글 PATCH 즉시, 삭제는 ConfirmDialog→DELETE).
 * create: staged 로컬 목록 (에이전트 생성 성공 후 페이지가 순차 POST).
 */
const SchedulePanel = ({
  mode,
  agentId,
  stagedSchedules,
  onStagedAdd,
  onStagedRemove,
}: SchedulePanelProps) => {
  const isEdit = mode === 'edit';

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editing, setEditing] = useState<ScheduleResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ScheduleResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [expandedRunsId, setExpandedRunsId] = useState<string | null>(null);

  const { data: schedules, isLoading, isError, refetch } = useAgentSchedules(
    isEdit ? agentId : null,
  );
  const createMutation = useCreateSchedule();
  const updateMutation = useUpdateSchedule();
  const deleteMutation = useDeleteSchedule();
  const toggleMutation = useToggleScheduleEnabled();

  const count = isEdit ? (schedules?.length ?? 0) : stagedSchedules.length;
  const isFull = count >= MAX_SCHEDULES_PER_AGENT;

  const closeForm = () => {
    setIsFormOpen(false);
    setEditing(null);
    setSubmitError(null);
  };

  const handleSubmit = (payload: ScheduleCreateRequest) => {
    if (!isEdit) {
      onStagedAdd({ localId: crypto.randomUUID(), ...payload });
      closeForm();
      return;
    }
    if (!agentId) return;
    const options = {
      onSuccess: closeForm,
      onError: (e: Error) => setSubmitError(extractScheduleError(e)),
    };
    if (editing) {
      updateMutation.mutate(
        { agentId, scheduleId: editing.id, data: payload },
        options,
      );
    } else {
      createMutation.mutate({ agentId, data: payload }, options);
    }
  };

  const handleDeleteConfirm = () => {
    if (!agentId || !deleteTarget) return;
    deleteMutation.mutate(
      { agentId, scheduleId: deleteTarget.id },
      { onSuccess: () => setDeleteTarget(null) },
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* 고정 헤더 */}
      <div className="flex shrink-0 items-center justify-between border-b border-zinc-200 px-4 py-3">
        <div className="flex items-center gap-2 text-[13px] text-zinc-500">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
          에이전트 자동 실행 스케줄을 관리합니다
        </div>
        <button
          type="button"
          disabled={isFull}
          title={isFull ? `에이전트당 최대 ${MAX_SCHEDULES_PER_AGENT}개까지 등록할 수 있습니다` : undefined}
          onClick={() => {
            setEditing(null);
            setSubmitError(null);
            setIsFormOpen(true);
          }}
          className="flex items-center gap-1.5 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] font-medium text-zinc-700 transition-all hover:border-zinc-300 hover:bg-zinc-50 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          스케줄 추가
        </button>
      </div>

      {/* 스크롤 바디 */}
      <div style={{ flex: 1, overflowY: 'auto' }} className="px-4 py-4">
        {(isFormOpen || editing) && (
          <div className="mb-4">
            <ScheduleForm
              initial={editing}
              isSubmitting={createMutation.isPending || updateMutation.isPending}
              submitError={submitError}
              onSubmit={handleSubmit}
              onCancel={closeForm}
            />
          </div>
        )}

        {!isEdit ? (
          /* 생성 모드 — staged 목록 */
          stagedSchedules.length === 0 ? (
            !isFormOpen && <EmptyState />
          ) : (
            <div className="flex flex-col gap-2.5">
              <p className="text-[12px] text-zinc-400">에이전트 생성 시 함께 등록됩니다</p>
              {stagedSchedules.map((s) => (
                <div
                  key={s.localId}
                  className="flex items-center justify-between rounded-2xl border border-zinc-200 bg-white p-4"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-[13.5px] font-medium text-zinc-900">{describeSpec(s.spec)}</p>
                      <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10.5px] font-semibold text-violet-600">
                        등록 대기
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-1 text-[12px] text-zinc-400">{s.instruction}</p>
                  </div>
                  <button
                    type="button"
                    aria-label={`${describeSpec(s.spec)} 삭제`}
                    onClick={() => onStagedRemove(s.localId)}
                    className="ml-3 shrink-0 rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )
        ) : isLoading ? (
          <div className="flex flex-col gap-2.5">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="h-[88px] animate-pulse rounded-2xl border border-zinc-200 bg-zinc-100" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center py-16 text-center">
            <p className="text-[13.5px] text-zinc-500">스케줄 목록을 불러올 수 없습니다</p>
            <button
              type="button"
              onClick={() => refetch()}
              className="mt-3 rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
            >
              다시 시도
            </button>
          </div>
        ) : !schedules || schedules.length === 0 ? (
          !isFormOpen && <EmptyState />
        ) : (
          <div className="flex flex-col gap-2.5">
            {schedules.map((schedule) => (
              <ScheduleCard
                key={schedule.id}
                agentId={agentId!}
                schedule={schedule}
                isRunsExpanded={expandedRunsId === schedule.id}
                onToggleRuns={() =>
                  setExpandedRunsId((prev) => (prev === schedule.id ? null : schedule.id))
                }
                onEdit={() => {
                  setSubmitError(null);
                  setIsFormOpen(false);
                  setEditing(schedule);
                }}
                onDelete={() => setDeleteTarget(schedule)}
                onToggleEnabled={(enabled) =>
                  toggleMutation.mutate({ agentId: agentId!, scheduleId: schedule.id, enabled })
                }
              />
            ))}
          </div>
        )}
      </div>

      {/* 삭제 확인 */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="스케줄 삭제"
        description={
          <>
            <span className="font-semibold">{deleteTarget ? describeSpec(deleteTarget.spec) : ''}</span>{' '}
            스케줄을 삭제하시겠습니까?
            <br />
            실행 이력도 함께 삭제되며 되돌릴 수 없습니다.
          </>
        }
        confirmLabel="삭제"
        variant="danger"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        isPending={deleteMutation.isPending}
        error={deleteMutation.isError ? extractScheduleError(deleteMutation.error) : null}
      />
    </div>
  );
};

// ── ScheduleCard ────────────────────────────────

interface ScheduleCardProps {
  agentId: string;
  schedule: ScheduleResponse;
  isRunsExpanded: boolean;
  onToggleRuns: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onToggleEnabled: (enabled: boolean) => void;
}

const ScheduleCard = ({
  agentId,
  schedule,
  isRunsExpanded,
  onToggleRuns,
  onEdit,
  onDelete,
  onToggleEnabled,
}: ScheduleCardProps) => {
  const summary = describeSpec(schedule.spec);
  // daily/weekly는 백엔드 직접 생성분 — 이 화면의 폼(cron/once)으로 편집 불가
  const isFormEditable =
    schedule.spec.schedule_type === SCHEDULE_TYPE.CRON ||
    schedule.spec.schedule_type === SCHEDULE_TYPE.ONCE;

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className={`text-[13.5px] font-medium ${schedule.enabled ? 'text-zinc-900' : 'text-zinc-400'}`}>
              {summary}
            </p>
            {!schedule.enabled && (
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10.5px] font-semibold text-zinc-500">
                일시중지
              </span>
            )}
          </div>
          <p className="mt-1 text-[12px] text-zinc-400">
            다음 실행: {schedule.next_run_at ? formatDate(schedule.next_run_at) : '-'}
            {schedule.last_run_at && ` · 최근: ${formatDate(schedule.last_run_at)}`}
          </p>
          <p className="mt-1 line-clamp-1 text-[12px] text-zinc-400">{schedule.instruction}</p>
        </div>

        <div className="ml-3 flex shrink-0 items-center gap-1">
          {/* 활성 토글 */}
          <button
            type="button"
            role="switch"
            aria-checked={schedule.enabled}
            aria-label={`${summary} 활성화`}
            onClick={() => onToggleEnabled(!schedule.enabled)}
            className={`relative h-5 w-9 rounded-full transition-colors ${
              schedule.enabled ? 'bg-violet-600' : 'bg-zinc-300'
            }`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${
                schedule.enabled ? 'left-[18px]' : 'left-0.5'
              }`}
            />
          </button>
          <button
            type="button"
            aria-label={`${summary} 수정`}
            disabled={!isFormEditable}
            title={isFormEditable ? undefined : '이 유형은 화면에서 편집할 수 없습니다'}
            onClick={onEdit}
            className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
            </svg>
          </button>
          <button
            type="button"
            aria-label={`${summary} 삭제`}
            onClick={onDelete}
            className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
            </svg>
          </button>
        </div>
      </div>

      {/* 실행 이력 토글 */}
      <button
        type="button"
        onClick={onToggleRuns}
        className="mt-2 flex items-center gap-1 text-[12px] font-medium text-zinc-400 transition-colors hover:text-zinc-600"
      >
        이력 보기
        <svg
          className={`h-3 w-3 transition-transform ${isRunsExpanded ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {isRunsExpanded && (
        <ScheduleRunsList agentId={agentId} scheduleId={schedule.id} />
      )}
    </div>
  );
};

// ── ScheduleRunsList ────────────────────────────

const ScheduleRunsList = ({ agentId, scheduleId }: { agentId: string; scheduleId: string }) => {
  const { data: runs, isLoading } = useScheduleRuns(agentId, scheduleId, { enabled: true });

  if (isLoading) {
    return <p className="mt-2 text-[12px] text-zinc-400">이력을 불러오는 중…</p>;
  }
  if (!runs || runs.length === 0) {
    return <p className="mt-2 text-[12px] text-zinc-400">실행 이력이 없습니다</p>;
  }
  return (
    <div className="mt-2 flex flex-col gap-1.5 border-t border-zinc-100 pt-2.5">
      {runs.map((run) => {
        const badge = RUN_STATUS_BADGE[run.status];
        return (
          <div key={run.id} className="text-[12px] text-zinc-500">
            <div className="flex items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${badge.className}`}>
                {badge.label}
              </span>
              <span>
                {formatDate(run.scheduled_for)}
                {run.finished_at && ` → ${formatDate(run.finished_at)}`}
              </span>
            </div>
            {run.error_message && (
              <p className="mt-0.5 pl-1 text-[12px] text-red-500">{run.error_message}</p>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default SchedulePanel;
