import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAgentDraftStore } from '@/store/agentDraftStore';
import type { AgentCreateIntent } from '@/store/agentDraftStore';
import {
  PIPELINE_ERROR,
  useAgentPipelineStream,
} from '@/hooks/useAgentPipelineStream';
import { useToolCatalog } from '@/hooks/useToolCatalog';
import {
  MAX_CLARIFY_ROUNDS,
  MAX_PIPELINE_USER_REQUEST_CHARS,
  PIPELINE_STOP,
} from '@/types/agentPipeline';
import type {
  AgentPipelineRequest,
  AgentPipelineResponse,
  PipelineAnswer,
  PipelineDocumentRequest,
  PipelineIntentEcho,
  PipelineQuestion,
} from '@/types/agentPipeline';
import type { DocumentExtractorDraft } from '@/types/documentExtractor';
import { buildDocumentTemplateRequest } from '@/utils/documentTemplate';
import EntryHero from './components/EntryHero';
import DescriptionComposer from './components/DescriptionComposer';
import EntryActionCards from './components/EntryActionCards';
import WizardShell from './components/WizardShell';
import WizardProgress from './components/WizardProgress';
import IntentStep from './components/IntentStep';
import ToolsStep from './components/ToolsStep';
import PromptStep from './components/PromptStep';
import DocumentsStep from './components/DocumentsStep';
import { RAG_CATALOG_TOOL_ID } from '@/utils/agentDetailMapping';
import WizardFailureCard from './components/WizardFailureCard';
import PipelineUnavailableCard from './components/PipelineUnavailableCard';

// agent-kb-quick-setup FR-11: 'documents' 는 서버 호출이 없는 클라이언트 로컬 단계다.
type WizardStep = 'description' | 'intent' | 'tools' | 'documents' | 'prompt';

/**
 * 질문 라운드 이력 (wizard-chat-layout FR-07).
 * 교체가 아니라 누적 — 지난 라운드 카드가 잠긴 채 트랜스크립트에 남는다.
 */
interface WizardRound {
  round: number;
  questions: PipelineQuestion[];
  answered: boolean;
}

interface WizardState {
  userRequest: string;
  round: number;
  rounds: WizardRound[];
  answers: PipelineAnswer[];
  intentEcho: PipelineIntentEcho | null;
  recommendedIds: string[];
  selectedIds: string[];
  unknownIds: string[];
  prompt: string;
  promptOriginal: string;
  promptClampReason: string | null;
  promptDegraded: boolean;
  sessionId: string | null;
  versionId: string | null;
  suggestedName: string;
  /** agent-kb-quick-setup FR-11: 문서 단계에서 연결한 KB */
  kbId: string | null;
  // wizard-template-request §3.1 — 양식 요청 카드 상태 4필드.
  /** 마지막 tools_proposed/prompt_ready 응답의 문서 요청 목록 (D1) */
  documentRequests: PipelineDocumentRequest[];
  /** 추출 결과 + 확정 상태. 스튜디오 드래프트와 같은 형태 (D2) */
  templateDraft: DocumentExtractorDraft | null;
  templateSkipped: boolean;
  templateBusy: boolean;
}

const EMPTY: WizardState = {
  userRequest: '',
  round: 0,
  rounds: [],
  answers: [],
  intentEcho: null,
  recommendedIds: [],
  selectedIds: [],
  unknownIds: [],
  prompt: '',
  promptOriginal: '',
  promptClampReason: null,
  promptDegraded: false,
  sessionId: null,
  versionId: null,
  suggestedName: '',
  kbId: null,
  documentRequests: [],
  templateDraft: null,
  templateSkipped: false,
  templateBusy: false,
};

/**
 * 응답의 document_requests 를 상태에 반영한다 (D1 / FR-03).
 * 요청이 사라지면(사용자가 추출기를 뺀 경우) 보관 템플릿도 버린다 —
 * 남겨두면 서버가 422 로 거절한다 (FR-05).
 */
const syncDocumentRequests = (
  sent: WizardState,
  result: AgentPipelineResponse,
): Pick<WizardState, 'documentRequests' | 'templateDraft' | 'templateSkipped'> => {
  const documentRequests = result.document_requests ?? [];
  if (documentRequests.length > 0) {
    return {
      documentRequests,
      templateDraft: sent.templateDraft,
      templateSkipped: sent.templateSkipped,
    };
  }
  return { documentRequests, templateDraft: null, templateSkipped: false };
};

