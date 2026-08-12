import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useJobList,
  useMarkAllSeen,
  useMarkSeen,
  useMyScheduleRuns,
} from '@/hooks/useBackgroundJobs';
import { chatSessionPath } from '@/types/backgroundJob';
import type { BackgroundJob, MyScheduleRun } from '@/types/backgroundJob';

// background-jobs S7: 작업함 — 요청 작업(job) + 스케줄 실행 이력 2탭 (D9)

type TabKey = 'jobs' | 'schedules';

const STATUS_LABEL: Record<string, string> = {
  queued: '대기 중',
  running: '실행 중',
  success: '완료',
  failed: '실패',
};

const statusBadgeClass = (status: string): string => {
  if (status === 'success') return 'bg-emerald-50 text-emerald-600';
  if (status === 'failed') return 'bg-red-50 text-red-500';
  return 'bg-violet-50 text-violet-600';
};

const formatDateTime = (iso: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`);
  return d.toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatDuration = (
  started: string | null,
  finished: string | null,
): string => {
  if (!started || !finished) return '—';
  const ms = new Date(finished).getTime() - new Date(started).getTime();
  if (ms < 0) return '—';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}초`;
  return `${Math.floor(sec / 60)}분 ${sec % 60}초`;
};

const StatusBadge = ({ status }: { status: string }) => (
  <span
    className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${statusBadgeClass(status)}`}
  >
    {(status === 'queued' || status === 'running') && (
      <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    )}
    {STATUS_LABEL[status] ?? status}
  </span>
);

const JobsPage = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>('jobs');

  const { data: jobs, isLoading: jobsLoading } = useJobList();
  const { data: scheduleRuns, isLoading: runsLoading } = useMyScheduleRuns();
  const markSeen = useMarkSeen();
  const markAllSeen = useMarkAllSeen();

  const openJobResult = (job: BackgroundJob) => {
    if (job.seen_at === null && (job.status === 'success' || job.status === 'failed')) {
      markSeen.mutate({ jobId: job.id });
    }
    navigate(
      job.session_id
        ? chatSessionPath(job.agent_id, job.session_id)
        : '/chatpage',
    );
  };

  const renderJobRow = (job: BackgroundJob) => (
    <div
      key={job.id}
      className="flex items-start justify-between gap-4 border-b border-zinc-100 px-5 py-4 last:border-b-0"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <StatusBadge status={job.status} />
          {job.agent_name && (
            <span className="truncate text-[12px] font-medium text-zinc-500">
              {job.agent_name}
            </span>
          )}
          {job.seen_at === null &&
            (job.status === 'success' || job.status === 'failed') && (
              <span className="text-[11px] font-semibold text-violet-500">
                새 결과
              </span>
            )}
        </div>
        <p className="mt-1.5 truncate text-[14px] text-zinc-800">{job.query}</p>
        <p className="mt-1 text-[12px] text-zinc-400">
          요청 {formatDateTime(job.queued_at)} · 소요{' '}
          {formatDuration(job.started_at, job.finished_at)}
        </p>
        {job.status === 'failed' && job.error_message && (
          <p className="mt-1.5 rounded-lg bg-red-50 px-3 py-1.5 text-[12.5px] text-red-500">
            {job.error_message}
          </p>
        )}
      </div>
      {job.status === 'success' && (
        <button
          type="button"
          onClick={() => openJobResult(job)}
          className="shrink-0 rounded-xl border border-violet-200 bg-violet-50 px-3.5 py-2 text-[12.5px] font-medium text-violet-700 transition-all hover:bg-violet-100"
        >
          결과 보기
        </button>
      )}
    </div>
  );

  const renderScheduleRow = (run: MyScheduleRun) => (
    <div
      key={run.id}
      className="flex items-start justify-between gap-4 border-b border-zinc-100 px-5 py-4 last:border-b-0"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <StatusBadge status={run.status} />
          <span className="truncate text-[13.5px] font-medium text-zinc-800">
            {run.schedule_name}
          </span>
          {run.agent_name && (
            <span className="truncate text-[12px] font-medium text-zinc-500">
              {run.agent_name}
            </span>
          )}
        </div>
        <p className="mt-1 text-[12px] text-zinc-400">
          예정 {formatDateTime(run.scheduled_for)} · 실행{' '}
          {formatDateTime(run.started_at)} · 소요{' '}
          {formatDuration(run.started_at, run.finished_at)}
        </p>
        {run.status === 'failed' && run.error_message && (
          <p className="mt-1.5 rounded-lg bg-red-50 px-3 py-1.5 text-[12.5px] text-red-500">
            {run.error_message}
          </p>
        )}
      </div>
      {run.status === 'success' && run.session_id && (
        <button
          type="button"
          onClick={() => navigate(chatSessionPath(run.agent_id, run.session_id as string))}
          className="shrink-0 rounded-xl border border-violet-200 bg-violet-50 px-3.5 py-2 text-[12.5px] font-medium text-violet-700 transition-all hover:bg-violet-100"
        >
          결과 보기
        </button>
      )}
    </div>
  );

  const emptyState = (message: string) => (
    <p className="px-5 py-14 text-center text-[13.5px] text-zinc-400">
      {message}
    </p>
  );

  return (
    <div className="h-full overflow-y-auto bg-zinc-50">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h1 className="text-[20px] font-bold text-zinc-900">작업함</h1>
            <p className="mt-1 text-[13px] text-zinc-500">
              백그라운드로 맡긴 작업과 스케줄 실행 결과를 확인합니다
            </p>
          </div>
          <button
            type="button"
            onClick={() => markAllSeen.mutate()}
            className="rounded-xl border border-zinc-200 bg-white px-3.5 py-2 text-[12.5px] font-medium text-zinc-600 transition-all hover:bg-zinc-100"
          >
            모두 확인
          </button>
        </div>

        {/* 탭 (D9) */}
        <div className="mb-4 flex gap-1 rounded-xl bg-zinc-100 p-1">
          {(
            [
              { key: 'jobs', label: '요청 작업' },
              { key: 'schedules', label: '스케줄 실행' },
            ] as { key: TabKey; label: string }[]
          ).map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`flex-1 rounded-lg px-4 py-2 text-[13.5px] font-medium transition-all ${
                tab === key
                  ? 'bg-white text-violet-700 shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
          {tab === 'jobs' &&
            (jobsLoading
              ? emptyState('불러오는 중…')
              : (jobs ?? []).length === 0
                ? emptyState('등록된 백그라운드 작업이 없습니다')
                : (jobs ?? []).map(renderJobRow))}
          {tab === 'schedules' &&
            (runsLoading
              ? emptyState('불러오는 중…')
              : (scheduleRuns ?? []).length === 0
                ? emptyState('스케줄 실행 이력이 없습니다')
                : (scheduleRuns ?? []).map(renderScheduleRow))}
        </div>
      </div>
    </div>
  );
};

export default JobsPage;
