import { useState } from 'react';
import Modal from '@/components/common/Modal';
import {
  extractApprovalError,
  useApprovalDetail,
  useApproveApproval,
} from '@/hooks/useApprovals';
import {
  APPROVAL_NOT_EDITABLE_HINT,
  APPROVAL_STATUS_LABELS,
  APPROVAL_STATUS_TONES,
  isApprovalActionable,
} from '@/types/approval';
import type { ApprovalDecisionResponse, ApprovalDetail } from '@/types/approval';
import { buildEditForm, diffEditedArgs, hasNonBodyChange } from '@/utils/approvalEdit';
import { formatLocalDateTime } from '@/utils/formatters';

// approval-edit-before-approve Design §5 — 승인 상세 (보기 / 수정 후 승인)

interface ApprovalDetailDrawerProps {
  approvalId: string | null;
  onClose: () => void;
  /** 결정 성공 — 부모가 안내 문구를 띄우고 드로어를 닫는다 */
  onDone: (res: ApprovalDecisionResponse) => void;
  /** 거절은 기존 사유 다이얼로그를 쓰도록 부모에게 위임 */
  onReject: (detail: ApprovalDetail) => void;
}

const formatValue = (value: unknown): string =>
  typeof value === 'string' ? value : JSON.stringify(value);

const fieldClass = (changed: boolean) =>
  `w-full rounded-lg border px-2.5 py-1.5 text-sm text-zinc-900 outline-none focus:border-violet-400 ${
    changed ? 'border-amber-300 bg-amber-50' : 'border-zinc-300 bg-white'
  }`;

