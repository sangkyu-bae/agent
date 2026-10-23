// Design Ref: ui-redesign-chat §5.3 — 상태 배지. 색만으로 의미를 전달하지 않도록 텍스트(children)가 필수다.
import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/utils/cn';
import type { BadgeTone } from '@/types/ui';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  /** 앞쪽 상태 점 */
  dot?: boolean;
  /** 점 깜빡임 (온라인 등). reduced-motion에서는 전역 규칙으로 정지 */
  pulse?: boolean;
  children: ReactNode;
}

const TONE_CLASS: Record<BadgeTone, string> = {
  neutral: 'border-border bg-surface-sunken text-fg-muted',
  success: 'border-success-border bg-success-bg text-success',
  warning: 'border-warning-border bg-warning-bg text-warning',
  danger: 'border-danger-border bg-danger-bg text-danger',
  info: 'border-info-border bg-info-bg text-info',
  brand: 'border-brand-200 bg-brand-50 text-brand-700',
};

const Badge = ({ tone = 'neutral', dot = false, pulse = false, className, children, ...rest }: BadgeProps) => (
  <span
    className={cn(
      'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium',
      TONE_CLASS[tone],
      className,
    )}
    {...rest}
  >
    {dot && (
      <span
        aria-hidden="true"
        data-testid="badge-dot"
        className={cn('h-1.5 w-1.5 shrink-0 rounded-full bg-current', pulse && 'animate-pulse')}
      />
    )}
    {children}
  </span>
);

export default Badge;
