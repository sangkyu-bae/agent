/**
 * ProgressCard — 정적 다단계 진행 상황 카드.
 *
 * `steps` 배열만 넘기면 렌더링되는 표시 전용 컴포넌트 (내부 상태 없음).
 * WebSocket 실시간 실행 로그는 `components/agent/AgentRunProgress`를 사용할 것.
 */
// Design Ref: progress-card §2.0 Option C — 카드 프레임 + 헤더 + steps 배열 → <ol> 조합 진입점.
// 상수·타입은 @/types/progress (react-refresh 규칙상 컴포넌트 파일에서 런타임 상수 export 금지).
import type { ReactNode } from 'react';

import type { ProgressStep } from '@/types/progress';

import ProgressStepItem from './ProgressStepItem';

export type { ProgressStep, ProgressStepStatus } from '@/types/progress';

interface ProgressCardProps {
  steps: ProgressStep[];
  title?: string;
  icon?: ReactNode;
  className?: string;
}

const DefaultHeaderIcon = () => (
  <svg
    className="h-5 w-5 text-violet-600"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
    <rect x="9" y="3" width="6" height="4" rx="1" />
    <path d="M9 12h6M9 16h4" />
  </svg>
);

const ProgressCard = ({
  steps,
  title = '진행 상황',
  icon,
  className = '',
}: ProgressCardProps) => {
  return (
    <div
      className={`rounded-2xl border border-zinc-200 bg-white shadow-sm ${className}`.trim()}
    >
      <div className="flex items-center gap-2.5 border-b border-zinc-100 px-5 py-4">
        {icon ?? <DefaultHeaderIcon />}
        <h3 className="text-[15px] font-semibold text-zinc-900">{title}</h3>
      </div>

      <div className="px-5 py-4">
        {steps.length === 0 ? (
          <p className="text-[12px] text-zinc-400">표시할 단계가 없습니다</p>
        ) : (
          <ol>
            {steps.map((step, index) => (
              <ProgressStepItem
                key={step.id ?? index}
                step={step}
                isLast={index === steps.length - 1}
              />
            ))}
          </ol>
        )}
      </div>
    </div>
  );
};

export default ProgressCard;
