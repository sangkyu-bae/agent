// Design Ref: ui-redesign-chat §5.4 — 점 3개 bounce. reduced-motion에서는 전역 규칙으로 정지.
import { AssistantAvatar } from './MessageBubble';

const TypingIndicator = () => (
  <div className="flex items-start gap-4" role="status" aria-label="답변 작성 중">
    <AssistantAvatar />
    <div className="flex items-center gap-1.5 rounded-xl border border-border bg-surface-muted px-4 py-3.5">
      <span className="h-2 w-2 animate-bounce rounded-full bg-fg-subtle [animation-delay:-0.3s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-fg-subtle [animation-delay:-0.15s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-fg-subtle" />
    </div>
  </div>
);

export default TypingIndicator;
