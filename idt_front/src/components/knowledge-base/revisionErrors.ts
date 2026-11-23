// Design Ref: document-revision §6.1 — 409 detail.reason 을 운영자용 문장으로.
import { ApiError } from '@/services/api/ApiError';

const REASON_MESSAGES: Record<string, string> = {
  // 되돌리기
  first_version: '첫 버전은 되돌릴 수 없습니다.',
  no_previous: '되돌릴 이전 버전이 없습니다.',
  // 연결·대상 공통
  not_found: '문서를 찾을 수 없습니다. 목록을 새로 고쳐 주세요.',
  not_active: '검색에서 제외된 버전에는 적용할 수 없습니다.',
  other_kb: '다른 지식베이스의 문서입니다.',
  same_document: '같은 문서끼리는 연결할 수 없습니다.',
  source_has_history: '이 문서에 이미 이전 버전이 있어 다른 문서와 연결할 수 없습니다.',
  target_not_latest: '대상 문서가 최신 버전이 아닙니다. 최신 버전을 고르세요.',
  not_latest: '대상 문서가 최신 버전이 아닙니다. 최신 버전을 고르세요.',
};

const FALLBACK = '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.';

export const revisionErrorMessage = (err: unknown): string => {
  if (err instanceof ApiError && err.detail && typeof err.detail === 'object') {
    const reason = (err.detail as { reason?: unknown }).reason;
    if (typeof reason === 'string' && REASON_MESSAGES[reason]) {
      return REASON_MESSAGES[reason];
    }
  }
  if (err instanceof Error && err.message) return err.message;
  return FALLBACK;
};
