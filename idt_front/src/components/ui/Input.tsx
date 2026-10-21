// Design Ref: ui-redesign-chat §5.3 — 라벨·힌트·에러 슬롯을 가진 입력. aria-describedby를 자동 연결한다.
import { useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/utils/cn';
import type { ControlSize } from '@/types/ui';

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string;
  hint?: string;
  error?: string;
  leadingIcon?: ReactNode;
  size?: ControlSize;
  /** 바깥 래퍼 className (input 자체는 className) */
  wrapperClassName?: string;
}

const SIZE_CLASS: Record<ControlSize, string> = {
  sm: 'h-8 text-sm',
  md: 'h-10 text-base',
};

const Input = ({
  label,
  hint,
  error,
  leadingIcon,
  size = 'md',
  id,
  className,
  wrapperClassName,
  ...rest
}: InputProps) => {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={cn('flex flex-col gap-1.5', wrapperClassName)}>
      {label && (
        <label htmlFor={inputId} className="text-sm font-medium text-fg-secondary">
          {label}
        </label>
      )}
      <div className="relative">
        {leadingIcon && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-fg-subtle"
          >
            {leadingIcon}
          </span>
        )}
        <input
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={cn(
            'w-full rounded-md border bg-surface px-3 text-fg outline-none transition-colors duration-150 placeholder:text-fg-subtle focus:border-brand-400 disabled:cursor-not-allowed disabled:bg-surface-sunken disabled:opacity-60',
            SIZE_CLASS[size],
            leadingIcon ? 'pl-9' : null,
            error ? 'border-danger' : 'border-border-strong',
            className,
          )}
          {...rest}
        />
      </div>
      {hint && !error && (
        <p id={hintId} className="text-xs text-fg-subtle">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
};

export default Input;
