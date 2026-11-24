// Design Ref: firewall-admin-console §5 — 상태 띠 + 탭 4개(현황·탐지·감사·승인).
// 백엔드 모듈이 꺼져 있으면(status 404) 안내만 보여 준다 (Plan FR-16, SC-1).
// 브라우저는 idt API 만 호출한다. dry-run ↔ LIVE 전환은 화면에 없다(fireware .env 로만).
import { useState } from 'react';
import Tabs from '@/components/ui/Tabs';
import {
  firewallErrorMessage,
  useFirewallAlerts,
  useFirewallApprovals,
  useFirewallStatus,
} from '@/hooks/useFirewall';
import {
  FIREWALL_TAB_LABELS,
  FIREWALL_TABS,
  type FirewallBlockDraft,
  type FirewallTab,
} from '@/types/firewall';
import FirewallApprovalsTab from './FirewallApprovalsTab';
import FirewallAuditTab from './FirewallAuditTab';
import FirewallBlocksTab from './FirewallBlocksTab';
import FirewallDetectionTab from './FirewallDetectionTab';
import FirewallStatusBar from './FirewallStatusBar';

const AdminFirewallPage = () => {
  const statusQuery = useFirewallStatus();
  const [tab, setTab] = useState<FirewallTab>('blocks');
  // 탐지 탭 → 차단 폼 초안. nonce 가 바뀌면 폼이 새 초안으로 다시 만들어진다 (Plan FR-21).
  const [draft, setDraft] = useState<FirewallBlockDraft | null>(null);

  const status = statusQuery.data;

  // 탭 배지 — 탭 내용과 같은 쿼리를 공유한다. 꺼져 있거나 Grafana 미설정이면 묻지 않는다.
  const alertsQuery = useFirewallAlerts({
    enabled: status?.enabled === true && status.grafana.configured,
  });
  const approvals = useFirewallApprovals({ enabled: status?.enabled === true });
  const firingCount = alertsQuery.data?.firing_count ?? 0;
  const approvalCount = approvals.items.length;

  const tabCount: Partial<Record<FirewallTab, number>> = {
    detection: firingCount > 0 ? firingCount : undefined,
    approvals: approvalCount > 0 ? approvalCount : undefined,
  };

  const handleBlockRequest = (ip: string, reason: string) => {
    setDraft((prev) => ({ ip, reason, nonce: (prev?.nonce ?? 0) + 1 }));
    setTab('blocks');
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-fg">방화벽</h1>
          <p className="mt-1 text-sm text-fg-muted">
            차단 현황을 보고 IP를 일정 시간 차단하거나 해제합니다. 모든 차단에는 유지 시간이 있으며
            시간이 지나면 자동으로 풀립니다.
          </p>
        </div>
        {status?.enabled && status.grafana.dashboard_url && (
          <a
            href={status.grafana.dashboard_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-fg transition-colors duration-150 hover:bg-surface-sunken"
          >
            Grafana 대시보드 ↗
          </a>
        )}
      </div>

      {statusQuery.isLoading && (
        <p className="py-10 text-center text-sm text-fg-muted">불러오는 중…</p>
      )}

      {statusQuery.isError && (
        <p
          role="alert"
          className="rounded-lg border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger"
        >
          {firewallErrorMessage(statusQuery.error, '방화벽 상태를 가져오지 못했습니다.')}
        </p>
      )}

      {status && !status.enabled && (
        <div className="rounded-lg border border-border bg-surface px-5 py-8 text-center">
          <p className="text-sm font-medium text-fg">방화벽 관리 기능이 꺼져 있습니다.</p>
          <p className="mt-2 text-sm text-fg-muted">
            서버 설정 <code>FIREWALL_ADMIN_ENABLED</code>를 <code>true</code>로 바꾸고 백엔드를 다시
            시작하면 사용할 수 있습니다.
          </p>
        </div>
      )}

      {status?.enabled && (
        <>
          <FirewallStatusBar status={status} />

          <Tabs
            aria-label="방화벽 관리"
            items={FIREWALL_TABS.map((key) => ({
              key,
              label: FIREWALL_TAB_LABELS[key],
              count: tabCount[key],
            }))}
            value={tab}
            onChange={(key) => setTab(key as FirewallTab)}
            className="mb-5"
          />

          {tab === 'blocks' && <FirewallBlocksTab status={status} draft={draft} />}
          {tab === 'detection' && (
            <FirewallDetectionTab status={status} onBlockRequest={handleBlockRequest} />
          )}
          {tab === 'audit' && <FirewallAuditTab status={status} />}
          {tab === 'approvals' && <FirewallApprovalsTab />}
        </>
      )}
    </div>
  );
};

export default AdminFirewallPage;
