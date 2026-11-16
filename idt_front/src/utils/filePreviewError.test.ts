// Design Ref: document-file-preview §6.1 — 미리보기 오류 문구·다운로드 노출 규칙
import { describe, expect, it } from 'vitest';

import { ApiError } from '@/services/api/ApiError';
import {
  DocumentRenderError,
  DocumentTooLargeError,
  previewErrorView,
} from './filePreviewError';

describe('previewErrorView', () => {
  it('404는 만료 문구 + 다운로드 숨김', () => {
    expect(previewErrorView(new ApiError('x', 404))).toEqual({
      message: '파일이 만료되었거나 찾을 수 없습니다.',
      canDownload: false,
    });
  });

  it('403은 소유자 문구 + 다운로드 숨김', () => {
    expect(previewErrorView(new ApiError('x', 403))).toEqual({
      message: '본인이 생성한 파일만 볼 수 있습니다.',
      canDownload: false,
    });
  });

  it.each([415, 422])('%i(엑셀 미지원·손상)는 미리보기 불가 + 다운로드 표시', (status) => {
    expect(previewErrorView(new ApiError('x', status))).toEqual({
      message: '미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다.',
      canDownload: true,
    });
  });

  it('docx 크기 초과는 크기 문구 + 다운로드 표시', () => {
    expect(previewErrorView(new DocumentTooLargeError())).toEqual({
      message: '파일이 커서 미리볼 수 없습니다. 다운로드해서 확인해주세요.',
      canDownload: true,
    });
  });

  it('렌더 실패는 미리보기 불가 + 다운로드 표시', () => {
    expect(previewErrorView(new DocumentRenderError())).toEqual({
      message: '미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다.',
      canDownload: true,
    });
  });

  it.each([new ApiError('x', 500), new ApiError('x', 0), new Error('boom'), 'str'])(
    '그 외는 재시도 문구 + 다운로드 표시',
    (error) => {
      expect(previewErrorView(error)).toEqual({
        message: '미리보기를 불러오지 못했습니다. 다시 시도해주세요.',
        canDownload: true,
      });
    },
  );
});
