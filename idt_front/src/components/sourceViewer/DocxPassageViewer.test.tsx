// Design Ref: source-passage-viewer §5.4, §8.3 — docx 원본 음영(shadow DOM). 렌더 경계만 mock.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { renderDocx } from '@/lib/docxRenderer';

import DocxPassageViewer from './DocxPassageViewer';

vi.mock('@/lib/docxRenderer', () => ({ renderDocx: vi.fn() }));

const blob = new Blob(['PK'], { type: 'application/zip' });

const shadowMarks = () => {
  const host = screen.getByTestId('docx-passage-host');
  return [...(host.shadowRoot?.querySelectorAll('mark') ?? [])].map((m) => m.textContent);
};

describe('DocxPassageViewer', () => {
  beforeEach(() => {
    vi.mocked(renderDocx).mockReset();
    vi.mocked(renderDocx).mockImplementation(async (_b, root) => {
      const body = document.createElement('div');
      body.innerHTML = '<p>제1조 계약 당사자는</p><p>성실히 이행한다.</p>';
      root.replaceChildren(body);
    });
  });

  it('렌더된 문서에서 구절을 찾아 shadow DOM 안에 음영을 넣는다', async () => {
    render(<DocxPassageViewer blob={blob} texts={['계약 당사자는 성실히']} index={0} onFallback={vi.fn()} />);
    await waitFor(() => expect(shadowMarks().join('')).toBe('계약 당사자는성실히'));
    const host = screen.getByTestId('docx-passage-host');
    expect(host.shadowRoot?.querySelector('style[data-spv]')).not.toBeNull();
  });

  it('못 찾으면 안내한다', async () => {
    render(<DocxPassageViewer blob={blob} texts={['없는 문장']} index={0} onFallback={vi.fn()} />);
    expect(await screen.findByText('원문에서 정확한 위치를 찾지 못했습니다.')).toBeInTheDocument();
  });

  it('렌더 실패는 onFallback', async () => {
    vi.mocked(renderDocx).mockRejectedValue(new Error('bad docx'));
    const onFallback = vi.fn();
    render(<DocxPassageViewer blob={blob} texts={['x']} index={0} onFallback={onFallback} />);
    await waitFor(() => expect(onFallback).toHaveBeenCalledWith('render'));
  });
});
