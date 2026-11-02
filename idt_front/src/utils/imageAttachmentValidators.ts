// chat-image-attachment Design §5.4 — 이미지 첨부 사전 검증 (순수 함수, 서버 검증과 별개의 UX 가드)
import {
  IMAGE_ATTACHMENT_LIMITS,
  IMAGE_REJECT_REASON,
  type ImageRejectReason,
} from '@/types/agentAttachment';

const EXCEL_EXTENSIONS = ['.xlsx', '.xls'] as const;

const extensionOf = (name: string): string => {
  const idx = name.lastIndexOf('.');
  return idx < 0 ? '' : name.slice(idx).toLowerCase();
};

export const isImageFile = (file: File): boolean => {
  const mimes: readonly string[] = IMAGE_ATTACHMENT_LIMITS.mimeTypes;
  const exts: readonly string[] = IMAGE_ATTACHMENT_LIMITS.extensions;
  return mimes.includes(file.type) || exts.includes(extensionOf(file.name));
};

export const isExcelFile = (file: File): boolean => {
  const exts: readonly string[] = EXCEL_EXTENSIONS;
  return exts.includes(extensionOf(file.name));
};

export interface ImageValidationResult {
  accepted: File[];
  rejected: Array<{ file: File; reason: ImageRejectReason }>;
}

/**
 * 형식 → 크기 → 장수 순으로 검사한다. 장수는 현재 첨부된 이미지 수와 합산하며
 * 앞에서부터 상한까지만 수락한다.
 */
export const validateImageFiles = (
  files: File[],
  currentImageCount: number,
): ImageValidationResult => {
  const accepted: File[] = [];
  const rejected: ImageValidationResult['rejected'] = [];
  let count = currentImageCount;
  for (const file of files) {
    if (!isImageFile(file)) {
      rejected.push({ file, reason: IMAGE_REJECT_REASON.UNSUPPORTED_TYPE });
      continue;
    }
    if (file.size > IMAGE_ATTACHMENT_LIMITS.maxBytes) {
      rejected.push({ file, reason: IMAGE_REJECT_REASON.TOO_LARGE });
      continue;
    }
    if (count >= IMAGE_ATTACHMENT_LIMITS.maxCount) {
      rejected.push({ file, reason: IMAGE_REJECT_REASON.TOO_MANY });
      continue;
    }
    accepted.push(file);
    count += 1;
  }
  return { accepted, rejected };
};

export const rejectReasonMessage = (reason: ImageRejectReason): string => {
  switch (reason) {
    case IMAGE_REJECT_REASON.UNSUPPORTED_TYPE:
      return '이미지는 png, jpg, webp 형식만 첨부할 수 있습니다.';
    case IMAGE_REJECT_REASON.TOO_LARGE:
      return '이미지는 장당 10MB 이하여야 합니다.';
    case IMAGE_REJECT_REASON.TOO_MANY:
      return `이미지는 최대 ${IMAGE_ATTACHMENT_LIMITS.maxCount}장까지 첨부할 수 있습니다.`;
    default:
      return '첨부할 수 없는 파일입니다.';
  }
};
