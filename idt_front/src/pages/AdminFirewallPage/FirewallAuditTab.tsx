// Design Ref: firewall-admin-console §5.4 감사 탭 (Plan FR-14) — fwctl 감사 이력(차단·해제)을 조회한다.
// 이력의 출처는 fwctl 감사 한 곳이고 화면은 Loki 보존 기간(7일)까지만 볼 수 있다.
// 해제는 fwctl 계약상 actor 가 없어, 관리자 화면 요청은 요청 ID(adm-<user_id>-…)로 수행자를 표시한다.
import { useState, type FormEvent } from 'react';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import { firewallErrorMessage, useFirewallAudit } from '@/hooks/useFirewall';
import type { BadgeTone } from '@/types/ui';
import {
  FIREWALL_ACTOR_ADMIN_PREFIX,
  FIREWALL_ACTOR_AGENT_PREFIX,
  FIREWALL_ADMIN_REQUEST_ID_RE,
  FIREWALL_AUDIT_EVENTS,
  FIREWALL_AUDIT_EVENT_LABELS,
  FIREWALL_AUDIT_RANGES,
  FIREWALL_IPV4_RE,
  FIREWALL_RANGE_LABELS,
  type FirewallAuditEvent,
  type FirewallAuditParams,
  type FirewallAuditRange,
  type FirewallAuditRecord,
  type FirewallStatusResponse,
} from '@/types/firewall';

interface FirewallAuditTabProps {
  status: FirewallStatusResponse;
}

interface Performer {
  kind: '관리자' | '에이전트' | '기타';
  detail: string;
}

/** 수행자 표시. actor 가 없으면 관리자 화면 요청 ID 에서 사용자 ID 를 읽는다. */
const performerOf = (record: FirewallAuditRecord): Performer => {
  const actor = record.actor ?? '';
  if (actor.startsWith(FIREWALL_ACTOR_ADMIN_PREFIX)) {
    return { kind: '관리자', detail: `ID ${actor.slice(FIREWALL_ACTOR_ADMIN_PREFIX.length)}` };
  }
  if (actor.startsWith(FIREWALL_ACTOR_AGENT_PREFIX)) return { kind: '에이전트', detail: actor };
  const fromRequestId = record.request_id?.match(FIREWALL_ADMIN_REQUEST_ID_RE);
  if (fromRequestId) return { kind: '관리자', detail: `ID ${fromRequestId[1]}` };
  return { kind: '기타', detail: actor || '-' };
};

const RESULT: Record<string, { label: string; tone: BadgeTone }> = {
  ok: { label: '성공', tone: 'success' },
  rejected: { label: '거부', tone: 'warning' },
  error: { label: '오류', tone: 'danger' },
};

const formatTime = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR');
};

// 서버 규칙과 같다 (Design §4.2): 허용 문자만, 영숫자 1자 이상. 서버가 다시 검증한다.
const ACTOR_RE = /^[A-Za-z0-9._:/-]{1,100}$/;
const HAS_ALNUM_RE = /[A-Za-z0-9]/;

const controlClass = 'rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg';
const thClass = 'px-4 py-2 font-medium';
const tdClass = 'px-4 py-2 align-top';

