// Design Ref: firewall-admin-console §5.4 승인 탭 (Plan FR-22) — 에이전트가 요청한 block_ip·unblock_ip
// 승인 대기 건을 보여 주고 기존 승인 API 로 처리한다. 승인 상태 전이 계약은 건드리지 않는다.
// 상세 확인과 수정 후 승인은 작업함(기존 화면)에서 한다.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import Button from '@/components/ui/Button';
import {
  extractApprovalError,
  isApprovalConflict,
  useApproveApproval,
  useRejectApproval,
} from '@/hooks/useApprovals';
import { firewallToolName, useFirewallApprovals } from '@/hooks/useFirewall';
import RejectReasonDialog from '@/pages/JobsPage/RejectReasonDialog';
import { ApiError } from '@/services/api/ApiError';
import type { ApprovalItem } from '@/types/approval';
import { FIREWALL_AUDIT_EVENT_LABELS } from '@/types/firewall';

const TOOL_LABELS: Record<string, string> = {
  block_ip: FIREWALL_AUDIT_EVENT_LABELS.block,
  unblock_ip: FIREWALL_AUDIT_EVENT_LABELS.unblock,
};

const formatTime = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR');
};

const CONFLICT_NOTICE = '이미 처리된 요청입니다. 목록을 새로 불러왔습니다.';
const NO_RESPONSE_NOTICE =
  '응답을 받지 못했습니다. 요청은 처리됐을 수 있습니다. 잠시 뒤 이 목록과 감사 탭에서 결과를 확인하세요.';

type NoticeTone = 'success' | 'warning' | 'danger';
const NOTICE_CLASS: Record<NoticeTone, string> = {
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
};

const FirewallApprovalsTab = () => {
  const approvals = useFirewallApprovals();
  const approve = useApproveApproval();
  const reject = useRejectApproval();

  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<ApprovalItem | null>(null);
  const [notice, setNotice] = useState<{ tone: NoticeTone; text: string } | null>(null);

  const fail = (e: unknown) => {
    if (isApprovalConflict(e)) return setNotice({ tone: 'danger', text: CONFLICT_NOTICE });
    // 응답을 받지 못한 경우(제한 시간 초과·연결 끊김)는 실패로 단정하지 않는다.
    // 승인 API 는 에이전트 재개까지 기다려 30초를 넘길 수 있고, 그동안 요청은 처리된다
    // (module-5 실측: 화면은 오류였지만 승인·실행은 끝나 있었다).
    if (e instanceof ApiError && e.status === 0) {
      return setNotice({ tone: 'warning', text: NO_RESPONSE_NOTICE });
    }
    return setNotice({ tone: 'danger', text: extractApprovalError(e) });
  };

  // 승인·거절 뒤에는 결과와 무관하게 목록을 직접 다시 불러온다.
  const reload = () => void approvals.refetch();

  const handleApprove = async (item: ApprovalItem) => {
    setBusyId(item.id);
    setNotice(null);
    try {
      const res = await approve.mutateAsync({ approvalId: item.id });
      setNotice({ tone: 'success', text: res.message || '승인했습니다.' });
    } catch (e) {
      fail(e);
    } finally {
      setBusyId(null);
      reload();
    }
  };

  const handleReject = async (reason: string) => {
    if (!rejectTarget) return;
    const target = rejectTarget;
    setBusyId(target.id);
    setNotice(null);
    try {
      const res = await reject.mutateAsync({ approvalId: target.id, reason });
      setNotice({ tone: 'success', text: res.message || '거절했습니다.' });
      setRejectTarget(null);
    } catch (e) {
      fail(e);
      setRejectTarget(null);
    } finally {
      setBusyId(null);
      reload();
    }
  };

  const { items } = approvals;

  return (
    <section aria-label="승인 대기">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-fg">차단 요청 승인 대기 ({items.length})</h2>
        <Link to="/jobs" className="text-sm font-medium text-brand-700 hover:underline">
          작업함에서 보기
        </Link>
      </div>
      <p className="mb-3 text-xs text-fg-subtle">
        내가 소유한 에이전트의 요청만 표시됩니다. 내용 전체 확인과 수정 후 승인은 작업함에서 합니다.
      </p>

      {notice && (
        <p
          role="status"
          className={`mb-3 text-sm ${NOTICE_CLASS[notice.tone]}`}
        >
          {notice.text}
        </p>
      )}
      {approvals.truncated && (
        <p className="mb-3 text-sm text-warning">
          승인 대기 건이 많아 일부만 확인했습니다. 나머지는 작업함에서 확인하세요.
        </p>
      )}

      {approvals.isLoading ? (
        <p className="px-4 py-6 text-center text-sm text-fg-muted">불러오는 중…</p>
      ) : approvals.isError ? (
        <p role="alert" className="rounded-xl border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger">
          {extractApprovalError(approvals.error)}
        </p>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface px-5 py-8 text-center">
          <p className="text-sm font-medium text-fg">승인 대기 중인 차단 요청이 없습니다.</p>
          <p className="mt-2 text-sm text-fg-muted">
            에이전트의 차단 요청이 여기에 나타나려면 MCP 서버(mcp-firewall-server)를 등록하고,
            block_ip 도구를 승인 필요로 지정한 뒤 방화벽 에이전트에 도구를 연결해야 합니다.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => {
            const tool = firewallToolName(item.tool_id);
            const busy = busyId === item.id;
            return (
              <li
                key={item.id}
                className="rounded-xl border border-border bg-surface p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-fg">
                      {TOOL_LABELS[tool] ?? tool} 요청
                      <span className="ml-2 font-normal text-fg-muted">
                        {item.agent_name ?? item.agent_id}
                      </span>
                    </p>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm text-fg-secondary">
                      {item.draft_preview}
                    </p>
                    <p className="mt-2 text-xs text-fg-subtle">
                      요청 {formatTime(item.created_at)} · 만료 {formatTime(item.expires_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      size="sm"
                      isPending={busy && approve.isPending}
                      pendingText="승인 중…"
                      disabled={busyId !== null}
                      aria-label={`${item.agent_name ?? item.agent_id} ${TOOL_LABELS[tool] ?? tool} 요청 승인`}
                      onClick={() => void handleApprove(item)}
                    >
                      승인
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={busyId !== null}
                      aria-label={`${item.agent_name ?? item.agent_id} ${TOOL_LABELS[tool] ?? tool} 요청 거절`}
                      onClick={() => setRejectTarget(item)}
                    >
                      거절
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <RejectReasonDialog
        open={rejectTarget !== null}
        submitting={busyId === rejectTarget?.id}
        onCancel={() => setRejectTarget(null)}
        onSubmit={(reason) => void handleReject(reason)}
      />
    </section>
  );
};

export default FirewallApprovalsTab;
