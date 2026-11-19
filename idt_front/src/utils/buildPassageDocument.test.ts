// Design Ref: source-passage-viewer §5.4 — 텍스트 뷰어 문서 구성·구절 위치 해석
import { describe, expect, it } from 'vitest';

import type { KbDocumentChunksResponse } from '@/types/knowledgeBase';
import type { SourceViewerPassage } from '@/types/sourceViewer';

import { buildPassageDocument, toSegments } from './buildPassageDocument';

describe('toSegments', () => {
  it('겹치는 구절은 경계에서 잘라 각 조각에 구절 번호를 단다', () => {
    const segments = toSegments('0123456789', [{ start: 2, end: 6 }, null, { start: 4, end: 8 }]);
    expect(segments).toEqual([
      { text: '01', passages: [] },
      { text: '23', passages: [0] },
      { text: '45', passages: [0, 2] },
      { text: '67', passages: [2] },
      { text: '89', passages: [] },
    ]);
  });
});

const chunk = (id: string, idx: number, content: string, type = 'child') => ({
  chunk_id: id, chunk_index: idx, chunk_type: type, content, metadata: {},
});

const base = (over: Partial<KbDocumentChunksResponse>): KbDocumentChunksResponse => ({
  source: 'qdrant', search_mode: null, document_id: 'doc-1', filename: 'a.pdf',
  chunk_strategy: 'parent_child', total_chunks: 0, chunks: [], parents: null, ...over,
});

const passage = (chunk_id: string, excerpt = '', page: number | null = null): SourceViewerPassage => ({
  chunk_id, parent_id: null, page, excerpt,
});

const textOf = (doc: ReturnType<typeof buildPassageDocument>, i: number) => {
  const r = doc.ranges[i];
  return r ? doc.text.slice(r.start, r.end) : null;
};

describe('buildPassageDocument', () => {
  it('parent 를 chunk_index 순으로 잇고 child 구절은 parent 안에서 찾는다', () => {
    const data = base({
      parents: [
        { ...chunk('p2', 1, '둘째 조항 본문입니다.', 'parent'), children: [chunk('c3', 0, '둘째 조항')] },
        { ...chunk('p1', 0, '첫째 조항 본문입니다.', 'parent'), children: [chunk('c1', 0, '본문입니다.')] },
      ],
    });
    const doc = buildPassageDocument(data, [passage('c1'), passage('p2')]);
    expect(doc.text).toBe('첫째 조항 본문입니다.\n\n둘째 조항 본문입니다.');
    expect(textOf(doc, 0)).toBe('본문입니다.');
    expect(textOf(doc, 1)).toBe('둘째 조항 본문입니다.');
  });

  it('parent 가 없으면 chunks 를 chunk_index 순으로 잇는다', () => {
    const data = base({ chunks: [chunk('b', 1, '나중'), chunk('a', 0, '먼저')] });
    const doc = buildPassageDocument(data, [passage('b')]);
    expect(doc.text).toBe('먼저\n\n나중');
    expect(textOf(doc, 0)).toBe('나중');
  });

  it('chunk_id 가 맞지 않으면 excerpt 로 찾는다(routed 검색)', () => {
    const data = base({ chunks: [chunk('a', 0, '제3조 담보는\n감정가로 평가한다.')] });
    const doc = buildPassageDocument(data, [passage('section-ref-3', '담보는 감정가로')]);
    expect(textOf(doc, 0)).toBe('담보는\n감정가로');
  });

  it('찾지 못한 구절은 null 범위', () => {
    const data = base({ chunks: [chunk('a', 0, '본문')] });
    const doc = buildPassageDocument(data, [passage('zzz', '없는 문장')]);
    expect(doc.ranges[0]).toBeNull();
  });
});
