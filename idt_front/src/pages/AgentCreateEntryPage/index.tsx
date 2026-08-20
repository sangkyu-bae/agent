import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAgentDraftStore } from '@/store/agentDraftStore';
import type { AgentCreateIntent } from '@/store/agentDraftStore';
import {
  PIPELINE_ERROR,
  useAgentPipelineStream,
} from '@/hooks/useAgentPipelineStream';
import { useToolCatalog } from '@/hooks/useToolCatalog';
import { PIPELINE_STOP } from '@/types/agentPipeline';
import type {
  AgentPipelineRequest,
  AgentPipelineResponse,
  PipelineAnswer,
  PipelineIntentEcho,
  PipelineQuestion,
} from '@/types/agentPipeline';
import EntryHero from './components/EntryHero';
import DescriptionComposer, {
  MAX_USER_REQUEST_CHARS,
} from './components/DescriptionComposer';
import EntryActionCards from './components/EntryActionCards';
import WizardProgress from './components/WizardProgress';
import IntentStep from './components/IntentStep';
import ToolsStep from './components/ToolsStep';
import PromptStep from './components/PromptStep';
import WizardFailureCard from './components/WizardFailureCard';
import PipelineUnavailableCard from './components/PipelineUnavailableCard';

/**
 * 서버 `SlotLimits.max_rounds` 와 맞춘 값 (FR-F05).
 * 서버가 라운드 상한에 도달하면 질문을 아예 내려주지 않으므로 화면은 자연히
 * 다음 단계로 넘어간다 — 여기 값은 "남은 라운드" 안내 표기용이다.
 */
const MAX_CLARIFY_ROUNDS = 2;

type WizardStep = 'description' | 'intent' | 'tools' | 'prompt';

interface WizardState {
  userRequest: string;
  round: number;
  questions: PipelineQuestion[];
  answers: PipelineAnswer[];
  answered: boolean;
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
}

const EMPTY: WizardState = {
  userRequest: '',
  round: 0,
  questions: [],
  answers: [],
  answered: false,
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
};

/**
 * 에이전트 생성 위저드 (/agent-builder/new).
 *
 * Design Ref: agent-create-wizard §5.2 — 설명 → 의도 → 도구 → 프롬프트 4단계.
 * 정지 지점 3곳에서 사용자가 개입하고, **저장은 하지 않는다**: DB 반영은
 * 스튜디오의 [저장] 버튼에서만 일어난다(무저장 계약 유지).
 *
 * 진행 상태를 영속하지 않는다 (Design A-6, 핸드오프 G1) — 새로고침 시 유실은
 * 버그가 아니라 정의된 동작이다.
 */
