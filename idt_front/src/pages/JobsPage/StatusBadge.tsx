import { JOB_STATUS_LABEL, isJobActive } from '@/types/backgroundJob';
import type { JobStatus } from '@/types/backgroundJob';

// jobs-page-revamp Design §5.4 — 상태 배지 4종 (대기 중/실행 중=스피너, 완료, 실패)

const badgeClass = (status: JobStatus): string => {
  if (status === 'success') return 'text-emerald-600';
  if (status === 'failed') return 'text-red-500';
  return 'text-violet-600';
};

const StatusIcon = ({ status }: { status: JobStatus }) => {
  if (isJobActive(status)) {
    return (
      <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
    );
  }
  if (status === 'failed') {
    return (
      <svg
        className="h-4 w-4"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.8}
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    );
  }
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.8}
      stroke="currentColor"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  );
};

const StatusBadge = ({ status }: { status: JobStatus }) => (
  <span
    className={`inline-flex items-center gap-1.5 text-[13px] font-medium ${badgeClass(status)}`}
  >
    <StatusIcon status={status} />
    {JOB_STATUS_LABEL[status] ?? status}
  </span>
);

export default StatusBadge;