const ApprovalDetailDrawer = ({
  approvalId, onClose, onDone, onReject,
}: ApprovalDetailDrawerProps) => {
  const { data: detail, isLoading, isError } = useApprovalDetail(approvalId);
  const approve = useApproveApproval();
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const editing = form !== null;
  const changed = detail && form ? diffEditedArgs(detail.display_args, form) : {};
  const changedKeys = Object.keys(changed);

  const submit = async (editedArgs?: Record<string, string>) => {
    if (!detail) return;
    setBusy(true);
    setError(null);
    try {
      const res = await approve.mutateAsync(
        editedArgs ? { approvalId: detail.id, editedArgs } : { approvalId: detail.id },
      );
      onDone(res);
    } catch (e) {
      // Design §5.2: 422·409 는 드로어에 남아 이유를 보여준다
      setError(extractApprovalError(e));
    } finally {
      setBusy(false);
      setConfirmOpen(false);
    }
  };

  const isChanged = (key: string) =>
    !!detail && !!form && form[key] !== detail.display_args[key];

  const renderEditor = (key: string, multiline: boolean) => {
    const props = {
      'aria-label': key,
      'data-changed': String(isChanged(key)),
      value: form?.[key] ?? '',
      className: fieldClass(isChanged(key)),
    };
    const update = (value: string) =>
      setForm((prev) => ({ ...(prev ?? {}), [key]: value }));
    return multiline ? (
      <textarea {...props} rows={10} onChange={(e) => update(e.target.value)} />
    ) : (
      <input {...props} type="text" onChange={(e) => update(e.target.value)} />
    );
  };

  const renderBody = (d: ApprovalDetail) => {
    const bodyEditable = editing && !!d.body_key && d.editable_keys.includes(d.body_key);
    return (
      <section className="mt-4">
        <h3 className="mb-1.5 text-xs font-medium text-zinc-500">
          {d.body_key ? `본문 (${d.body_key})` : '초안'}
        </h3>
        {bodyEditable ? (
          renderEditor(d.body_key!, true)
        ) : (
          <div className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg bg-zinc-50 p-3 text-sm text-zinc-800">
            {d.draft || '(초안 없음)'}
          </div>
        )}
      </section>
    );
  };

  const renderArgs = (d: ApprovalDetail) => {
    const rows = Object.entries(d.display_args).filter(([key]) => key !== d.body_key);
    if (rows.length === 0) return null;
    return (
      <section className="mt-4">
        <h3 className="mb-1.5 text-xs font-medium text-zinc-500">호출 인자</h3>
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([key, value]) => (
              <tr key={key} className="border-t border-zinc-100">
                <th className="w-32 py-1.5 pr-3 text-left align-top font-normal text-zinc-500">
                  {key}
                </th>
                <td className="py-1.5 text-zinc-800">
                  {editing && d.editable_keys.includes(key) ? (
                    renderEditor(key, false)
                  ) : (
                    <span className="break-all">{formatValue(value)}</span>
                  )}
                  {typeof value !== 'string' && (
                    <span className="ml-2 text-xs text-zinc-400">수정 불가</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    );
  };

  const renderHistory = (d: ApprovalDetail) =>
    d.original_tool_args && (
      <section className="mt-4">
        <button
          type="button"
          aria-expanded={showOriginal}
          className="text-xs text-violet-600 hover:underline"
          onClick={() => setShowOriginal((v) => !v)}
        >
          {showOriginal ? '▾' : '▸'} 원본 보기
        </button>
        {showOriginal && (
          <div className="mt-2 rounded-lg bg-zinc-50 p-3 text-xs text-zinc-600">
            <p className="mb-2">
              수정: {d.edited_by ?? '-'}
              {d.edited_at && ` · ${formatLocalDateTime(d.edited_at)}`}
            </p>
            <pre className="whitespace-pre-wrap break-all">
              {JSON.stringify(d.original_tool_args, null, 2)}
            </pre>
          </div>
        )}
      </section>
    );

  const renderFooter = (d: ApprovalDetail) => {
    if (!isApprovalActionable(d.status)) {
      return (
        <button type="button" onClick={onClose} className="rounded border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600">
          닫기
        </button>
      );
    }
    if (editing) {
      return (
        <>
          <button type="button" onClick={() => setForm(null)} disabled={busy} className="rounded border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50">
            취소
          </button>
          <button type="button" onClick={() => setConfirmOpen(true)} disabled={busy || changedKeys.length === 0} className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-40">
            수정 후 승인
          </button>
        </>
      );
    }
    return (
      <>
        <button type="button" onClick={() => onReject(d)} disabled={busy} className="rounded border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-40">
          거절
        </button>
        <button
          type="button"
          onClick={() => setForm(buildEditForm(d.display_args, d.editable_keys))}
          disabled={busy || !d.editable}
          title={d.editable ? undefined : APPROVAL_NOT_EDITABLE_HINT}
          className="rounded border border-violet-200 px-3 py-1.5 text-sm text-violet-600 hover:bg-violet-50 disabled:opacity-40"
        >
          수정
        </button>
        <button type="button" onClick={() => void submit()} disabled={busy} className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-40">
          {busy ? '처리 중…' : '승인'}
        </button>
      </>
    );
  };

  const renderContent = (d: ApprovalDetail) => (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-zinc-900">{d.agent_name ?? d.agent_id}</span>
        <span className={`rounded border px-1.5 py-0.5 text-xs ${APPROVAL_STATUS_TONES[d.status]}`}>
          {APPROVAL_STATUS_LABELS[d.status]}
        </span>
        {d.edited && (
          <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-xs text-amber-600">
            수정됨
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-zinc-500">
        도구: {d.tool_id} · 만료: {formatLocalDateTime(d.expires_at)}
      </p>
      {isApprovalActionable(d.status) && !d.editable && (
        <p className="mt-3 rounded bg-zinc-50 p-2 text-xs text-zinc-500">
          {APPROVAL_NOT_EDITABLE_HINT}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 rounded bg-red-50 p-2 text-sm text-red-600">
          {error}
        </p>
      )}
      {renderBody(d)}
      {renderArgs(d)}
      {renderHistory(d)}
    </>
  );

  return (
    <>
      <Modal
        isOpen={approvalId !== null}
        onClose={onClose}
        title="승인 상세"
        size="2xl"
        scroll="body"
        closeOnEsc={!confirmOpen}
        disableClose={busy}
        footer={detail ? renderFooter(detail) : undefined}
      >
        {isLoading && <p className="text-sm text-zinc-500">불러오는 중…</p>}
        {isError && (
          <p role="alert" className="text-sm text-red-500">상세를 불러오지 못했습니다.</p>
        )}
        {detail && renderContent(detail)}
      </Modal>

      {/* Design §5.1: 확인 다이얼로그 — 변경 필드 목록 + 본문 외 변경 경고 */}
      <Modal
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="수정 후 승인 확인"
        size="sm"
        disableClose={busy}
        footer={
          <>
            <button type="button" onClick={() => setConfirmOpen(false)} disabled={busy} className="rounded border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600">
              돌아가기
            </button>
            <button type="button" onClick={() => void submit(changed)} disabled={busy} className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-40">
              {busy ? '처리 중…' : '수정 후 승인'}
            </button>
          </>
        }
      >
        <p className="text-sm text-zinc-700">
          다음 필드를 수정해 승인합니다: {changedKeys.join(', ')}
        </p>
        {hasNonBodyChange(changed, detail?.body_key ?? null) && (
          <p className="mt-2 text-sm text-red-500">
            수신자·대상 등 본문 외 값이 바뀌었습니다. 다시 확인해 주세요.
          </p>
        )}
      </Modal>
    </>
  );
};

export default ApprovalDetailDrawer;
