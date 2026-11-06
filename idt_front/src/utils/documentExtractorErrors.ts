/**
 * 문서추출기 추출 API 에러 코드 → 사용자 문구 (wizard-template-request §6.1).
 *
 * 위저드 양식 카드와 스튜디오 추출기 패널이 공유한다. 코드는 백엔드
 * `document_extractor_router.extract_document` 의 5종과 1:1.
 */
import { ApiError } from '@/services/api/ApiError';

export const EXTRACT_ERROR_MESSAGE: Record<string, string> = {
  INVALID_DOCUMENT: 'PDF 또는 DOCX 파일만 올릴 수 있습니다.',
  DOCUMENT_TOO_LARGE: '파일이 너무 큽니다. 상한을 확인해 주세요.',
  MCP_TOOL_NOT_CONFIGURED:
    '문서 변환 도구가 설정되지 않았습니다. 관리자에게 문의하세요.',
  MCP_CONVERSION_FAILED:
    '문서 변환에 실패했습니다. 다른 파일로 다시 시도해 주세요.',
  SLOT_EXTRACTION_FAILED: '채움 항목을 찾지 못했습니다. 다시 시도해 주세요.',
};

/** 프론트 토큰화 실패 (confirmTemplateDraft NO_USABLE_SLOTS). */
export const NO_USABLE_SLOTS_MESSAGE =
  '확정할 수 있는 항목이 없습니다. 예시값이 문서에 있는 항목이 1개 이상 필요합니다.';

const FALLBACK_MESSAGE = '양식 분석에 실패했습니다. 다시 시도해 주세요.';

/**
 * 에러 → 문구. 코드가 있으면 코드 매핑, 없으면 message 원문, 둘 다 없으면 기본 문구.
 * ApiError 가 아닌 Error(네트워크 등)는 message 를 그대로 쓴다.
 */
export const extractErrorMessage = (error: unknown): string => {
  if (error instanceof ApiError) {
    if (error.code && EXTRACT_ERROR_MESSAGE[error.code]) {
      return EXTRACT_ERROR_MESSAGE[error.code];
    }
    return error.message || FALLBACK_MESSAGE;
  }
  if (error instanceof Error && error.message) return error.message;
  return FALLBACK_MESSAGE;
};
