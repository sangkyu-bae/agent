import { useState } from 'react';
import type { AgentBuilderFormData, RightTabId } from '@/types/agentBuilder';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';
import type { StagedSchedule } from '@/types/agentSchedule';
import type { LlmModel } from '@/types/llmModel';
import TestChatView from './TestChatView';
import AgentSkillPanel from './AgentSkillPanel';
import SchedulePanel from './schedule/SchedulePanel';
import FixAgentPanel from './fix/FixAgentPanel';
import SettingsPanel from './settings/SettingsPanel';

interface AgentTestPanelProps {
  mode: 'create' | 'edit';
  agentId: string | null;
  agentName: string;
  form: AgentBuilderFormData;
  models?: LlmModel[];
  onApplyDraft: (draft: ComposeAgentDraftResponse) => void;
  selectedSkills: string[];
  onSkillToggle: (skillId: string) => void;
  stagedSchedules: StagedSchedule[];
  onStagedScheduleAdd: (item: StagedSchedule) => void;
  onStagedScheduleRemove: (localId: string) => void;
  /** agent-settings-tab D6: 반복 한도 확정값 반영 (clamp는 SettingsPanel 책임) */
  onMaxIterationsChange: (value: number) => void;
}

interface TabDef {
  id: RightTabId;
  label: string;
  enabled: boolean;
}

/**
 * 우측 패널 — 탭 바 + Fix/테스트/스킬/스케줄/설정 콘텐츠.
 * Fix는 채팅→compose→초안 적용(fix-agent-composer), 테스트는 항상 활성,
 * 스킬은 생성·수정 모두 활성(agent-skill-toggle, staged),
 * 스케줄은 생성=staged/수정=즉시 CRUD (agent-schedule),
 * 설정은 생성·수정 모두 활성 (agent-settings-tab — Recursion Limit 실기능).
 * 나머지(오프너/파일)는 비활성 placeholder — Design §5.1.
 */
const AgentTestPanel = ({
  mode,
  agentId,
  agentName,
  form,
  models,
  onApplyDraft,
  selectedSkills,
  onSkillToggle,
  stagedSchedules,
  onStagedScheduleAdd,
  onStagedScheduleRemove,
  onMaxIterationsChange,
}: AgentTestPanelProps) => {
  const [tab, setTab] = useState<RightTabId>('test');

  const tabs: TabDef[] = [
    { id: 'fix', label: 'Fix 에이전트', enabled: true },
    { id: 'test', label: '테스트', enabled: true },
    { id: 'opener', label: '오프너', enabled: false },
    { id: 'file', label: '파일', enabled: false },
    { id: 'skill', label: '스킬', enabled: true },
    { id: 'schedule', label: '스케줄', enabled: true },
    { id: 'settings', label: '설정', enabled: true },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* 탭 바 */}
      <div className="flex shrink-0 items-center gap-0.5 overflow-x-auto border-b border-zinc-200 px-3">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            disabled={!t.enabled}
            onClick={() => t.enabled && setTab(t.id)}
            title={t.enabled ? undefined : '준비중'}
            className={`shrink-0 border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors ${
              !t.enabled
                ? 'cursor-not-allowed border-transparent text-zinc-300'
                : tab === t.id
                  ? 'border-zinc-900 text-zinc-900'
                  : 'border-transparent text-zinc-400 hover:text-zinc-600'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 콘텐츠 */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {tab === 'fix' ? (
          <FixAgentPanel
            mode={mode}
            form={form}
            models={models}
            onApplyDraft={onApplyDraft}
          />
        ) : tab === 'skill' ? (
          <div style={{ height: '100%', overflowY: 'auto' }} className="px-4 py-4">
            <AgentSkillPanel selectedIds={selectedSkills} onToggle={onSkillToggle} />
          </div>
        ) : tab === 'schedule' ? (
          <SchedulePanel
            mode={mode}
            agentId={agentId}
            stagedSchedules={stagedSchedules}
            onStagedAdd={onStagedScheduleAdd}
            onStagedRemove={onStagedScheduleRemove}
          />
        ) : tab === 'settings' ? (
          <SettingsPanel
            agentId={agentId}
            maxIterations={form.maxIterations}
            onMaxIterationsChange={onMaxIterationsChange}
          />
        ) : (
          <TestChatView mode={mode} agentId={agentId} agentName={agentName} />
        )}
      </div>
    </div>
  );
};

export default AgentTestPanel;
