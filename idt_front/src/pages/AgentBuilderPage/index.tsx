import { useState, useEffect } from 'react';
import { useToolCatalog } from '@/hooks/useToolCatalog';
import { useLlmModels } from '@/hooks/useLlmModels';
import {
  useMyBuilderAgents,
  useBuilderAgentDetail,
  useCreateBuilderAgent,
  useUpdateBuilderAgent,
  useDeleteBuilderAgent,
} from '@/hooks/useAgentBuilder';
import { useCreateSchedule } from '@/hooks/useAgentSchedules';
import StudioLayout from '@/components/agent-builder/StudioLayout';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import type { StagedSchedule } from '@/types/agentSchedule';
import type { RagToolConfig } from '@/types/ragToolConfig';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import type { StoreAgentSummary } from '@/types/agentStore';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';
import { MAX_ATTACHED_SKILLS } from '@/constants/agentSkill';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import { buildDocumentTemplateRequest } from '@/utils/documentTemplate';
import { mapDraftToolIdsToCatalog } from '@/utils/draftToolMapping';

type ViewMode = 'list' | 'create' | 'edit';

const VISIBILITY_STYLES = {
  private: 'bg-zinc-100 text-zinc-500',
  department: 'bg-amber-100 text-amber-700',
  public: 'bg-emerald-100 text-emerald-700',
} as const;

const VISIBILITY_LABELS = {
  private: '비공개',
  department: '부서',
  public: '공개',
} as const;

const RAG_TOOL_ID = 'internal:internal_document_search';

const DEFAULT_FORM: AgentBuilderFormData = {
  name: '',
  description: '',
  model: '',
  systemPrompt: '',
  tools: [],
  temperature: 0.7,
  toolConfigs: {},
  subAgents: [],
  skills: [],
  schedules: [],
};

