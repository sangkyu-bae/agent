import { useState } from 'react';
import ApprovalGateConfigForm from './ApprovalGateConfigForm';
import {
  extractApprovalError,
  useApprovalGateSettings,
  useSaveApprovalGateSettings,
} from '@/hooks/useApprovals';
import {
  DEFAULT_APPROVAL_GATE_CONFIG,
  DEFAULT_GATE_TIMEZONE,
} from '@/types/approval';
import type { ApprovalGateConfig } from '@/types/approval';

interface ApprovalGateSettingsPanelProps {
  agentId: string;
}

// approval-gate Check G3 / FR-22: 에이전트 편집 화면의 승인 게이트 설정.
// 설정 폼(ApprovalGateConfigForm)은 이전에 만들어져 있었지만 어디에도 마운트되지
// 않았고, 저장할 API 도 없었다. 이 컨테이너가 조회·저장을 붙인다.
const ApprovalGateSettingsPanel = ({ agentId }: ApprovalGateSettingsPanelProps) => {
  const { data, isLoading, isError } = useApprovalGateSettings(agentId);
  const save = useSaveApprovalGateSettings(agentId);
  const [draft, setDraft] = useState<ApprovalGateConfig | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (isLoading) {
    return <p className="text-[12.5px] text-zinc-400">승인 게이트 설정을 불러오는 중…</p>;
  }
  if (isError || !data) {
    return (
      <p role="alert" className="text-[12.5px] text-red-500">
        승인 게이트 설정을 불러오지 못했습니다.
      </p>
    );
  }
  if (!data.available) {
    return (
      <p className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-3 text-center text-[12.5px] text-zinc-400">
        관리자가 승인 게이트를 활성화하지 않았습니다.
      </p>
    );
  }

  // 서버 값이 기준 — 사용자가 손대기 전까지는 draft 없이 서버 값을 그린다.
  const current: ApprovalGateConfig = draft ?? {
    ...DEFAULT_APPROVAL_GATE_CONFIG,
    ...data.config,
    // enabled=false 면 행이 없는 상태다 — 폼에서는 꺼진 것으로 보여준다.
    mode: data.enabled ? (data.config.mode ?? 'always') : 'off',
  };

  const handleSave = () => {
    setNotice(null);
    // 공백 정리는 저장 시점에 — 입력 중 trim 은 cron 구분 공백을 지운다.
    const cron = current.execute_after?.trim() || null;
    save.mutate({ ...current, execute_after: cron }, {
      onSuccess: () => {
        setDraft(null);
        setNotice('승인 게이트 설정을 저장했습니다.');
      },
      onError: (e) => setNotice(extractApprovalError(e)),
    });
  };

  return (
    <div className="space-y-2">
      <ApprovalGateConfigForm
        value={current}
        enforced={data.is_enforced}
        onChange={setDraft}
      />
      <p className="text-[11.5px] text-zinc-400">
        집행 시각은 {current.timezone ?? DEFAULT_GATE_TIMEZONE} 기준으로 해석됩니다.
      </p>
      <div className="flex items-center justify-end gap-2">
        {notice && (
          <span role="status" className="text-[12px] text-zinc-500">
            {notice}
          </span>
        )}
        <button
          type="button"
          onClick={handleSave}
          disabled={draft === null || save.isPending}
          className="rounded-lg bg-zinc-900 px-3 py-1.5 text-[12.5px] text-white disabled:opacity-40"
        >
          {save.isPending ? '저장 중…' : '승인 게이트 저장'}
        </button>
      </div>
    </div>
  );
};

export default ApprovalGateSettingsPanel;
