import { useState } from 'react';
import type { ChatSession } from '@/types/chat';
import { formatDate } from '@/utils/formatters';

interface ChatHistoryPanelProps {
  isOpen: boolean;
  onToggle: () => void;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

const ChatHistoryPanel = ({
  isOpen,
  onToggle,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  isLoading = false,
  isError = false,
  onRetry,
}: ChatHistoryPanelProps) => {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredSessions = searchQuery
    ? sessions.filter((s) => s.title.toLowerCase().includes(searchQuery.toLowerCase()))
    : sessions;

  if (!isOpen) {
    return (
      <div className="flex h-full w-12 shrink-0 flex-col items-center border-r border-zinc-200 bg-white pt-4 gap-1">
        <button
          onClick={onToggle}
          title="펼치기"
          className="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 transition-all"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" />
          </svg>
        </button>
        <button
          onClick={onNewChat}
          title="새 채팅"
          className="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 transition-all"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Z" />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-r border-zinc-200 bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-5 pb-3">
        <button
          onClick={onToggle}
          title="접기"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 transition-all"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M12 17.25H3.75" />
          </svg>
        </button>
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Z" />
          </svg>
          <span className="text-[14px] font-semibold text-zinc-800">채팅</span>
        </div>
      </div>

      {/* New chat button */}
      <div className="px-3 pb-2">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2.5 text-[13px] font-medium text-zinc-600 hover:border-zinc-300 hover:bg-zinc-100 transition-all"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Z" />
          </svg>
          새 채팅
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-3">
        <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2">
          <svg className="h-4 w-4 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
          <input
            type="text"
            placeholder="채팅 검색..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-transparent text-[13px] text-zinc-700 placeholder-zinc-400 outline-none"
          />
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {isError ? (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-center">
            <p className="text-[12.5px] text-red-600">대화 내역을 불러오지 못했습니다</p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="mt-2 rounded-lg border border-red-200 px-3 py-1 text-[11.5px] text-red-500 hover:bg-red-100"
              >
                다시 시도
              </button>
            )}
          </div>
        ) : isLoading && sessions.length === 0 ? (
          <div className="space-y-1 px-1">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-xl px-3 py-3">
                <span className="block h-3 w-3/4 animate-pulse rounded bg-zinc-100" />
                <span className="mt-2 block h-2 w-1/3 animate-pulse rounded bg-zinc-50" />
              </div>
            ))}
          </div>
        ) : filteredSessions.length > 0 ? (
          <div className="space-y-0.5">
            {filteredSessions.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <button
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  className={`w-full rounded-xl px-4 py-3 text-left transition-all duration-150 ${
                    isActive
                      ? 'bg-violet-50 border-l-2 border-violet-500'
                      : 'hover:bg-zinc-50'
                  }`}
                >
                  <span className={`block truncate text-[13.5px] font-medium ${isActive ? 'text-violet-700' : 'text-zinc-800'}`}>
                    {session.title}
                  </span>
                  <span className="mt-1 block text-[11px] text-zinc-400">
                    {formatDate(session.updatedAt)}
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="mt-8 text-center">
            <p className="text-[12.5px] text-zinc-400">
              {searchQuery ? '검색 결과가 없습니다' : '대화 내역이 없습니다'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatHistoryPanel;
