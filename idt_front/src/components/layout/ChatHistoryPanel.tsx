// Design Ref: ui-redesign-chat §5.3 — 대화 목록 패널. overlay 모드(≤768)에서는 레일 옆에 떠서 열리고 바깥 클릭·ESC로 닫힌다.
import { useEffect, useState } from 'react';
import { History, Search, SquarePen, X } from 'lucide-react';
import Button from '@/components/ui/Button';
import IconButton from '@/components/ui/IconButton';
import Input from '@/components/ui/Input';
import { cn } from '@/utils/cn';
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
  /** ≤768: 본문 위에 오버레이로 열림 (Plan SC: FR-13) */
  overlay?: boolean;
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
  overlay = false,
}: ChatHistoryPanelProps) => {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredSessions = searchQuery
    ? sessions.filter((s) => s.title.toLowerCase().includes(searchQuery.toLowerCase()))
    : sessions;

  // overlay 모드에서 ESC로 닫기
  useEffect(() => {
    if (!overlay || !isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onToggle();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlay, isOpen, onToggle]);

  const rail = (
    <div className="flex h-full w-12 shrink-0 flex-col items-center gap-1 border-r border-border bg-surface pt-3">
      <IconButton aria-label="대화 목록 열기" onClick={onToggle} isActive={overlay && isOpen}>
        <History className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
      </IconButton>
      <IconButton aria-label="새 대화" onClick={onNewChat}>
        <SquarePen className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
      </IconButton>
    </div>
  );

  if (!isOpen) return rail;

  const panel = (
    <section
      aria-label="대화 목록"
      className={cn(
        'flex h-full w-72 shrink-0 flex-col border-r border-border bg-surface',
        overlay && 'absolute left-full top-0 z-20 shadow-lg',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <div className="flex items-center gap-2 px-1">
          <History className="h-4 w-4 text-fg-subtle" strokeWidth={1.75} aria-hidden="true" />
          <span className="text-base font-semibold text-fg">대화</span>
        </div>
        <IconButton aria-label="대화 목록 닫기" size="sm" onClick={onToggle}>
          <X className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        </IconButton>
      </div>

      {/* New chat */}
      <div className="px-3 pb-2">
        <Button
          variant="secondary"
          size="sm"
          className="w-full"
          onClick={onNewChat}
          leadingIcon={<SquarePen className="h-4 w-4" strokeWidth={2} aria-hidden="true" />}
        >
          새 대화
        </Button>
      </div>

      {/* Search */}
      <div className="px-3 pb-3">
        <Input
          aria-label="대화 검색"
          size="sm"
          placeholder="대화 검색"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          leadingIcon={<Search className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
        />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {isError ? (
          <div className="mt-6 rounded-xl border border-danger-border bg-danger-bg px-4 py-3 text-center">
            <p className="text-xs text-danger">대화 내역을 불러오지 못했습니다</p>
            {onRetry && (
              <Button variant="danger" size="sm" className="mt-2" onClick={onRetry}>
                다시 시도
              </Button>
            )}
          </div>
        ) : isLoading && sessions.length === 0 ? (
          <div className="space-y-1 px-1" role="status" aria-label="불러오는 중">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-md px-3 py-3">
                <span className="block h-3 w-3/4 animate-pulse rounded-md bg-surface-sunken" />
                <span className="mt-2 block h-2 w-1/3 animate-pulse rounded-md bg-surface-muted" />
              </div>
            ))}
          </div>
        ) : filteredSessions.length > 0 ? (
          <ul className="space-y-0.5">
            {filteredSessions.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <li key={session.id}>
                  <button
                    type="button"
                    onClick={() => onSelectSession(session.id)}
                    aria-current={isActive ? 'true' : undefined}
                    className={cn(
                      'w-full rounded-md px-3 py-2.5 text-left transition-colors duration-150',
                      isActive ? 'bg-brand-50' : 'hover:bg-surface-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'block truncate text-sm font-medium',
                        isActive ? 'text-brand-700' : 'text-fg',
                      )}
                    >
                      {session.title}
                    </span>
                    <span className="mt-0.5 block text-xs text-fg-subtle">{formatDate(session.updatedAt)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="mt-8 text-center text-xs text-fg-subtle">
            {searchQuery ? '검색 결과가 없습니다' : '대화 내역이 없습니다'}
          </p>
        )}
      </div>
    </section>
  );

  if (!overlay) return panel;

  return (
    <div className="relative flex h-full shrink-0">
      {rail}
      <div
        aria-hidden="true"
        data-testid="history-backdrop"
        onClick={onToggle}
        className="fixed inset-0 z-10 bg-fg/20"
      />
      {panel}
    </div>
  );
};

export default ChatHistoryPanel;
