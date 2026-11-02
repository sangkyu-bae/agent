// Design Ref: ui-redesign-chat §5.4 — Textarea(unstyled, autoResize) + Button + IconButton.
// Design Ref: chat-image-attachment §5.1/§5.4 — 이미지 첨부(선택·붙여넣기·드롭), 첨부 칩 배열, 비전 미지원 비활성.
import {
  useState,
  useRef,
  type ChangeEvent,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from 'react';
import { Clock, FileText, Image as ImageIcon, Loader2, Paperclip, Send } from 'lucide-react';
import AttachmentChip from '@/components/chat/AttachmentChip';
import Button from '@/components/ui/Button';
import IconButton from '@/components/ui/IconButton';
import Textarea from '@/components/ui/Textarea';
import { IMAGE_ATTACHMENT_LIMITS, type PendingAttachment } from '@/types/agentAttachment';
import { isImageFile } from '@/utils/imageAttachmentValidators';
import { cn } from '@/utils/cn';

interface ChatInputProps {
  onSend: (content: string) => void;
  isLoading?: boolean;
  useRag?: boolean;
  onToggleRag?: () => void;
  // ws-agent-excel-attachment / chat-image-attachment: 첨부 (agent 선택 시에만 노출)
  attachmentEnabled?: boolean;
  attachments?: PendingAttachment[];
  attachmentUploading?: boolean;
  /** 엑셀·이미지 공통 — 어떤 파일인지는 페이지가 판별한다 */
  onAttachFiles?: (files: File[]) => void;
  onRemoveAttachment?: (id: string) => void;
  /** 비전 지원 모델일 때만 true. false 면 버튼 비활성 + 붙여넣기/드롭 무시 */
  imageAttachmentEnabled?: boolean;
  imageDisabledReason?: string | null;
  /** 검증·업로드 실패 안내 (인라인) */
  attachmentNotice?: string | null;
  // background-jobs S9: 백그라운드 전환 (agent 모드에서만 노출)
  backgroundEnabled?: boolean;
  onSendBackground?: (content: string) => void;
}

const filesOf = (list: FileList | File[] | null | undefined): File[] => Array.from(list ?? []);

const ChatInput = ({
  onSend,
  isLoading = false,
  useRag = false,
  onToggleRag,
  attachmentEnabled = false,
  attachments = [],
  attachmentUploading = false,
  onAttachFiles,
  onRemoveAttachment,
  imageAttachmentEnabled = true,
  imageDisabledReason = null,
  attachmentNotice = null,
  backgroundEnabled = false,
  onSendBackground,
}: ChatInputProps) => {
  const [value, setValue] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const excelInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // 파일을 받을 수 있는 상태. 어떤 파일인지(엑셀/이미지/기타)와 비전 지원 여부는 페이지가
  // 판별해 안내한다 (Analysis G-I5: 비이미지 드롭·비전 미지원 드롭도 조용히 버리지 않는다).
  const canReceiveFiles = attachmentEnabled && !!onAttachFiles;

  const handlePickFiles = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0 && onAttachFiles) onAttachFiles(files);
    e.target.value = ''; // 같은 파일 재선택 허용
  };

  // §5.4: 클립보드에 이미지 파일이 있을 때만 가로채고, 텍스트 붙여넣기는 기본 동작 유지.
  // 비전 미지원이어도 페이지로 넘겨 사유를 안내한다 (G-I5).
  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    if (!canReceiveFiles) return;
    const images = filesOf(e.clipboardData?.files).filter(isImageFile);
    if (images.length === 0) return;
    e.preventDefault();
    onAttachFiles?.(images);
  };

  // 드래그 기본 동작(브라우저가 파일을 여는 것)은 첨부 가능 여부와 무관하게 막는다 (G-I5)
  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!attachmentEnabled) return;
    e.preventDefault();
    if (imageAttachmentEnabled) setIsDragging(true);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    setIsDragging(false);
    if (!attachmentEnabled) return;
    e.preventDefault();
    if (!canReceiveFiles) return;
    const files = filesOf(e.dataTransfer?.files);
    if (files.length > 0) onAttachFiles?.(files); // 비이미지·엑셀 포함 — 페이지가 분류·안내
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

  // Analysis G-I2 (Design §5.4 #7): 업로드가 끝나기 전에는 전송하지 않는다 — 업로드 중인
  // 이미지가 빠진 채 전송되는 것을 막는다.
  const canSend = value.trim().length > 0 && !isLoading && !attachmentUploading;

  // background-jobs S9: 현재 입력을 백그라운드 작업으로 등록하고 입력창을 비운다.
  const handleSendBackground = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading || !onSendBackground) return;
    onSendBackground(trimmed);
    setValue('');
  };

  const showChips = attachmentEnabled && (attachments.length > 0 || attachmentUploading);

  return (
    <div className="px-4 pb-5 pt-2 sm:px-6">
      <div className="mx-auto max-w-3xl">
        {/* chat-image-attachment §5.4: 검증·업로드 실패 안내 */}
        {attachmentNotice && (
          <p role="status" className="mb-2 text-xs text-danger-600">
            {attachmentNotice}
          </p>
        )}
        <div
          data-testid="chat-input-dropzone"
          onDragOver={handleDragOver}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={cn(
            'relative overflow-hidden rounded-xl border bg-surface shadow-lg transition-colors duration-150 focus-within:border-brand-400',
            isDragging ? 'border-dashed border-brand-400' : 'border-border-strong',
          )}
        >
          {isDragging && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-brand-50/80 text-sm font-medium text-brand-700">
              이미지를 놓으세요
            </div>
          )}

          {/* 첨부 칩 행 — 엑셀 1 + 이미지 N */}
          {showChips && (
            <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
              {attachments.map((a) => (
                <AttachmentChip key={a.id} attachment={a} onRemove={onRemoveAttachment} />
              ))}
              {attachmentUploading && (
                <AttachmentChip
                  attachment={{ id: '__uploading', ref: { type: 'image', file_id: '' }, name: '' }}
                  uploading
                />
              )}
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
              onPaste={handlePaste}
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
                    ref={excelInputRef}
                    data-testid="excel-file-input"
                    type="file"
                    accept=".xlsx,.xls"
                    className="hidden"
                    onChange={handlePickFiles}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => excelInputRef.current?.click()}
                    disabled={isLoading || attachmentUploading}
                    title="엑셀 첨부 (데이터 분석)"
                    leadingIcon={<Paperclip className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />}
                  >
                    엑셀
                  </Button>

                  {/* chat-image-attachment: 이미지 첨부 — 비전 미지원이면 비활성 + 사유 */}
                  <input
                    ref={imageInputRef}
                    data-testid="image-file-input"
                    type="file"
                    accept={IMAGE_ATTACHMENT_LIMITS.accept}
                    multiple
                    className="hidden"
                    onChange={handlePickFiles}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => imageInputRef.current?.click()}
                    disabled={isLoading || attachmentUploading || !imageAttachmentEnabled}
                    aria-label="이미지 첨부"
                    title={
                      imageAttachmentEnabled
                        ? `이미지 첨부 (png/jpg/webp, 최대 ${IMAGE_ATTACHMENT_LIMITS.maxCount}장)`
                        : (imageDisabledReason ?? '이미지 첨부를 사용할 수 없습니다')
                    }
                    leadingIcon={<ImageIcon className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />}
                  >
                    이미지
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
