// Design Ref: source-passage-viewer §5.5 SourceCitation, §8.3 #4·5 — viewer 유무로만 분기
import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { useSourceViewerStore } from '@/store/sourceViewerStore';
import type { DocumentSource } from '@/types/chat';
import type { SourceViewerRef } from '@/types/sourceViewer';

import SourceCitation from './SourceCitation';

const viewer: SourceViewerRef = {
  document_id: 'doc-1',
  kb_id: 'kb-1',
  original: null,
  passages: [{ chunk_id: 'c1', parent_id: null, page: 3, excerpt: '발췌' }],
};

const doc = (over: Partial<DocumentSource> = {}): DocumentSource => ({
  kind: 'document', source: '여신규정.pdf', content: '발췌', chunk_id: 'doc-1', ...over,
});

const renderChips = (sources: DocumentSource[]) =>
  render(
    <MemoryRouter>
      <SourceCitation sources={sources} />
    </MemoryRouter>,
  );

describe('SourceCitation — 원문 보기', () => {
  beforeEach(() => useSourceViewerStore.getState().close());

  it('viewer 가 없으면 버튼이 없다', () => {
    renderChips([doc()]);
    expect(screen.queryByRole('button', { name: /원문 보기/ })).not.toBeInTheDocument();
  });

  it('viewer 가 null 이어도(재진입 API) 버튼이 없다', () => {
    renderChips([doc({ viewer: null })]);
    expect(screen.queryByRole('button', { name: /원문 보기/ })).not.toBeInTheDocument();
  });

  it('viewer 가 있으면 버튼을 누를 때 패널 대상을 연다', async () => {
    renderChips([doc({ viewer })]);
    await userEvent.click(screen.getByRole('button', { name: '여신규정.pdf 원문 보기' }));
    const target = useSourceViewerStore.getState().target;
    expect(target?.filename).toBe('여신규정.pdf');
    expect(target?.viewer.document_id).toBe('doc-1');
  });

  it('기존 발췌 토글은 그대로 동작한다', async () => {
    renderChips([doc({ viewer })]);
    await userEvent.click(screen.getByRole('button', { name: /여신규정\.pdf$/ }));
    expect(screen.getByRole('region', { name: '여신규정.pdf 발췌' })).toBeInTheDocument();
  });
});
