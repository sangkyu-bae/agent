// answer-citation-verification §5.2 FR-14 — docx 원본: 근거 문장 진하게, 스타일 포함.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { renderDocx } from '@/lib/docxRenderer';
import type { SourceViewerPassage } from '@/types/sourceViewer';

import DocxPassageViewer from './DocxPassageViewer';

vi.mock('@/lib/docxRenderer', () => ({ renderDocx: vi.fn() }));

const blob = new Blob(['PK'], { type: 'application/zip' });
const passage: SourceViewerPassage = {
  chunk_id: 'c', parent_id: null, page: null, excerpt: '', focus: '성실히 이행한다',
};

describe('DocxPassageViewer — 근거 문장', () => {
  beforeEach(() => {
    vi.mocked(renderDocx).mockReset();
    vi.mocked(renderDocx).mockImplementation(async (_b, root) => {
      const body = document.createElement('div');
      body.innerHTML = '<p>제1조 계약 당사자는 성실히 이행한다.</p>';
      root.replaceChildren(body);
    });
  });

  it('근거 문장 mark 에 data-spv-focus 와 aria-current, 진한 음영 스타일이 있다', async () => {
    render(
      <DocxPassageViewer
        blob={blob}
        passages={[passage]}
        texts={['계약 당사자는 성실히 이행한다']}
        index={0}
        onFallback={vi.fn()}
      />,
    );
    const host = screen.getByTestId('docx-passage-host');
    await waitFor(() =>
      expect(host.shadowRoot?.querySelector('mark[data-spv-focus]')?.textContent).toBe('성실히 이행한다'),
    );
    expect(host.shadowRoot?.querySelector('mark[data-spv-focus]')).toHaveAttribute('aria-current', 'true');
    expect(host.shadowRoot?.querySelector('style[data-spv]')?.textContent).toContain('data-spv-focus');
  });
});
