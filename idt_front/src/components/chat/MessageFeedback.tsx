// agent-eval-gate: 답변 아래 👍/👎 평가 버튼 — 낙관적 토글, 실패 시 서버 값으로 복원.
import { useMessageFeedback, useSubmitFeedback } from '@/hooks/useMessageFeedback';
import type { Rating } from '@/types/messageFeedback';

interface MessageFeedbackProps {
  messageId: number;
}

const MessageFeedback = ({ messageId }: MessageFeedbackProps) => {
  const { data } = useMessageFeedback(messageId);
  const submit = useSubmitFeedback(messageId);
  const current = data?.rating ?? null;

  const onRate = (rating: Rating) => {
    // 같은 값 재클릭이면 취소(서버가 처리) — 낙관적 반영은 캐시 갱신으로 대체
    submit.mutate({ rating });
  };

  const btn = (rating: Rating, label: string, icon: string) => (
    <button
      type="button"
      aria-label={label}
      aria-pressed={current === rating}
      onClick={() => onRate(rating)}
      disabled={submit.isPending}
      className={`rounded-lg border px-2 py-1 text-[13px] transition-colors ${
        current === rating
          ? 'border-violet-300 bg-violet-50 text-violet-700'
          : 'border-zinc-200 text-zinc-400 hover:bg-zinc-50 hover:text-zinc-600'
      }`}
    >
      {icon}
    </button>
  );

  return (
    <div className="mt-2 flex items-center gap-1">
      {btn('up', '좋아요', '👍')}
      {btn('down', '싫어요', '👎')}
    </div>
  );
};

export default MessageFeedback;
