import { useState } from 'react';

interface RejectReasonDialogProps {
  open: boolean;
  submitting?: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}

// approval-gate: 거절 사유 입력 (Design §5.4)
// 사유가 필수인 이유 — 재개 시 에이전트에 주입되므로 빈 값은 의미가 없다.
const RejectReasonDialog = ({
  open,
  submitting = false,
  onCancel,
  onSubmit,
}: RejectReasonDialogProps) => {
  // 닫힌 동안은 렌더하지 않고, 열릴 때 부모가 key 로 리마운트해 사유가 초기화된다
  // (effect 안에서 setState 하지 않는다 — react-hooks/set-state-in-effect).
  if (!open) return null;
  return <RejectReasonDialogBody submitting={submitting} onCancel={onCancel} onSubmit={onSubmit} />;
};

interface BodyProps {
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}

const RejectReasonDialogBody = ({ submitting, onCancel, onSubmit }: BodyProps) => {
  const [reason, setReason] = useState('');

  const trimmed = reason.trim();
  const disabled = submitting || trimmed.length === 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-label="거절 사유 입력"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h3 className="text-base font-semibold text-zinc-900">거절 사유</h3>
        <p className="mt-1 text-sm text-zinc-500">
          입력한 사유는 에이전트에 전달되어 후속 판단에 사용됩니다.
        </p>
        <textarea
          className="mt-3 h-28 w-full resize-none rounded border border-zinc-300 p-2 text-sm outline-none focus:border-violet-400"
          value={reason}
          maxLength={1000}
          placeholder="예: 금리 인상폭이 승인 한도를 초과합니다"
          aria-label="거절 사유"
          onChange={(e) => setReason(e.target.value)}
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="rounded border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50"
            onClick={onCancel}
            disabled={submitting}
          >
            취소
          </button>
          <button
            type="button"
            className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            onClick={() => onSubmit(trimmed)}
            disabled={disabled}
          >
            {submitting ? '처리 중…' : '거절'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default RejectReasonDialog;
