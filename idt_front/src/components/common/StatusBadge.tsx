// Design Ref: progress-card §5.2 — 상태를 색상만으로 전달하지 않도록 배지 텍스트를 병행한다.
// Design Ref: ui-redesign-chat §5.3 — ui/Badge 호환 래퍼. ProgressStepStatus → BadgeTone 매핑.
import Badge from '@/components/ui/Badge';
import type { BadgeTone } from '@/types/ui';
import type { ProgressStepStatus } from '@/types/progress';

interface StatusBadgeProps {
  status: ProgressStepStatus;
  /** 미지정·빈 문자열이면 상태별 기본 라벨 사용 */
  label?: string;
}

const BADGE_MAP: Record<ProgressStepStatus, { label: string; tone: BadgeTone }> = {
  completed: { label: '완료', tone: 'brand' },
  in_progress: { label: '진행중', tone: 'info' },
  pending: { label: '대기중', tone: 'neutral' },
  error: { label: '실패', tone: 'danger' },
};

const StatusBadge = ({ status, label }: StatusBadgeProps) => {
  const { label: defaultLabel, tone } = BADGE_MAP[status];
  return <Badge tone={tone}>{label || defaultLabel}</Badge>;
};

export default StatusBadge;
