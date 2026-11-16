// Design Ref: document-file-preview §5.3 — 판별 기준은 링크 텍스트(=파일명) 확장자 (excel-preview §5.3과 동일)
import type { PreviewKind } from '@/types/filePreview';

const EXTENSION_KIND: Record<string, PreviewKind> = {
  xlsx: 'xlsx',
  docx: 'docx',
  pdf: 'pdf',
};

/** 파일명 확장자(대소문자 무시)로 미리보기 종류를 정한다. 대상이 아니면 null. */
export const previewKindOf = (filename: string): PreviewKind | null => {
  const match = /\.([a-z0-9]+)$/i.exec(filename);
  if (!match) return null;
  return EXTENSION_KIND[match[1].toLowerCase()] ?? null;
};
