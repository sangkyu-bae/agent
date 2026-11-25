// Design Ref: firewall-agent §5.1 (Plan FR-15~17) — 보안 에이전트의 자동 점검(스케줄·알림 수신)을
// 방화벽 화면에서 끄고 켠다. 끌 때만 확인창, 켤 때는 바로. 조회 실패는 이 영역에만 표시한다.
import { useState } from 'react';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import Badge from '@/components/ui/Badge';
import {
  firewallErrorMessage,
  useFirewallAutomation,
  useUpdateFirewallAutomation,
} from '@/hooks/useFirewall';
import { SCHEDULE_SKIP_REASON_LABEL } from '@/types/agentSchedule';
import {
  FIREWALL_AUTOMATION_RESULT_LABEL,
  type FirewallAutomationResponse,
  type FirewallAutomationUpdate,
} from '@/types/firewall';
import { formatDate } from '@/utils/formatters';

type Target = 'schedule' | 'alert';

const TARGET_LABEL: Record<Target, string> = {
  schedule: '스케줄',
  alert: '알림 수신',
};

interface ToggleProps {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (next: boolean) => void;
}

const Toggle = ({ label, checked, disabled, onChange }: ToggleProps) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={`relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:opacity-50 ${
      checked ? 'bg-violet-600' : 'bg-zinc-300'
    }`}
  >
    <span
      className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${
        checked ? 'left-[18px]' : 'left-0.5'
      }`}
    />
  </button>
);

const resultText = (status: string, skipReason?: string | null): string => {
  const label = FIREWALL_AUTOMATION_RESULT_LABEL[status] ?? status;
  if (!skipReason) return label;
  return `${label} (${SCHEDULE_SKIP_REASON_LABEL[skipReason] ?? skipReason})`;
};

const ScheduleLine = ({ data }: { data: FirewallAutomationResponse }) => {
  const next = data.schedules
    .map((s) => s.next_run_at)
    .filter((v): v is string => v !== null)
    .sort()[0];
  const last = data.schedules
    .map((s) => s.last_run)
    .filter((r) => r !== null)
    .sort((a, b) => (a!.started_at < b!.started_at ? 1 : -1))[0];
  return (
    <span className="text-fg-muted">
      {data.schedules.some((s) => s.enabled) && next && <>다음 {formatDate(next)} · </>}
      {last ? (
        <>
          마지막 {formatDate(last.started_at)} {resultText(last.status, last.skip_reason)}
        </>
      ) : (
        '실행 이력 없음'
      )}
    </span>
  );
};

const FirewallAutomationBar = () => {
  const query = useFirewallAutomation();
  const mutation = useUpdateFirewallAutomation();
  const [confirm, setConfirm] = useState<Target | null>(null);

  const send = (target: Target, enabled: boolean) => {
    const body: FirewallAutomationUpdate =
      target === 'schedule' ? { schedule_enabled: enabled } : { alert_enabled: enabled };
    mutation.mutate(body, { onSettled: () => setConfirm(null) });
  };

  const change = (target: Target, next: boolean) => {
    if (next) send(target, true);
    else setConfirm(target);
  };

  const data = query.data;
  const scheduleOn = data?.schedules.some((s) => s.enabled) ?? false;
  const alert = data?.alert_receiver;

  return (
    <section
      aria-label="자동 점검"
      className="mb-5 rounded-lg border border-border bg-surface px-4 py-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium text-fg">자동 점검</span>
        {data?.agent && <Badge tone="neutral">{data.agent.name}</Badge>}
      </div>

      {query.isLoading && (
        <p className="mt-2 text-fg-muted">자동 점검 상태를 불러오는 중…</p>
      )}
      {query.isError && (
        <p className="mt-2 text-danger">
          {firewallErrorMessage(query.error, '자동 점검 상태를 가져오지 못했습니다.')}
        </p>
      )}

      {data && !data.configured && (
        <p className="mt-2 text-fg-muted">
          {data.reason === 'AGENT_NOT_FOUND'
            ? '설정한 보안 에이전트를 찾을 수 없습니다. 에이전트 ID를 확인하세요: '
            : '보안 에이전트가 지정되지 않았습니다. 서버 설정에 보안 에이전트 ID를 넣으세요: '}
          <code>FIREWALL_ADMIN_AGENT_ID</code> (docs/firewall-admin-setup.md)
        </p>
      )}

      {data?.configured && (
        <div className="mt-2 flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <span className="w-16 text-fg-subtle">스케줄</span>
            {data.schedules.length > 0 ? (
              <>
                <Toggle
                  label="스케줄 자동 점검"
                  checked={scheduleOn}
                  disabled={mutation.isPending}
                  onChange={(next) => change('schedule', next)}
                />
                <ScheduleLine data={data} />
              </>
            ) : (
              <span className="text-fg-muted">스케줄 없음</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="w-16 text-fg-subtle">알림 수신</span>
            {alert?.configured ? (
              <>
                <Toggle
                  label="알림 수신 자동 점검"
                  checked={alert.enabled === true}
                  disabled={mutation.isPending}
                  onChange={(next) => change('alert', next)}
                />
                <span className="text-fg-muted">
                  {alert.last_result && alert.last_received_at
                    ? `마지막 수신 ${formatDate(alert.last_received_at)} ${resultText(alert.last_result)}`
                    : '수신 이력 없음'}
                </span>
              </>
            ) : (
              <span className="text-fg-muted">알림 수신 미설정</span>
            )}
          </div>
          {mutation.isError && !confirm && (
            <p className="text-danger">
              {firewallErrorMessage(mutation.error, '자동 점검 설정을 바꾸지 못했습니다.')}
            </p>
          )}
        </div>
      )}

      <ConfirmDialog
        isOpen={confirm !== null}
        title={`${confirm ? TARGET_LABEL[confirm] : ''} 자동 점검 끄기`}
        description="끄면 새 탐지에 대한 자동 판단이 멈춥니다. 이미 대기 중인 승인 요청은 그대로 남습니다."
        confirmLabel="끄기"
        variant="warning"
        isPending={mutation.isPending}
        error={
          mutation.isError
            ? firewallErrorMessage(mutation.error, '자동 점검 설정을 바꾸지 못했습니다.')
            : null
        }
        onClose={() => setConfirm(null)}
        onConfirm={() => confirm && send(confirm, false)}
      />
    </section>
  );
};

export default FirewallAutomationBar;
