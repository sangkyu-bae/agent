// Design Ref: firewall-admin-console §5.4 현황 탭 (Plan FR-20) — 차단 폼 + 현재 차단 목록 + 해제.
// 목록은 10초마다 다시 조회하고, 그 사이에는 남은 시간을 1초 단위로 줄여 보여 준다.
import { useEffect, useState } from 'react';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import LoadingButton from '@/components/common/LoadingButton';
import { firewallErrorMessage, useFirewallBlocks, useUnblockIp } from '@/hooks/useFirewall';
import type { FirewallBlockDraft, FirewallStatusResponse } from '@/types/firewall';
import BlockIpForm from './BlockIpForm';

interface FirewallBlocksTabProps {
  status: FirewallStatusResponse;
  draft?: FirewallBlockDraft | null;
}

const formatRemaining = (seconds: number): string => {
  const s = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(s / 60);
  const rest = s % 60;
  return minutes > 0 ? `${minutes}분 ${rest}초` : `${rest}초`;
};

/** 1초마다 현재 시각(ms)을 돌려준다 — 남은 시간 표시용 */
const useNow = (): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return now;
};

const FirewallBlocksTab = ({ status, draft }: FirewallBlocksTabProps) => {
  const available = status.fwctl.configured && status.fwctl.reachable;
  const blocksQuery = useFirewallBlocks({ enabled: available });
  const unblock = useUnblockIp();
  const now = useNow();

  const [target, setTarget] = useState<string | null>(null);
  const [unblockError, setUnblockError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const items = blocksQuery.data?.items ?? [];
  const elapsed = blocksQuery.dataUpdatedAt
    ? Math.max(0, (now - blocksQuery.dataUpdatedAt) / 1000)
    : 0;

  const handleUnblock = async () => {
    if (!target) return;
    setUnblockError(null);
    try {
      const result = await unblock.mutateAsync(target);
      setTarget(null);
      if (result.already_absent) setNotice(`${result.ip}은(는) 이미 해제된 주소입니다.`);
      else if (result.dry_run) setNotice(`실제로 해제되지 않았습니다(DRY-RUN). ${result.ip}`);
      else setNotice(`${result.ip} 차단을 해제했습니다.`);
    } catch (err) {
      setUnblockError(firewallErrorMessage(err, '해제에 실패했습니다.'));
    }
  };

  return (
    <div>
      <BlockIpForm key={draft?.nonce ?? 0} status={status} draft={draft} />

      <section aria-label="현재 차단 목록">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-fg">
            현재 차단 목록 ({blocksQuery.data?.count ?? 0})
          </h2>
          <span className="text-xs text-fg-muted">10초마다 갱신</span>
        </div>

        {notice && (
          <p role="status" className="mb-2 text-sm text-fg-muted">
            {notice}
          </p>
        )}

        {!available ? (
          <p className="rounded-lg border border-border bg-surface px-4 py-6 text-center text-sm text-fg-muted">
            fwctl에 연결되면 차단 목록이 표시됩니다.
          </p>
        ) : blocksQuery.isLoading ? (
          <p className="px-4 py-6 text-center text-sm text-fg-muted">불러오는 중…</p>
        ) : blocksQuery.isError ? (
          <p role="alert" className="rounded-lg border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger">
            {firewallErrorMessage(blocksQuery.error, '차단 목록을 가져오지 못했습니다.')}
          </p>
        ) : items.length === 0 ? (
          <p className="rounded-lg border border-border bg-surface px-4 py-6 text-center text-sm text-fg-muted">
            차단 중인 IP가 없습니다.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-surface-sunken text-left text-xs text-fg-subtle">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">IP</th>
                  <th scope="col" className="px-4 py-2 font-medium">남은 시간</th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">패킷</th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">바이트</th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">
                    <span className="sr-only">조작</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border bg-surface text-fg">
                {items.map((entry) => (
                  <tr key={entry.ip}>
                    <td className="px-4 py-2 font-medium">{entry.ip}</td>
                    <td className="px-4 py-2 tabular-nums">
                      {formatRemaining(entry.ttl_remaining_seconds - elapsed)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {entry.packets.toLocaleString('ko-KR')}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {entry.bytes.toLocaleString('ko-KR')}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <LoadingButton
                        type="button"
                        isPending={unblock.isPending && target === entry.ip}
                        pendingText="해제 중…"
                        disabled={unblock.isPending}
                        onClick={() => {
                          setUnblockError(null);
                          setTarget(entry.ip);
                        }}
                        aria-label={`${entry.ip} 해제`}
                        className="rounded-md border border-border px-3 py-1 text-xs font-medium text-fg transition-colors duration-150 hover:bg-surface-sunken disabled:opacity-50"
                      >
                        해제
                      </LoadingButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <ConfirmDialog
        isOpen={target !== null}
        title="차단 해제 확인"
        variant="warning"
        confirmLabel="해제"
        isPending={unblock.isPending}
        error={unblockError}
        onClose={() => setTarget(null)}
        onConfirm={handleUnblock}
        description={`${target ?? ''} 차단을 지금 해제합니다.`}
      />
    </div>
  );
};

export default FirewallBlocksTab;
