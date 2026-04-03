import type { Message } from '@/types/chat';
import SourceCitation from './SourceCitation';

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
        <p className="whitespace-pre-wrap">
          {message.content}
          {message.isStreaming && (
            <span className="ml-1 inline-block h-[18px] w-[3px] animate-pulse rounded-full bg-violet-500 align-middle" />
          )}
        </p>
        {message.sources && message.sources.length > 0 && (
          <SourceCitation sources={message.sources} />
        )}
      </div>
    </div>
  </div>
);

const MessageBubble = ({ message }: MessageBubbleProps) => {
  if (message.role === 'user') return <UserMessage content={message.content} />;
  return <AssistantMessage message={message} />;
};

export default MessageBubble;
