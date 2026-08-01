// mutation-pending-guard: TanStack Query isPending과 직결되는 공통 대기 버튼.
// isPending을 필수로 받아 "가드 누락" 실수를 타입 레벨에서 차단한다.
import type { ButtonHTMLAttributes } from 'react';

interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** mutation.isPending 직결 — true면 disable + 스피너 */
  isPending: boolean;
  /** 대기 중 대체 문구 (미지정 시 children 유지) */
  pendingText?: string;
}

const LoadingButton = ({
  isPending,
  pendingText,
  disabled,
  children,
  onClick,
  type = 'button',
  ...rest
}: LoadingButtonProps) => (
  <button
    type={type}
    disabled={isPending || disabled}
    onClick={isPending ? undefined : onClick}
    {...rest}
  >
    {isPending && (
      <svg
        aria-hidden="true"
        className="mr-1.5 inline h-3.5 w-3.5 animate-spin"
        viewBox="0 0 24 24"
        fill="none"
      >
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
          d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
        />
      </svg>
    )}
    {isPending ? (pendingText ?? children) : children}
  </button>
);

export default LoadingButton;
