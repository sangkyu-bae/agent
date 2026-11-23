// document-revision §5.2 — 점검 결과 → 기본 결정 → 업로드 옵션 변환 (순수 함수)
import { describe, expect, it } from 'vitest';
import type { RevisionCheckResponse } from '@/types/knowledgeBase';
import { canUpload, initialDecision, toUploadOptions } from './revisionDecision';

const base: RevisionCheckResponse = {
  check_id: 'chk',
  verdict: 'new',
  duplicate_of: null,
  suggested_document_id: null,
  candidates: [],
  llm_status: 'skipped',
  elapsed_ms: 1,
};

const cand = (id: string) => ({
  document_id: id, filename: `${id}.pdf`, version_no: 1, version_label: null,
  filename_score: 1, content_score: 1, combined_score: 1, llm_verdict: null,
  llm_reason: null,
});

describe('revisionDecision', () => {
  it('개정 후보는 제안 문서 개정이 기본', () => {
    expect(
      initialDecision({ ...base, verdict: 'revision_candidate', suggested_document_id: 'o', candidates: [cand('o')] }),
    ).toEqual({ mode: 'revision', targetId: 'o', versionLabel: '', effectiveDate: '' });
  });

  it('신규는 새 문서가 기본이되 첫 후보를 대상으로 준비해 둔다', () => {
    expect(initialDecision({ ...base, candidates: [cand('a'), cand('b')] })).toMatchObject({
      mode: 'new', targetId: 'a',
    });
  });

  it('점검 결과가 없으면(점검 실패) 새 문서', () => {
    expect(initialDecision(null)).toMatchObject({ mode: 'new', targetId: null });
  });

  it('업로드 옵션: 개정이면 대상·라벨·시행일·check_id, 새 문서면 check_id 만', () => {
    expect(
      toUploadOptions(
        { mode: 'revision', targetId: 'o', versionLabel: ' 2026-11 개정 ', effectiveDate: '2026-12-01' },
        'chk',
      ),
    ).toEqual({
      supersedesDocumentId: 'o', versionLabel: '2026-11 개정',
      effectiveDate: '2026-12-01', revisionCheckId: 'chk',
    });
    expect(
      toUploadOptions(
        { mode: 'new', targetId: 'o', versionLabel: 'x', effectiveDate: '2026-12-01' },
        'chk',
      ),
    ).toEqual({ revisionCheckId: 'chk' });
    expect(toUploadOptions({ mode: 'new', targetId: null, versionLabel: '', effectiveDate: '' }, null)).toEqual({
      revisionCheckId: undefined,
    });
  });

  it('업로드 가능 여부: 중복 금지, 개정은 대상 필수', () => {
    const dup = { ...base, verdict: 'duplicate' as const };
    const newDecision = { mode: 'new' as const, targetId: null, versionLabel: '', effectiveDate: '' };
    expect(canUpload(dup, newDecision)).toBe(false);
    expect(canUpload(base, newDecision)).toBe(true);
    expect(canUpload(base, { ...newDecision, mode: 'revision' })).toBe(false);
    expect(canUpload(null, newDecision)).toBe(true);
  });
});
