import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import type { CollectionInfo, KnowledgeBaseInfo, RagToolConfig } from '@/types/ragToolConfig';
import { DEFAULT_RAG_CONFIG, SEARCH_MODES } from '@/types/ragToolConfig';
import type { AgentBuilderFormData, LeftTabId, SubAgentCandidate } from '@/types/agentBuilder';
import CollapsibleSection from './CollapsibleSection';
import ModelSettingsModal from './ModelSettingsModal';
import ToolPickerModal from './ToolPickerModal';
import SkillPickerModal from './SkillPickerModal';
import RagConfigModal from './RagConfigModal';
import DocumentExtractorConfigModal from './DocumentExtractorConfigModal';
import DocumentGeneratorConfigModal from './DocumentGeneratorConfigModal';
import PresentationGeneratorConfigModal from './PresentationGeneratorConfigModal';
import SubAgentManagerModal from './SubAgentManagerModal';
import { useSkills } from '@/hooks/useSkills';
import { useMiddlewareCatalog } from '@/hooks/useMiddlewareCatalog';
import type { MiddlewareCatalogItem } from '@/types/middleware';
import ApprovalGateSettingsPanel from '@/components/agent/ApprovalGateSettingsPanel';
import { SEPARATELY_MANAGED_MIDDLEWARE_TYPES } from '@/types/approval';
import { useCollections } from '@/hooks/useRagToolConfig';
import { useKnowledgeBases } from '@/hooks/useKnowledgeBases';
import { MAX_ATTACHED_SKILLS } from '@/constants/agentSkill';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import type { DocumentExtractorDraft } from '@/types/documentExtractor';
import { DOCUMENT_GENERATOR_TOOL_ID } from '@/types/documentGenerator';
import type { DocumentGeneratorDraft } from '@/types/documentGenerator';
import type { PresentationGeneratorDraft } from '@/types/presentationGenerator';
import { PRESENTATION_GENERATOR_TOOL_ID } from '@/types/presentationGenerator';
import {
  loadDraftFromSession,
  saveDraftToSession,
} from '@/utils/documentTemplate';
import { RAG_CATALOG_TOOL_ID } from '@/utils/agentDetailMapping';

const VisualCanvas = lazy(() => import('./visual/VisualCanvas'));

const RAG_TOOL_ID = RAG_CATALOG_TOOL_ID;

/** 옵션 설정 모달을 갖는 도구 (tool-config-modal Design §2.4) */
const CONFIGURABLE_TOOL_IDS: readonly string[] = [
  RAG_TOOL_ID,
  DOCUMENT_EXTRACTOR_TOOL_ID,
  DOCUMENT_GENERATOR_TOOL_ID,
  PRESENTATION_GENERATOR_TOOL_ID,
];

interface LeftConfigPanelProps {
  form: AgentBuilderFormData;
  onChange: (form: AgentBuilderFormData) => void;
  onToolToggle: (toolId: string) => void;
  onSkillToggle: (skillId: string) => void;
  onRagConfigChange: (config: RagToolConfig) => void;
  /** builtin-tools D8: 빌트인 수동 해제/복원 토글 (create 모드 전용) */
  onBuiltinToggle: (toolId: string) => void;
  /** builtin-middleware D10: 미들웨어 토글 (create=빌트인 opt-out, edit=전체 교체) */
  onMiddlewareToggle: (middlewareType: string) => void;
  isEditMode: boolean;
  agentId?: string | null;
  /** agent-instruction-required: 지침 미입력 시 인라인 에러 메시지 */
  systemPromptError?: string | null;
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
  onBuiltinToggle,
  onMiddlewareToggle,
  isEditMode,
  agentId,
  systemPromptError,
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
  const [isGeneratorConfigOpen, setGeneratorConfigOpen] = useState(false);
  const [isPresentationConfigOpen, setPresentationConfigOpen] = useState(false);

