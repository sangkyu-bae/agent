// Design Ref: ui-redesign-chat §5.3 — 액션 버튼. variant 4 × size 2, isPending 가드, 아이콘 슬롯.
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/utils/cn';
import type { ButtonVariant, ControlSize } from '@/types/ui';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ControlSize;
  /** mutation.isPending 직결 — true면 disable + 스피너 + 클릭 가드 */
  isPending?: boolean;
  /** 대기 중 대체 문구 (미지정 시 children 유지) */
  pendingText?: string;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
  /** variant/size 클래스를 붙이지 않는다. 기존 className을 그대로 쓰는 호환 래퍼(LoadingButton) 전용 */
  unstyled?: boolean;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: 'bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:scale-95',
  secondary:
    'border border-border bg-surface-muted text-fg-secondary hover:border-border-strong hover:bg-surface-sunken',
  ghost: 'text-fg-muted hover:bg-surface-sunken hover:text-fg',
  danger: 'text-danger hover:bg-danger-bg',
};

const SIZE_CLASS: Record<ControlSize, string> = {
  sm: 'h-8 gap-1.5 px-3 text-sm',
  md: 'h-10 gap-2 px-4 text-base',
};

const Spinner = () => (
  <svg aria-hidden="true" className="mr-1.5 inline h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
  </svg>
);

const Button = ({
  variant = 'primary',
  size = 'md',
  isPending = false,
  pendingText,
  leadingIcon,
  trailingIcon,
  unstyled = false,
  disabled,
  children,
  onClick,
  className,
  type = 'button',
  ...rest
}: ButtonProps) => (
  <button
    type={type}
    disabled={isPending || disabled}
    // Plan SC: FR-03 — pending 중 프로그래매틱 click도 차단
    onClick={isPending ? undefined : onClick}
    className={cn(
      !unstyled &&
        'inline-flex items-center justify-center whitespace-nowrap rounded-md font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100',
      !unstyled && VARIANT_CLASS[variant],
      !unstyled && SIZE_CLASS[size],
      className,
    )}
    {...rest}
  >
    {isPending ? <Spinner /> : leadingIcon}
    {isPending ? (pendingText ?? children) : children}
    {!isPending && trailingIcon}
  </button>
);

export default Button;
