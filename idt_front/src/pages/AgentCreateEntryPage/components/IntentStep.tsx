import { QuestionCardFlow } from '@/components/common/question-card';
import type { FlowAnswer } from '@/components/common/question-card';
import type { PipelineAnswer, PipelineQuestion } from '@/types/agentPipeline';

interface IntentStepProps {
  questions: PipelineQuestion[];
  /** 서버가 clamp 한 라운드 — 남은 왕복 안내에 쓴다. */
  round: number;
  maxRounds: number;
  isPending: boolean;
  /** 답변이 이미 제출됐는지. true 면 카드가 잠긴다 (스테일 카드 가드). */
  answered: boolean;
  onSubmit: (answers: PipelineAnswer[]) => void;
  onSkip: () => void;
}

/**
 * FlowAnswer → PipelineAnswer 역매핑.
 *
 * compose 계약(question_id + question 텍스트 에코백)과 달리 파이프라인은
 * `slot_key` 만 되돌린다 — 서버가 spec 으로 축을 알고 있어 질문 텍스트를
 * 재구성할 필요가 없기 때문이다.
 *
 * 무응답(`value === ''`)은 아예 보내지 않는다: 서버 `SlotAnswer` 가
 * `min_length=1` 이라 빈 값을 실으면 422 다.
 */
const toPipelineAnswers = (answers: FlowAnswer[]): PipelineAnswer[] =>
  answers
    .filter((a) => a.value.trim() !== '')
    .map((a) => ({ slot_key: a.id, value: a.value }));

/**
 * ② 의도 수집 — HITL 질문 카드 (Design §5.4 step②).
 *
 * 질문 UI 를 새로 만들지 않고 공통 `question-card` 를 조합한다
 * (common-card-components 위키 — 신규 구현 = 중복).
 */
const IntentStep = ({
  questions,
  round,
  maxRounds,
  isPending,
  answered,
  onSubmit,
  onSkip,
}: IntentStepProps) => {
  const remaining = Math.max(0, maxRounds - round);

  return (
    <div className="space-y-3">
      <QuestionCardFlow
        // 라운드가 바뀌면 Flow 를 새로 마운트한다 — 내부 done 잠금이 남으면
        // 다음 라운드 질문에 답할 수 없다.
        key={`intent-round-${round}`}
        questions={questions.map((q) => ({
          id: q.slot_key,
          title: q.question,
          options: q.options,
          allowFreeText: q.allow_free_text,
        }))}
        // 잠긴 라운드(이력 카드)에는 진행 안내를 남기지 않는다 — "남은 라운드"
        // 표기가 지난 카드에 남으면 거짓 정보가 된다 (wizard-chat-layout FR-07).
        header={
          answered ? undefined : (
            <p className="text-[12.5px] leading-relaxed text-zinc-500">
              에이전트를 정확히 만들기 위해 몇 가지만 확인할게요.
              {remaining > 0 && ` (남은 질문 라운드 ${remaining}회)`}
            </p>
          )
        }
        // F10 스테일 카드 가드 — 새 응답이 오기 전까지 잠근다. Flow 내부
        // `done` 과 이중으로 걸어야 이전 라운드 카드가 오표시되지 않는다.
        disabled={isPending}
        completed={answered}
        onComplete={(answers) => onSubmit(toPipelineAnswers(answers))}
      />
      {!answered && (
        <button
          type="button"
          onClick={onSkip}
          disabled={isPending}
          className="text-[12.5px] text-zinc-400 transition-colors hover:text-violet-600 disabled:cursor-not-allowed"
        >
          건너뛰고 계속하기
        </button>
      )}
    </div>
  );
};

export default IntentStep;
