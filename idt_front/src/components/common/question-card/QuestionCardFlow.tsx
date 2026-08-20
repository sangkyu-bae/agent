import { useState } from 'react';
import type { ReactNode } from 'react';
import QuestionCard from './QuestionCard';
import QuestionOptionItem from './QuestionOptionItem';
import QuestionFreeTextOption from './QuestionFreeTextOption';
import type { FlowAnswer, FlowQuestion } from './types';

interface QuestionCardFlowProps {
  questions: FlowQuestion[];
  /** isPending 등 — 모든 조작 차단 (F9) */
  disabled?: boolean;
  /** 외부 완료 상태(answered) — 전 카드 잠금 표시 (F8) */
  completed?: boolean;
  compact?: boolean;
  /** planSummary 등 플로우 상단 슬롯 */
  header?: ReactNode;
  /** 마지막 질문 제출 시 1회 호출 — 미답변 질문은 value='' (F6/F7) */
  onComplete: (answers: FlowAnswer[]) => void;
}

// 직접 입력 라디오 선택을 나타내는 내부 센티널 — 옵션 문자열과 충돌하지 않도록 제어 문자 사용
const FREE_TEXT = '\u0000free-text';

/**
 * Design Ref: question-card §5.1 F1-F9 — 질문당 카드 1장 순차 위저드.
 * 제출 → 카드 잠금 → 다음 질문 노출, 마지막 제출 시 전체 답변을 일괄 전달한다.
 * 상태는 로컬 useState — 일시적 UI 상태이므로 전역 스토어를 쓰지 않는다.
 */
const QuestionCardFlow = ({
  questions,
  disabled = false,
  completed = false,
  compact = false,
  header,
  onComplete,
}: QuestionCardFlowProps) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [freeText, setFreeText] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);

  if (questions.length === 0) return null;

  const allLocked = completed || done;

  /** 직접 입력이 선택되면 입력 텍스트가, 아니면 선택 옵션이 답변 값 (F3) */
  const answerOf = (q: FlowQuestion): string => {
    const sel = selected[q.id];
    if (sel === FREE_TEXT) return (freeText[q.id] ?? '').trim();
    return sel ?? '';
  };

  /** value를 확정하고 전진 — 마지막이면 onComplete 1회 (F6/F7) */
  const advance = (q: FlowQuestion, index: number, value: string) => {
    if (disabled || done) return;
    const nextConfirmed = { ...confirmed, [q.id]: value };
    setConfirmed(nextConfirmed);
    if (index >= questions.length - 1) {
      setDone(true);
      // Plan SC: 부분 답변 허용 — 미확정 질문은 ''로 채워 백엔드 계약 유지
      onComplete(questions.map((qq) => ({ id: qq.id, value: nextConfirmed[qq.id] ?? '' })));
    } else {
      setCurrentIndex(index + 1);
    }
  };

  /** 건너뛰기 = 무응답 확정 (F5). 선택도 해제해 잠금 카드에 오해 소지를 남기지 않는다. */
  const handleSkip = (q: FlowQuestion, index: number) => {
    setSelected((prev) => ({ ...prev, [q.id]: '' }));
    advance(q, index, '');
  };

  const visibleCount = allLocked ? questions.length : currentIndex + 1;

  return (
    <div className="space-y-3">
      {header}
      {questions.slice(0, visibleCount).map((q, index) => {
        const locked = allLocked || index < currentIndex;
        const rowDisabled = locked || disabled;
        const submittable = answerOf(q) !== '';
        return (
          <QuestionCard
            key={q.id}
            title={q.title}
            locked={locked}
            compact={compact}
            footer={
              <>
                <button
                  type="button"
                  onClick={() => handleSkip(q, index)}
                  disabled={disabled}
                  className="text-[12.5px] text-zinc-400 transition-colors hover:text-violet-600 disabled:cursor-not-allowed"
                >
                  건너뛰기
                </button>
                <button
                  type="button"
                  onClick={() => advance(q, index, answerOf(q))}
                  disabled={disabled || !submittable}
                  className={`flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-[13.5px] font-medium text-white transition-all ${
                    disabled || !submittable
                      ? 'cursor-not-allowed bg-violet-300'
                      : 'bg-violet-600 hover:bg-violet-700 active:scale-95'
                  }`}
                >
                  <svg
                    className="h-3.5 w-3.5"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z"
                    />
                  </svg>
                  제출
                </button>
              </>
            }
          >
            {q.options.map((opt) => (
              <QuestionOptionItem
                key={opt}
                name={q.id}
                label={opt}
                compact={compact}
                selected={selected[q.id] === opt}
                disabled={rowDisabled}
                onSelect={() => setSelected((prev) => ({ ...prev, [q.id]: opt }))}
              />
            ))}
            {q.allowFreeText && (
              <QuestionFreeTextOption
                name={q.id}
                label={q.freeTextLabel}
                compact={compact}
                selected={selected[q.id] === FREE_TEXT}
                disabled={rowDisabled}
                value={freeText[q.id] ?? ''}
                inputAriaLabel={`${q.title} 직접 입력`}
                onSelect={() => setSelected((prev) => ({ ...prev, [q.id]: FREE_TEXT }))}
                onChange={(v) => setFreeText((prev) => ({ ...prev, [q.id]: v }))}
              />
            )}
          </QuestionCard>
        );
      })}
    </div>
  );
};

export default QuestionCardFlow;
