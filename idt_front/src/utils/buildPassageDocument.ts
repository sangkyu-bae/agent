// Design Ref: source-passage-viewer §5.4 — 텍스트 뷰어 문서 구성과 구절 위치 해석.
// 해석 순서: 블록(parent·평면 청크) id → child id(부모 안에서 위치 탐색) → excerpt 텍스트 → null.
import type { KbBrowseChunkDetail, KbDocumentChunksResponse } from '@/types/knowledgeBase';
import type { SourceViewerPassage, TextRange } from '@/types/sourceViewer';

import { findPassage } from './passageMatch';

const BLOCK_SEPARATOR = '\n\n';

interface Block {
  chunkId: string;
  start: number;
  end: number;
  children: KbBrowseChunkDetail[];
}

export interface PassageDocument {
  text: string;
  /** passages 와 같은 순서. 위치를 못 찾은 구절은 null */
  ranges: (TextRange | null)[];
}

const byIndex = <T extends { chunk_index: number }>(items: T[]) =>
  [...items].sort((a, b) => a.chunk_index - b.chunk_index);

const layoutBlocks = (data: KbDocumentChunksResponse) => {
  const sources = data.parents?.length
    ? byIndex(data.parents).map((p) => ({ id: p.chunk_id, content: p.content, children: p.children }))
    : byIndex(data.chunks).map((c) => ({ id: c.chunk_id, content: c.content, children: [] }));
  let text = '';
  const blocks: Block[] = sources.map((s, i) => {
    if (i > 0) text += BLOCK_SEPARATOR;
    const start = text.length;
    text += s.content;
    return { chunkId: s.id, start, end: text.length, children: s.children };
  });
  return { text, blocks };
};

const offset = (range: TextRange | null, by: number): TextRange | null =>
  range ? { start: range.start + by, end: range.end + by } : null;

const resolve = (text: string, blocks: Block[], passage: SourceViewerPassage): TextRange | null => {
  const block = blocks.find((b) => b.chunkId === passage.chunk_id);
  if (block) return { start: block.start, end: block.end };
  for (const b of blocks) {
    const child = b.children.find((c) => c.chunk_id === passage.chunk_id);
    if (child) {
      const found = offset(findPassage(text.slice(b.start, b.end), child.content), b.start);
      if (found) return found;
    }
  }
  return passage.excerpt ? findPassage(text, passage.excerpt) : null;
};

export interface TextSegment {
  text: string;
  /** 이 조각을 덮는 구절 번호들. 빈 배열이면 일반 텍스트 */
  passages: number[];
}

/**
 * 원문을 음영 조각과 일반 조각으로 나눈다. 구절 범위가 겹치면 경계마다 잘라
 * 한 조각이 여러 구절에 속할 수 있다 — 어느 구절로 이동해도 해당 조각이 강조된다.
 */
export const toSegments = (text: string, ranges: (TextRange | null)[]): TextSegment[] => {
  const cuts = new Set<number>([0, text.length]);
  ranges.forEach((r) => {
    if (r) {
      cuts.add(r.start);
      cuts.add(r.end);
    }
  });
  const points = [...cuts].sort((a, b) => a - b);
  const segments: TextSegment[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const [start, end] = [points[i], points[i + 1]];
    if (start === end) continue;
    const passages = ranges.flatMap((r, idx) => (r && r.start <= start && end <= r.end ? [idx] : []));
    segments.push({ text: text.slice(start, end), passages });
  }
  return segments;
};

export const buildPassageDocument = (
  data: KbDocumentChunksResponse,
  passages: SourceViewerPassage[],
): PassageDocument => {
  const { text, blocks } = layoutBlocks(data);
  return { text, ranges: passages.map((p) => resolve(text, blocks, p)) };
};
