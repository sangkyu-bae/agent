// Design Ref: firewall-admin-console §5.4 현황 탭 (Plan FR-18·19·23) — 입력 → 확인창 → 결과 안내.
// 확인창이 모드·IP·유지 시간·사유를 다시 보여 주고, 결과가 dry_run 이면 적용되지 않았음을 알린다.
// 형식 검증은 서버가 다시 한다. 여기서는 잘못된 요청을 보내지 않기 위한 사전 확인이다.
import { useState } from 'react';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import LoadingButton from '@/components/common/LoadingButton';
import { firewallErrorMessage, useBlockIp } from '@/hooks/useFirewall';
import {
  FIREWALL_IPV4_RE,
  FIREWALL_REASON_MAX_CHARS,
  type FirewallBlockDraft,
  type FirewallStatusResponse,
} from '@/types/firewall';

interface BlockIpFormProps {
  status: FirewallStatusResponse;
  /** 탐지 탭에서 넘어온 초안 (module-4) */
  draft?: FirewallBlockDraft | null;
}

const FALLBACK_MAX_TTL = 3600;

const formatDateTime = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR');
};

const BlockIpForm = ({ status, draft }: BlockIpFormProps) => {
  const { fwctl } = status;
  const maxTtl = fwctl.max_ttl_seconds ?? FALLBACK_MAX_TTL;
  const available = fwctl.configured && fwctl.reachable;
  const isLive = fwctl.dry_run === false;

  // 초안은 초기값으로만 쓴다. 새 초안이 오면 부모가 key(nonce)를 바꿔 폼을 새로 만든다
  // (effect 로 상태를 덮어쓰지 않는다).
  const [ip, setIp] = useState(draft?.ip ?? '');
  const [ttl, setTtl] = useState(String(status.default_ttl_seconds));
  const [reason, setReason] = useState(draft?.reason ?? '');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'warning'; text: string } | null>(null);
  const block = useBlockIp();

  const ipTrimmed = ip.trim();
  const reasonTrimmed = reason.trim();
  const ttlNumber = Number(ttl);
  const ipError = ipTrimmed && !FIREWALL_IPV4_RE.test(ipTrimmed) ? 'IPv4 주소 한 개를 입력하세요.' : null;
  const ttlValid = /^\d+$/.test(ttl.trim()) && ttlNumber >= 1 && ttlNumber <= maxTtl;
  const ttlError = ttl.trim() && !ttlValid ? `유지 시간은 1~${maxTtl}초입니다.` : null;
  const reasonTooLong = reasonTrimmed.length > FIREWALL_REASON_MAX_CHARS;
  const canSubmit =
    available && !!ipTrimmed && !ipError && ttlValid && !!reasonTrimmed && !reasonTooLong;

  const openConfirm = () => {
    setConfirmError(null);
    // 이전 요청의 결과 안내가 새 요청 뒤에 남아 있으면 오해를 부른다.
    setNotice(null);
    setConfirmOpen(true);
  };

  const handleConfirm = async () => {
    setConfirmError(null);
    try {
      const result = await block.mutateAsync({
        ip: ipTrimmed,
        ttl_seconds: ttlNumber,
        reason: reasonTrimmed,
      });
      setConfirmOpen(false);
      setNotice(
        result.dry_run
          ? {
              tone: 'warning',
              text: `실제로 차단되지 않았습니다(DRY-RUN). ${result.ip} 요청은 감사 기록에만 남았습니다.`,
            }
          : {
              tone: 'success',
              text: `${result.ip}을(를) 차단했습니다. 만료: ${formatDateTime(result.expires_at)}`,
            },
      );
      setIp('');
      setReason('');
    } catch (err) {
      setConfirmError(firewallErrorMessage(err, '차단 요청에 실패했습니다.'));
    }
  };

  const inputClass =
    'rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg disabled:opacity-50';

  return (
    <section aria-label="IP 차단" className="mb-6 rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-fg">IP 차단</h2>
      <form
        className="flex flex-wrap items-start gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) openConfirm();
        }}
      >
        <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
          IP
          <input
            // 탐지 탭에서 넘어온 초안이면 폼으로 포커스를 옮긴다
            autoFocus={!!draft}
            aria-label="IP"
            aria-invalid={!!ipError}
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            placeholder="예: 172.28.10.66"
            disabled={!available}
            className={`w-44 ${inputClass}`}
          />
          {ipError && <span className="text-xs font-normal text-danger">{ipError}</span>}
        </label>

        <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
          유지 시간(초)
          <input
            aria-label="유지 시간(초)"
            aria-invalid={!!ttlError}
            inputMode="numeric"
            value={ttl}
            onChange={(e) => setTtl(e.target.value)}
            disabled={!available}
            className={`w-28 ${inputClass}`}
          />
          <span className={`text-xs font-normal ${ttlError ? 'text-danger' : 'text-fg-muted'}`}>
            {ttlError ?? `1~${maxTtl}초`}
          </span>
        </label>

        <label className="flex min-w-64 flex-1 flex-col gap-1 text-xs font-medium text-fg-subtle">
          사유
          <input
            aria-label="사유"
            aria-invalid={reasonTooLong}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="예: R02 포트 스캔, 5분 41건"
            disabled={!available}
            className={inputClass}
          />
          <span
            className={`text-xs font-normal ${reasonTooLong ? 'text-danger' : 'text-fg-muted'}`}
          >
            {reasonTrimmed.length}/{FIREWALL_REASON_MAX_CHARS}자 · 감사 기록에 그대로 남습니다
          </span>
        </label>

        <LoadingButton
          type="submit"
          isPending={block.isPending}
          pendingText="요청 중…"
          disabled={!canSubmit}
          className="mt-5 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-brand-700 disabled:opacity-50"
        >
          차단 요청
        </LoadingButton>
      </form>

      {notice && (
        <p
          role="status"
          className={`mt-3 text-sm ${notice.tone === 'warning' ? 'text-warning' : 'text-success'}`}
        >
          {notice.text}
        </p>
      )}

      <ConfirmDialog
        isOpen={confirmOpen}
        title="IP 차단 확인"
        variant={isLive ? 'danger' : 'warning'}
        confirmLabel="차단"
        isPending={block.isPending}
        error={confirmError}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleConfirm}
        description={
          <div className="space-y-3 text-sm">
            <dl className="grid grid-cols-[5.5rem_1fr] gap-x-3 gap-y-1.5">
              <dt className="text-fg-subtle">모드</dt>
              <dd className="font-medium">{isLive ? 'LIVE' : 'DRY-RUN'}</dd>
              <dt className="text-fg-subtle">IP</dt>
              <dd className="font-medium">{ipTrimmed}</dd>
              <dt className="text-fg-subtle">유지 시간</dt>
              <dd>{ttlNumber}초</dd>
              <dt className="text-fg-subtle">사유</dt>
              <dd className="break-words">{reasonTrimmed}</dd>
            </dl>
            {isLive ? (
              <p className="text-danger">
                실제 트래픽이 차단됩니다. 주소를 다시 확인하세요.
              </p>
            ) : (
              <p className="text-fg-muted">
                DRY-RUN이라 실제로 차단되지 않고 감사 기록만 남습니다.
              </p>
            )}
          </div>
        }
      />
    </section>
  );
};

export default BlockIpForm;
