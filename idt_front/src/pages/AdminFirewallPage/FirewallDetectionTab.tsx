// Design Ref: firewall-admin-console §5.4 탐지 탭 (Plan FR-12·13·21) — 룰 8개 전체 + 발화 강조,
// 출발지 Top 10, 최근 차단 로그. "이 IP 차단"은 현황 탭 폼에 IP 와 사유 초안을 넘긴다.
// 데이터는 Grafana 경유라 실패해도 현황 탭은 영향받지 않는다 (Plan SC-8).
import { useState } from 'react';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import {
  firewallErrorMessage,
  useFirewallAlerts,
  useFirewallBlocks,
  useFirewallEvents,
} from '@/hooks/useFirewall';
import type { BadgeTone } from '@/types/ui';
import {
  FIREWALL_ACTION_HINT_LABELS,
  FIREWALL_ALERT_STATE_LABELS,
  FIREWALL_EVENT_ACTIONS,
  FIREWALL_EVENT_ACTION_LABELS,
  FIREWALL_EVENT_RANGES,
  FIREWALL_PROTOCOL_LABELS,
  FIREWALL_RANGE_LABELS,
  type FirewallAlertRule,
  type FirewallAlertState,
  type FirewallEventAction,
  type FirewallEventRange,
  type FirewallStatusResponse,
} from '@/types/firewall';

interface FirewallDetectionTabProps {
  status: FirewallStatusResponse;
  /** 현황 탭 차단 폼으로 초안을 넘긴다 */
  onBlockRequest: (ip: string, reason: string) => void;
}

const STATE_TONE: Record<FirewallAlertState, BadgeTone> = {
  firing: 'danger',
  pending: 'warning',
  normal: 'neutral',
  nodata: 'neutral',
  error: 'danger',
};

const ACTIVE_STATES: FirewallAlertState[] = ['firing', 'pending'];

const formatTime = (iso: string | null): string => {
  if (!iso) return '-';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR');
};

// 인스턴스의 value 는 화면에 쓰지 않는다. 실측(Grafana 12.0.0)에서 이 값은 건수가 아니라
// 임계 조건식의 결과(1)였다. 건수는 아래 "출발지 상위"에서 본다.
const ruleDraftReason = (rule: FirewallAlertRule): string => `${rule.name} 탐지`;

const selectClass = 'rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg';
const thClass = 'whitespace-nowrap px-4 py-2 font-medium';
const tdClass = 'px-4 py-2';