/**
 * 에이전트 생성 위저드 (/agent-builder/new).
 *
 * Design Ref: wizard-chat-layout §5 — 채팅 트랜스크립트형 2-모드 레이아웃.
 * centered(첫 화면 세로 중앙) ↔ chat(하단 고정 입력창 + 카드 누적).
 * 파이프라인 전이 로직은 agent-create-wizard §5.2 원형을 유지하고,
 * **저장은 하지 않는다**: DB 반영은 스튜디오 [저장]에서만 (무저장 계약).
 *
 * 진행 상태를 영속하지 않는다 (agent-create-wizard Design A-6, 핸드오프 G1) —
 * 새로고침 시 유실은 버그가 아니라 정의된 동작이다.
 */
const AgentCreateEntryPage = () => {
  const navigate = useNavigate();
  const pipeline = useAgentPipelineStream();
  const { data: catalogTools } = useToolCatalog();

  const [step, setStep] = useState<WizardStep>('description');
  const [input, setInput] = useState('');
  const [state, setState] = useState<WizardState>(EMPTY);

  /**
   * 모드 파생 (wizard-chat-layout Design §3.2) — 전송 순간 userRequest 를 즉시
   * 커밋하므로 첫 응답 전에도 chat 으로 전환되고, 첫 요청이 실패해도 centered 로
   * 튕기지 않아 요청 버블 + 실패 카드가 함께 보인다.
   */
  const mode: 'centered' | 'chat' =
    state.userRequest !== '' ? 'chat' : 'centered';

  // 스튜디오에서 뒤로가기로 되돌아온 경우 이전 의도가 남아 있을 수 있다.
  // 진입 시점에 비워야 [직접 만들기]가 유령 초안을 끌고 가지 않는다 (G3).
  useEffect(() => {
    useAgentDraftStore.getState().clearPendingIntent();
  }, []);

  // 진행 중 이탈 경고 (FR-F16 / wizard-chat-layout FR-11).
  // centered 는 잃을 게 없어 제외한다.
  useEffect(() => {
    if (mode === 'centered') return undefined;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [mode]);

  const goStudio = (intent: AgentCreateIntent) => {
    useAgentDraftStore.getState().setPendingIntent(intent);
    navigate('/agent-builder');
  };

  /** 응답 status → 다음 단계 전이 (agent-create-wizard Design §5.2). */
  const applyResult = (result: AgentPipelineResponse, sent: WizardState) => {
    if (result.status === 'need_input') {
      setState({
        ...sent,
        round: result.round,
        // FR-07 — 라운드는 교체가 아니라 push. 지난 카드가 이력으로 남는다.
        rounds: [
          ...sent.rounds,
          { round: result.round, questions: result.questions, answered: false },
        ],
        intentEcho: result.intent
          ? {
              label: result.intent.label,
              filled_slots: result.intent.filled_slots,
              degraded: result.intent.degraded,
            }
          : null,
      });
      setStep('intent');
      return;
    }

    if (result.status === 'tools_proposed') {
      setState({
        ...sent,
        round: result.round,
        // 답변 없이 도구가 바로 오면(라운드 상한 등) 남은 활성 카드를 잠근다.
        rounds: sent.rounds.map((r) => ({ ...r, answered: true })),
        intentEcho: result.intent
          ? {
              label: result.intent.label,
              filled_slots: result.intent.filled_slots,
              degraded: result.intent.degraded,
            }
          : sent.intentEcho,
        recommendedIds: result.recommended_tool_ids,
        // 추천은 기본 전부 선택 — 사용자는 빼는 쪽으로만 개입하면 된다.
        selectedIds: result.final_tool_ids,
        unknownIds: result.unknown_tool_ids,
        suggestedName: result.suggested_name ?? sent.suggestedName,
        ...syncDocumentRequests(sent, result),
      });
      setStep('tools');
      return;
    }

    if (result.status === 'prompt_ready') {
      const prompt = result.assembled_prompt ?? '';
      setState({
        ...sent,
        prompt,
        promptOriginal: prompt,
        promptClampReason: result.prompt_clamp_reason,
        promptDegraded: result.degraded_stages.includes('prompt'),
        sessionId: result.session_id,
        versionId: result.version_id,
        unknownIds: result.unknown_tool_ids,
        suggestedName: result.suggested_name ?? sent.suggestedName,
        ...syncDocumentRequests(sent, result),
      });
      setStep('prompt');
    }
  };

  // pipeline.result 가 채워지면 단계를 전이한다. 훅이 통신 상태를 소유하고
  // 화면은 전이만 담당하도록 분리했다. `pendingState` 는 "이 응답이 어떤
  // 요청에 대한 것인지"의 스냅샷이다 — 응답이 늦게 와도 그때의 입력으로 병합한다.
  const [pendingState, setPendingState] = useState<WizardState | null>(null);
  useEffect(() => {
    if (!pipeline.result || !pendingState) return;
    applyResult(pipeline.result, pendingState);
    setPendingState(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipeline.result]);

  const dispatch = (body: AgentPipelineRequest, next: WizardState) => {
    setPendingState(next);
    void pipeline.send(body);
  };

  // ── 단계별 액션 ─────────────────────────────────────────────────────

  /** 요청 전송 공통부 — userRequest 를 즉시 커밋해 chat 모드로 전환한다 (§3.2). */
  const sendDescription = (text: string) => {
    const next = { ...EMPTY, userRequest: text };
    setState(next);
    dispatch({ user_request: text, stop_after: PIPELINE_STOP.TOOLS }, next);
  };

  const handleSubmitDescription = () => {
    const text = input.trim().slice(0, MAX_PIPELINE_USER_REQUEST_CHARS);
    if (!text || pipeline.isPending) return;
    // 요청 버블이 원문을 보여주므로 입력창은 비운다 — chat 모드 하단 입력창은
    // 재전송 창구가 아니다 (FR-08).
    setInput('');
    sendDescription(text);
  };

  /** 첫 요청 실패 후 재시도 — 입력창은 비워졌으므로 커밋된 요청으로 다시 보낸다. */
  const handleResendDescription = () => {
    if (!state.userRequest || pipeline.isPending) return;
    sendDescription(state.userRequest);
  };

  const handleAnswers = (answers: PipelineAnswer[]) => {
    if (pipeline.isPending) return;
    // 이전 라운드 답변을 누적해 에코백한다 — 서버는 무상태다.
    const merged = [
      ...state.answers.filter(
        (prev) => !answers.some((a) => a.slot_key === prev.slot_key),
      ),
      ...answers,
    ];
    const next = {
      ...state,
      answers: merged,
      // 활성(마지막) 라운드를 잠근다 — 스테일 카드 가드 (F10).
      rounds: state.rounds.map((r, i) =>
        i === state.rounds.length - 1 ? { ...r, answered: true } : r,
      ),
    };
    setState(next);
    dispatch(
      {
        user_request: state.userRequest,
        answers: merged,
        round: state.round,
        stop_after: PIPELINE_STOP.TOOLS,
      },
      next,
    );
  };

  /** 건너뛰기 — 답변 없이 그대로 재호출한다(서버가 의도 없이 진행). */
  const handleSkipQuestions = () => handleAnswers([]);

  const handleToggleTool = (toolId: string) => {
    setState((prev) => ({
      ...prev,
      selectedIds: prev.selectedIds.includes(toolId)
        ? prev.selectedIds.filter((id) => id !== toolId)
        : [...prev.selectedIds, toolId],
    }));
  };

  // agent-kb-quick-setup FR-11: 도구 확정은 서버 호출 없이 문서 단계로 넘어간다.
  const handleConfirmTools = () => {
    if (pipeline.isPending) return;
    setStep('documents');
  };

  /** 문서 단계 [건너뛰기]/[계속] — 기존 PROMPT 요청에 kb_id 만 더 싣는다. */
  const requestPrompt = (
    sessionId: string | null = null,
    snapshot: WizardState = state,
  ) => {
    if (pipeline.isPending) return;
    const template = buildDocumentTemplateRequest(
      snapshot.templateDraft,
      snapshot.suggestedName || '양식',
    );
    dispatch(
      {
        user_request: snapshot.userRequest,
        answers: snapshot.answers,
        round: snapshot.round,
        tool_ids: snapshot.selectedIds,
        // D1 — 확정 목록이므로 셀렉터를 다시 돌리지 않는다.
        tools_confirmed: true,
        // D2 — 의도를 재사용해 단계 간 근거가 갈리지 않게 한다.
        intent: snapshot.intentEcho,
        ...(sessionId ? { session_id: sessionId } : {}),
        ...(snapshot.kbId ? { kb_id: snapshot.kbId } : {}),
        // wizard-template-request FR-08: 확정 템플릿만 동봉 (미확정이면 undefined)
        ...(template ? { document_template: template } : {}),
        stop_after: PIPELINE_STOP.PROMPT,
      },
      snapshot,
    );
  };

  /** 건너뛰기 — 미확정 양식은 버리고 이력에 "건너뜀"으로 남긴다 (FR-10/11). */
  const handleSkipDocuments = () => {
    if (pipeline.isPending || state.templateBusy) return;
    const skippedTemplate = !state.templateDraft?.confirmed;
    const next: WizardState = skippedTemplate
      ? { ...state, templateDraft: null, templateSkipped: true }
      : state;
    setState(next);
    requestPrompt(null, next);
  };
  const handleContinueFromDocuments = () => requestPrompt();

  const handleTemplateDraftChange = (draft: DocumentExtractorDraft | null) =>
    setState((prev) => ({ ...prev, templateDraft: draft, templateSkipped: false }));
  const handleTemplateBusyChange = (busy: boolean) =>
    setState((prev) => ({ ...prev, templateBusy: busy }));

  /** 업로드/기존 KB 선택 — 문서 검색 도구를 확정 목록에 더한다 (FR-07 과 대칭). */
  const handleKbAttached = (kbId: string) => {
    setState((prev) => ({
      ...prev,
      kbId,
      selectedIds: prev.selectedIds.includes(RAG_CATALOG_TOOL_ID)
        ? prev.selectedIds
        : [...prev.selectedIds, RAG_CATALOG_TOOL_ID],
    }));
  };
  const handleKbDetached = () => {
    setState((prev) => ({
      ...prev,
      kbId: null,
      selectedIds: prev.selectedIds.filter((id) => id !== RAG_CATALOG_TOOL_ID),
    }));
  };

  // 같은 세션에 새 버전으로 쌓는다 — 세션이 늘어나지 않게.
  const handleRegeneratePrompt = () => requestPrompt(state.sessionId);

  const handleSendToStudio = () => {
    goStudio({
      kind: 'wizard',
      result: {
        systemPrompt: state.prompt,
        promptEdited: state.prompt !== state.promptOriginal,
        toolIds: state.selectedIds,
        suggestedName: state.suggestedName,
        sessionId: state.sessionId,
        versionId: state.versionId,
        // agent-kb-quick-setup FR-13: 스튜디오가 RAG 도구 + kb_id 로 프리필한다
        kbId: state.kbId,
        // wizard-template-request FR-12: 확정 템플릿을 추출기 드래프트로 넘긴다 (D2)
        documentExtractorDraft: state.templateDraft?.confirmed
          ? state.templateDraft
          : null,
      },
    });
  };

  const handleRetry = () => {
    pipeline.clearError();
    if (step === 'tools') handleConfirmTools();
    else if (step === 'documents') requestPrompt();
    else if (step === 'prompt') handleRegeneratePrompt();
    else if (step === 'intent') handleSkipQuestions();
    else handleResendDescription();
  };

  const handleRestart = () => {
    pipeline.clearError();
    setState(EMPTY);
    setInput('');
    setStep('description');
  };

  /** ③ [처음부터] — 되돌리기가 아니라 전체 초기화다(무상태 위저드). */
  const handleRestartWithConfirm = () => {
    if (!window.confirm('입력한 내용이 사라집니다. 그래도 진행할까요?')) return;
    handleRestart();
  };

  // ── 렌더 ────────────────────────────────────────────────────────────

  const toolNames = state.selectedIds.map(
    (id) => catalogTools?.find((t) => t.tool_id === id)?.name ?? id,
  );

  // 첫 전송 전에는 진행바를 감춘다 — 전부 '대기중'인 5단계는 정보가 아니라
  // 잡음이고, 첫 화면은 "한 문장 쓰세요"에 집중시키는 편이 낫다.
  const showProgress = pipeline.isPending || pipeline.steps.length > 0;

  /** 킬스위치 off — 위저드 자체가 불가능하므로 본문을 안내로 대체한다. */
  const unavailable = pipeline.error?.kind === PIPELINE_ERROR.DISABLED;

  if (unavailable) {
    return (
      <WizardShell mode="centered">
        <EntryHero />
        <PipelineUnavailableCard
          onManualCreate={() => goStudio({ kind: 'blank' })}
        />
      </WizardShell>
    );
  }

  // 첫 화면 (FR-01/02) — 헤더바 없이 히어로 + 중앙 입력창 + 액션 카드.
  if (mode === 'centered') {
    return (
      <WizardShell mode="centered">
        <EntryHero />
        <DescriptionComposer
          value={input}
          onChange={setInput}
          onSubmit={handleSubmitDescription}
          isPending={pipeline.isPending}
        />
        <EntryActionCards onManualCreate={() => goStudio({ kind: 'blank' })} />
      </WizardShell>
    );
  }

  // chat 모드 (FR-03~10) — 트랜스크립트 누적 + 하단 고정 입력창.
  return (
    <WizardShell
      mode="chat"
      scrollKey={[
        step,
        state.rounds.length,
        pipeline.steps.length,
        pipeline.error ? 'err' : '',
        pipeline.isPending ? 'p' : '',
      ].join(':')}
      composer={
        <DescriptionComposer
          variant="chat"
          value={input}
          onChange={setInput}
          onSubmit={handleSubmitDescription}
          isPending={pipeline.isPending}
        />
      }
    >
      {/* 요청 버블 (FR-05) — 유저 메시지 스타일, 우측 정렬 */}
      <div className="flex justify-end">
        <div
          className="max-w-[85%] rounded-2xl rounded-br-sm px-5 py-3.5 text-[15px] leading-[1.65] text-white"
          style={{
            background: 'linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%)',
          }}
        >
          <p className="whitespace-pre-wrap">{state.userRequest}</p>
        </div>
      </div>

      {showProgress && (
        <div className="space-y-3">
          <WizardProgress
            steps={pipeline.steps}
            activeStage={pipeline.activeStage}
          />
          <p className="px-1 text-[11.5px] leading-relaxed text-zinc-400">
            마지막 두 단계는 스튜디오에서 [저장]을 누르면 완료됩니다.
          </p>
        </div>
      )}

      {/* 질문 라운드 이력 (FR-07) — 지난 라운드는 잠긴 채 남는다 */}
      {state.rounds.map((r, i) => {
        const isActive = i === state.rounds.length - 1 && !r.answered;
        return (
          <IntentStep
            key={`intent-round-${r.round}`}
            questions={r.questions}
            round={r.round}
            maxRounds={MAX_CLARIFY_ROUNDS}
            isPending={pipeline.isPending}
            answered={!isActive}
            onSubmit={handleAnswers}
            onSkip={handleSkipQuestions}
          />
        );
      })}

      {/* 도구 카드 — 프롬프트 단계에선 잠긴 이력으로 남는다 (FR-09) */}
      {(step === 'tools' || step === 'documents' || step === 'prompt') && (
        <ToolsStep
          recommendedIds={state.recommendedIds}
          selectedIds={state.selectedIds}
          unknownIds={state.unknownIds}
          isPending={pipeline.isPending}
          locked={step !== 'tools'}
          onToggle={handleToggleTool}
          onConfirm={handleConfirmTools}
          onRestart={handleRestartWithConfirm}
        />
      )}

      {/* 문서 단계 (agent-kb-quick-setup FR-11) — 프롬프트 단계에선 잠긴 이력으로 남는다 */}
      {(step === 'documents' || step === 'prompt') && (
        <DocumentsStep
          agentName={state.suggestedName}
          attachedKbId={state.kbId}
          isPending={pipeline.isPending}
          locked={step === 'prompt'}
          onAttached={handleKbAttached}
          onDetach={handleKbDetached}
          onSkip={handleSkipDocuments}
          onContinue={handleContinueFromDocuments}
          // wizard-template-request §5.1 — 서버 요청이 있을 때만 양식 카드가 뜬다
          documentRequests={state.documentRequests}
          templateDraft={state.templateDraft}
          templateSkipped={state.templateSkipped}
          templateBusy={state.templateBusy}
          onTemplateDraftChange={handleTemplateDraftChange}
          onTemplateBusyChange={handleTemplateBusyChange}
        />
      )}

      {step === 'prompt' && (
        <PromptStep
          value={state.prompt}
          clampReason={state.promptClampReason}
          degraded={state.promptDegraded}
          toolNames={toolNames}
          isPending={pipeline.isPending}
          onChange={(next) => setState((prev) => ({ ...prev, prompt: next }))}
          onRegenerate={handleRegeneratePrompt}
          onSubmit={handleSendToStudio}
          // [이전]은 도구 단계로 — 도구 카드 잠금이 풀리고(FR-09) 문서 단계는 재확정 후 다시 보인다 (kbId 유지)
          onBack={() => setStep('tools')}
        />
      )}

      {pipeline.error && (
        <WizardFailureCard
          error={pipeline.error}
          onRetry={handleRetry}
          onManualCreate={() => goStudio({ kind: 'blank' })}
        />
      )}
    </WizardShell>
  );
};

export default AgentCreateEntryPage;
