import { useEffect, useRef } from 'react';
import type { Message } from '@/types/chat';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  onSuggestionClick?: (text: string) => void;
}

const SUGGESTIONS = [
  {
    label: '문서 요약',
    text: '업로드한 문서를 요약해줘',
    gradient: 'from-violet-500 to-purple-600',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
      </svg>
    ),
  },
  {
    label: '문서 검색',
    text: '관련 자료를 찾아줘',
    gradient: 'from-blue-500 to-cyan-600',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
    ),
  },
  {
    label: 'AI Agent',
    text: 'Agent로 데이터 분석해줘',
    gradient: 'from-emerald-500 to-teal-600',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6" />
      </svg>
    ),
  },
  {
    label: '자유 대화',
    text: '자유롭게 질문하기',
    gradient: 'from-orange-500 to-rose-500',
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 9.75a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 0 1 .778-.332 48.294 48.294 0 0 0 5.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
      </svg>
    ),
  },
];

const EmptyState = ({ onSuggestionClick }: { onSuggestionClick?: (text: string) => void }) => (
  <div className="flex h-full flex-col items-center justify-center px-6 pb-32">
    <div className="w-full max-w-xl text-center">
      {/* 로고 */}
      <div className="mx-auto mb-8">
        <img
          src="https://m.sangsanginplussb.com/mob/img/ssiplus_logo.png"
          alt="상상인플러스저축은행"
          className="h-14 w-auto object-contain"
        />
      </div>

      <h2 className="text-3xl font-bold tracking-tight text-zinc-900">
        상플AI에 오신 것을 환영합니다
      </h2>
      <p className="mt-3 text-base leading-relaxed text-zinc-500">
        문서 기반 질의응답, AI Agent 실행, 자료 검색을 도와드립니다.
        <br />
        무엇이든 물어보세요.
      </p>

      {/* 제안 카드 */}
      <div className="mt-10 grid grid-cols-2 gap-3">
        {SUGGESTIONS.map(({ label, text, gradient, icon }) => (
          <button
            key={text}
            onClick={() => onSuggestionClick?.(text)}
            className="group relative overflow-hidden rounded-2xl border border-zinc-200 bg-white p-4 text-left shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-transparent hover:shadow-xl"
          >
            {/* hover 배경 */}
            <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-0 transition-opacity duration-200 group-hover:opacity-[0.06]`} />

            <div className={`mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${gradient} text-white shadow-sm`}>
              {icon}
            </div>
            <p className="text-[13.5px] font-semibold text-zinc-800">{label}</p>
            <p className="mt-0.5 text-[12px] leading-relaxed text-zinc-500">{text}</p>
          </button>
        ))}
      </div>
    </div>
  </div>
);

const MessageList = ({ messages, isStreaming, onSuggestionClick }: MessageListProps) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  if (messages.length === 0) return <EmptyState onSuggestionClick={onSuggestionClick} />;

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
