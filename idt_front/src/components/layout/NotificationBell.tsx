import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useJobList,
  useMarkAllSeen,
  useMarkSeen,
  useUnseenCount,
} from '@/hooks/useBackgroundJobs';
import { chatSessionPath, isJobFinished } from '@/types/backgroundJob';
import type { BackgroundJob } from '@/types/backgroundJob';

// background-jobs S8: 헤더 벨 — 미확인 완료/실패 배지 + 최근 작업 드롭다운 (D11)

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

const NotificationBell = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const { data: unseen } = useUnseenCount();
  const { data: jobs } = useJobList({ limit: 20 });
  const markSeen = useMarkSeen();
  const markAllSeen = useMarkAllSeen();

  const count = unseen?.count ?? 0;

  // 드롭다운은 최근 완료/실패 5건만 — 진행중 혼입 방지 (Design §5-3)
  const recentFinished = useMemo(
    () => (jobs ?? []).filter((j) => isJobFinished(j.status)).slice(0, 5),
    [jobs],
  );

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const goToJob = (job: BackgroundJob) => {
    if (job.seen_at === null && isJobFinished(job.status)) {
      markSeen.mutate({ jobId: job.id });
    }
    setOpen(false);
    navigate(
      job.session_id
        ? chatSessionPath(job.agent_id, job.session_id)
        : '/jobs',
    );
  };

  return (
    <div ref={rootRef} className="relative ml-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="백그라운드 작업 알림"
        className="relative flex h-8 w-8 items-center justify-center rounded-full text-zinc-500 transition-all hover:bg-zinc-100 hover:text-zinc-700"
      >
        <svg className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" strokeWidth={1.7} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
        </svg>
        {count > 0 && (
          <span
            data-testid="bell-badge"
            className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white"
          >
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-80 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-xl shadow-zinc-200/60">
          <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3">
            <p className="text-[13px] font-semibold text-zinc-800">백그라운드 작업</p>
            {count > 0 && (
              <button
                type="button"
                onClick={() => markAllSeen.mutate()}
                className="text-[12px] font-medium text-violet-600 hover:text-violet-800"
              >
                모두 확인
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto p-1.5">
            {recentFinished.length === 0 ? (
              <p className="px-3.5 py-6 text-center text-[12.5px] text-zinc-400">
                등록된 백그라운드 작업이 없습니다
              </p>
            ) : (
              recentFinished.map((job) => (
                <button
                  key={job.id}
                  type="button"
                  onClick={() => goToJob(job)}
                  className="flex w-full items-start gap-2.5 rounded-xl px-3.5 py-2.5 text-left transition-all hover:bg-zinc-50"
                >
                  <span
                    className={`mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-semibold ${statusBadgeClass(job.status)}`}
                  >
                    {STATUS_LABEL[job.status] ?? job.status}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] text-zinc-700">
                      {job.query}
                    </span>
                    {job.seen_at === null &&
                      (job.status === 'success' || job.status === 'failed') && (
                        <span className="text-[11px] font-medium text-violet-500">
                          새 결과
                        </span>
                      )}
                  </span>
                </button>
              ))
            )}
          </div>
          <div className="border-t border-zinc-100 p-1.5">
            <button
              type="button"
              onClick={() => { setOpen(false); navigate('/jobs'); }}
              className="w-full rounded-xl px-3.5 py-2 text-center text-[13px] font-medium text-violet-600 transition-all hover:bg-violet-50"
            >
              작업함 가기
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
