import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import type { CollectionInfo, RagToolConfig } from '@/types/ragToolConfig';
import { DEFAULT_RAG_CONFIG, SEARCH_MODES } from '@/types/ragToolConfig';
import type { AgentBuilderFormData, LeftTabId, SubAgentCandidate } from '@/types/agentBuilder';
import CollapsibleSection from './CollapsibleSection';
import PlaceholderSection from './PlaceholderSection';
import ModelSettingsModal from './ModelSettingsModal';
import ToolPickerModal from './ToolPickerModal';
import SkillPickerModal from './SkillPickerModal';
import RagConfigModal from './RagConfigModal';
import DocumentExtractorConfigModal from './DocumentExtractorConfigModal';
import SubAgentManagerModal from './SubAgentManagerModal';
import { useSkills } from '@/hooks/useSkills';
import { useCollections } from '@/hooks/useRagToolConfig';
import { MAX_ATTACHED_SKILLS } from '@/constants/agentSkill';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import type { DocumentExtractorDraft } from '@/types/documentExtractor';
import {
  loadDraftFromSession,
  saveDraftToSession,
} from '@/utils/documentTemplate';

const VisualCanvas = lazy(() => import('./visual/VisualCanvas'));

const RAG_TOOL_ID = 'internal:internal_document_search';

/** 옵션 설정 모달을 갖는 도구 (tool-config-modal Design §2.4) */
const CONFIGURABLE_TOOL_IDS: readonly string[] = [
  RAG_TOOL_ID,
  DOCUMENT_EXTRACTOR_TOOL_ID,
];