const AgentBuilderPage = () => {
  const [view, setView] = useState<ViewMode>('list');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<AgentBuilderFormData>(DEFAULT_FORM);
  const [deleteTarget, setDeleteTarget] = useState<StoreAgentSummary | null>(null);
  const [saveResult, setSaveResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  // agent-instruction-required: 지침 미입력 시 저장 차단 + 인라인 에러
  const [promptError, setPromptError] = useState<string | null>(null);

  const { data: agentsData, isLoading: isAgentsLoading, isError: isAgentsError, refetch: refetchAgents } = useMyBuilderAgents();
  const { data: editDetail } = useBuilderAgentDetail(editingId && view === 'edit' ? editingId : null);
  const { data: catalogTools, isLoading: isToolsLoading, isError: isToolsError, refetch: refetchTools } = useToolCatalog();
  const { data: models, isLoading: isModelsLoading, isError: isModelsError, refetch: refetchModels } = useLlmModels();

  const createMutation = useCreateBuilderAgent();
  const updateMutation = useUpdateBuilderAgent();
  const deleteMutation = useDeleteBuilderAgent();
  const createScheduleMutation = useCreateSchedule();

  const agents = agentsData?.agents ?? [];

  useEffect(() => {
    if (models && !form.model) {
      const defaultModel = models.find(m => m.is_default);
      if (defaultModel) {
        setForm(prev => ({ ...prev, model: defaultModel.model_name }));
      }
    }
  }, [models, form.model]);

  useEffect(() => {
    if (editDetail && view === 'edit') {
      const subAgents = (editDetail.workers ?? [])
        .filter((w) => w.worker_type === 'sub_agent' && w.ref_agent_id)
        .map((w) => ({
          ref_agent_id: w.ref_agent_id as string,
          name: w.ref_agent_name ?? (w.ref_agent_id as string),
          description: w.description ?? '',
        }));
      setForm({
        name: editDetail.name,
        description: editDetail.description,
        model: editDetail.llm_model_id,
        systemPrompt: editDetail.system_prompt,
        tools: editDetail.tool_ids,
        temperature: editDetail.temperature,
        toolConfigs: {},
        subAgents,
        skills: editDetail.skill_ids ?? [],
        // edit 모드 스케줄은 SchedulePanel이 서버 직결 — staged 미사용
        schedules: [],
      });
    }
  }, [editDetail, view]);

  // 폼 변경 시 지침이 채워지면 인라인 에러 해제 (effect 내 setState 지양)
  const handleFormChange = (next: AgentBuilderFormData) => {
    if (promptError && next.systemPrompt.trim()) setPromptError(null);
    setForm(next);
  };

  const handleNew = () => {
    setForm(DEFAULT_FORM);
    setEditingId(null);
    setPromptError(null);
    setView('create');
  };

  const handleEdit = (agent: StoreAgentSummary) => {
    setEditingId(agent.agent_id);
    setPromptError(null);
    setView('edit');
  };

  const handleDeleteRequest = (agent: StoreAgentSummary) => {
    setDeleteTarget(agent);
  };

  const handleDeleteConfirm = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.agent_id, {
      onSuccess: () => setDeleteTarget(null),
    });
  };

  const handleSave = () => {
    if (!form.name.trim()) return;

    // agent-instruction-required: 지침 필수 — 생성/수정 공통으로 빈 값 저장 차단
    if (!form.systemPrompt.trim()) {
      setPromptError('지침을 입력해주세요. Fix 에이전트 탭에서 초안을 생성할 수도 있습니다.');
      return;
    }
    setPromptError(null);

    if (view === 'edit' && editingId) {
      updateMutation.mutate(
        {
          agentId: editingId,
          data: {
            name: form.name,
            system_prompt: form.systemPrompt,
            temperature: form.temperature,
            sub_agent_configs: form.subAgents.map((s) => ({
              ref_agent_id: s.ref_agent_id,
              description: s.description,
            })),
            // 빈 배열도 명시 전송 → 전체 해제 의미 (undefined=무변경과 구분)
            skill_ids: form.skills,
            // undefined = 템플릿 변경 안 함, 값 = 교체 (기존 soft-delete)
            document_template: buildDocumentTemplateRequest(
              form.documentExtractorDraft,
              form.name,
            ),
          },
        },
        {
          onSuccess: () => {
            setSaveResult({ type: 'success', message: '에이전트가 성공적으로 수정되었습니다.' });
          },
          onError: (error) => {
            setSaveResult({ type: 'error', message: error.message });
          },
        },
      );
    } else {
      const selectedModel = models?.find(m => m.model_name === form.model);
      const toolConfigs = Object.keys(form.toolConfigs).length > 0 ? form.toolConfigs : undefined;

      // fix-agent-composer FR-08: 저장 API가 mcp_{server_id}를 수용하므로 MCP 필터 없이 전송
      const toolIds = form.tools.length > 0 ? form.tools : undefined;

      const subAgentConfigs = form.subAgents.length > 0
        ? form.subAgents.map((s) => ({
            ref_agent_id: s.ref_agent_id,
            description: s.description,
          }))
        : undefined;

      createMutation.mutate(
        {
          user_request: form.description || form.name,
          name: form.name,
          // agent-instruction-required: 지침을 create 본문에 직접 포함 (create→update 2-call 제거)
          system_prompt: form.systemPrompt,
          llm_model_id: selectedModel?.id,
          temperature: form.temperature,
          tool_ids: toolIds,
          tool_configs: toolConfigs,
          sub_agent_configs: subAgentConfigs,
          skill_ids: form.skills.length > 0 ? form.skills : undefined,
          document_template: buildDocumentTemplateRequest(
            form.documentExtractorDraft,
            form.name,
          ),
        },
        {
          onSuccess: async (response) => {
            // agent-schedule: staged 스케줄 순차 등록 (병렬 금지 — 10개 제한 경합/실패 지점 명확화)
            let failed = 0;
            for (const s of form.schedules) {
              try {
                await createScheduleMutation.mutateAsync({
                  agentId: response.agent_id,
                  data: {
                    name: s.name,
                    spec: s.spec,
                    instruction: s.instruction,
                    timezone: s.timezone,
                    enabled: s.enabled,
                  },
                });
              } catch {
                failed += 1;
              }
            }
            const suffix =
              form.schedules.length === 0
                ? ''
                : failed === 0
                  ? ` 스케줄 ${form.schedules.length}건이 함께 등록되었습니다.`
                  : ` 스케줄 ${form.schedules.length}건 중 ${failed}건 등록에 실패했습니다. 수정 화면의 스케줄 탭에서 다시 등록해주세요.`;
            setSaveResult({
              type: 'success',
              message: `에이전트가 성공적으로 등록되었습니다.${suffix}`,
            });
          },
          onError: (error) => {
            setSaveResult({ type: 'error', message: error.message });
          },
        },
      );
    }
  };

  const handleToolToggle = (toolId: string) => {
    setForm((prev) => {
      const isRemoving = prev.tools.includes(toolId);
      const newTools = isRemoving
        ? prev.tools.filter((t) => t !== toolId)
        : [...prev.tools, toolId];

      const newConfigs = { ...prev.toolConfigs };
      if (toolId === RAG_TOOL_ID) {
        if (isRemoving) {
          delete newConfigs[RAG_TOOL_ID];
        } else {
          newConfigs[RAG_TOOL_ID] = { ...DEFAULT_RAG_CONFIG };
        }
      }

      // 문서추출기 해제 시 보유 드래프트 정리 (document-template-extractor)
      const next = { ...prev, tools: newTools, toolConfigs: newConfigs };
      if (toolId === DOCUMENT_EXTRACTOR_TOOL_ID && isRemoving) {
        next.documentExtractorDraft = null;
      }
      return next;
    });
  };

  const handleSkillToggle = (skillId: string) => {
    setForm((prev) => {
      const isOn = prev.skills.includes(skillId);
      if (!isOn && prev.skills.length >= MAX_ATTACHED_SKILLS) return prev;
      return {
        ...prev,
        skills: isOn
          ? prev.skills.filter((s) => s !== skillId)
          : [...prev.skills, skillId],
      };
    });
  };

  const handleStagedScheduleAdd = (item: StagedSchedule) => {
    setForm((prev) => ({ ...prev, schedules: [...prev.schedules, item] }));
  };

  const handleStagedScheduleRemove = (localId: string) => {
    setForm((prev) => ({
      ...prev,
      schedules: prev.schedules.filter((s) => s.localId !== localId),
    }));
  };

  // fix-agent-composer FR-05: 초안 카드 [적용하기] → 폼 원자적 반영
  // compose-tool-instructions FR-08: 저장 형식 tool_ids → 카탈로그 형식 변환
  // (변환 없이는 도구함 체크 비교/RAG_TOOL_ID 부수효과가 모두 미동작)
  const handleApplyDraft = (draft: ComposeAgentDraftResponse) => {
    if (draft.system_prompt?.trim()) setPromptError(null);
    setForm((prev) => {
      const newTools = mapDraftToolIdsToCatalog(draft.tool_ids, catalogTools);

      // handleToolToggle과 동일한 부수효과 동기화 (RAG 설정 / 문서추출기 드래프트)
      const newConfigs = { ...prev.toolConfigs };
      if (newTools.includes(RAG_TOOL_ID)) {
        if (!newConfigs[RAG_TOOL_ID]) {
          newConfigs[RAG_TOOL_ID] = { ...DEFAULT_RAG_CONFIG };
        }
      } else {
        delete newConfigs[RAG_TOOL_ID];
      }

      // llm_model_id 역매핑 실패 시 모델 미변경 (카드에 안내 표시됨)
      const modelName = models?.find((m) => m.id === draft.llm_model_id)?.model_name;

      return {
        ...prev,
        name: draft.name_suggestion,
        systemPrompt: draft.system_prompt,
        tools: newTools,
        temperature: draft.temperature,
        model: modelName ?? prev.model,
        toolConfigs: newConfigs,
        documentExtractorDraft: newTools.includes(DOCUMENT_EXTRACTOR_TOOL_ID)
          ? prev.documentExtractorDraft
          : null,
      };
    });
  };

  const handleRagConfigChange = (config: RagToolConfig) => {
    setForm((prev) => ({
      ...prev,
      toolConfigs: { ...prev.toolConfigs, [RAG_TOOL_ID]: config },
    }));
  };

  const handleSaveResultConfirm = () => {
    if (saveResult?.type === 'success') {
      setView('list');
    }
    setSaveResult(null);
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <>
      {view === 'list' ? (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#fff' }}>
          {/* 헤더 */}
          <header className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
            <div className="flex items-center gap-3">
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md"
                style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
              >
                <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
                </svg>
              </div>
              <div>
                <h1 className="text-[15px] font-semibold text-zinc-900">에이전트 만들기</h1>
                <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                  Agent Builder
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-[12.5px] text-zinc-400">
                전체 <span className="font-semibold text-violet-600">{agentsData?.total ?? 0}개</span>
              </span>
              <button
                onClick={handleNew}
                className="flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                새 에이전트
              </button>
            </div>
          </header>

          {/* 콘텐츠 */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <ListView
              agents={agents}
              isLoading={isAgentsLoading}
              isError={isAgentsError}
              onRetry={refetchAgents}
              onEdit={handleEdit}
              onDelete={handleDeleteRequest}
              onNew={handleNew}
            />
          </div>
        </div>
      ) : (
        <StudioLayout
          mode={view === 'edit' ? 'edit' : 'create'}
          agentId={editingId}
          form={form}
          onChange={handleFormChange}
          onToolToggle={handleToolToggle}
          onSkillToggle={handleSkillToggle}
          onRagConfigChange={handleRagConfigChange}
          onStagedScheduleAdd={handleStagedScheduleAdd}
          onStagedScheduleRemove={handleStagedScheduleRemove}
          onApplyDraft={handleApplyDraft}
          onSave={handleSave}
          onCancel={() => setView('list')}
          isSaving={isSaving}
          systemPromptError={promptError}
          catalogTools={catalogTools}
          isToolsLoading={isToolsLoading}
          isToolsError={isToolsError}
          onRetryTools={refetchTools}
          models={models}
          isModelsLoading={isModelsLoading}
          isModelsError={isModelsError}
          onRetryModels={refetchModels}
        />
      )}

      {/* 삭제 확인 다이얼로그 */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="에이전트 삭제"
        description={
          <>
            <span className="font-semibold">{deleteTarget?.name}</span> 에이전트를 삭제하시겠습니까?
            <br />
            이 작업은 되돌릴 수 없습니다.
          </>
        }
        confirmLabel="삭제"
        variant="danger"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        isPending={deleteMutation.isPending}
        error={deleteMutation.isError ? '삭제에 실패했습니다. 다시 시도해주세요.' : null}
      />

      {/* 저장 결과 다이얼로그 */}
      <ConfirmDialog
        isOpen={!!saveResult}
        title={
          saveResult?.type === 'success'
            ? view === 'edit' ? '에이전트 수정 완료' : '에이전트 등록 완료'
            : view === 'edit' ? '수정 실패' : '등록 실패'
        }
        description={saveResult?.message ?? ''}
        confirmLabel="확인"
        variant={saveResult?.type === 'success' ? 'info' : 'danger'}
        onClose={handleSaveResultConfirm}
        onConfirm={handleSaveResultConfirm}
      />
    </>
  );
};

// ── ListView ────────────────────────────────────

interface ListViewProps {
  agents: StoreAgentSummary[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onEdit: (agent: StoreAgentSummary) => void;
  onDelete: (agent: StoreAgentSummary) => void;
  onNew: () => void;
}

const ListView = ({ agents, isLoading, isError, onRetry, onEdit, onDelete, onNew }: ListViewProps) => {
  if (isLoading) {
    return (
      <div className="p-6">
        <div className="grid grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-[200px] animate-pulse rounded-2xl border border-zinc-200 bg-zinc-100" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-center">
        <p className="text-[15px] font-semibold text-zinc-900">불러오기 실패</p>
        <p className="mt-1.5 text-[13px] text-zinc-400">에이전트 목록을 불러올 수 없습니다</p>
        <button
          onClick={onRetry}
          className="mt-5 rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          다시 시도
        </button>
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-center">
        <div
          className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl shadow-lg"
          style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
        >
          <svg className="h-8 w-8 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </div>
        <p className="text-[15px] font-semibold text-zinc-900">에이전트가 없습니다</p>
        <p className="mt-1.5 text-[13px] text-zinc-400">첫 AI 에이전트를 만들어 보세요</p>
        <button
          onClick={onNew}
          className="mt-5 rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          새 에이전트 만들기
        </button>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="grid grid-cols-3 gap-4">
        {agents.map((agent) => (
          <AgentCard
            key={agent.agent_id}
            agent={agent}
            onEdit={onEdit}
            onDelete={onDelete}
          />
        ))}
      </div>
    </div>
  );
};

// ── AgentCard ───────────────────────────────────

interface AgentCardProps {
  agent: StoreAgentSummary;
  onEdit: (agent: StoreAgentSummary) => void;
  onDelete: (agent: StoreAgentSummary) => void;
}

const AgentCard = ({ agent, onEdit, onDelete }: AgentCardProps) => {
  const initials = agent.name.slice(0, 2);
  const gradients = [
    'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)',
    'linear-gradient(135deg, #0ea5e9 0%, #2563eb 100%)',
    'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
    'linear-gradient(135deg, #10b981 0%, #059669 100%)',
  ];
  const gradientIndex = agent.agent_id.length % gradients.length;
  const visibilityStyle = VISIBILITY_STYLES[agent.visibility] ?? VISIBILITY_STYLES.private;
  const visibilityLabel = VISIBILITY_LABELS[agent.visibility] ?? '비공개';

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg">
      {/* 카드 상단 */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-[13px] font-bold text-white shadow-md"
            style={{ background: gradients[gradientIndex] }}
          >
            {initials}
          </div>
          <div>
            <p className="text-[14px] font-semibold text-zinc-900">{agent.name}</p>
            <span className={`mt-0.5 inline-block rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${visibilityStyle}`}>
              {visibilityLabel}
            </span>
          </div>
        </div>
      </div>

      {/* 설명 */}
      <p className="mt-3 line-clamp-2 text-[12.5px] leading-[1.6] text-zinc-500">{agent.description}</p>

      {/* 메타 정보 + 액션 버튼 */}
      <div className="mt-4 flex items-center justify-between border-t border-zinc-100 pt-3">
        <div className="flex items-center gap-3 text-[11.5px] text-zinc-400">
          <span>T: {agent.temperature.toFixed(1)}</span>
          <span>{agent.created_at?.slice(0, 10)}</span>
        </div>

        <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {agent.can_edit && (
            <button
              onClick={() => onEdit(agent)}
              className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
              </svg>
            </button>
          )}
          {agent.can_delete && (
            <button
              onClick={() => onDelete(agent)}
              className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default AgentBuilderPage;
