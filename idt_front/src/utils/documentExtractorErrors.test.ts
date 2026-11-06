// wizard-template-request Design §6.1 — 추출 에러 코드 → 문구
import { describe, expect, it } from 'vitest';
import { ApiError } from '@/services/api/ApiError';
import { EXTRACT_ERROR_MESSAGE, extractErrorMessage } from './documentExtractorErrors';

describe('extractErrorMessage', () => {
  it.each([
    ['INVALID_DOCUMENT', 400],
    ['DOCUMENT_TOO_LARGE', 413],
    ['MCP_TOOL_NOT_CONFIGURED', 400],
    ['MCP_CONVERSION_FAILED', 502],
    ['SLOT_EXTRACTION_FAILED', 502],
  ])('코드 %s 는 고정 문구로', (code, status) => {
    const err = new ApiError('raw detail', status, code);
    expect(extractErrorMessage(err)).toBe(EXTRACT_ERROR_MESSAGE[code]);
  });

  it('모르는 코드면 message 원문', () => {
    expect(extractErrorMessage(new ApiError('뭔가 잘못됨', 500, 'UNKNOWN'))).toBe('뭔가 잘못됨');
  });

  it('ApiError 가 아닌 Error 는 message, 그 외는 기본 문구', () => {
    expect(extractErrorMessage(new Error('Network Error'))).toBe('Network Error');
    expect(extractErrorMessage('???')).toBe('양식 분석에 실패했습니다. 다시 시도해 주세요.');
  });
});
