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
import RagConfigPanel from '@/components/agent-builder/RagConfigPanel';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import type { RagToolConfig } from '@/types/ragToolConfig';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import type { StoreAgentSummary } from '@/types/agentStore';
import type { AgentBuilderFormData } from '@/types/agentBuilder';

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

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-emerald-100 text-emerald-700',
  anthropic: 'bg-violet-100 text-violet-700',
};
const DEFAULT_PROVIDER_COLOR = 'bg-zinc-100 text-zinc-700';

const getProviderColor = (provider: string): string =>
  PROVIDER_COLORS[provider] ?? DEFAULT_PROVIDER_COLOR;

const RAG_TOOL_ID = 'internal:internal_document_search';

const DEFAULT_FORM: AgentBuilderFormData = {
  name: '',
  description: '',
  model: '',
  systemPrompt: '',
  tools: [],
  temperature: 0.7,
  toolConfigs: {},
};

const AgentBuilderPage = () => {
  const [view, setView] = useState<ViewMode>('list');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<AgentBuilderFormData>(DEFAULT_FORM);
  const [deleteTarget, setDeleteTarget] = useState<StoreAgentSummary | null>(null);
  const [saveResult, setSaveResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const { data: agentsData, isLoading: isAgentsLoading, isError: isAgentsError, refetch: refetchAgents } = useMyBuilderAgents();
  const { data: editDetail } = useBuilderAgentDetail(editingId && view === 'edit' ? editingId : null);
  const { data: catalogTools, isLoading: isToolsLoading, isError: isToolsError, refetch: refetchTools } = useToolCatalog();
  const { data: models, isLoading: isModelsLoading, isError: isModelsError, refetch: refetchModels } = useLlmModels();

  const createMutation = useCreateBuilderAgent();
  const updateMutation = useUpdateBuilderAgent();
  const deleteMutation = useDeleteBuilderAgent();

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
      setForm({
        name: editDetail.name,
        description: editDetail.description,
        model: editDetail.llm_model_id,
        systemPrompt: editDetail.system_prompt,
        tools: editDetail.tool_ids,
        temperature: editDetail.temperature,
        toolConfigs: {},
      });
    }
  }, [editDetail, view]);

  const handleNew = () => {
    setForm(DEFAULT_FORM);
    setEditingId(null);
    setView('create');
  };

  const handleEdit = (agent: StoreAgentSummary) => {
    setEditingId(agent.agent_id);
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

    if (view === 'edit' && editingId) {
      updateMutation.mutate(
        {
          agentId: editingId,
          data: {
            name: form.name,
            system_prompt: form.systemPrompt || undefined,
            temperature: form.temperature,
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

      createMutation.mutate(
        {
          user_request: form.description || form.name,
          name: form.name,
          llm_model_id: selectedModel?.id,
          temperature: form.temperature,
          tool_configs: toolConfigs,
        },
        {
          onSuccess: (response) => {
            if (form.systemPrompt.trim()) {
              updateMutation.mutate({
                agentId: response.agent_id,
                data: { system_prompt: form.systemPrompt },
              });
            }
            setSaveResult({ type: 'success', message: '에이전트가 성공적으로 등록되었습니다.' });
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

      return { ...prev, tools: newTools, toolConfigs: newConfigs };
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
            {view === 'list' ? (
              <>
                <h1 className="text-[15px] font-semibold text-zinc-900">에이전트 만들기</h1>
                <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                  Agent Builder
                </p>
              </>
            ) : (
              <>
                <h1 className="text-[15px] font-semibold text-zinc-900">
                  {view === 'edit' ? '에이전트 수정' : '새 에이전트'}
                </h1>
                <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                  {view === 'edit' ? 'Edit Agent' : 'New Agent'}
                </p>
              </>
            )}
          </div>
        </div>

        {view === 'list' ? (
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
        ) : (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setView('list')}
              className="flex items-center rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              취소
            </button>
            <button
              onClick={handleSave}
              disabled={!form.name.trim() || isSaving}
              className="flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isSaving ? (
                <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : null}
              {isSaving ? '저장 중...' : '저장'}
            </button>
          </div>
        )}
      </header>

      {/* 콘텐츠 */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {view === 'list' ? (
          <ListView
            agents={agents}
            isLoading={isAgentsLoading}
            isError={isAgentsError}
            onRetry={refetchAgents}
            catalogTools={catalogTools}
            models={models}
            onEdit={handleEdit}
            onDelete={handleDeleteRequest}
            onNew={handleNew}
          />
        ) : (
          <FormView
            form={form}
            onChange={setForm}
            onToolToggle={handleToolToggle}
            onRagConfigChange={handleRagConfigChange}
            catalogTools={catalogTools}
            isToolsLoading={isToolsLoading}
            isToolsError={isToolsError}
            onRetryTools={refetchTools}
            models={models}
            isModelsLoading={isModelsLoading}
            isModelsError={isModelsError}
            onRetryModels={refetchModels}
            isEditMode={view === 'edit'}
          />
        )}
      </div>

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
    </div>
  );
};

// ── ListView ────────────────────────────────────

interface ListViewProps {
  agents: StoreAgentSummary[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  catalogTools?: CatalogTool[];
  models?: LlmModel[];
  onEdit: (agent: StoreAgentSummary) => void;
  onDelete: (agent: StoreAgentSummary) => void;
  onNew: () => void;
}

const ListView = ({ agents, isLoading, isError, onRetry, catalogTools, models, onEdit, onDelete, onNew }: ListViewProps) => {
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
            catalogTools={catalogTools}
            models={models}
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
  catalogTools?: CatalogTool[];
  models?: LlmModel[];
  onEdit: (agent: StoreAgentSummary) => void;
  onDelete: (agent: StoreAgentSummary) => void;
}

const AgentCard = ({ agent, catalogTools, models, onEdit, onDelete }: AgentCardProps) => {
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

// ── FormView ────────────────────────────────────

interface FormViewProps {
  form: AgentBuilderFormData;
  onChange: (form: AgentBuilderFormData) => void;
  onToolToggle: (toolId: string) => void;
  onRagConfigChange: (config: RagToolConfig) => void;
  catalogTools?: CatalogTool[];
  isToolsLoading: boolean;
  isToolsError: boolean;
  onRetryTools: () => void;
  models?: LlmModel[];
  isModelsLoading: boolean;
  isModelsError: boolean;
  onRetryModels: () => void;
  isEditMode: boolean;
}

const FormView = ({ form, onChange, onToolToggle, onRagConfigChange, catalogTools, isToolsLoading, isToolsError, onRetryTools, models, isModelsLoading, isModelsError, onRetryModels, isEditMode }: FormViewProps) => {
  const ragConfig = form.toolConfigs[RAG_TOOL_ID];
  return (
    <div style={{ maxWidth: '720px', margin: '0 auto', padding: '2rem 1.5rem' }}>
      <div className="space-y-6">
        {/* 이름 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">
            에이전트 이름 <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => onChange({ ...form, name: e.target.value })}
            placeholder="예: 문서 분석가"
            className="w-full rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          />
        </div>

        {/* 설명 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">설명</label>
          <input
            type="text"
            value={form.description}
            onChange={(e) => onChange({ ...form, description: e.target.value })}
            placeholder="에이전트의 역할과 용도를 간략히 설명하세요 (AI가 이를 기반으로 도구를 자동 선택합니다)"
            className="w-full rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          />
        </div>

        {/* 모델 선택 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">모델</label>
          {isModelsLoading ? (
            <div className="grid grid-cols-4 gap-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-[42px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
              ))}
            </div>
          ) : isModelsError ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 py-6">
              <p className="text-[13px] text-zinc-500">모델 목록을 불러올 수 없습니다</p>
              <button
                onClick={onRetryModels}
                className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
              >
                다시 시도
              </button>
            </div>
          ) : models && models.length > 0 ? (
            <div className="grid grid-cols-4 gap-2">
              {models.map((m) => (
                <button
                  key={m.id}
                  onClick={() => onChange({ ...form, model: m.model_name })}
                  className={`rounded-xl border px-3 py-2.5 text-[12px] font-medium transition-all ${
                    form.model === m.model_name
                      ? 'border-violet-400 bg-violet-50 text-violet-700 shadow-sm'
                      : 'border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300 hover:bg-zinc-50'
                  }`}
                >
                  {m.display_name}
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 py-6 text-center">
              <p className="text-[13px] text-zinc-400">등록된 모델이 없습니다</p>
            </div>
          )}
        </div>

        {/* 시스템 프롬프트 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">시스템 프롬프트</label>
          <div className="overflow-hidden rounded-2xl border border-zinc-300 bg-white transition-all focus-within:border-violet-400 focus-within:ring-2 focus-within:ring-violet-100">
            <textarea
              value={form.systemPrompt}
              onChange={(e) => onChange({ ...form, systemPrompt: e.target.value })}
              placeholder={
                isEditMode
                  ? '에이전트의 역할, 행동 방식, 제약 사항 등을 정의하세요'
                  : '비워두면 AI가 설명을 기반으로 자동 생성합니다\n\n직접 입력하면 생성 후 해당 프롬프트로 덮어씁니다'
              }
              rows={6}
              className="block w-full resize-none bg-transparent px-4 py-3.5 text-[14px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none"
            />
          </div>
        </div>

        {/* 도구 연결 */}
        <div>
          <div className="mb-1.5 flex items-center gap-2">
            <label className="text-[13px] font-semibold text-zinc-700">도구 연결</label>
            {!isEditMode && (
              <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10.5px] font-medium text-violet-500">
                AI 자동 선택
              </span>
            )}
          </div>
          {isToolsLoading ? (
            <div className="grid grid-cols-2 gap-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-[52px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
              ))}
            </div>
          ) : isToolsError ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 py-6">
              <p className="text-[13px] text-zinc-500">도구 목록을 불러올 수 없습니다</p>
              <button
                onClick={onRetryTools}
                className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
              >
                다시 시도
              </button>
            </div>
          ) : catalogTools && catalogTools.length > 0 ? (
            <div className="grid grid-cols-2 gap-2">
              {catalogTools.map((tool) => {
                const isSelected = form.tools.includes(tool.tool_id);
                return (
                  <button
                    key={tool.tool_id}
                    onClick={() => onToolToggle(tool.tool_id)}
                    className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all ${
                      isSelected
                        ? 'border-violet-300 bg-violet-50'
                        : 'border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50'
                    }`}
                  >
                    <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${isSelected ? 'bg-violet-100' : 'bg-zinc-100'}`}>
                      <svg className={`h-4 w-4 ${isSelected ? 'text-violet-600' : 'text-zinc-400'}`} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l5.653-4.655m5.976-.511a.076.076 0 0 1 .014.107l-.014-.107Zm0 0 2.355-2.355a2.553 2.553 0 0 0-3.612-3.612l-2.355 2.355" />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <span className={`text-[13px] font-medium ${isSelected ? 'text-violet-700' : 'text-zinc-600'}`}>{tool.name}</span>
                      {tool.source === 'mcp' && (
                        <span className="ml-1.5 rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold text-sky-600">MCP</span>
                      )}
                    </div>
                    {isSelected && (
                      <svg className="ml-auto h-4 w-4 shrink-0 text-violet-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 py-6 text-center">
              <p className="text-[13px] text-zinc-400">등록된 도구가 없습니다</p>
            </div>
          )}
        </div>

        {/* RAG 설정 패널 (조건부) */}
        {ragConfig && (
          <RagConfigPanel config={ragConfig} onChange={onRagConfigChange} />
        )}

        {/* Temperature */}
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-[13px] font-semibold text-zinc-700">Temperature</label>
            <span className="rounded-lg bg-zinc-100 px-2.5 py-1 text-[12.5px] font-semibold tabular-nums text-zinc-700">
              {form.temperature.toFixed(1)}
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={form.temperature}
            onChange={(e) => onChange({ ...form, temperature: parseFloat(e.target.value) })}
            className="h-2 w-full cursor-pointer appearance-none rounded-full bg-zinc-200 accent-violet-600"
          />
          <div className="mt-1 flex justify-between text-[11px] text-zinc-400">
            <span>0.0 (정확)</span>
            <span>0.5 (균형)</span>
            <span>1.0 (창의적)</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentBuilderPage;
