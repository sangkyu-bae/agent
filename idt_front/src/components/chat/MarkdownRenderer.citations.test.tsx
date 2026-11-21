// answer-citation-verification FR-12 — 본문 [n] 위첨자. 인용 목록에 있는 번호만, 코드 안 제외.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { useSourceViewerStore } from '@/store/sourceViewerStore';
import type { DocumentSource } from '@/types/chat';
import { buildCitationView } from '@/utils/citationView';

import MarkdownRenderer from './MarkdownRenderer';

const source: DocumentSource = {
  kind: 'document',
  source: 'a.pdf',
  content: '',
  chunk_id: 'doc-a',
  viewer: {
    document_id: 'doc-a',
    kb_id: 'kb',
    original: null,
    passages: [{ chunk_id: 'a1', parent_id: null, page: 2, excerpt: '청크' }],
  },
  citation: {
    status: 'verified',
    entries: [{ no: 1, chunk_id: 'a1', page: 2, evidence: '근거 문장' }],
  },
};
const rows = buildCitationView([source]).rows;

describe('MarkdownRenderer citations', () => {
  beforeEach(() => {
    useSourceViewerStore.getState().close();
  });

  it('citations 가 없으면 [1] 을 글자 그대로 둔다', () => {
    render(<MarkdownRenderer content="총량을 관리합니다[1]." />);
    expect(screen.getByText('총량을 관리합니다[1].')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /근거 1/ })).not.toBeInTheDocument();
  });

  it('목록에 있는 번호만 위첨자 버튼으로 바꾸고, 없는 번호·코드는 그대로', () => {
    const { container } = render(
      <MarkdownRenderer content={'총량을 관리합니다[1]. 참고[7] `x[1]`'} citations={rows} />,
    );
    const button = screen.getByRole('button', { name: '근거 1 원문 보기' });
    expect(button).toHaveTextContent('1');
    expect(button.closest('sup')).not.toBeNull();
    expect(container.textContent).toContain('참고[7]');
    expect(container.querySelector('code')?.textContent).toBe('x[1]');
  });

  it('누르면 원문 뷰어가 그 인용 위치로 열린다', async () => {
    const user = userEvent.setup();
    render(<MarkdownRenderer content="총량을 관리합니다[1]." citations={rows} />);
    await user.click(screen.getByRole('button', { name: '근거 1 원문 보기' }));
    const state = useSourceViewerStore.getState();
    expect(state.target?.viewer.passages[0].focus).toBe('근거 문장');
    expect(state.index).toBe(0);
  });

  it('원문 뷰어 정보가 없으면 버튼이 아닌 번호만 보여 준다', () => {
    const plain = buildCitationView([{ ...source, viewer: null }]).rows;
    const { container } = render(<MarkdownRenderer content="관리합니다[1]." citations={plain} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(container.querySelector('sup')?.textContent).toBe('1');
  });
});
