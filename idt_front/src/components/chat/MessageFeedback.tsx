// agent-eval-gate: 답변 아래 👍/👎 평가 버튼 — 낙관적 토글, 실패 시 서버 값으로 복원.
// eval-feedback-loop §3-6: 👎 상태면 이유 칩 + 자유 코멘트 패널 노출(기존 comment 필드 재사용).
// Design Ref: ui-redesign-chat §5.4 — IconButton(isActive→aria-pressed) + 토큰. 로직 변경 없음.
import { useState } from 'react';
import { ThumbsDown, ThumbsUp } from 'lucide-react';

import Button from '@/components/ui/Button';
import IconButton from '@/components/ui/IconButton';
import Input from '@/components/ui/Input';
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

  const showPanel = current === 'down' && (!comment || editing);

  return (
    <div className="mt-2">
      <div className="flex items-center gap-1">
        <IconButton
          aria-label="좋아요"
          size="sm"
          isActive={current === 'up'}
          onClick={() => onRate('up')}
          disabled={submit.isPending}
          className={current === 'up' ? 'text-brand-700' : undefined}
        >
          <ThumbsUp className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        </IconButton>
        <IconButton
          aria-label="싫어요"
          size="sm"
          isActive={current === 'down'}
          onClick={() => onRate('down')}
          disabled={submit.isPending}
          className={current === 'down' ? 'text-danger' : undefined}
        >
          <ThumbsDown className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        </IconButton>
      </div>
      {showPanel && (
        <div role="group" aria-label="싫어요 이유" className="mt-2 flex flex-wrap items-center gap-1.5">
          {REASON_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              aria-pressed={comment === chip}
              onClick={() => sendReason(chip)}
              disabled={submit.isPending}
              className="rounded-full border border-border px-2.5 py-1 text-xs text-fg-muted transition-colors duration-150 hover:border-danger-border hover:bg-danger-bg hover:text-danger disabled:opacity-50"
            >
              {chip}
            </button>
          ))}
          <Input
            aria-label="싫어요 이유 직접 입력"
            size="sm"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="무엇이 아쉬웠나요?"
            maxLength={500}
            wrapperClassName="min-w-40 flex-1"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => sendReason(text)}
            disabled={submit.isPending || !text.trim()}
          >
            보내기
          </Button>
        </div>
      )}
      {current === 'down' && comment && !editing && (
        <div className="mt-1.5 flex items-center gap-2 text-xs text-fg-muted">
          <span>이유: {comment}</span>
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-fg-subtle underline-offset-2 hover:text-fg hover:underline"
          >
            수정
          </button>
        </div>
      )}
    </div>
  );
};

export default MessageFeedback;