const FirewallDetectionTab = ({ status, onBlockRequest }: FirewallDetectionTabProps) => {
  const [range, setRange] = useState<FirewallEventRange>('1h');
  const [action, setAction] = useState<FirewallEventAction>('all');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const grafanaReady = status.grafana.configured;
  const alertsQuery = useFirewallAlerts({ enabled: grafanaReady });
  const eventsQuery = useFirewallEvents({ range, action }, { enabled: grafanaReady });
  // "차단 중" 표시용 — 현황 탭과 같은 쿼리를 공유한다.
  const blocksQuery = useFirewallBlocks({
    enabled: status.fwctl.configured && status.fwctl.reachable,
  });
  const blockedIps = new Set((blocksQuery.data?.items ?? []).map((b) => b.ip));
  const canBlock = status.fwctl.configured && status.fwctl.reachable;

  if (!grafanaReady) {
    return (
      <p className="rounded-xl border border-border bg-surface px-4 py-8 text-center text-sm text-fg-muted">
        Grafana 주소와 토큰이 설정되지 않아 탐지 정보를 볼 수 없습니다. 설정 이름:{' '}
        <code>FIREWALL_ADMIN_GRAFANA_URL</code>, <code>FIREWALL_ADMIN_GRAFANA_TOKEN</code>
      </p>
    );
  }

  const toggle = (uid: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });

  const refresh = () => {
    void alertsQuery.refetch();
    void eventsQuery.refetch();
  };

  const rules = alertsQuery.data?.rules ?? [];
  const top = eventsQuery.data?.top_sources ?? [];
  const recent = eventsQuery.data?.recent ?? [];
  const maxCount = top.reduce((m, s) => Math.max(m, s.count), 0);

  const blockButton = (ip: string, reason: string) =>
    blockedIps.has(ip) ? (
      <Badge tone="info">차단 중</Badge>
    ) : (
      <Button
        variant="secondary"
        size="sm"
        disabled={!canBlock}
        aria-label={`${ip} 차단`}
        onClick={() => onBlockRequest(ip, reason)}
      >
        이 IP 차단
      </Button>
    );

  return (
    <div className="space-y-8">
      <section aria-label="탐지 룰">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-base font-semibold text-fg">
            탐지 룰 ({rules.length})
            {alertsQuery.data && alertsQuery.data.firing_count > 0 && (
              <span className="ml-2 text-sm font-normal text-danger">
                발화 {alertsQuery.data.firing_count}건
              </span>
            )}
          </h2>
          <div className="flex items-center gap-3">
            <span className="text-xs text-fg-subtle">30초마다 갱신</span>
            <Button variant="ghost" size="sm" onClick={refresh}>
              새로고침
            </Button>
          </div>
        </div>

        {alertsQuery.isLoading ? (
          <p className="px-4 py-6 text-center text-sm text-fg-muted">불러오는 중…</p>
        ) : alertsQuery.isError ? (
          <p role="alert" className="rounded-xl border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger">
            {firewallErrorMessage(alertsQuery.error, '탐지 정보를 가져올 수 없습니다.')}
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead className="bg-surface-sunken text-left text-xs text-fg-subtle">
                <tr>
                  <th scope="col" className={thClass}>상태</th>
                  <th scope="col" className={thClass}>룰</th>
                  <th scope="col" className={thClass}>심각도</th>
                  <th scope="col" className={thClass}>권고</th>
                  <th scope="col" className={`${thClass} text-right`}>출발지</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border bg-surface text-fg">
                {rules.map((rule) => {
                  const active = rule.instances.filter((i) => ACTIVE_STATES.includes(i.state));
                  const isOpen = expanded.has(rule.uid) || active.length > 0;
                  const reportOnly = rule.action_hint === 'report';
                  return [
                    <tr key={rule.uid} data-testid={`rule-${rule.uid}`}>
                      <td className={tdClass}>
                        <Badge tone={STATE_TONE[rule.state]} dot={rule.state === 'firing'}>
                          {FIREWALL_ALERT_STATE_LABELS[rule.state]}
                        </Badge>
                      </td>
                      <td className={tdClass}>
                        <div className="font-medium">{rule.name}</div>
                        <div className="text-xs text-fg-subtle">{rule.description}</div>
                      </td>
                      <td className={`${tdClass} whitespace-nowrap`}>{rule.severity || '-'}</td>
                      <td className={`${tdClass} whitespace-nowrap`}>
                        {FIREWALL_ACTION_HINT_LABELS[rule.action_hint] ?? (rule.action_hint || '-')}
                      </td>
                      <td className={`${tdClass} text-right`}>
                        {rule.instances.length === 0 ? (
                          <span className="text-fg-subtle">-</span>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-expanded={isOpen}
                            aria-label={`${rule.name} 출발지 ${isOpen ? '접기' : '펼치기'}`}
                            onClick={() => toggle(rule.uid)}
                            disabled={active.length > 0}
                          >
                            {rule.instances.length}개
                          </Button>
                        )}
                      </td>
                    </tr>,
                    isOpen && rule.instances.length > 0 && (
                      <tr key={`${rule.uid}-instances`} className="bg-surface-muted">
                        <td colSpan={5} className="px-4 py-2">
                          <ul aria-label={`${rule.name} 출발지`} className="space-y-1.5">
                            {rule.instances.map((inst, idx) => (
                              <li
                                key={`${inst.src_ip ?? 'none'}-${idx}`}
                                className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm"
                              >
                                <Badge tone={STATE_TONE[inst.state]}>
                                  {FIREWALL_ALERT_STATE_LABELS[inst.state]}
                                </Badge>
                                <span className="font-medium">{inst.src_ip ?? '출발지 없음'}</span>
                                <span className="text-fg-muted">시작 {formatTime(inst.active_at)}</span>
                                <span className="ml-auto">
                                  {/* 차단 버튼은 지금 발화·대기 중인 출발지에만 낸다.
                                      발화가 끝난 과거 출발지(정상·데이터 없음)는 조치 대상이 아니다. */}
                                  {reportOnly ? (
                                    <span className="text-xs text-fg-subtle">보고 전용 룰</span>
                                  ) : (
                                    inst.src_ip &&
                                    ACTIVE_STATES.includes(inst.state) &&
                                    blockButton(inst.src_ip, ruleDraftReason(rule))
                                  )}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    ),
                  ];
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-label="차단 로그">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-base font-semibold text-fg">차단 로그</h2>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
              기간
              <select
                aria-label="기간"
                value={range}
                onChange={(e) => setRange(e.target.value as FirewallEventRange)}
                className={selectClass}
              >
                {FIREWALL_EVENT_RANGES.map((r) => (
                  <option key={r} value={r}>{FIREWALL_RANGE_LABELS[r]}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
              구분
              <select
                aria-label="구분"
                value={action}
                onChange={(e) => setAction(e.target.value as FirewallEventAction)}
                className={selectClass}
              >
                {FIREWALL_EVENT_ACTIONS.map((a) => (
                  <option key={a} value={a}>{FIREWALL_EVENT_ACTION_LABELS[a]}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {eventsQuery.isLoading ? (
          <p className="px-4 py-6 text-center text-sm text-fg-muted">불러오는 중…</p>
        ) : eventsQuery.isError ? (
          <p role="alert" className="rounded-xl border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger">
            {firewallErrorMessage(eventsQuery.error, '차단 로그를 가져올 수 없습니다.')}
          </p>
        ) : top.length === 0 && recent.length === 0 ? (
          <p className="rounded-xl border border-border bg-surface px-4 py-6 text-center text-sm text-fg-muted">
            선택한 기간에 차단 로그가 없습니다.
          </p>
        ) : (
          <div className="space-y-5">
            <div>
              <h3 className="mb-2 text-xs font-medium text-fg-subtle">출발지 상위 {top.length}개</h3>
              <ul aria-label="출발지 상위" className="space-y-1.5">
                {top.map((source) => (
                  <li key={source.src_ip} className="flex items-center gap-3 text-sm">
                    <span className="w-32 shrink-0 font-medium text-fg">{source.src_ip}</span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-sunken" aria-hidden="true">
                      <span
                        className="block h-full rounded-full bg-brand-600"
                        style={{ width: `${maxCount ? (source.count / maxCount) * 100 : 0}%` }}
                      />
                    </span>
                    <span className="w-16 shrink-0 text-right tabular-nums text-fg-muted">
                      {source.count.toLocaleString('ko-KR')}건
                    </span>
                    <span className="w-24 shrink-0 text-right">
                      {blockButton(
                        source.src_ip,
                        `차단 로그 ${FIREWALL_RANGE_LABELS[range]} ${source.count}건`,
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="overflow-x-auto rounded-xl border border-border">
              <table aria-label="최근 차단 로그" className="w-full text-sm">
                <thead className="bg-surface-sunken text-left text-xs text-fg-subtle">
                  <tr>
                    <th scope="col" className={thClass}>시각</th>
                    <th scope="col" className={thClass}>구분</th>
                    <th scope="col" className={thClass}>출발지</th>
                    <th scope="col" className={thClass}>목적지</th>
                    <th scope="col" className={thClass}>포트</th>
                    <th scope="col" className={thClass}>프로토콜</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border bg-surface text-fg">
                  {recent.map((event, idx) => (
                    <tr key={`${event.ts}-${idx}`}>
                      <td className={`${tdClass} whitespace-nowrap text-fg-muted`}>{formatTime(event.ts)}</td>
                      <td className={tdClass}>
                        {FIREWALL_EVENT_ACTION_LABELS[event.action as FirewallEventAction] ?? event.action}
                      </td>
                      <td className={tdClass}>{event.src_ip ?? '-'}</td>
                      <td className={tdClass}>{event.dest_ip ?? '-'}</td>
                      <td className={`${tdClass} tabular-nums`}>{event.dport ?? '-'}</td>
                      <td className={tdClass}>
                        {event.protocol === null
                          ? '-'
                          : (FIREWALL_PROTOCOL_LABELS[event.protocol] ?? event.protocol)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

export default FirewallDetectionTab;