const AgentCreateEntryPage = () => {
  const navigate = useNavigate();
  const pipeline = useAgentPipelineStream();
  const { data: catalogTools } = useToolCatalog();

  const [step, setStep] = useState<WizardStep>('description');
  const [input, setInput] = useState('');
  const [state, setState] = useState<WizardState>(EMPTY);

  // 스튜디오에서 뒤로가기로 되돌아온 경우 이전 의도가 남아 있을 수 있다.
  // 진입 시점에 비워야 [직접 만들기]가 유령 초안을 끌고 가지 않는다 (G3).
  useEffect(() => {
    useAgentDraftStore.getState().clearPendingIntent();
  }, []);

  // 진행 중 이탈 경고 (FR-F16). description 단계는 잃을 게 없어 제외한다.
  useEffect(() => {
    if (step === 'description') return undefined;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [step]);

  const goStudio = (intent: AgentCreateIntent) => {
    useAgentDraftStore.getState().setPendingIntent(intent);
    navigate('/agent-builder');
  };

  /** 응답 status → 다음 단계 전이 (Design §5.2). */
  const applyResult = (result: AgentPipelineResponse, sent: WizardState) => {
    if (result.status === 'need_input') {
      setState({
        ...sent,
        round: result.round,
        questions: result.questions,
        answered: false,
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
        questions: [],
        answered: true,
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

  const handleSubmitDescription = () => {
    const text = input.trim().slice(0, MAX_USER_REQUEST_CHARS);
    if (!text || pipeline.isPending) return;
    const next = { ...EMPTY, userRequest: text };
    dispatch(
      { user_request: text, stop_after: PIPELINE_STOP.TOOLS },
      next,
    );
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
    const next = { ...state, answers: merged, answered: true };
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

  const handleConfirmTools = () => {
    if (pipeline.isPending) return;
    dispatch(
      {
        user_request: state.userRequest,
        answers: state.answers,
        round: state.round,
        tool_ids: state.selectedIds,
        // D1 — 확정 목록이므로 셀렉터를 다시 돌리지 않는다.
        tools_confirmed: true,
        // D2 — 의도를 재사용해 단계 간 근거가 갈리지 않게 한다.
        intent: state.intentEcho,
        stop_after: PIPELINE_STOP.PROMPT,
      },
      state,
    );
  };

  const handleRegeneratePrompt = () => {
    if (pipeline.isPending) return;
    dispatch(
      {
        user_request: state.userRequest,
        answers: state.answers,
        round: state.round,
        tool_ids: state.selectedIds,
        tools_confirmed: true,
        intent: state.intentEcho,
        // 같은 세션에 새 버전으로 쌓는다 — 세션이 늘어나지 않게.
        session_id: state.sessionId,
        stop_after: PIPELINE_STOP.PROMPT,
      },
      state,
    );
  };

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
      },
    });
  };

  const handleRetry = () => {
    pipeline.clearError();
    if (step === 'tools') handleConfirmTools();
    else if (step === 'prompt') handleRegeneratePrompt();
    else if (step === 'intent') handleSkipQuestions();
    else handleSubmitDescription();
  };

  const handleRestart = () => {
    pipeline.clearError();
    setState(EMPTY);
    setStep('description');
  };

  // ── 렌더 ────────────────────────────────────────────────────────────

  if (pipeline.error?.kind === PIPELINE_ERROR.DISABLED) {
    return (
      <div className="h-full overflow-y-auto bg-zinc-50/60">
        <div className="mx-auto flex min-h-full w-full max-w-[760px] flex-col justify-center gap-8 px-6 py-16">
          <EntryHero />
          <PipelineUnavailableCard
            onManualCreate={() => goStudio({ kind: 'blank' })}
          />
        </div>
      </div>
    );
  }

  const toolNames = state.selectedIds.map(
    (id) => catalogTools?.find((t) => t.tool_id === id)?.name ?? id,
  );

  // 첫 전송 전에는 진행바를 감춘다 — 전부 '대기중'인 5단계는 정보가 아니라
  // 잡음이고, 첫 화면은 "한 문장 쓰세요"에 집중시키는 편이 낫다.
  const showProgress = pipeline.isPending || pipeline.steps.length > 0;

  return (
    <div className="h-full overflow-y-auto bg-zinc-50/60">
      <div className="mx-auto flex min-h-full w-full max-w-[760px] flex-col justify-center gap-8 px-6 py-16">
          {step === 'description' && <EntryHero />}

          {/*
            입력창과 진행 상황을 한 덩어리로 묶는다 — 사용자가 보낸 문장 바로
            아래에서 단계가 진행되는 것이 보여야 "지금 뭘 하고 있는지"가
            시선 이동 없이 읽힌다. 전송 전에는 렌더하지 않는다(빈 5단계는 잡음).
          */}
          <div className="space-y-3">
            {step === 'description' ? (
              <DescriptionComposer
                value={input}
                onChange={setInput}
                onSubmit={handleSubmitDescription}
                isPending={pipeline.isPending}
              />
            ) : (
              <p className="rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-[13px] leading-relaxed text-zinc-600">
                <span className="mr-2 text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                  요청
                </span>
                {state.userRequest}
              </p>
            )}

            {showProgress && (
              <>
                <WizardProgress
                  steps={pipeline.steps}
                  activeStage={pipeline.activeStage}
                />
                <p className="px-1 text-[11.5px] leading-relaxed text-zinc-400">
                  마지막 두 단계는 스튜디오에서 [저장]을 누르면 완료됩니다.
                </p>
              </>
            )}
          </div>

          {step === 'intent' && state.questions.length > 0 && (
            <IntentStep
              questions={state.questions}
              round={state.round}
              maxRounds={MAX_CLARIFY_ROUNDS}
              isPending={pipeline.isPending}
              answered={state.answered}
              onSubmit={handleAnswers}
              onSkip={handleSkipQuestions}
            />
          )}

          {step === 'tools' && (
            <ToolsStep
              recommendedIds={state.recommendedIds}
              selectedIds={state.selectedIds}
              unknownIds={state.unknownIds}
              isPending={pipeline.isPending}
              onToggle={handleToggleTool}
              onConfirm={handleConfirmTools}
              onBack={handleRestart}
            />
          )}

          {step === 'prompt' && (
            <PromptStep
              value={state.prompt}
              clampReason={state.promptClampReason}
              degraded={state.promptDegraded}
              toolNames={toolNames}
              isPending={pipeline.isPending}
              onChange={(next) =>
                setState((prev) => ({ ...prev, prompt: next }))
              }
              onRegenerate={handleRegeneratePrompt}
              onSubmit={handleSendToStudio}
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

          {step === 'description' && (
            <EntryActionCards
              onManualCreate={() => goStudio({ kind: 'blank' })}
            />
          )}
      </div>
    </div>
  );
};

export default AgentCreateEntryPage;