  const subAgents = form.subAgents ?? [];
  const { data: skillList } = useSkills({ scope: 'all', size: 100 });
  // builtin-middleware D10: 카탈로그 조회 — create는 빌트인·강제만, edit은 전 항목 노출
  const { data: middlewareCatalog } = useMiddlewareCatalog();
  const { data: collections } = useCollections();
  const { data: knowledgeBases } = useKnowledgeBases();
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
      else if (toolId === DOCUMENT_GENERATOR_TOOL_ID) setGeneratorConfigOpen(true);
      else if (toolId === PRESENTATION_GENERATOR_TOOL_ID) setPresentationConfigOpen(true);
      else setExtractorConfigOpen(true);
    }
  };

  const openConfig = (toolId: string) => {
    if (toolId === RAG_TOOL_ID) setRagConfigOpen(true);
    else if (toolId === DOCUMENT_EXTRACTOR_TOOL_ID) setExtractorConfigOpen(true);
    else if (toolId === DOCUMENT_GENERATOR_TOOL_ID) setGeneratorConfigOpen(true);
    else if (toolId === PRESENTATION_GENERATOR_TOOL_ID) setPresentationConfigOpen(true);
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
  // builtin-tools D8: 빌트인 표시는 카탈로그 is_builtin − excluded 파생값 (create 전용).
  // edit 모드에선 저장된 워커가 form.tools로 매핑되어 일반 칩으로 표시된다.
  const builtinTools = isEditMode
    ? []
    : (catalogTools ?? []).filter(
        (t) => t.is_builtin && !form.excludedBuiltinTools.includes(t.tool_id),
      );
  const currentModel = models?.find((m) => m.model_name === form.model);
  // agent-builder-edit-mapping: 역매핑 실패로 raw id가 남은 경우 미등록 안내
  const modelLabel = currentModel
    ? `${currentModel.provider}:${currentModel.model_name}`
    : form.model
      ? `${form.model} (미등록 모델)`
      : '모델 미선택';

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
        {/* 지침 (시스템 프롬프트) — agent-instruction-required: 필수 입력 */}
        <CollapsibleSection
          title="지침"
          action={<span className="text-[10px] font-semibold text-red-400">필수</span>}
        >
          <div
            className={`overflow-hidden rounded-2xl border bg-white transition-all focus-within:ring-2 ${
              systemPromptError
                ? 'border-red-300 focus-within:border-red-400 focus-within:ring-red-100'
                : 'border-zinc-300 focus-within:border-violet-400 focus-within:ring-violet-100'
            }`}
          >
            <textarea
              value={form.systemPrompt}
              onChange={(e) => onChange({ ...form, systemPrompt: e.target.value })}
              placeholder="에이전트의 시스템 프롬프트/지침을 입력하세요..."
              rows={6}
              aria-label="지침"
              aria-invalid={systemPromptError ? true : undefined}
              className="block w-full resize-none bg-transparent px-4 py-3.5 text-[14px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none"
            />
          </div>
          {systemPromptError ? (
            <p role="alert" className="mt-1 text-[11.5px] text-red-500">{systemPromptError}</p>
          ) : (
            <p className="mt-1 text-right text-[11.5px] text-zinc-400">{form.systemPrompt.length}자</p>
          )}
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
          {/* agent-builder-edit-mapping FR-6 유예 방어: 도구 워커 교체는 후속 feature */}
          {isEditMode && (
            <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-[11.5px] text-amber-700">
              도구 구성 변경은 아직 저장되지 않습니다 (모델·지침·서브에이전트·스킬은 저장됨)
            </p>
          )}
          {builtinTools.length > 0 && (
            <ul className="mb-2 space-y-2">
              {builtinTools.map((tool) => (
                <li
                  key={tool.tool_id}
                  className="rounded-xl border border-violet-200 bg-violet-50/50 px-4 py-2.5"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-zinc-700">{tool.name}</span>
                    <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-600">기본</span>
                    {tool.source === 'mcp' && (
                      <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold text-sky-600">MCP</span>
                    )}
                    <button
                      type="button"
                      onClick={() => onBuiltinToggle(tool.tool_id)}
                      aria-label={`${tool.name} 제거`}
                      className="ml-auto rounded-lg px-2 py-1 text-[12px] font-medium text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
                    >
                      제거
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
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
                      <RagConfigSummaryBadge
                        config={ragConfig}
                        collections={collections}
                        knowledgeBases={knowledgeBases}
                      />
                    )}
                    {tool.tool_id === DOCUMENT_EXTRACTOR_TOOL_ID && (
                      <ExtractorSummaryBadge draft={form.documentExtractorDraft ?? null} />
                    )}
                    {tool.tool_id === DOCUMENT_GENERATOR_TOOL_ID && (
                      <GeneratorSummaryBadge draft={form.documentGeneratorDraft ?? null} />
                    )}
                    {tool.tool_id === PRESENTATION_GENERATOR_TOOL_ID && (
                      <PresentationSummaryBadge draft={form.presentationGeneratorDraft ?? null} />
                    )}
                  </li>
                );
              })}
            </ul>
          ) : builtinTools.length === 0 ? (
            <p className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-4 text-center text-[12.5px] text-zinc-400">
              추가된 도구가 없습니다
            </p>
          ) : null}
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

        {/* 미들웨어 (builtin-middleware D10) */}
        <CollapsibleSection title="미들웨어">
          <MiddlewareSection
            catalog={middlewareCatalog}
            isEditMode={isEditMode}
            middlewares={form.middlewares}
            excludedBuiltinMiddlewares={form.excludedBuiltinMiddlewares}
            onToggle={onMiddlewareToggle}
          />
        </CollapsibleSection>

        {/* approval-gate Check G3 / FR-22: 승인 게이트 — 에이전트가 저장된 뒤에만
            설정할 수 있다(설정 API 가 agent_id 를 요구). 생성 모드에선 안내만. */}
        <CollapsibleSection title="승인 게이트">
          {agentId ? (
            <ApprovalGateSettingsPanel agentId={agentId} />
          ) : (
            <p className="text-[12.5px] text-zinc-400">
              에이전트를 저장한 뒤 승인 게이트를 설정할 수 있습니다.
            </p>
          )}
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
        // builtin-tools D8: edit 모드는 미전달 → 빌트인도 일반 도구로 취급
        excludedBuiltinIds={isEditMode ? undefined : form.excludedBuiltinTools}
        onToggleBuiltin={isEditMode ? undefined : onBuiltinToggle}
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
      <DocumentGeneratorConfigModal
        isOpen={isGeneratorConfigOpen}
        draft={form.documentGeneratorDraft ?? null}
        onChange={(draft) => onChange({ ...form, documentGeneratorDraft: draft })}
        onClose={() => setGeneratorConfigOpen(false)}
      />
      <PresentationGeneratorConfigModal
        isOpen={isPresentationConfigOpen}
        draft={form.presentationGeneratorDraft ?? null}
        onChange={(draft) => onChange({ ...form, presentationGeneratorDraft: draft })}
        onClose={() => setPresentationConfigOpen(false)}
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

