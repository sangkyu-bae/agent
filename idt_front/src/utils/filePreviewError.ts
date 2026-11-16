// Design Ref: document-file-preview §6.1 — 엑셀 모달 errorView를 이관해 문서 모달과 공유한다.
// canDownload=false면 다운로드 버튼을 숨긴다 (만료·권한 없음은 다운로드도 실패하므로).
import { ApiError } from '@/services/api/ApiError';

/** blob 크기가 DOCX_PREVIEW_MAX_BYTES를 넘을 때 */
export class DocumentTooLargeError extends Error {
  constructor() {
    super('document too large to preview');
    this.name = 'DocumentTooLargeError';
  }
}

/** docx-preview 렌더 실패(손상·미지원 구조·청크 로드 실패) */
export class DocumentRenderError extends Error {
  constructor(cause?: unknown) {
    super('document render failed', { cause });
    this.name = 'DocumentRenderError';
  }
}

export interface PreviewErrorView {
  message: string;
  canDownload: boolean;
}

const CANNOT_PREVIEW = '미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다.';

export const previewErrorView = (error: unknown): PreviewErrorView => {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return { message: '파일이 만료되었거나 찾을 수 없습니다.', canDownload: false };
    }
    if (error.status === 403) {
      return { message: '본인이 생성한 파일만 볼 수 있습니다.', canDownload: false };
    }
    if (error.status === 415 || error.status === 422) {
      return { message: CANNOT_PREVIEW, canDownload: true };
    }
  }
  if (error instanceof DocumentTooLargeError) {
    return {
      message: '파일이 커서 미리볼 수 없습니다. 다운로드해서 확인해주세요.',
      canDownload: true,
    };
  }
  if (error instanceof DocumentRenderError) {
    return { message: CANNOT_PREVIEW, canDownload: true };
  }
  return { message: '미리보기를 불러오지 못했습니다. 다시 시도해주세요.', canDownload: true };
};
