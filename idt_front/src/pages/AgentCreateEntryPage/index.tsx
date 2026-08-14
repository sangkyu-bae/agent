import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useComposeAgent } from '@/hooks/useAgentComposer';
import { useAgentDraftStore } from '@/store/agentDraftStore';
import type { AgentCreateIntent } from '@/store/agentDraftStore';
import ClarifyQuestionCard from '@/components/agent-builder/fix/ClarifyQuestionCard';
import EntryHero from './components/EntryHero';
import DescriptionComposer, {
  MAX_USER_REQUEST_CHARS,
} from './components/DescriptionComposer';
import EntryActionCards from './components/EntryActionCards';
import ComposeFailureCard from './components/ComposeFailureCard';
import type { ComposeFailure } from './components/ComposeFailureCard';
import type {
  ClarificationAnswer,
  ClarifyingQuestion,
  ComposeAgentDraftResponse,
} from '@/types/agentComposer';

/**
 * 서버 상한(10)보다 보수적인 클라이언트 상한.
 * 플래너가 계속 되물으면 사용자가 빠져나갈 방법이 없으므로 여기서 끊는다 (Design §4.3).
 */
const MAX_CLARIFY_ROUNDS = 3;

/**
 * 에이전트 생성 진입 화면 (/agent-builder/new).
 *
 * Design Ref: agent-create-entry §2.1 — 설명 한 문장을 compose 초안으로 바꿔
 * 스튜디오에 프리필한다. 저장은 하지 않는다(무저장 계약) — DB 반영은 스튜디오의
 * [저장] 버튼에서만 일어난다.
 */
const AgentCreateEntryPage = () => {
  const navigate = useNavigate();
  const composeMutation = useComposeAgent();
  const isPending = composeMutation.isPending;

  const [input, setInput] = useState('');
  const [questions, setQuestions] = useState<ClarifyingQuestion[] | null>(null);
  const [planSummary, setPlanSummary] = useState('');
  const [answered, setAnswered] = useState(false);
  const [pendingClarify, setPendingClarify] = useState<{
    userRequest: string;
    round: number;
  } | null>(null);
  const [failure, setFailure] = useState<ComposeFailure | null>(null);

  const composerRef = useRef<HTMLDivElement>(null);

  // Design §2.4 G3: 스튜디오에서 뒤로가기로 되돌아온 경우 이전 의도가 남아 있을 수
  // 있다. 진입 시점에 비워야 다음 [직접 만들기]가 유령 초안을 끌고 가지 않는다.
  useEffect(() => {
    useAgentDraftStore.getState().clearPendingIntent();
  }, []);

  const goStudio = (intent: AgentCreateIntent) => {
    useAgentDraftStore.getState().setPendingIntent(intent);
    navigate('/agent-builder');
  };

  const handleDraftResult = (
    draft: ComposeAgentDraftResponse,
    userRequest: string,
    currentRound: number,
  ) => {
    if (draft.status === 'needs_clarification') {
      const nextRound = currentRound + 1;
      if (nextRound > MAX_CLARIFY_ROUNDS) {
        setQuestions(null);
        setPendingClarify(null);
        setFailure({
          reason: 'clarify_exhausted',
          message: draft.plan_summary ?? '',
          missing: [],
        });
        return;
      }
      setQuestions(draft.questions ?? []);
      setPlanSummary(draft.plan_summary ?? '');
      setAnswered(false);
      setPendingClarify({ userRequest, round: nextRound });
      return;
    }

    setQuestions(null);
    setPendingClarify(null);

    // coverage='none'이면 초안 필드가 모두 비어 있다 — 프리필해도 빈 폼이므로
    // 스튜디오로 보내지 않고 사유를 보여준다 (Design §4.3).
    if (draft.coverage === 'none') {
      setFailure({
        reason: 'coverage_none',
        message: draft.notes,
        missing: draft.missing_capabilities,
      });
      return;
    }

    goStudio({ kind: 'draft', draft });
  };

  /** compose 호출 공통 경로 — clarify가 있으면 HITL 답변으로 재호출(stateless). */
  const sendCompose = (
    userRequest: string,
    clarify?: { answers: ClarificationAnswer[]; round: number },
  ) => {
    composeMutation.mutate(
      {
        user_request: userRequest,
        name: null,
        // 진입 화면은 편집 대상 폼이 없다 — Fix 탭과 달리 스냅샷을 보내지 않는다
        current_config: null,
        history: null,
        clarification_answers: clarify?.answers ?? null,
        clarification_round: clarify?.round ?? 0,
      },
      {
        onSuccess: (draft) =>
          handleDraftResult(draft, userRequest, clarify?.round ?? 0),
        onError: (error) => {
          setQuestions(null);
          setPendingClarify(null);
          setFailure({ reason: 'api_error', message: error.message, missing: [] });
        },
      },
    );
  };

  const handleSubmit = () => {
    const text = input.trim().slice(0, MAX_USER_REQUEST_CHARS);
    if (!text || isPending) return;
    setQuestions(null);
    setPendingClarify(null);
    setFailure(null);
    sendCompose(text);
  };

  const handleAnswerSubmit = (answers: ClarificationAnswer[]) => {
    if (!pendingClarify || isPending) return;
    setAnswered(true);
    sendCompose(pendingClarify.userRequest, {
      answers,
      round: pendingClarify.round,
    });
  };

  /** 질문을 건너뛰고 초안을 강제한다 — 전부 무응답(answer='')으로 재호출. */
  const handleSkipQuestions = () => {
    if (!pendingClarify || isPending || !questions) return;
    handleAnswerSubmit(
      questions.map((q) => ({
        question_id: q.id,
        question: q.question,
        answer: '',
      })),
    );
  };

  /** 실패 카드 닫고 입력으로 복귀 — 사용자가 문장을 고칠 수 있게 input은 보존한다. */
  const handleRetry = () => {
    setFailure(null);
    composerRef.current?.querySelector('textarea')?.focus();
  };

  return (
    <div className="h-full overflow-y-auto bg-zinc-50/60">
      <div className="mx-auto flex min-h-full w-full max-w-[760px] flex-col justify-center gap-8 px-6 py-16">
        <EntryHero />

        <div ref={composerRef}>
          <DescriptionComposer
            value={input}
            onChange={setInput}
            onSubmit={handleSubmit}
            isPending={isPending}
          />
        </div>

        {questions && questions.length > 0 && (
          <div className="space-y-2">
            <ClarifyQuestionCard
              questions={questions}
              planSummary={planSummary}
              answered={answered}
              isPending={isPending}
              onSubmit={handleAnswerSubmit}
            />
            {!answered && (
              <button
                type="button"
                onClick={handleSkipQuestions}
                disabled={isPending}
                className="text-[12.5px] text-zinc-400 transition-colors hover:text-violet-600 disabled:cursor-not-allowed"
              >
                건너뛰고 초안 만들기
              </button>
            )}
          </div>
        )}

        {failure && (
          <ComposeFailureCard
            failure={failure}
            onRetry={handleRetry}
            onManualCreate={() => goStudio({ kind: 'blank' })}
          />
        )}

        <EntryActionCards onManualCreate={() => goStudio({ kind: 'blank' })} />
      </div>
    </div>
  );
};

export default AgentCreateEntryPage;
