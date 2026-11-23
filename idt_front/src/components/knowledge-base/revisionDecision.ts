// Design Ref: document-revision §5.2 — 점검 결과 → 운영자 결정 → 업로드 옵션.
// "LLM은 제안, 사람이 확정": 기본값만 제안에 맞추고 최종 선택은 운영자가 바꿀 수 있다.
import type {
  RevisionCheckResponse,
  RevisionUploadOptions,
} from '@/types/knowledgeBase';

export interface RevisionDecision {
  mode: 'revision' | 'new';
  /** 개정 대상(구버전) document_id */
  targetId: string | null;
  versionLabel: string;
  /** YYYY-MM-DD, 빈 문자열 = 미입력 */
  effectiveDate: string;
}

/** 점검 결과(실패 시 null)로 기본 결정을 만든다 */
export const initialDecision = (
  result: RevisionCheckResponse | null,
): RevisionDecision => {
  const empty = { versionLabel: '', effectiveDate: '' };
  if (result?.verdict === 'revision_candidate' && result.suggested_document_id) {
    return { mode: 'revision', targetId: result.suggested_document_id, ...empty };
  }
  return {
    mode: 'new',
    targetId: result?.candidates[0]?.document_id ?? null,
    ...empty,
  };
};

export const toUploadOptions = (
  decision: RevisionDecision,
  checkId: string | null,
): RevisionUploadOptions => {
  const revisionCheckId = checkId ?? undefined;
  if (decision.mode !== 'revision' || !decision.targetId) {
    return { revisionCheckId };
  }
  return {
    supersedesDocumentId: decision.targetId,
    versionLabel: decision.versionLabel.trim() || null,
    effectiveDate: decision.effectiveDate || null,
    revisionCheckId,
  };
};

/** 완전 동일 파일은 막고, 개정을 고르면 대상이 있어야 한다 */
export const canUpload = (
  result: RevisionCheckResponse | null,
  decision: RevisionDecision,
): boolean => {
  if (result?.verdict === 'duplicate') return false;
  if (decision.mode === 'revision') return !!decision.targetId;
  return true;
};
