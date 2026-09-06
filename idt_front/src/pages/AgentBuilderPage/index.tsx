import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { MAX_ITERATIONS } from '@/constants/agentSettings';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import { DOCUMENT_GENERATOR_TOOL_ID } from '@/types/documentGenerator';
import { PRESENTATION_GENERATOR_TOOL_ID } from '@/types/presentationGenerator';
import { buildPresentationGeneratorRequest } from '@/utils/presentationGenerator';
import { buildToolIdsForSave } from '@/utils/agentToolPayload';
import { buildDocumentTemplateRequest } from '@/utils/documentTemplate';
import { buildDocumentGenerationTypeRequest } from '@/utils/documentGenerator';
import { composeDraftToForm } from '@/utils/composeDraftToForm';
import { wizardResultToForm } from '@/utils/wizardResultToForm';
import { agentPipelineService } from '@/services/agentPipelineService';
import { useAgentDraftStore } from '@/store/agentDraftStore';
import type {
  AgentCreateIntent,
  WizardResult,
} from '@/store/agentDraftStore';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import { mapDetailToForm, RAG_CATALOG_TOOL_ID } from '@/utils/agentDetailMapping';

type ViewMode = 'list' | 'create' | 'edit';

/**
 * 위저드 결과를 프롬프트 세션에 반영한다 — 저장 **성공 후** 부수 작업.
 *
 * Design Ref: agent-create-wizard §2.2 / FR-F13.
 *
 * 두 호출 모두 실패를 흡수한다: 이미 `agent_id` 라는 쓸 수 있는 결과가
 * 존재하므로 백필 실패가 생성 성공을 뒤집으면 안 된다
 * (degradation-vs-failure-boundary 위키의 판정 기준과 동일).
 *
 * @returns 사용자에게 알릴 경고 문구. 문제 없으면 빈 문자열.
 */
const linkPromptSession = async (
  wizard: WizardResult,
  agentId: string,
): Promise<string> => {
  if (!wizard.sessionId) return '';

  const failures: string[] = [];
  // 편집본만 새 버전으로 쌓는다 — 안 고쳤으면 LLM 원본이 이미 최신 버전이다.
  if (wizard.promptEdited) {
    try {
      await agentPipelineService.appendPromptVersion(wizard.sessionId, {
        assembled: wizard.systemPrompt,
        tool_ids: wizard.toolIds,
      });
    } catch {
      failures.push('수정한 프롬프트의 이력 저장');
    }
  }
  try {
    await agentPipelineService.bindPromptSession(wizard.sessionId, agentId);
  } catch {
    failures.push('프롬프트 이력 연결');
  }

  return failures.length === 0
    ? ''
    : ` 다만 ${failures.join('과 ')}에 실패했습니다. 에이전트 자체는 정상 저장되었습니다.`;
};

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

const RAG_TOOL_ID = RAG_CATALOG_TOOL_ID;

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
  excludedBuiltinTools: [],
  excludedBuiltinMiddlewares: [],
  middlewares: [],
  maxIterations: MAX_ITERATIONS.DEFAULT,
};

/** 핸드오프 의도 → 초기 폼. 종류별 변환은 각각의 순수 함수가 담당한다. */
const prefillFromIntent = (
  intent: AgentCreateIntent,
  deps: { catalogTools?: CatalogTool[]; models?: LlmModel[] },
): AgentBuilderFormData => {
  if (intent.kind === 'draft') {
    return composeDraftToForm(intent.draft, DEFAULT_FORM, deps);
  }
  if (intent.kind === 'wizard') {
    return wizardResultToForm(intent.result, DEFAULT_FORM, deps);
  }
  return DEFAULT_FORM;
};

