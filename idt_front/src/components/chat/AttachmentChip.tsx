// Design Ref: chat-image-attachment §5.3 — 엑셀/이미지 첨부 칩 1개 (썸네일·이름·제거)
import { Paperclip, X } from 'lucide-react';
import Badge from '@/components/ui/Badge';
import type { PendingAttachment } from '@/types/agentAttachment';

interface AttachmentChipProps {
  attachment: PendingAttachment;
  uploading?: boolean;
  onRemove?: (id: string) => void;
}

const AttachmentChip = ({ attachment, uploading = false, onRemove }: AttachmentChipProps) => {
  const isImage = attachment.ref.type === 'image';
  return (
    <Badge tone="brand" className="max-w-xs gap-1.5 py-1">
      {isImage && attachment.previewUrl ? (
        <img
          src={attachment.previewUrl}
          alt={`${attachment.name} 미리보기`}
          className="h-10 w-10 shrink-0 rounded object-cover"
        />
      ) : (
        <Paperclip className="h-3.5 w-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
      )}
      <span className="truncate">{uploading ? '업로드 중…' : attachment.name}</span>
      {!uploading && onRemove && (
        <button
          type="button"
          onClick={() => onRemove(attachment.id)}
          aria-label={`첨부 제거: ${attachment.name}`}
          className="-my-1 ml-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-brand-500 hover:bg-brand-100 hover:text-brand-700"
        >
          <X className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
        </button>
      )}
    </Badge>
  );
};

export default AttachmentChip;
