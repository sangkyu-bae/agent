import { memo } from 'react';
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
    <div className="max-w-[85%] sm:max-w-[75%]">
      <div
        className="rounded-2xl rounded-br-sm px-5 py-3.5 text-[15px] leading-[1.65] text-white"
        style={{ background: 'linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%)' }}
      >
        <p className="whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  </div>
);

const AssistantMessage = ({ message }: { message: Message }) => (
  <div className="flex items-start gap-4">
    {/* 아바타 */}
    <div
      className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md"
      style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
    >
      <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
      </svg>
    </div>

    {/* 메시지 내용 */}
    <div className="min-w-0 flex-1">
      <p className="mb-2 text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
        상플AI
      </p>
      <div className="text-[15px] leading-[1.8] text-zinc-800">
        <MarkdownRenderer content={message.content} />
        {message.isStreaming && (
          <span className="ml-1 inline-block h-[18px] w-[3px] animate-pulse rounded-full bg-violet-500 align-middle" />
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
