import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import type { RagToolConfig } from '@/types/ragToolConfig';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';
import type { StagedSchedule } from '@/types/agentSchedule';
import StudioHeader from './StudioHeader';
import LeftConfigPanel from './LeftConfigPanel';
import AgentTestPanel from './AgentTestPanel';

interface StudioLayoutProps {
  mode: 'create' | 'edit';
  agentId: string | null;
  form: AgentBuilderFormData;
  onChange: (form: AgentBuilderFormData) => void;
  onToolToggle: (toolId: string) => void;
  onSkillToggle: (skillId: string) => void;
  onRagConfigChange: (config: RagToolConfig) => void;
  onStagedScheduleAdd: (item: StagedSchedule) => void;
  onStagedScheduleRemove: (localId: string) => void;
  onApplyDraft: (draft: ComposeAgentDraftResponse) => void;
  onSave: () => void;
  onCancel: () => void;
  isSaving: boolean;
  catalogTools?: CatalogTool[];
  isToolsLoading: boolean;
  isToolsError: boolean;
  onRetryTools: () => void;
  models?: LlmModel[];
  isModelsLoading: boolean;
  isModelsError: boolean;
  onRetryModels: () => void;
}

/**
 * 2-패널 Studio 셸 — 상단 헤더 + (좌)구성 패널 + (우)테스트 패널.
 * 각 패널은 자체 스크롤 컨테이너를 가진다 (AgentChatLayout overflow:hidden 대응).
 * agent-builder-studio-ui Design §5.1.
 */
const StudioLayout = ({
  mode,
  agentId,
  form,
  onChange,
  onToolToggle,
  onSkillToggle,
  onRagConfigChange,
  onStagedScheduleAdd,
  onStagedScheduleRemove,
  onApplyDraft,
  onSave,
  onCancel,
  isSaving,
  catalogTools,
  isToolsLoading,
  isToolsError,
  onRetryTools,
  models,
  isModelsLoading,
  isModelsError,
  onRetryModels,
}: StudioLayoutProps) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#fff' }}>
      <StudioHeader
        mode={mode}
        form={form}
        onChange={onChange}
        onSave={onSave}
        onCancel={onCancel}
        isSaving={isSaving}
      />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* 좌측 구성 패널 */}
        <div style={{ flex: 1, minWidth: 0, borderRight: '1px solid #e4e4e7' }}>
          <LeftConfigPanel
            form={form}
            onChange={onChange}
            onToolToggle={onToolToggle}
            onSkillToggle={onSkillToggle}
            onRagConfigChange={onRagConfigChange}
            isEditMode={mode === 'edit'}
            agentId={agentId}
            catalogTools={catalogTools}
            isToolsLoading={isToolsLoading}
            isToolsError={isToolsError}
            onRetryTools={onRetryTools}
            models={models}
            isModelsLoading={isModelsLoading}
            isModelsError={isModelsError}
            onRetryModels={onRetryModels}
          />
        </div>

        {/* 우측 테스트 패널 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <AgentTestPanel
            mode={mode}
            agentId={agentId}
            agentName={form.name}
            form={form}
            models={models}
            onApplyDraft={onApplyDraft}
            selectedSkills={form.skills}
            onSkillToggle={onSkillToggle}
            stagedSchedules={form.schedules}
            onStagedScheduleAdd={onStagedScheduleAdd}
            onStagedScheduleRemove={onStagedScheduleRemove}
          />
        </div>
      </div>
    </div>
  );
};

export default StudioLayout;
