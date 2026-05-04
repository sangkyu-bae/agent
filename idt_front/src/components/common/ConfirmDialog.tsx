import type { ReactNode } from 'react';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  description: string | ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
  onClose: () => void;
  onConfirm: () => void;
  isPending?: boolean;
  error?: string | null;
}

const VARIANT_STYLES = {
  danger: 'border-red-200 text-red-500 hover:bg-red-50',
  warning: 'border-amber-200 text-amber-600 hover:bg-amber-50',
  info: 'border-violet-200 text-violet-600 hover:bg-violet-50',
} as const;

const ConfirmDialog = ({
  isOpen,
  title,
  description,
  confirmLabel = '확인',
  cancelLabel = '취소',
  variant = 'danger',
  onClose,
  onConfirm,
  isPending = false,
  error = null,
}: ConfirmDialogProps) => {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-[15px] font-semibold text-zinc-900">{title}</h2>
        <div className="mt-3 text-[14px] leading-relaxed text-zinc-600">
          {description}
        </div>

        {error && (
          <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
            {error}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className={`flex items-center justify-center rounded-xl border bg-white px-4 py-2.5 text-[13.5px] font-medium transition-all active:scale-95 disabled:opacity-50 ${VARIANT_STYLES[variant]}`}
          >
            {isPending ? (
              <svg
                className="h-4 w-4 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
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
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
