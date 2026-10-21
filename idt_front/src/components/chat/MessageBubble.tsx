// Design Ref: ui-redesign-chat §5.4 — 유저 버블·어시스턴트 아바타를 토큰 그라데이션으로, eyebrow 대문자 라벨은 제거.
import { memo } from 'react';
import { Sparkles } from 'lucide-react';
import type { Message } from '@/types/chat';
import SourceCitation from './SourceCitation';
import ChartRenderer from './ChartRenderer';
import MarkdownRenderer from './MarkdownRenderer';
import MessageFeedback from './MessageFeedback';

interface MessageBubbleProps {
  message: Message;
}

const UserMessage = ({ content }: { content: string }) => (
  <div className="flex justify-end">
    <div className="max-w-[85%] lg:max-w-[75%]">
      <div className="rounded-xl rounded-br-md bg-linear-to-br from-bubble-from to-bubble-to px-5 py-3.5 text-md leading-[1.65] text-white">
        <p className="whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  </div>
);

/** 어시스턴트 아바타 — TypingIndicator와 공유 */
export const AssistantAvatar = () => (
  <div
    aria-hidden="true"
    className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-brand-600 to-brand-800 shadow-sm"
  >
    <Sparkles className="h-5 w-5 text-white" strokeWidth={1.75} />
  </div>
);

const AssistantMessage = ({ message }: { message: Message }) => (
  <div className="flex items-start gap-4">
    <AssistantAvatar />

    <div className="min-w-0 flex-1">
      <p className="mb-1.5 text-xs font-medium text-fg-subtle">상플AI</p>
      <div className="text-md leading-[1.7] text-fg">
        <MarkdownRenderer content={message.content} />
        {message.isStreaming && (
          <span
            aria-hidden="true"
            className="ml-1 inline-block h-4 w-0.5 animate-pulse rounded-full bg-brand-500 align-middle"
          />
        )}
        {message.charts && message.charts.length > 0 && (
          <div className="flex flex-col gap-3">
            {message.charts.map((chart, i) => (
              <ChartRenderer key={i} payload={chart} />
            ))}
          </div>
        )}
        {message.sources && message.sources.length > 0 && (
          <SourceCitation sources={message.sources} />
        )}
        {/* agent-eval-gate: 스트리밍 완료된 답변에 평가 버튼 (평가 대상 id 확정 시) */}
        {!message.isStreaming && feedbackId(message) !== null && (
          <MessageFeedback messageId={feedbackId(message) as number} />
        )}
      </div>
    </div>
  </div>
);

// 평가 대상 메시지 id 결정:
// - 히스토리 메시지: 서버 저장 numeric id (String으로 변환되어 있음)
// - 방금 스트리밍 완료된 메시지: feedbackMessageId (ANSWER_COMPLETED의 assistant_message_id)
// 둘 다 없으면(임시 placeholder 등) 평가 미노출.
const feedbackId = (message: Message): number | null => {
  if (typeof message.feedbackMessageId === 'number') return message.feedbackMessageId;
  if (/^\d+$/.test(message.id)) return Number(message.id);
  return null;
};

const MessageBubble = ({ message }: MessageBubbleProps) => {
  if (message.role === 'user') return <UserMessage content={message.content} />;
  return <AssistantMessage message={message} />;
};

// 스트리밍 중 완료된 과거 메시지의 재렌더(마크다운 재파싱) 차단
export default memo(MessageBubble);
