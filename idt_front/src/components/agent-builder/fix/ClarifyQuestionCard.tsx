import { useState } from 'react';
import type { ClarificationAnswer, ClarifyingQuestion } from '@/types/agentComposer';

interface ClarifyQuestionCardProps {
  questions: ClarifyingQuestion[];
  planSummary?: string;
  answered: boolean;
  isPending: boolean;
  onSubmit: (answers: ClarificationAnswer[]) => void;
}

/**
 * fix-agent-planner-hitl: HITL 구조화 질문 카드.
 * 질문별 선택지 토글 + 자유 입력. 부분 답변 허용 — 미답변은 answer=''로 제출된다.
 */
const ClarifyQuestionCard = ({
  questions,
  planSummary,
  answered,
  isPending,
  onSubmit,
}: ClarifyQuestionCardProps) => {
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [freeText, setFreeText] = useState<Record<string, string>>({});

  const disabled = answered || isPending;

  /** 자유 입력이 있으면 선택지보다 우선한다. */
  const answerOf = (q: ClarifyingQuestion): string =>
    freeText[q.id]?.trim() || selected[q.id] || '';

  const handleSubmit = () => {
    if (disabled) return;
    onSubmit(
      questions.map((q) => ({
        question_id: q.id,
        question: q.question,
        answer: answerOf(q),
      })),
    );
  };

  return (
    <div className="rounded-2xl border border-violet-200 bg-violet-50/50 p-4">
      {planSummary && (
        <p className="mb-3 text-[12.5px] leading-relaxed text-zinc-500">
          {planSummary}
        </p>
      )}
      <p className="text-[13.5px] font-semibold text-zinc-900">
        더 정확한 초안을 위해 몇 가지만 확인할게요
      </p>
      <div className="mt-3 space-y-4">
        {questions.map((q) => (
          <div key={q.id}>
            <p className="text-[13px] font-medium text-zinc-800">{q.question}</p>
            {q.options.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    disabled={disabled}
                    onClick={() =>
                      setSelected((prev) => ({
                        ...prev,
                        [q.id]: prev[q.id] === opt ? '' : opt,
                      }))
                    }
                    className={`rounded-lg border px-2.5 py-1 text-[12.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                      selected[q.id] === opt
                        ? 'border-violet-500 bg-violet-500 text-white'
                        : 'border-zinc-300 bg-white text-zinc-600 hover:border-violet-400'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            )}
            {q.allow_free_text && (
              <input
                type="text"
                value={freeText[q.id] ?? ''}
                disabled={disabled}
                onChange={(e) =>
                  setFreeText((prev) => ({ ...prev, [q.id]: e.target.value }))
                }
                placeholder="직접 입력 (선택)"
                aria-label={`${q.question} 직접 입력`}
                className="mt-1.5 block w-full rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-[12.5px] text-zinc-800 placeholder-zinc-400 outline-none focus:border-violet-400 disabled:cursor-not-allowed disabled:bg-zinc-50"
              />
            )}
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <p className="text-[11.5px] text-zinc-400">
          모르는 항목은 비워두면 알아서 가정해요
        </p>
        {answered ? (
          <span className="text-[12.5px] font-medium text-violet-500">
            ✓ 답변 완료
          </span>
        ) : (
          <button
            type="button"
            disabled={isPending}
            onClick={handleSubmit}
            className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12.5px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
          >
            답변 제출
          </button>
        )}
      </div>
    </div>
  );
};

export default ClarifyQuestionCard;
