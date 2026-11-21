// answer-citation-verification FR-13 — 인용 행 · 미사용 구절 접힘 · 근거 확인 안 됨.
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { useSourceViewerStore } from '@/store/sourceViewerStore';
import type { DocumentSource } from '@/types/chat';

import SourceCitation from './SourceCitation';

const viewer = {
  document_id: 'doc-a',
  kb_id: 'kb',
  original: null,
  passages: [{ chunk_id: 'a1', parent_id: null, page: 2, excerpt: '청크' }],
};
const cited: DocumentSource = {
  kind: 'document',
  source: '가계부채.pdf',
  content: '청크 발췌',
  chunk_id: 'doc-a',
  viewer,
  citation: {
    status: 'verified',
    entries: [{ no: 1, chunk_id: 'a1', page: 2, evidence: '총량 목표를 경상성장률 이내로 관리' }],
  },
};
const noEvidence: DocumentSource = {
  kind: 'document',
  source: '전세.pdf',
  content: '전세 발췌',
  chunk_id: 'doc-b',
  citation: { status: 'verified', entries: [{ no: 2, chunk_id: 'b1', page: null, evidence: null }] },
};
const unused: DocumentSource = {
  kind: 'document',
  source: '미사용.pdf',
  content: '미사용 발췌',
  chunk_id: 'doc-c',
  citation: { status: 'verified', entries: [] },
};
const web: DocumentSource = { kind: 'web', source: '뉴스', content: '', chunk_id: 'w', url: 'https://example.com' };

const renderSources = (sources: DocumentSource[]) =>
  render(
    <MemoryRouter>
      <SourceCitation sources={sources} />
    </MemoryRouter>,
  );

describe('SourceCitation — 인용 검증', () => {
  beforeEach(() => useSourceViewerStore.getState().close());

  it('인용 행: 번호·파일·쪽·근거 문장, 근거 없으면 청크 발췌', () => {
    renderSources([cited, noEvidence, unused, web]);
    const list = screen.getByRole('list', { name: '답변 근거' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('1');
    expect(items[0]).toHaveTextContent('가계부채.pdf');
    expect(items[0]).toHaveTextContent('2쪽');
    expect(items[0]).toHaveTextContent('총량 목표를 경상성장률 이내로 관리');
    expect(items[1]).toHaveTextContent('전세 발췌');
    expect(items[1]).not.toHaveTextContent('쪽');
  });

  it('원문 보기는 뷰어 정보가 있는 행에만, 누르면 그 인용에서 열린다', async () => {
    const user = userEvent.setup();
    renderSources([cited, noEvidence]);
    const buttons = screen.getAllByRole('button', { name: /원문 보기/ });
    expect(buttons).toHaveLength(1);
    await user.click(buttons[0]);
    expect(useSourceViewerStore.getState().target?.viewer.passages[0].focus).toBe(
      '총량 목표를 경상성장률 이내로 관리',
    );
  });

  it('미사용 구절은 접혀 있고 펼치면 기존 칩으로 보인다, 웹 칩은 그대로', async () => {
    const user = userEvent.setup();
    renderSources([cited, unused, web]);
    expect(screen.getByText('뉴스')).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: /검색했지만 답변에 쓰지 않은 구절 1건/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('미사용.pdf')).not.toBeInTheDocument();
    await user.click(toggle);
    expect(screen.getByText('미사용.pdf')).toBeInTheDocument();
  });

  it('none: 근거 확인 안 됨 배지와 검색된 구절 접힘', () => {
    renderSources([
      { ...cited, citation: { status: 'none', entries: [] } },
      { ...unused, citation: { status: 'none', entries: [] } },
    ]);
    expect(screen.getByRole('status')).toHaveTextContent('근거 확인 안 됨');
    expect(screen.getByRole('button', { name: /검색된 구절 2건/ })).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '답변 근거' })).not.toBeInTheDocument();
  });

  it('citation 이 없으면 기존 칩 렌더(참고 문서)', () => {
    renderSources([{ ...cited, citation: undefined }]);
    expect(screen.getByText('참고 문서')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '답변 근거' })).not.toBeInTheDocument();
  });
});
