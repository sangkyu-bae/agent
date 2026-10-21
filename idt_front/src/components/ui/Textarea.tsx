// Design Ref: ui-redesign-chat §5.3 — Input과 같은 슬롯 + autoResize. unstyled는 ChatInput처럼 바깥 컨테이너가 테두리를 그릴 때 쓴다.
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type ChangeEvent,
  type TextareaHTMLAttributes,
} from 'react';
import { cn } from '@/utils/cn';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
  /** 입력 내용에 맞춰 높이를 늘린다 (maxRows 상한) */
  autoResize?: boolean;
  maxRows?: number;
  /** 테두리·배경·패딩 없이 텍스트 스타일만 적용 */
  unstyled?: boolean;
  wrapperClassName?: string;
}

const FALLBACK_LINE_HEIGHT = 24;

const Textarea = ({
  label,
  hint,
  error,
  autoResize = false,
  maxRows = 8,
  unstyled = false,
  id,
  className,
  wrapperClassName,
  onChange,
  value,
  rows = 1,
  ...rest
}: TextareaProps) => {
  const autoId = useId();
  const textareaId = id ?? autoId;
  const hintId = hint ? `${textareaId}-hint` : undefined;
  const errorId = error ? `${textareaId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  const ref = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = ref.current;
    if (!el || !autoResize) return;
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || FALLBACK_LINE_HEIGHT;
    const max = lineHeight * maxRows;
    el.style.height = 'auto';
    const next = Math.min(el.scrollHeight, max);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden';
  }, [autoResize, maxRows]);

  useEffect(() => {
    resize();
  }, [resize, value]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    onChange?.(e);
    resize();
  };

  return (
    <div className={cn('flex flex-col gap-1.5', wrapperClassName)}>
      {label && (
        <label htmlFor={textareaId} className="text-sm font-medium text-fg-secondary">
          {label}
        </label>
      )}
      <textarea
        ref={ref}
        id={textareaId}
        rows={rows}
        value={value}
        onChange={handleChange}
        aria-describedby={describedBy}
        aria-invalid={error ? true : undefined}
        className={cn(
          'block w-full resize-none text-fg outline-none placeholder:text-fg-subtle disabled:cursor-not-allowed disabled:opacity-60',
          unstyled
            ? 'bg-transparent text-md'
            : 'rounded-md border bg-surface px-3 py-2 text-base transition-colors duration-150 focus:border-brand-400 disabled:bg-surface-sunken',
          !unstyled && (error ? 'border-danger' : 'border-border-strong'),
          className,
        )}
        {...rest}
      />
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

export default Textarea;