interface LeftConfigPanelProps {
  form: AgentBuilderFormData;
  onChange: (form: AgentBuilderFormData) => void;
  onToolToggle: (toolId: string) => void;
  onSkillToggle: (skillId: string) => void;
  onRagConfigChange: (config: RagToolConfig) => void;
  isEditMode: boolean;
  agentId?: string | null;
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
 * 좌측 구성 패널 — 지침/서브에이전트/모델/도구함/미들웨어 섹션.
 * 모델·도구 추가는 모달로 위임한다. agent-builder-studio-ui Design §5.1/§5.6.
 */
const LeftConfigPanel = ({
  form,
  onChange,
  onToolToggle,
  onSkillToggle,
  onRagConfigChange,
  isEditMode,
  agentId,
  catalogTools,
  isToolsLoading,
  isToolsError,
  onRetryTools,
  models,
  isModelsLoading,
  isModelsError,
  onRetryModels,
}: LeftConfigPanelProps) => {
  const [leftTab, setLeftTab] = useState<LeftTabId>('form');
  const [isModelModalOpen, setModelModalOpen] = useState(false);
  const [isToolModalOpen, setToolModalOpen] = useState(false);
  const [isSkillModalOpen, setSkillModalOpen] = useState(false);
  const [isSubAgentModalOpen, setSubAgentModalOpen] = useState(false);
  const [isRagConfigOpen, setRagConfigOpen] = useState(false);
  const [isExtractorConfigOpen, setExtractorConfigOpen] = useState(false);

  const subAgents = form.subAgents ?? [];
  const { data: skillList } = useSkills({ scope: 'all', size: 100 });
  const { data: collections } = useCollections();
  const selectedSkills = (skillList?.skills ?? []).filter((s) =>
    form.skills.includes(s.id),
  );

  // R4 복원: 추출기 도구가 선택돼 있고 드래프트가 없으면 sessionStorage에서 복원
  // (모달을 열지 않아도 배지가 정확하도록 패널에서 이동 — Design §2.5)
  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current) return;
    if (!form.tools.includes(DOCUMENT_EXTRACTOR_TOOL_ID) || form.documentExtractorDraft) return;
    restoredRef.current = true;
    const restored = loadDraftFromSession();
    if (restored) onChange({ ...form, documentExtractorDraft: restored });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.tools]);

  // R4 동기화: 드래프트 변경 → sessionStorage (도구 해제로 null이 되어도 정리됨)
  useEffect(() => {
    saveDraftToSession(form.documentExtractorDraft ?? null);
  }, [form.documentExtractorDraft]);

  // 설정형 도구를 picker에서 추가하면 picker를 닫고 설정 모달을 자동 오픈
  const handleToolToggle = (toolId: string) => {
    const isAdding = !form.tools.includes(toolId);
    onToolToggle(toolId);
    if (isAdding && CONFIGURABLE_TOOL_IDS.includes(toolId)) {
      setToolModalOpen(false);
      if (toolId === RAG_TOOL_ID) setRagConfigOpen(true);
      else setExtractorConfigOpen(true);
    }
  };

  const openConfig = (toolId: string) => {
    if (toolId === RAG_TOOL_ID) setRagConfigOpen(true);
    else if (toolId === DOCUMENT_EXTRACTOR_TOOL_ID) setExtractorConfigOpen(true);
  };

  const handleAddSubAgent = (candidate: SubAgentCandidate) => {
    if (subAgents.some((s) => s.ref_agent_id === candidate.agent_id)) return;
    onChange({
      ...form,
      subAgents: [
        ...subAgents,
        {
          ref_agent_id: candidate.agent_id,
          name: candidate.name,
          description: candidate.description,
        },
      ],
    });
  };

  const handleRemoveSubAgent = (refAgentId: string) => {
    onChange({
      ...form,
      subAgents: subAgents.filter((s) => s.ref_agent_id !== refAgentId),
    });
  };

  const ragConfig = form.toolConfigs[RAG_TOOL_ID];
  const selectedTools = (catalogTools ?? []).filter((t) => form.tools.includes(t.tool_id));
  const currentModel = models?.find((m) => m.model_name === form.model);
  const modelLabel = currentModel
    ? `${currentModel.provider}:${currentModel.model_name}`
    : form.model || '모델 미선택';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* 폼 / 비주얼 탭 */}
      <div className="flex shrink-0 items-center gap-1 border-b border-zinc-200 px-3">
        <button
          type="button"
          onClick={() => setLeftTab('form')}
          className={`border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors ${
            leftTab === 'form'
              ? 'border-zinc-900 text-zinc-900'
              : 'border-transparent text-zinc-400 hover:text-zinc-600'
          }`}
        >
          📋 폼
        </button>
        <button
          type="button"
          onClick={() => setLeftTab('visual')}
          className={`border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors ${
            leftTab === 'visual'
              ? 'border-zinc-900 text-zinc-900'
              : 'border-transparent text-zinc-400 hover:text-zinc-600'
          }`}
        >
          🕸 비주얼
        </button>
      </div>

      {leftTab === 'visual' ? (
        <div style={{ flex: 1, minHeight: 0 }}>
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center text-[13px] text-zinc-400">
                캔버스 로딩 중…
              </div>
            }
          >
            <VisualCanvas
              form={form}
              catalogTools={catalogTools}
              models={models}
              onAddTool={() => setToolModalOpen(true)}
              onConfigModel={() => setModelModalOpen(true)}
              onManageSubAgents={() => setSubAgentModalOpen(true)}
              onEditInForm={() => setLeftTab('form')}
            />
          </Suspense>
        </div>
      ) : (
      /* 스크롤 본문 */
      <div style={{ flex: 1, overflowY: 'auto' }} className="px-3 py-2">
        {/* 지침 (시스템 프롬프트) */}
        <CollapsibleSection title="지침">
          <div className="overflow-hidden rounded-2xl border border-zinc-300 bg-white transition-all focus-within:border-violet-400 focus-within:ring-2 focus-within:ring-violet-100">
            <textarea
              value={form.systemPrompt}
              onChange={(e) => onChange({ ...form, systemPrompt: e.target.value })}
              placeholder={
                isEditMode
                  ? '에이전트의 시스템 프롬프트/지침을 입력하세요...'
                  : '비워두면 AI가 설명을 기반으로 자동 생성합니다'
              }
              rows={6}
              aria-label="지침"
              className="block w-full resize-none bg-transparent px-4 py-3.5 text-[14px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none"
            />
          </div>
          <p className="mt-1 text-right text-[11.5px] text-zinc-400">{form.systemPrompt.length}자</p>
        </CollapsibleSection>

        {/* 서브에이전트 */}
        <CollapsibleSection
          title={`서브에이전트 (${subAgents.length})`}
          action={
            <button
              type="button"
              onClick={() => setSubAgentModalOpen(true)}
              className="flex items-center gap-1 rounded-lg bg-zinc-900 px-2.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
            >
              관리
            </button>
          }
        >
          {subAgents.length > 0 ? (
            <ul className="space-y-2">
              {subAgents.map((sa) => (
                <li
                  key={sa.ref_agent_id}
                  className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2.5"
                >
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-zinc-700">
                    {sa.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleRemoveSubAgent(sa.ref_agent_id)}
                    aria-label={`${sa.name} 제거`}
                    className="ml-auto rounded-lg px-2 py-1 text-[12px] font-medium text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
                  >
                    제거
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-4 text-center text-[12.5px] text-zinc-400">
              서브에이전트가 없습니다
            </p>
          )}
        </CollapsibleSection>

        {/* 모델 */}
        <CollapsibleSection
          title="모델"
          action={
            <button
              type="button"
              onClick={() => setModelModalOpen(true)}
              aria-label="모델 설정"
              className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.7} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.241.437-.613.43-.992a7.683 7.683 0 0 1 0-.255c.007-.378-.138-.75-.43-.991l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
              </svg>
            </button>
          }
        >
          <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5">
            <code className="text-[13px] font-medium text-zinc-700">{modelLabel}</code>
            {currentModel && !currentModel.is_active && (
              <span title="API 키 미등록" className="text-amber-500">⚠</span>
            )}
          </div>
        </CollapsibleSection>

        {/* 도구함 */}
        <CollapsibleSection
          title="도구함"
          action={
            <button
              type="button"
              onClick={() => setToolModalOpen(true)}
              className="flex items-center gap-1 rounded-lg bg-zinc-900 px-2.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              도구
            </button>
          }
        >
          {selectedTools.length > 0 ? (
            <ul className="space-y-2">
              {selectedTools.map((tool) => {
                const isConfigurable = CONFIGURABLE_TOOL_IDS.includes(tool.tool_id);
                return (
                  <li
                    key={tool.tool_id}
                    className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-medium text-zinc-700">{tool.name}</span>
                      {tool.source === 'mcp' && (
                        <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold text-sky-600">MCP</span>
                      )}
                      {isConfigurable && (
                        <button
                          type="button"
                          onClick={() => openConfig(tool.tool_id)}
                          aria-label={`${tool.name} 설정`}
                          className="ml-auto rounded-lg px-2 py-1 text-[12px] font-medium text-violet-600 transition-colors hover:bg-violet-50"
                        >
                          설정
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => onToolToggle(tool.tool_id)}
                        aria-label={`${tool.name} 제거`}
                        className={`${isConfigurable ? '' : 'ml-auto '}rounded-lg px-2 py-1 text-[12px] font-medium text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500`}
                      >
                        제거
                      </button>
                    </div>
                    {tool.tool_id === RAG_TOOL_ID && ragConfig && (
                      <RagConfigSummaryBadge config={ragConfig} collections={collections} />
                    )}
                    {tool.tool_id === DOCUMENT_EXTRACTOR_TOOL_ID && (
                      <ExtractorSummaryBadge draft={form.documentExtractorDraft ?? null} />
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-4 text-center text-[12.5px] text-zinc-400">
              추가된 도구가 없습니다
            </p>
          )}
        </CollapsibleSection>

        {/* 스킬 */}
        <CollapsibleSection
          title={`스킬 (${form.skills.length}/${MAX_ATTACHED_SKILLS})`}
          action={
            <button
              type="button"
              onClick={() => setSkillModalOpen(true)}
              className="flex items-center gap-1 rounded-lg bg-zinc-900 px-2.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              스킬
            </button>
          }
        >
          {selectedSkills.length > 0 ? (
            <ul className="space-y-2">
              {selectedSkills.map((s) => (
                <li
                  key={s.id}
                  className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2.5"
                >
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-zinc-700">{s.name}</span>
                  {s.script_type !== 'none' && (
                    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-600">⚠ script</span>
                  )}
                  <button
                    type="button"
                    onClick={() => onSkillToggle(s.id)}
                    aria-label={`${s.name} 제거`}
                    className="ml-auto rounded-lg px-2 py-1 text-[12px] font-medium text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
                  >
                    제거
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-4 text-center text-[12.5px] text-zinc-400">
              추가된 스킬이 없습니다
            </p>
          )}
        </CollapsibleSection>

        {/* 미들웨어 (준비중) */}
        <CollapsibleSection title="미들웨어">
          <PlaceholderSection emptyText="추가된 미들웨어가 없습니다" actionLabel="+ 미들웨어" />
        </CollapsibleSection>
      </div>
      )}

      {/* 모달 */}
      <ModelSettingsModal
        isOpen={isModelModalOpen}
        models={models}
        current={{ model: form.model, temperature: form.temperature }}
        isLoading={isModelsLoading}
        isError={isModelsError}
        onRetry={onRetryModels}
        onApply={({ model, temperature }) => onChange({ ...form, model, temperature })}
        onClose={() => setModelModalOpen(false)}
      />
      <ToolPickerModal
        isOpen={isToolModalOpen}
        catalogTools={catalogTools}
        selectedIds={form.tools}
        isLoading={isToolsLoading}
        isError={isToolsError}
        onRetry={onRetryTools}
        onToggle={handleToolToggle}
        onClose={() => setToolModalOpen(false)}
      />
      <RagConfigModal
        isOpen={isRagConfigOpen && !!ragConfig}
        config={ragConfig ?? DEFAULT_RAG_CONFIG}
        onApply={onRagConfigChange}
        onClose={() => setRagConfigOpen(false)}
      />
      <DocumentExtractorConfigModal
        isOpen={isExtractorConfigOpen}
        draft={form.documentExtractorDraft ?? null}
        onChange={(draft) => onChange({ ...form, documentExtractorDraft: draft })}
        onClose={() => setExtractorConfigOpen(false)}
      />
      <SkillPickerModal
        isOpen={isSkillModalOpen}
        selectedIds={form.skills}
        onToggle={onSkillToggle}
        onClose={() => setSkillModalOpen(false)}
      />
      <SubAgentManagerModal
        isOpen={isSubAgentModalOpen}
        currentAgentId={agentId ?? null}
        selected={subAgents}
        models={models}
        onAdd={handleAddSubAgent}
        onRemove={handleRemoveSubAgent}
        onClose={() => setSubAgentModalOpen(false)}
      />
    </div>
  );
};

// ── 설정 요약 배지 (tool-config-modal Design §2.4) ─────────

interface RagConfigSummaryBadgeProps {
  config: RagToolConfig;
  collections?: CollectionInfo[];
}

const RagConfigSummaryBadge = ({ config, collections }: RagConfigSummaryBadgeProps) => {
  const collectionLabel = config.collection_name
    ? collections?.find((c) => c.name === config.collection_name)?.display_name ??
      config.collection_name
    : '전체';
  const modeLabel =
    SEARCH_MODES.find((m) => m.value === config.search_mode)?.label ?? config.search_mode;

  return (
    <p className="mt-1.5 text-[11.5px] text-zinc-400">
      {collectionLabel} · {modeLabel} · top_k {config.top_k}
      {config.use_wiki_first && (
        <span className="ml-1.5 rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-600">
          위키
        </span>
      )}
    </p>
  );
};

interface ExtractorSummaryBadgeProps {
  draft: DocumentExtractorDraft | null;
}

const ExtractorSummaryBadge = ({ draft }: ExtractorSummaryBadgeProps) => {
  if (!draft) {
    return (
      <p className="mt-1.5 inline-block rounded bg-amber-50 px-1.5 py-0.5 text-[11.5px] font-medium text-amber-600">
        ⚠ 양식 미등록
      </p>
    );
  }
  if (!draft.confirmed) {
    return (
      <p className="mt-1.5 inline-block rounded bg-zinc-100 px-1.5 py-0.5 text-[11.5px] font-medium text-zinc-500">
        작성 중 · 슬롯 {draft.slots.length}
      </p>
    );
  }
  return (
    <p className="mt-1.5 inline-block rounded bg-emerald-50 px-1.5 py-0.5 text-[11.5px] font-medium text-emerald-700">
      ✓ 양식 확정됨
    </p>
  );
};

export default LeftConfigPanel;
