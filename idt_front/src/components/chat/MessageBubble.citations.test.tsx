// answer-citation-verification §5.3 — 말풍선이 검증된 인용을 본문 렌더러에 넘긴다.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { DocumentSource, Message } from '@/types/chat';

import MessageBubble from './MessageBubble';

vi.mock('@/hooks/useChart', () => ({ useChart: () => ({ current: null }) }));

const source = (status: 'verified' | 'none'): DocumentSource => ({
  kind: 'document',
  source: 'a.pdf',
  content: '청크',
  chunk_id: 'doc-a',
  viewer: {
    document_id: 'doc-a',
    kb_id: 'kb',
    original: null,
    passages: [{ chunk_id: 'a1', parent_id: null, page: 1, excerpt: '청크' }],
  },
  citation: {
    status,
    entries: status === 'verified' ? [{ no: 1, chunk_id: 'a1', page: 1, evidence: '근거' }] : [],
  },
});

const message = (sources: DocumentSource[]): Message => ({
  id: 'm1',
  role: 'assistant',
  content: '한도는 6억 원입니다[1].',
  createdAt: '2026-11-21T00:00:00.000Z',
  sources,
});

const renderMessage = (m: Message) =>
  render(
    <MemoryRouter>
      <MessageBubble message={m} />
    </MemoryRouter>,
  );

describe('MessageBubble citations', () => {
  it('verified 면 본문 [1] 이 위첨자 버튼이 된다', () => {
    renderMessage(message([source('verified')]));
    expect(screen.getAllByRole('button', { name: '근거 1 원문 보기' }).length).toBeGreaterThan(0);
    expect(screen.queryByText(/\[1\]/)).not.toBeInTheDocument();
  });

  it('인용 정보가 없으면 본문은 글자 그대로', () => {
    renderMessage(message([{ ...source('verified'), citation: undefined }]));
    expect(screen.getByText('한도는 6억 원입니다[1].')).toBeInTheDocument();
  });
});
