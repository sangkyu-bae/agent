// Design Ref: ui-redesign-chat §5.3 — 아이콘 전용 버튼. aria-label을 타입으로 강제하고 title을 동일하게 채운다.
import type { ButtonHTMLAttributes } from 'react';
import { cn } from '@/utils/cn';
import type { ControlSize, IconButtonTone } from '@/types/ui';

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> {
  'aria-label': string;
  size?: ControlSize;
  tone?: IconButtonTone;
  /** 토글형 버튼의 켜짐 상태 (aria-pressed 병행) */
  isActive?: boolean;
}

const SIZE_CLASS: Record<ControlSize, string> = {
  sm: 'h-8 w-8',
  md: 'h-9 w-9',
};

const TONE_CLASS: Record<IconButtonTone, string> = {
  neutral: 'text-fg-subtle hover:bg-surface-sunken hover:text-fg',
  danger: 'text-fg-subtle hover:bg-danger-bg hover:text-danger',
};

const IconButton = ({
  'aria-label': ariaLabel,
  size = 'md',
  tone = 'neutral',
  isActive = false,
  className,
  title,
  type = 'button',
  ...rest
}: IconButtonProps) => (
  <button
    type={type}
    aria-label={ariaLabel}
    title={title ?? ariaLabel}
    aria-pressed={isActive || undefined}
    className={cn(
      'inline-flex shrink-0 items-center justify-center rounded-md transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50',
      SIZE_CLASS[size],
      TONE_CLASS[tone],
      isActive && 'bg-surface-sunken text-fg',
      className,
    )}
    {...rest}
  />
);

export default IconButton;
