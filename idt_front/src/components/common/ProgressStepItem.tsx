// Design Ref: progress-card §5.2 — 상태별 원형 아이콘 + 세로 커넥터 + 라벨 + 배지 1행.
// 아이콘은 aria-hidden: 상태 의미는 StatusBadge 텍스트가 전달한다.
import type { ProgressStep, ProgressStepStatus } from '@/types/progress';
import StatusBadge from './StatusBadge';

interface ProgressStepItemProps {
  step: ProgressStep;
  /** true면 커넥터 라인 미표시 (FR-08) */
  isLast?: boolean;
}

const ICON_PATH: Record<ProgressStepStatus, string> = {
  completed: 'M5 13l4 4L19 7',
  in_progress: 'M5 12h14m-6-6 6 6-6 6',
  pending: 'M12 8v4l2.5 2.5M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18Z',
  error: 'M6 6l12 12M18 6 6 18',
};

const ICON_CIRCLE: Record<ProgressStepStatus, string> = {
  completed: 'text-white',
  in_progress: 'bg-indigo-600 text-white',
  pending: 'border border-zinc-200 bg-white text-zinc-400',
  error: 'bg-red-500 text-white',
};

const LABEL_CLASS: Record<ProgressStepStatus, string> = {
  completed: 'text-zinc-700',
  in_progress: 'font-semibold text-zinc-900',
  pending: 'text-zinc-500',
  error: 'text-red-600',
};

const ProgressStepItem = ({ step, isLast = false }: ProgressStepItemProps) => {
  const { status } = step;
  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center">
        <div
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${ICON_CIRCLE[status]}`}
          style={
            status === 'completed'
              ? { background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }
              : undefined
          }
        >
          <svg
            className="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d={ICON_PATH[status]} />
          </svg>
        </div>
        {!isLast && (
          <span
            data-testid="step-connector"
            className={`h-5 w-px ${status === 'completed' ? 'bg-violet-400' : 'bg-zinc-200'}`}
          />
        )}
      </div>

      <div className="flex h-8 min-w-0 flex-1 items-center gap-3">
        <span className={`min-w-0 flex-1 truncate text-[14px] ${LABEL_CLASS[status]}`}>
          {step.label}
        </span>
        <StatusBadge status={status} label={step.badgeLabel} />
      </div>
    </li>
  );
};

export default ProgressStepItem;