// ── 미들웨어 섹션 (builtin-middleware D10) ─────────────────

interface MiddlewareSectionProps {
  catalog?: MiddlewareCatalogItem[];
  isEditMode: boolean;
  /** edit 전용: 적용 중 타입 (detail 프리필, 전체 교체 전송 기준선) */
  middlewares: string[];
  /** create 전용: 수동 해제된 빌트인 타입 */
  excludedBuiltinMiddlewares: string[];
  onToggle: (middlewareType: string) => void;
}

/** default_config를 "key value" 요약으로 표기 (읽기 전용 — 관리자만 편집). */
const formatMiddlewareConfig = (config: Record<string, unknown>): string =>
  Object.entries(config)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') || '(없음)' : String(v)}`)
    .join(' · ');

// 테스트용 named export
export const MiddlewareSection = ({
  catalog,
  isEditMode,
  middlewares,
  excludedBuiltinMiddlewares,
  onToggle,
}: MiddlewareSectionProps) => {
  // approval-gate Check G3: approval_gate 는 전용 패널이 관리한다. 여기서도
  // 토글하게 두면 에이전트 저장과 전용 API 가 같은 행을 두고 다툰다.
  const active = (catalog ?? []).filter(
    (m) =>
      m.is_active &&
      !SEPARATELY_MANAGED_MIDDLEWARE_TYPES.includes(m.middleware_type),
  );
  // create: 빌트인·강제만 노출 (비빌트인 선택은 수정 폼에서 — Design §12.2)
  const visible = isEditMode
    ? active
    : active.filter((m) => m.is_builtin || m.is_enforced);

  if (visible.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-4 text-center text-[12.5px] text-zinc-400">
        적용 가능한 미들웨어가 없습니다
      </p>
    );
  }

  const isChecked = (m: MiddlewareCatalogItem): boolean => {
    if (m.is_enforced) return true; // 강제 — 항상 적용 (해제 불가)
    if (isEditMode) return middlewares.includes(m.middleware_type);
    return m.is_builtin && !excludedBuiltinMiddlewares.includes(m.middleware_type);
  };

  return (
    <ul className="space-y-2">
      {visible.map((m) => {
        const checked = isChecked(m);
        return (
          <li
            key={m.middleware_type}
            className={`rounded-xl border px-4 py-2.5 ${
              checked ? 'border-violet-200 bg-violet-50/50' : 'border-zinc-200 bg-white'
            }`}
          >
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={checked}
                disabled={m.is_enforced}
                // enforced 가드 이중화 — jsdom은 disabled에도 이벤트를 전달한다
                onChange={() => {
                  if (!m.is_enforced) onToggle(m.middleware_type);
                }}
                aria-label={`${m.name} ${checked ? '해제' : '적용'}`}
                title={
                  m.is_enforced
                    ? '관리자가 항상 적용으로 설정한 항목입니다'
                    : undefined
                }
                className="h-4 w-4 accent-violet-600 disabled:cursor-not-allowed"
              />
              <span className="text-[13px] font-medium text-zinc-700">{m.name}</span>
              {m.is_builtin && !m.is_enforced && (
                <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-600">
                  기본
                </span>
              )}
              {m.is_enforced && (
                <span
                  title="관리자가 항상 적용으로 설정한 항목입니다"
                  className="rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-600"
                >
                  🔒 항상 적용
                </span>
              )}
            </div>
            <p className="mt-1 text-[11.5px] text-zinc-400">{m.description}</p>
            {Object.keys(m.default_config).length > 0 && (
              <p className="mt-0.5 text-[11px] text-zinc-400">
                설정: {formatMiddlewareConfig(m.default_config)}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
};

// ── 설정 요약 배지 (tool-config-modal Design §2.4) ─────────

interface RagConfigSummaryBadgeProps {
  config: RagToolConfig;
  collections?: CollectionInfo[];
  knowledgeBases?: KnowledgeBaseInfo[];
}

// 테스트용 named export (kb-rag-filter FE-3)
export const RagConfigSummaryBadge = ({
  config,
  collections,
  knowledgeBases,
}: RagConfigSummaryBadgeProps) => {
  // kb-rag-filter: KB 선택 시 KB 이름이 최우선 라벨
  const kbLabel = config.kb_id
    ? knowledgeBases?.find((kb) => kb.kb_id === config.kb_id)?.name ?? config.kb_id
    : null;
  const collectionLabel =
    kbLabel ??
    (config.collection_name
      ? collections?.find((c) => c.name === config.collection_name)?.display_name ??
        config.collection_name
      : '전체');
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

// ── 문서생성기 요약 배지 (doc-generator §5-2) ─────────────────

interface GeneratorSummaryBadgeProps {
  draft: DocumentGeneratorDraft | null;
}

const GeneratorSummaryBadge = ({ draft }: GeneratorSummaryBadgeProps) => {
  if (!draft || draft.sections.length === 0) {
    return (
      <p className="mt-1.5 inline-block rounded bg-amber-50 px-1.5 py-0.5 text-[11.5px] font-medium text-amber-600">
        ⚠ 문서 유형 미등록
      </p>
    );
  }
  return (
    <p className="mt-1.5 inline-block rounded bg-emerald-50 px-1.5 py-0.5 text-[11.5px] font-medium text-emerald-700">
      ✓ {draft.name || '문서 유형'} · 섹션 {draft.sections.length} ·{' '}
      {draft.outputFormat.toUpperCase()}
    </p>
  );
};

// ── 발표자료생성기 요약 배지 (golden-sample-blueprint §5.4) ─────────────

interface PresentationSummaryBadgeProps {
  draft: PresentationGeneratorDraft | null;
}

const PresentationSummaryBadge = ({ draft }: PresentationSummaryBadgeProps) => {
  if (!draft || !draft.blueprintId) {
    return (
      <p className="mt-1.5 inline-block rounded bg-amber-50 px-1.5 py-0.5 text-[11.5px] font-medium text-amber-600">
        ⚠ 양식 미선택
      </p>
    );
  }
  return (
    <p className="mt-1.5 inline-block rounded bg-emerald-50 px-1.5 py-0.5 text-[11.5px] font-medium text-emerald-700">
      ✓ 양식 선택됨 · 최대 {draft.maxSlides}장 · {draft.outputFormat.toUpperCase()}
    </p>
  );
};

export default LeftConfigPanel;
