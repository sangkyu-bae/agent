// Design Ref: source-passage-viewer §5.3 — 패널 상태는 스토어가 소유한다
import { beforeEach, describe, expect, it } from 'vitest';

import type { SourceViewerRef } from '@/types/sourceViewer';

import { useSourceViewerStore } from './sourceViewerStore';

const viewer = (n: number): SourceViewerRef => ({
  document_id: 'doc-1',
  kb_id: 'kb-1',
  original: null,
  passages: Array.from({ length: n }, (_, i) => ({
    chunk_id: `c${i}`, parent_id: null, page: null, excerpt: `발췌${i}`,
  })),
});

describe('sourceViewerStore', () => {
  beforeEach(() => useSourceViewerStore.getState().close());

  it('open 은 대상과 첫 구절을 잡는다', () => {
    useSourceViewerStore.getState().open({ viewer: viewer(2), filename: '규정.pdf' });
    const s = useSourceViewerStore.getState();
    expect(s.target?.filename).toBe('규정.pdf');
    expect(s.index).toBe(0);
  });

  it('next/prev 는 범위 안에서만 움직인다', () => {
    const { open, next, prev } = useSourceViewerStore.getState();
    open({ viewer: viewer(2), filename: 'a' });
    prev();
    expect(useSourceViewerStore.getState().index).toBe(0);
    next();
    next();
    expect(useSourceViewerStore.getState().index).toBe(1);
  });

  it('다른 칩으로 다시 열면 첫 구절로 돌아간다', () => {
    const { open, next } = useSourceViewerStore.getState();
    open({ viewer: viewer(3), filename: 'a' });
    next();
    open({ viewer: viewer(3), filename: 'b' });
    expect(useSourceViewerStore.getState().index).toBe(0);
  });

  it('close 는 대상을 비운다', () => {
    const { open, close } = useSourceViewerStore.getState();
    open({ viewer: viewer(1), filename: 'a' });
    close();
    expect(useSourceViewerStore.getState().target).toBeNull();
  });
});
