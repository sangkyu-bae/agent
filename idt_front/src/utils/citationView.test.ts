import { describe, expect, it } from 'vitest';

import type { DocumentSource } from '@/types/chat';

import { buildCitationView } from './citationView';

const doc = (key: string, citation?: DocumentSource['citation']): DocumentSource => ({
  kind: 'document',
  source: `${key}.pdf`,
  content: '발췌',
  chunk_id: key,
  citation,
});
const web: DocumentSource = { kind: 'web', source: '웹', content: '', chunk_id: 'w', url: 'https://x' };

describe('buildCitationView', () => {
  it('citation 이 없으면 status null — 기존 렌더 대상', () => {
    const view = buildCitationView([doc('a'), web]);
    expect(view.status).toBeNull();
    expect(view.rows).toEqual([]);
  });

  it('verified: 인용 행은 번호 순, 인용 없는 문서는 미사용, 비문서 칩은 기타', () => {
    const a = doc('a', {
      status: 'verified',
      entries: [{ no: 2, chunk_id: 'a2', page: 4, evidence: '근거 2' }],
    });
    const b = doc('b', {
      status: 'verified',
      entries: [{ no: 1, chunk_id: 'b1', page: null, evidence: null }],
    });
    const c = doc('c', { status: 'verified', entries: [] });
    const view = buildCitationView([a, b, c, web]);
    expect(view.status).toBe('verified');
    expect(view.rows.map((r) => [r.no, r.source.chunk_id])).toEqual([
      [1, 'b'],
      [2, 'a'],
    ]);
    expect(view.unused.map((s) => s.chunk_id)).toEqual(['c']);
    expect(view.others).toEqual([web]);
  });

  it('none: 행 없음, 모든 문서는 미사용(검색된 구절)', () => {
    const view = buildCitationView([
      doc('a', { status: 'none', entries: [] }),
      doc('b', { status: 'none', entries: [] }),
    ]);
    expect(view.status).toBe('none');
    expect(view.rows).toEqual([]);
    expect(view.unused.map((s) => s.chunk_id)).toEqual(['a', 'b']);
  });

  it('같은 번호가 두 번 오면 한 행만', () => {
    const a = doc('a', {
      status: 'verified',
      entries: [
        { no: 1, chunk_id: 'a1', page: 1, evidence: 'x' },
        { no: 1, chunk_id: 'a1', page: 1, evidence: 'x' },
      ],
    });
    expect(buildCitationView([a]).rows).toHaveLength(1);
  });
});