const FirewallAuditTab = ({ status }: FirewallAuditTabProps) => {
  const [params, setParams] = useState<FirewallAuditParams>({ range: '24h', event: 'all' });
  // 입력 중인 값 — 조회 버튼을 눌러야 조건에 반영한다(글자마다 조회하지 않는다).
  const [ipInput, setIpInput] = useState('');
  const [actorInput, setActorInput] = useState('');
  const [copied, setCopied] = useState<string | null>(null);

  const grafanaReady = status.grafana.configured;
  const auditQuery = useFirewallAudit(params, { enabled: grafanaReady });

  if (!grafanaReady) {
    return (
      <p className="rounded-xl border border-border bg-surface px-4 py-8 text-center text-sm text-fg-muted">
        Grafana 주소와 토큰이 설정되지 않아 감사 이력을 볼 수 없습니다. 설정 이름:{' '}
        <code>FIREWALL_ADMIN_GRAFANA_URL</code>, <code>FIREWALL_ADMIN_GRAFANA_TOKEN</code>
      </p>
    );
  }

  const ip = ipInput.trim();
  const actor = actorInput.trim();
  const ipError = ip && !FIREWALL_IPV4_RE.test(ip) ? 'IPv4 주소 한 개를 입력하세요.' : null;
  const actorError =
    actor && !(ACTOR_RE.test(actor) && HAS_ALNUM_RE.test(actor))
      ? '영문·숫자와 . _ : / - 만 쓸 수 있고, 영문·숫자가 1자 이상 있어야 합니다.'
      : null;

  const applyFilters = (e: FormEvent) => {
    e.preventDefault();
    if (ipError || actorError) return;
    setParams((prev) => ({
      range: prev.range,
      event: prev.event,
      ...(ip ? { ip } : {}),
      ...(actor ? { actor } : {}),
    }));
  };

  const copyRequestId = async (requestId: string) => {
    try {
      await navigator.clipboard.writeText(requestId);
      setCopied(requestId);
    } catch {
      setCopied(null);
    }
  };

  const items = auditQuery.data?.items ?? [];

  return (
    <section aria-label="감사 이력">
      <form className="mb-3 flex flex-wrap items-start gap-3" onSubmit={applyFilters}>
        <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
          기간
          <select
            aria-label="기간"
            value={params.range}
            onChange={(e) =>
              setParams((prev) => ({ ...prev, range: e.target.value as FirewallAuditRange }))
            }
            className={controlClass}
          >
            {FIREWALL_AUDIT_RANGES.map((r) => (
              <option key={r} value={r}>{FIREWALL_RANGE_LABELS[r]}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
          이벤트
          <select
            aria-label="이벤트"
            value={params.event}
            onChange={(e) =>
              setParams((prev) => ({ ...prev, event: e.target.value as FirewallAuditEvent }))
            }
            className={controlClass}
          >
            {FIREWALL_AUDIT_EVENTS.map((ev) => (
              <option key={ev} value={ev}>{FIREWALL_AUDIT_EVENT_LABELS[ev]}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
          IP
          <input
            aria-label="IP 필터"
            aria-invalid={!!ipError}
            value={ipInput}
            onChange={(e) => setIpInput(e.target.value)}
            placeholder="예: 172.28.10.66"
            className={`w-44 ${controlClass}`}
          />
          {ipError && <span className="text-xs font-normal text-danger">{ipError}</span>}
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
          수행자
          <input
            aria-label="수행자 필터"
            aria-invalid={!!actorError}
            value={actorInput}
            onChange={(e) => setActorInput(e.target.value)}
            placeholder="예: admin:7"
            className={`w-44 ${controlClass}`}
          />
          {actorError && <span className="text-xs font-normal text-danger">{actorError}</span>}
        </label>
        <Button type="submit" variant="secondary" className="mt-5" disabled={!!ipError || !!actorError}>
          조회
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="mt-5"
          onClick={() => void auditQuery.refetch()}
        >
          새로고침
        </Button>
      </form>

      <p className="mb-2 text-xs text-fg-subtle">
        최근 7일까지 조회됩니다. 차단·해제 요청만 표시합니다(거부된 요청 포함).
        {auditQuery.data && ` ${auditQuery.data.count}건`}
      </p>

      {auditQuery.isLoading ? (
        <p className="px-4 py-6 text-center text-sm text-fg-muted">불러오는 중…</p>
      ) : auditQuery.isError ? (
        <p role="alert" className="rounded-xl border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger">
          {firewallErrorMessage(auditQuery.error, '감사 이력을 가져올 수 없습니다.')}
        </p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-border bg-surface px-4 py-6 text-center text-sm text-fg-muted">
          선택한 조건에 맞는 감사 이력이 없습니다.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface-sunken text-left text-xs text-fg-subtle">
              <tr>
                <th scope="col" className={thClass}>시각</th>
                <th scope="col" className={thClass}>이벤트</th>
                <th scope="col" className={thClass}>수행자</th>
                <th scope="col" className={thClass}>IP</th>
                <th scope="col" className={thClass}>유지 시간</th>
                <th scope="col" className={thClass}>사유</th>
                <th scope="col" className={thClass}>결과</th>
                <th scope="col" className={thClass}>요청 ID</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-surface text-fg">
              {items.map((record, idx) => {
                const performer = performerOf(record);
                const result = RESULT[record.result ?? ''];
                return (
                  <tr key={`${record.request_id ?? 'none'}-${idx}`}>
                    <td className={`${tdClass} whitespace-nowrap text-fg-muted`}>
                      {formatTime(record.ts)}
                    </td>
                    <td className={tdClass}>
                      {FIREWALL_AUDIT_EVENT_LABELS[record.event as FirewallAuditEvent] ??
                        record.event ??
                        '-'}
                    </td>
                    <td className={tdClass}>
                      <div className="font-medium">{performer.kind}</div>
                      <div className="text-xs text-fg-subtle">{performer.detail}</div>
                    </td>
                    <td className={`${tdClass} font-medium`}>{record.ip ?? '-'}</td>
                    <td className={`${tdClass} tabular-nums`}>
                      {record.ttl_seconds === null ? '-' : `${record.ttl_seconds}초`}
                    </td>
                    <td className={`${tdClass} max-w-64 break-words`}>{record.reason ?? '-'}</td>
                    <td className={tdClass}>
                      <div className="flex flex-wrap items-center gap-1.5">
                        {result ? (
                          <Badge tone={result.tone}>{result.label}</Badge>
                        ) : (
                          <span>{record.result ?? '-'}</span>
                        )}
                        {record.dry_run && <Badge tone="warning">DRY-RUN</Badge>}
                      </div>
                      {record.error_code && (
                        <div className="mt-1 text-xs text-fg-subtle">{record.error_code}</div>
                      )}
                    </td>
                    <td className={tdClass}>
                      {record.request_id ? (
                        <button
                          type="button"
                          title={record.request_id}
                          aria-label={`요청 ID ${record.request_id} 복사`}
                          onClick={() => void copyRequestId(record.request_id as string)}
                          className="rounded-md px-1 text-xs text-fg-muted transition-colors duration-150 hover:bg-surface-sunken"
                        >
                          {copied === record.request_id
                            ? '복사됨'
                            : `${record.request_id.slice(0, 14)}…`}
                        </button>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};

export default FirewallAuditTab;
