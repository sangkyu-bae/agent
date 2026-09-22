import { useState } from 'react';
import ApprovalCard from './ApprovalCard';
import RejectReasonDialog from './RejectReasonDialog';
import {
  extractApprovalError,
  useApprovals,
  useApproveApproval,
  useMarkApprovalSeen,
  useRejectApproval,
} from '@/hooks/useApprovals';
import {
  ACTIVE_APPROVAL_STATUSES,
  APPROVAL_PAGE_SIZE,
} from '@/types/approval';
import type { ApprovalItem, ApprovalStatus } from '@/types/approval';
import { formatLocalDateTime } from '@/utils/formatters';

type FilterKey = 'active' | 'pending' | 'scheduled' | 'done';

const FILTERS: { key: FilterKey; label: string; statuses?: ApprovalStatus[] }[] =
  [
    { key: 'active', label: '전체', statuses: ACTIVE_APPROVAL_STATUSES },
    { key: 'pending', label: '대기', statuses: ['pending'] },
    { key: 'scheduled', label: '예약됨', statuses: ['scheduled'] },
    {
      key: 'done',
      label: '완료',
      statuses: ['executed', 'rejected', 'expired', 'failed'],
    },
  ];

// approval-gate: 승인 대기 목록 (Design §5.1 / §5.4)
const ApprovalTable = () => {
  const [filter, setFilter] = useState<FilterKey>('active');
  const [rejectTarget, setRejectTarget] = useState<ApprovalItem | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const statuses = FILTERS.find((f) => f.key === filter)?.statuses;
  const { data, isLoading, isError } = useApprovals({
    statuses,
    size: APPROVAL_PAGE_SIZE,
  });

  const approve = useApproveApproval();
  const reject = useRejectApproval();
  const markSeen = useMarkApprovalSeen();

  const handleApprove = async (item: ApprovalItem) => {
    setBusyId(item.id);
    setNotice(null);
    try {
      const res = await approve.mutateAsync({ approvalId: item.id });
      // Check G12: 예약 시각은 사용자 로캘로 표시한다 (서버는 UTC 만 안다).
      setNotice(
        res.status === 'scheduled' && res.execute_after
          ? `${formatLocalDateTime(res.execute_after)}에 집행 예정입니다.`
          : res.message,
      );
    } catch (e) {
      // 409(이미 처리됨)도 오류가 아니라 정상 안내다 — onSettled 가 목록을
      // 무효화했으므로 화면은 곧 최신 상태가 된다.
      setNotice(extractApprovalError(e));
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (reason: string) => {
    if (!rejectTarget) return;
    setBusyId(rejectTarget.id);
    try {
      const res = await reject.mutateAsync({
        approvalId: rejectTarget.id,
        reason,
      });
      setNotice(res.message);
    } catch (e) {
      setNotice(extractApprovalError(e));
    } finally {
      setBusyId(null);
      setRejectTarget(null);
    }
  };

  const items = data?.data ?? [];

  return (
    <section aria-label="승인 대기">
      <div className="mb-3 flex items-center gap-2">
        {FILTERS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
            className={`rounded px-2.5 py-1 text-sm ${
              filter === key
                ? 'bg-zinc-900 text-white'
                : 'text-zinc-600 hover:bg-zinc-100'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {notice && (
        <p role="status" className="mb-3 rounded bg-zinc-50 p-2 text-sm text-zinc-700">
          {notice}
        </p>
      )}

      {isLoading && <p className="text-sm text-zinc-500">불러오는 중…</p>}
      {isError && (
        <p role="alert" className="text-sm text-red-500">
          승인 목록을 불러오지 못했습니다.
        </p>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <p className="py-8 text-center text-sm text-zinc-400">
          승인 대기 중인 작업이 없습니다.
        </p>
      )}

      <ul className="space-y-3">
        {items.map((item) => (
          <ApprovalCard
            key={item.id}
            item={item}
            busy={busyId === item.id}
            onApprove={handleApprove}
            onReject={setRejectTarget}
            onSeen={(i) => markSeen.mutate(i.id)}
          />
        ))}
      </ul>

      <RejectReasonDialog
        open={rejectTarget !== null}
        submitting={busyId === rejectTarget?.id}
        onCancel={() => setRejectTarget(null)}
        onSubmit={handleReject}
      />
    </section>
  );
};

export default ApprovalTable;
