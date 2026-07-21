// agent-eval-gate: 답변 아래 👍/👎 평가 버튼 — 낙관적 토글, 실패 시 서버 값으로 복원.
// eval-feedback-loop §3-6: 👎 상태면 이유 칩 + 자유 코멘트 패널 노출(기존 comment 필드 재사용).
import { useState } from 'react';

import { useMessageFeedback, useSubmitFeedback } from '@/hooks/useMessageFeedback';
import type { Rating } from '@/types/messageFeedback';

const REASON_CHIPS = ['부정확함', '질문과 무관', '근거 부족', '형식/톤 불만'];

interface MessageFeedbackProps {
  messageId: number;
}

const MessageFeedback = ({ messageId }: MessageFeedbackProps) => {
  const { data } = useMessageFeedback(messageId);
  const submit = useSubmitFeedback(messageId);
  const [text, setText] = useState('');
  const [editing, setEditing] = useState(false);
  const current = data?.rating ?? null;
  const comment = data?.comment ?? null;

  const onRate = (rating: Rating) => {
    // 같은 값 재클릭이면 취소(서버가 처리) — 낙관적 반영은 캐시 갱신으로 대체
    submit.mutate({ rating });
  };

  const sendReason = (reason: string) => {
    const trimmed = reason.trim();
    if (!trimmed) return;
    submit.mutate({ rating: 'down', comment: trimmed });
    setText('');
    setEditing(false);
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

  const showPanel = current === 'down' && (!comment || editing);

  return (
    <div className="mt-2">
      <div className="flex items-center gap-1">
        {btn('up', '좋아요', '👍')}
        {btn('down', '싫어요', '👎')}
      </div>
      {showPanel && (
        <div
          role="group"
          aria-label="싫어요 이유"
          className="mt-2 flex flex-wrap items-center gap-1.5"
        >
          {REASON_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              aria-pressed={comment === chip}
              onClick={() => sendReason(chip)}
              disabled={submit.isPending}
              className="rounded-full border border-zinc-200 px-2.5 py-1 text-[12px] text-zinc-500 transition-colors hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600"
            >
              {chip}
            </button>
          ))}
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="무엇이 아쉬웠나요?"
            maxLength={500}
            className="min-w-[160px] flex-1 rounded-lg border border-zinc-200 px-2 py-1 text-[12px] focus:border-violet-300 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => sendReason(text)}
            disabled={submit.isPending || !text.trim()}
            className="rounded-lg border border-zinc-200 px-2 py-1 text-[12px] text-zinc-500 transition-colors hover:bg-zinc-50 disabled:opacity-40"
          >
            보내기
          </button>
        </div>
      )}
      {current === 'down' && comment && !editing && (
        <div className="mt-1.5 flex items-center gap-2 text-[12px] text-zinc-500">
          <span>이유: {comment}</span>
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-zinc-400 underline-offset-2 hover:text-zinc-600 hover:underline"
          >
            수정
          </button>
        </div>
      )}
    </div>
  );
};

export default MessageFeedback;
