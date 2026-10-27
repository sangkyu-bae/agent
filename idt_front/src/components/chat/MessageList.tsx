// Design Ref: ui-redesign-chat §5.4 — 빈 상태는 ui/EmptyState + 제안 카드. 메시지 간격 gap-8 유지.
import { useEffect, useRef, type ComponentType } from 'react';
import { ChartColumn, FileSearch, FileText, MessageSquare, type LucideProps } from 'lucide-react';
import EmptyState from '@/components/ui/EmptyState';
import type { Message } from '@/types/chat';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  onSuggestionClick?: (text: string) => void;
}

export interface Suggestion {
  label: string;
  text: string;
  icon: ComponentType<LucideProps>;
}

const SUGGESTIONS: Suggestion[] = [
  { label: '문서 요약', text: '업로드한 문서를 요약해줘', icon: FileText },
  { label: '문서 검색', text: '관련 자료를 찾아줘', icon: FileSearch },
  { label: 'AI Agent', text: 'Agent로 데이터 분석해줘', icon: ChartColumn },
  { label: '자유 대화', text: '자유롭게 질문하기', icon: MessageSquare },
];

/**
 * 빈 상태 제안 카드. ChatPage의 EmptyAgentState에서도 쓴다 (G-01).
 * agent-opener §5.2: `items`를 주면 그 목록(에이전트 오프너), 없으면 고정 4종.
 */
export const SuggestionCards = ({
  onSuggestionClick,
  items = SUGGESTIONS,
}: {
  onSuggestionClick?: (text: string) => void;
  items?: Suggestion[];
}) => (
  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
    {items.map(({ label, text, icon: Icon }, index) => (
      <button
        key={`${index}:${text}`}
        type="button"
        onClick={() => onSuggestionClick?.(text)}
        className="flex items-start gap-3 rounded-xl border border-border bg-surface p-4 text-left shadow-sm transition-colors duration-150 hover:border-brand-200 hover:bg-brand-50/40"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-600">
          <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-fg">{label}</span>
          {text !== label && (
            <span className="mt-0.5 block text-xs text-fg-muted">{text}</span>
          )}
        </span>
      </button>
    ))}
  </div>
);

const EmptyMessages = ({ onSuggestionClick }: { onSuggestionClick?: (text: string) => void }) => (
  <div className="flex h-full items-center justify-center pb-16">
    <EmptyState
      icon={<img src="/logo.png" alt="상상인플러스저축은행" className="h-14 w-auto object-contain" />}
      iconUnstyled
      title="상플AI에 오신 것을 환영합니다"
      description="문서 기반 질의응답, AI Agent 실행, 자료 검색을 도와드립니다. 무엇이든 물어보세요."
      className="w-full max-w-xl"
    >
      <SuggestionCards onSuggestionClick={onSuggestionClick} />
    </EmptyState>
  </div>
);

const MessageList = ({ messages, isStreaming, onSuggestionClick }: MessageListProps) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  if (messages.length === 0) return <EmptyMessages onSuggestionClick={onSuggestionClick} />;

  return (
    <div className="flex flex-col gap-8 px-4 py-8 sm:px-6">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isStreaming && <TypingIndicator />}
      <div ref={bottomRef} className="h-2" />
    </div>
  );
};

export default MessageList;
