import { describe, expect, it } from 'vitest';

import type { DocumentSource } from '@/types/chat';
import type { SourceViewerRef } from '@/types/sourceViewer';

import { buildCitationView } from './citationView';
import { citationViewerTarget } from './citationViewerTarget';

const viewer: SourceViewerRef = {
  document_id: 'doc-a',
  kb_id: 'kb',
  original: 'pdf',
  passages: [
    { chunk_id: 'a1', parent_id: 'p1', page: 2, excerpt: '청크1' },
    { chunk_id: 'a2', parent_id: null, page: 5, excerpt: '청크2' },
    { chunk_id: 'a9', parent_id: null, page: 9, excerpt: '미인용' },
  ],
};
const a: DocumentSource = {
  kind: 'document',
  source: 'a.pdf',
  content: '',
  chunk_id: 'doc-a',
  viewer,
  citation: {
    status: 'verified',
    entries: [
      { no: 1, chunk_id: 'a1', page: 2, evidence: '근거 1' },
      { no: 3, chunk_id: 'a3', page: null, evidence: null },
    ],
  },
};
const b: DocumentSource = {
  kind: 'document',
  source: 'b.pdf',
  content: '',
  chunk_id: 'doc-b',
  citation: { status: 'verified', entries: [{ no: 2, chunk_id: 'b1', page: 1, evidence: 'b' }] },
};

describe('citationViewerTarget', () => {
  const rows = buildCitationView([a, b]).rows;

  it('그 문서의 인용 구절만 번호 순으로, 근거 문장을 focus 로 싣고 누른 인용에서 시작', () => {
    const result = citationViewerTarget(rows, 3)!;
    expect(result.index).toBe(1);
    expect(result.target.filename).toBe('a.pdf');
    expect(result.target.viewer.passages).toEqual([
      { chunk_id: 'a1', parent_id: 'p1', page: 2, excerpt: '청크1', focus: '근거 1' },
      // 뷰어 구절에 없는 청크는 인용 정보로 만든다(위치 못 찾으면 안내)
      { chunk_id: 'a3', parent_id: null, page: null, excerpt: '', focus: null },
    ]);
    expect(result.target.viewer.document_id).toBe('doc-a');
  });

  it('원문 뷰어 정보가 없는 문서·없는 번호는 null', () => {
    expect(citationViewerTarget(rows, 2)).toBeNull();
    expect(citationViewerTarget(rows, 99)).toBeNull();
  });
});
