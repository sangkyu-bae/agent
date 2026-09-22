import { useState } from 'react';
import {
  APPROVAL_STATUS_LABELS,
  APPROVAL_STATUS_TONES,
  isApprovalActionable,
} from '@/types/approval';
import type { ApprovalItem } from '@/types/approval';
import { formatLocalDateTime } from '@/utils/formatters';

interface ApprovalCardProps {
  item: ApprovalItem;
  busy?: boolean;
  onApprove: (item: ApprovalItem) => void;
  onReject: (item: ApprovalItem) => void;
  onSeen: (item: ApprovalItem) => void;
}

const formatLocal = formatLocalDateTime;

const remainingText = (expiresAt: string): string => {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (Number.isNaN(ms)) return '';
  if (ms <= 0) return '만료됨';
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 24) return `${Math.floor(hours / 24)}일 남음`;
  if (hours >= 1) return `${hours}시간 남음`;
  return `${Math.max(1, Math.floor(ms / 60_000))}분 남음`;
};

// approval-gate: 승인 대기 1건 (Design §5.1 / §5.4)
const ApprovalCard = ({
  item, busy = false, onApprove, onReject, onSeen,
}: ApprovalCardProps) => {
  const [expanded, setExpanded] = useState(false);
  const actionable = isApprovalActionable(item.status);

  return (
    <li className="rounded-lg border border-zinc-200 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate font-medium text-zinc-900">
              {item.agent_name ?? item.agent_id}
            </span>
            <span
              className={`rounded border px-1.5 py-0.5 text-xs ${APPROVAL_STATUS_TONES[item.status]}`}
            >
              {APPROVAL_STATUS_LABELS[item.status]}
            </span>
            {item.seen_at === null && (
              <span
                className="h-1.5 w-1.5 rounded-full bg-violet-500"
                aria-label="미확인"
                title="미확인"
              />
            )}
          </div>
          <p className="mt-0.5 text-xs text-zinc-500">도구: {item.tool_id}</p>
        </div>
      </div>

      <button
        type="button"
        className={`mt-3 w-full rounded bg-zinc-50 p-3 text-left text-sm text-zinc-700 ${
          expanded ? '' : 'line-clamp-3'
        }`}
        aria-expanded={expanded}
        aria-label="초안 전문 보기"
        onClick={() => {
          setExpanded((v) => !v);
          if (item.seen_at === null) onSeen(item);
        }}
      >
        {item.draft_preview || '(초안 없음)'}
      </button>

      <dl className="mt-3 space-y-1 text-xs text-zinc-500">
        {item.execute_after && (
          <div className="flex gap-2">
            <dt>집행 예정</dt>
            <dd className="text-zinc-700">{formatLocal(item.execute_after)}</dd>
          </div>
        )}
        <div className="flex gap-2">
          <dt>만료</dt>
          <dd className="text-zinc-700">
            {formatLocal(item.expires_at)}
            <span className="ml-1 text-zinc-400">
              ({remainingText(item.expires_at)})
            </span>
          </dd>
        </div>
      </dl>

      {actionable && (
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="rounded border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-40"
            onClick={() => onReject(item)}
            disabled={busy}
          >
            거절
          </button>
          <button
            type="button"
            className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            onClick={() => onApprove(item)}
            disabled={busy}
          >
            {busy ? '처리 중…' : '승인'}
          </button>
        </div>
      )}
    </li>
  );
};

export default ApprovalCard;
