import { useState, useRef, type ChangeEvent, type KeyboardEvent } from 'react';

interface ChatInputProps {
  onSend: (content: string) => void;
  isLoading?: boolean;
  useRag?: boolean;
  onToggleRag?: () => void;
  // ws-agent-excel-attachment: 엑셀 첨부 (agent 선택 시에만 노출)
  attachmentEnabled?: boolean;
  attachmentName?: string | null;
  attachmentUploading?: boolean;
  onAttachFile?: (file: File) => void;
  onRemoveAttachment?: () => void;
}

const ChatInput = ({
  onSend,
  isLoading = false,
  useRag = false,
  onToggleRag,
  attachmentEnabled = false,
  attachmentName = null,
  attachmentUploading = false,
  onAttachFile,
  onRemoveAttachment,
}: ChatInputProps) => {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handlePickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onAttachFile) onAttachFile(file);
    e.target.value = ''; // 같은 파일 재선택 허용
  };

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  };

  const canSend = value.trim().length > 0 && !isLoading;

  return (
    <div className="px-4 pb-5 pt-2 sm:px-6">
      <div className="mx-auto max-w-3xl">
        {/* 입력창 */}
        <div
          className="overflow-hidden rounded-2xl border border-zinc-300 bg-white shadow-xl shadow-zinc-200/50 transition-all duration-200 focus-within:border-violet-400 focus-within:shadow-violet-100/60"
        >
          {/* ws-agent-excel-attachment: 첨부 칩 */}
          {attachmentEnabled && (attachmentName || attachmentUploading) && (
            <div className="flex items-center gap-2 px-5 pt-3">
              <span className="inline-flex max-w-xs items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-1.5 text-[13px] text-violet-700">
                <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13" />
                </svg>
                <span className="truncate">
                  {attachmentUploading ? '업로드 중…' : attachmentName}
                </span>
                {!attachmentUploading && onRemoveAttachment && (
                  <button
                    type="button"
                    onClick={onRemoveAttachment}
                    className="shrink-0 text-violet-400 hover:text-violet-700"
                    aria-label="첨부 제거"
                  >
                    ✕
                  </button>
                )}
              </span>
            </div>
          )}

          {/* 텍스트 입력 */}
          <div className="px-5 pt-4 pb-2">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onInput={handleInput}
              onKeyDown={handleKeyDown}
              rows={1}
              placeholder="상플AI에게 메시지 보내기..."
              disabled={isLoading}
              className="block w-full resize-none bg-transparent text-[15px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none disabled:opacity-60"
            />
          </div>

          {/* 하단 툴바 */}
          <div className="flex items-center justify-between px-4 py-3">
            {/* 왼쪽: 도구들 */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onToggleRag}
                title="문서 검색 RAG 모드"
                className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-[13px] font-medium transition-all duration-150 ${
                  useRag
                    ? 'bg-violet-600 text-white shadow-sm shadow-violet-200'
                    : 'border border-zinc-200 bg-zinc-50 text-zinc-500 hover:border-zinc-300 hover:bg-zinc-100 hover:text-zinc-700'
                }`}
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
                </svg>
                문서 검색
              </button>

              {/* ws-agent-excel-attachment: 엑셀 첨부 (agent 모드에서만) */}
              {attachmentEnabled && (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".xlsx,.xls"
                    className="hidden"
                    onChange={handlePickFile}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isLoading || attachmentUploading}
                    title="엑셀 첨부 (데이터 분석)"
                    className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-3.5 py-2 text-[13px] font-medium text-zinc-500 transition-all duration-150 hover:border-zinc-300 hover:bg-zinc-100 hover:text-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13" />
                    </svg>
                    엑셀
                  </button>
                </>
              )}
            </div>

            {/* 오른쪽: 힌트 + 전송 */}
            <div className="flex items-center gap-3">
              <span className="hidden text-[12px] text-zinc-400 sm:block">
                {value.length > 0 ? `${value.length}자` : 'Enter 전송 · Shift+Enter 줄바꿈'}
              </span>

              <button
                type="button"
                onClick={handleSend}
                disabled={!canSend}
                className={`flex h-9 w-9 items-center justify-center rounded-xl transition-all duration-150 ${
                  canSend
                    ? 'bg-violet-600 text-white shadow-sm hover:bg-violet-700 active:scale-95'
                    : 'cursor-not-allowed bg-zinc-200 text-zinc-400'
                }`}
              >
                {isLoading ? (
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M3.478 2.405a.75.75 0 0 0-.926.94l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.405Z" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>

        <p className="mt-2.5 text-center text-[12px] text-zinc-400">
          상플AI는 실수를 할 수 있습니다. 중요한 정보는 반드시 확인하세요.
        </p>
      </div>
    </div>
  );
};

export default ChatInput;
