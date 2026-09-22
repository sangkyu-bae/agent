import {
  DEFAULT_APPROVAL_GATE_CONFIG,
  GATE_EXPIRES_HOURS_MAX,
  GATE_EXPIRES_HOURS_MIN,
} from '@/types/approval';
import type { ApprovalGateConfig } from '@/types/approval';

interface ApprovalGateConfigFormProps {
  value: ApprovalGateConfig;
  /** 관리자가 강제한 게이트는 소유자가 끌 수 없다 (백엔드 FR-20). */
  enforced?: boolean;
  onChange: (next: ApprovalGateConfig) => void;
}

// approval-gate: 에이전트별 승인 게이트 설정 (Design §3.4 / §5.4)
const ApprovalGateConfigForm = ({
  value,
  enforced = false,
  onChange,
}: ApprovalGateConfigFormProps) => {
  const config = { ...DEFAULT_APPROVAL_GATE_CONFIG, ...value };
  const enabled = enforced || config.mode === 'always';

  const patch = (partial: Partial<ApprovalGateConfig>) =>
    onChange({ ...config, ...partial });

  return (
    <fieldset className="space-y-3 rounded-lg border border-zinc-200 p-4">
      <legend className="flex items-center gap-2 px-1 text-sm font-medium text-zinc-800">
        승인 게이트
        {enforced && (
          <span className="rounded border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-600">
            관리자 강제
          </span>
        )}
      </legend>

      <label className="flex items-center gap-2 text-sm text-zinc-700">
        <input
          type="checkbox"
          checked={enabled}
          disabled={enforced}
          aria-label="승인 게이트 사용"
          onChange={(e) => patch({ mode: e.target.checked ? 'always' : 'off' })}
        />
        승인이 필요한 도구 호출을 사람이 검토한 뒤 집행합니다.
      </label>

      <label className="block text-sm text-zinc-700">
        <span className="mb-1 block">집행 시각 (cron, 비우면 즉시 집행)</span>
        <input
          type="text"
          className="w-full rounded border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-violet-400 disabled:bg-zinc-50"
          placeholder="0 0 * * *"
          value={config.execute_after ?? ''}
          disabled={!enabled}
          aria-label="집행 시각 cron"
          // 입력 중에는 trim 하지 않는다 — 키 입력마다 trim 하면 cron 구분
          // 공백이 즉시 지워져 '30 23 * * *' 를 칠 수 없다 (Check 에서 발견).
          // 공백 정리는 저장 시점(ApprovalGateSettingsPanel)에서 한다.
          onChange={(e) =>
            patch({ execute_after: e.target.value === '' ? null : e.target.value })
          }
        />
      </label>

      <label className="block text-sm text-zinc-700">
        <span className="mb-1 block">
          만료 시간 (시간, {GATE_EXPIRES_HOURS_MIN}~{GATE_EXPIRES_HOURS_MAX})
        </span>
        <input
          type="number"
          className="w-full rounded border border-zinc-300 px-2 py-1.5 text-sm outline-none focus:border-violet-400 disabled:bg-zinc-50"
          min={GATE_EXPIRES_HOURS_MIN}
          max={GATE_EXPIRES_HOURS_MAX}
          value={config.expires_hours}
          disabled={!enabled}
          aria-label="만료 시간"
          onChange={(e) => patch({ expires_hours: Number(e.target.value) })}
        />
      </label>

      <p className="text-xs text-zinc-500">
        게이트는 관리자가 &apos;승인 필요&apos;로 지정한 도구에만 발동합니다.
        승인 시각과 집행 시각을 분리하면 새벽 작업도 낮에 승인해 둘 수 있습니다.
      </p>
    </fieldset>
  );
};

export default ApprovalGateConfigForm;