const AgentBuilderPage = () => {
  const navigate = useNavigate();
  const [view, setView] = useState<ViewMode>('list');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<AgentBuilderFormData>(DEFAULT_FORM);
  const [deleteTarget, setDeleteTarget] = useState<StoreAgentSummary | null>(null);
  const [saveResult, setSaveResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  // agent-instruction-required: 지침 미입력 시 저장 차단 + 인라인 에러
  const [promptError, setPromptError] = useState<string | null>(null);
  // agent-create-entry FR-11: 진입 화면(/agent-builder/new) 경유로 들어왔는지.
  // [취소] 복귀 지점을 목록 대신 진입 화면으로 되돌리는 데만 쓴다.
  const [fromEntry, setFromEntry] = useState(false);

  const { data: agentsData, isLoading: isAgentsLoading, isError: isAgentsError, refetch: refetchAgents } = useMyBuilderAgents();
  const { data: editDetail } = useBuilderAgentDetail(editingId && view === 'edit' ? editingId : null);
  const { data: catalogTools, isLoading: isToolsLoading, isError: isToolsError, refetch: refetchTools } = useToolCatalog();
  const { data: models, isLoading: isModelsLoading, isError: isModelsError, refetch: refetchModels } = useLlmModels();

  const createMutation = useCreateBuilderAgent();
  const updateMutation = useUpdateBuilderAgent();
  const deleteMutation = useDeleteBuilderAgent();
  const createScheduleMutation = useCreateSchedule();

  const agents = agentsData?.agents ?? [];

  // 기본 모델 주입은 create 전용 — edit 프라임(id→model_name 역매핑)과의 경합 차단
  useEffect(() => {
    if (view === 'create' && models && !form.model) {
      const defaultModel = models.find(m => m.is_default);
      if (defaultModel) {
        setForm(prev => ({ ...prev, model: defaultModel.model_name }));
      }
    }
  }, [models, form.model, view]);

  // agent-builder-edit-mapping FR-4: 쿼리 3종 settled 후 1회만 프라임.
  // 에러로 끝난 쿼리는 undefined로 전달 → mapDetailToForm의 raw 유지 폴백 동작.
  // 재시도 성공 후에도 재프라임하지 않음(편집 내용 보호 우선 — Design §2-2).
  const primedAgentRef = useRef<string | null>(null);
  useEffect(() => {
    if (view !== 'edit' || !editingId || !editDetail) return;
    if (isModelsLoading || isToolsLoading) return;
    if (primedAgentRef.current === editingId) return;
    primedAgentRef.current = editingId;
    setForm(mapDetailToForm(editDetail, models, catalogTools));
  }, [editDetail, models, catalogTools, isModelsLoading, isToolsLoading, view, editingId]);

  // agent-create-entry Design §2.4 — 진입 화면이 적재한 의도를 소비해 스튜디오를 연다.
  // G4: mount 후 1회 + ref 가드. selector 구독 없이 getState()로만 접근한다
  //     (구독하면 소비 → 리렌더 → 재소비 루프가 생긴다).
  // G5: catalogTools·models가 settled된 뒤에만 소비한다. 로딩 중 변환하면
  //     도구 매핑·모델 역매핑이 조용히 실패해 빈 칩/원시 id가 남는다.
  const consumedIntentRef = useRef(false);
  /** 위저드에서 넘어온 프롬프트 세션 정보 — 저장 성공 후 1회만 쓰고 비운다. */
  const wizardRef = useRef<WizardResult | null>(null);
  useEffect(() => {
    if (consumedIntentRef.current) return;
    if (isToolsLoading || isModelsLoading) return;
    consumedIntentRef.current = true;

    const intent = useAgentDraftStore.getState().consumePendingIntent();
    if (!intent) return;

    // agent-create-wizard §2.2 — 위저드는 프롬프트 세션을 남기고 온다.
    // 저장 성공 직후 그 세션에 agent_id 를 백필해야 버전 이력이 연결된다.
    // 폼 상태가 아니라 ref 에 두는 이유: 폼 필드가 아니고, 저장 콜백에서만
    // 읽으며, 값이 바뀌어도 리렌더가 필요 없다.
    wizardRef.current = intent.kind === 'wizard' ? intent.result : null;

    /* eslint-disable react-hooks/set-state-in-effect --
       라우트 간 핸드오프 소비는 mount 후 1회만 가능하고, ref 가드로 캐스케이드가 없다 */
    setEditingId(null);
    setPromptError(null);
    primedAgentRef.current = null;
    setFromEntry(true);
    setForm(prefillFromIntent(intent, { catalogTools, models }));
    setView('create');
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [isToolsLoading, isModelsLoading, catalogTools, models]);

  // 폼 변경 시 지침이 채워지면 인라인 에러 해제 (effect 내 setState 지양)
  const handleFormChange = (next: AgentBuilderFormData) => {
    if (promptError && next.systemPrompt.trim()) setPromptError(null);
    setForm(next);
  };

  const handleNew = () => {
    setForm(DEFAULT_FORM);
    setEditingId(null);
    setPromptError(null);
    primedAgentRef.current = null;
    // 목록 헤더/빈 상태 경유 — [취소]는 기존대로 목록으로 (Design §5.4)
    setFromEntry(false);
    setView('create');
  };

  const handleEdit = (agent: StoreAgentSummary) => {
    setEditingId(agent.agent_id);
    setPromptError(null);
    setFromEntry(false);
    // 재진입 시 최신 detail로 재프라임 허용 (react-query가 refetch)
    primedAgentRef.current = null;
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
            // agent-builder-edit-mapping FR-5: 역조회 실패(미등록 모델 유지 상태)
            // 시 undefined 전송 = 모델 변경 안 함
            llm_model_id: models?.find((m) => m.model_name === form.model)?.id,
            // agent-update-tool-editing D §5.1: 목표 상태 전체 교체.
            // 빈 배열도 명시 전송(전부 해제) — 빌트인은 서버가 재주입하므로
            // 상한(MAX_TOOLS) 왜곡을 막기 위해 여기서 걸러낸다.
            tool_ids: buildToolIdsForSave(form.tools, catalogTools),
            tool_configs:
              Object.keys(form.toolConfigs).length > 0
                ? form.toolConfigs
                : undefined,
            sub_agent_configs: form.subAgents.map((s) => ({
              ref_agent_id: s.ref_agent_id,
              description: s.description,
            })),
            // 빈 배열도 명시 전송 → 전체 해제 의미 (undefined=무변경과 구분)
            skill_ids: form.skills,
            // builtin-middleware D10: 프리필 기준 전체 교체 (빈 배열=전부 해제)
            middleware_types: form.middlewares,
            // agent-settings-tab D5: 프라임 값 기반 항상 전송
            max_iterations: form.maxIterations,
            // undefined = 템플릿 변경 안 함, 값 = 교체 (기존 soft-delete)
            document_template: buildDocumentTemplateRequest(
              form.documentExtractorDraft,
              form.name,
            ),
            // doc-generator: undefined = 문서 유형 변경 안 함, 값 = 교체
            document_generation_type: buildDocumentGenerationTypeRequest(
              form.documentGeneratorDraft,
              form.name,
            ),
            // golden-sample-blueprint: undefined = 변경 안 함, 값 = 교체
            presentation_generator: buildPresentationGeneratorRequest(
              form.presentationGeneratorDraft,
            ),
          },
        },
        {
          onSuccess: (response) => {
            // agent-update-tool-editing D §5.1: 도구 변경으로 공개 범위가
            // 좁혀졌으면 사용자가 모르고 지나치지 않도록 함께 알린다.
            const clampNotice = response?.visibility_clamped
              ? ` 지식 범위 제한으로 공개 범위가 '${response.visibility}'로 조정되었습니다.`
              : '';
            setSaveResult({
              type: 'success',
              message: `에이전트가 성공적으로 수정되었습니다.${clampNotice}`,
            });
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
          // builtin-tools D8: 폼에서 수동 해제된 빌트인만 전송 (없으면 생략)
          exclude_builtin_tool_ids:
            form.excludedBuiltinTools.length > 0
              ? form.excludedBuiltinTools
              : undefined,
          // builtin-middleware D10: 폼에서 수동 해제된 빌트인 미들웨어만 전송
          exclude_builtin_middleware_types:
            form.excludedBuiltinMiddlewares.length > 0
              ? form.excludedBuiltinMiddlewares
              : undefined,
          skill_ids: form.skills.length > 0 ? form.skills : undefined,
          document_template: buildDocumentTemplateRequest(
            form.documentExtractorDraft,
            form.name,
          ),
          // doc-generator: 섹션이 정의된 드래프트만 전송 (없으면 미등록)
          document_generation_type: buildDocumentGenerationTypeRequest(
            form.documentGeneratorDraft,
            form.name,
          ),
          presentation_generator: buildPresentationGeneratorRequest(
            form.presentationGeneratorDraft,
          ),
          // agent-settings-tab D5: 설정 탭 반복 한도 (기본 25)
          max_iterations: form.maxIterations,
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

            // agent-create-wizard FR-F13 — 위저드 경유 저장이면 프롬프트 세션에
            // agent_id 를 백필한다. 실패해도 저장은 성공으로 유지한다.
            const wizard = wizardRef.current;
            wizardRef.current = null; // 1회성 — 재저장 시 중복 바인딩(409) 방지
            const wizardSuffix = wizard
              ? await linkPromptSession(wizard, response.agent_id)
              : '';

            setSaveResult({
              type: 'success',
              message: `에이전트가 성공적으로 등록되었습니다.${suffix}${wizardSuffix}`,
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
      // 문서생성기 해제 시 문서 유형 드래프트 정리 (doc-generator)
      if (toolId === DOCUMENT_GENERATOR_TOOL_ID && isRemoving) {
        next.documentGeneratorDraft = null;
      }
      // 발표자료생성기 해제 시 드래프트 정리 (golden-sample-blueprint)
      if (toolId === PRESENTATION_GENERATOR_TOOL_ID && isRemoving) {
        next.presentationGeneratorDraft = null;
      }
      return next;
    });
  };

  // builtin-tools D8: 빌트인 수동 해제/복원 — ToolPickerModal·빌트인 칩에서만 호출.
  // Fix 초안 적용(handleApplyDraft)은 이 상태를 건드리지 않는다(채팅 우회 차단).
  const handleBuiltinToggle = (toolId: string) => {
    setForm((prev) => ({
      ...prev,
      excludedBuiltinTools: prev.excludedBuiltinTools.includes(toolId)
        ? prev.excludedBuiltinTools.filter((t) => t !== toolId)
        : [...prev.excludedBuiltinTools, toolId],
    }));
  };

  // builtin-middleware D10: create=빌트인 opt-out 토글, edit=적용 목록 전체 교체 토글.
  // Fix 초안 적용은 이 상태를 건드리지 않는다 (excludedBuiltinTools 패턴 대칭).
  const handleMiddlewareToggle = (middlewareType: string) => {
    setForm((prev) =>
      view === 'edit'
        ? {
            ...prev,
            middlewares: prev.middlewares.includes(middlewareType)
              ? prev.middlewares.filter((t) => t !== middlewareType)
              : [...prev.middlewares, middlewareType],
          }
        : {
            ...prev,
            excludedBuiltinMiddlewares: prev.excludedBuiltinMiddlewares.includes(
              middlewareType,
            )
              ? prev.excludedBuiltinMiddlewares.filter((t) => t !== middlewareType)
              : [...prev.excludedBuiltinMiddlewares, middlewareType],
          },
    );
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

  // agent-settings-tab D6: SettingsPanel이 clamp 완료한 확정값만 올라온다
  const handleMaxIterationsChange = (value: number) => {
    setForm((prev) => ({ ...prev, maxIterations: value }));
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
  // agent-create-entry Design §3.2: 변환 규칙은 composeDraftToForm에 단일화되어
  // 진입 화면(/agent-builder/new)과 공유된다. 여기는 얇은 래퍼로만 남긴다.
  const handleApplyDraft = (draft: ComposeAgentDraftResponse) => {
    if (draft.system_prompt?.trim()) setPromptError(null);
    setForm((prev) => composeDraftToForm(draft, prev, { catalogTools, models }));
  };

  const handleRagConfigChange = (config: RagToolConfig) => {
    setForm((prev) => ({
      ...prev,
      toolConfigs: { ...prev.toolConfigs, [RAG_TOOL_ID]: config },
    }));
  };

  // agent-create-entry FR-11: 진입 화면 경유면 그 화면으로 되돌리고,
  // 그 외(목록 헤더·빈 상태·편집)는 기존대로 목록 뷰로 복귀한다.
  const handleCancel = () => {
    if (fromEntry) {
      navigate('/agent-builder/new');
      return;
    }
    setView('list');
  };

  const handleSaveResultConfirm = () => {
    if (saveResult?.type === 'success') {
      setFromEntry(false);
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
          onBuiltinToggle={handleBuiltinToggle}
          onMiddlewareToggle={handleMiddlewareToggle}
          onStagedScheduleAdd={handleStagedScheduleAdd}
          onStagedScheduleRemove={handleStagedScheduleRemove}
          onMaxIterationsChange={handleMaxIterationsChange}
          onApplyDraft={handleApplyDraft}
          onSave={handleSave}
          onCancel={handleCancel}
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
              aria-label={`${agent.name} 수정`}
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
              aria-label={`${agent.name} 삭제`}
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
