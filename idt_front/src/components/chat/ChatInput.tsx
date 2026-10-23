// Design Ref: ui-redesign-chat §5.4 — Textarea(unstyled, autoResize) + Button + IconButton. props·전송 로직 변경 없음.
import { useState, useRef, type ChangeEvent, type KeyboardEvent } from 'react';
import { Clock, FileText, Loader2, Paperclip, Send, X } from 'lucide-react';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import IconButton from '@/components/ui/IconButton';
import Textarea from '@/components/ui/Textarea';
import { cn } from '@/utils/cn';

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
  // background-jobs S9: 백그라운드 전환 (agent 모드에서만 노출)
  backgroundEnabled?: boolean;
  onSendBackground?: (content: string) => void;
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
  backgroundEnabled = false,
  onSendBackground,
}: ChatInputProps) => {
  const [value, setValue] = useState('');
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
    setValue(''); // Textarea autoResize가 value 변화로 높이를 되돌린다
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const canSend = value.trim().length > 0 && !isLoading;

  // background-jobs S9: 현재 입력을 백그라운드 작업으로 등록하고 입력창을 비운다.
  const handleSendBackground = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading || !onSendBackground) return;
    onSendBackground(trimmed);
    setValue('');
  };

  return (
    <div className="px-4 pb-5 pt-2 sm:px-6">
      <div className="mx-auto max-w-3xl">
        <div className="overflow-hidden rounded-xl border border-border-strong bg-surface shadow-lg transition-colors duration-150 focus-within:border-brand-400">
          {/* ws-agent-excel-attachment: 첨부 칩 */}
          {attachmentEnabled && (attachmentName || attachmentUploading) && (
            <div className="flex items-center gap-2 px-4 pt-3">
              <Badge tone="brand" className="max-w-xs gap-1.5 py-1">
                <Paperclip className="h-3.5 w-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
                <span className="truncate">{attachmentUploading ? '업로드 중…' : attachmentName}</span>
                {!attachmentUploading && onRemoveAttachment && (
                  <button
                    type="button"
                    onClick={onRemoveAttachment}
                    aria-label="첨부 제거"
                    className="-my-1 ml-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-brand-500 hover:bg-brand-100 hover:text-brand-700"
                  >
                    <X className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                  </button>
                )}
              </Badge>
            </div>
          )}

          {/* 텍스트 입력 */}
          <div className="px-4 pt-4 pb-1">
            <Textarea
              unstyled
              autoResize
              maxRows={8}
              aria-label="메시지 입력"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="상플AI에게 메시지 보내기..."
              disabled={isLoading}
            />
          </div>

          {/* 하단 툴바 — 768에서도 한 줄 유지 (Plan SC: FR-11) */}
          <div className="flex items-center justify-between gap-2 px-3 py-2.5">
            <div className="flex min-w-0 items-center gap-2">
              <Button
                variant={useRag ? 'primary' : 'secondary'}
                size="sm"
                onClick={onToggleRag}
                aria-pressed={useRag}
                title="문서 검색 RAG 모드"
                leadingIcon={<FileText className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />}
              >
                문서 검색
              </Button>

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
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isLoading || attachmentUploading}
                    title="엑셀 첨부 (데이터 분석)"
                    leadingIcon={<Paperclip className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />}
                  >
                    엑셀
                  </Button>
                </>
              )}
            </div>

            <div className="flex shrink-0 items-center gap-2">
              {/* background-jobs S9: 백그라운드 전환 (agent 모드에서만) */}
              {backgroundEnabled && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleSendBackground}
                  disabled={!canSend}
                  title="백그라운드로 실행 — 채팅방을 나가도 계속 실행됩니다"
                  aria-label="백그라운드로 실행"
                  leadingIcon={<Clock className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />}
                  className={canSend ? 'border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100' : undefined}
                >
                  백그라운드
                </Button>
              )}
              {/* G-02: 768 이하에서는 툴바를 한 줄로 유지하기 위해 안내문을 숨긴다 */}
              <span className="hidden text-xs text-fg-subtle lg:block">
                {value.length > 0 ? `${value.length}자` : 'Enter 전송 · Shift+Enter 줄바꿈'}
              </span>

              <IconButton
                aria-label="전송"
                onClick={handleSend}
                disabled={!canSend}
                className={cn(
                  canSend
                    ? 'bg-brand-600 text-white shadow-sm hover:bg-brand-700 hover:text-white active:scale-95'
                    : 'bg-surface-sunken text-fg-subtle',
                )}
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} aria-hidden="true" />
                ) : (
                  <Send className="h-4 w-4" strokeWidth={2} aria-hidden="true" />
                )}
              </IconButton>
            </div>
          </div>
        </div>

        <p className="mt-2.5 text-center text-xs text-fg-subtle">
          상플AI는 실수를 할 수 있습니다. 중요한 정보는 반드시 확인하세요.
        </p>
      </div>
    </div>
  );
};

export default ChatInput;
