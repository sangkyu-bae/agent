// Design Ref: progress-card §5.2 — 상태를 색상만으로 전달하지 않도록 배지 텍스트를 병행한다.
import type { ProgressStepStatus } from '@/types/progress';

interface StatusBadgeProps {
  status: ProgressStepStatus;
  /** 미지정·빈 문자열이면 상태별 기본 라벨 사용 */
  label?: string;
}

const BADGE_STYLE: Record<ProgressStepStatus, { label: string; className: string }> = {
  completed: { label: '완료', className: 'bg-violet-100 text-violet-600' },
  in_progress: { label: '진행중', className: 'border border-indigo-200 bg-white text-indigo-600' },
  pending: { label: '대기중', className: 'border border-zinc-200 bg-white text-zinc-500' },
  error: { label: '실패', className: 'border border-red-200 bg-red-50 text-red-600' },
};

const StatusBadge = ({ status, label }: StatusBadgeProps) => {
  const style = BADGE_STYLE[status];
  return (
    <span
      className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[12px] font-medium ${style.className}`}
    >
      {label || style.label}
    </span>
  );
};

export default StatusBadge;
