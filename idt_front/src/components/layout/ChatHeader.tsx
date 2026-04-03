interface ChatHeaderProps {
  title?: string;
  messageCount?: number;
}

const ChatHeader = ({ title = '새 대화', messageCount = 0 }: ChatHeaderProps) => {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-100 bg-white px-5">
      <div className="flex items-center gap-3 min-w-0">
        <h1 className="truncate text-[15px] font-semibold text-zinc-900">{title}</h1>
        {messageCount > 0 && (
          <span className="shrink-0 rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] font-semibold text-zinc-500">
            {messageCount}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1.5">
        {/* 상태 뱃지 */}
        <div className="flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 px-3.5 py-1.5 text-[12px] font-medium text-zinc-600">
          <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-200 animate-pulse" />
          RAG · Agent
        </div>

        <button
          title="대화 내보내기"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-all hover:bg-zinc-100 hover:text-zinc-600"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
        </button>

        <button
          title="대화 삭제"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-all hover:bg-red-50 hover:text-red-500"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
          </svg>
        </button>
      </div>
    </header>
  );
};

export default ChatHeader;
