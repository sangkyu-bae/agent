// Design Ref: source-passage-viewer §5.4, §8.3 #10 — PDF 원본 음영·페이지 이동·대체 전환.
// jsdom 은 PDF 를 그릴 수 없으므로 렌더 경계(lib/pdfRenderer)만 mock 한다(docxRenderer 선례).
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { loadPdf } from '@/lib/pdfRenderer';
import type { SourceViewerPassage } from '@/types/sourceViewer';

import PdfPassageViewer from './PdfPassageViewer';

vi.mock('@/lib/pdfRenderer', () => ({ loadPdf: vi.fn() }));

const PAGES: Record<number, string[]> = {
  1: ['제1조 이 규정은 여신 심사의'],
  2: ['기준을 정한다.', '제2조 담보는 감정가로'],
  3: ['평가한다.'],
};

const fakeDoc = () => ({
  numPages: 3,
  renderPage: vi.fn(async (pageNo: number, container: HTMLElement) => {
    const layer = document.createElement('div');
    layer.dataset.page = String(pageNo);
    for (const str of PAGES[pageNo]) {
      const span = document.createElement('span');
      span.textContent = str;
      layer.appendChild(span);
    }
    container.appendChild(layer);
    return layer;
  }),
  destroy: vi.fn(),
});

const passage = (page: number | null): SourceViewerPassage => ({
  chunk_id: 'c', parent_id: null, page, excerpt: '',
});

const blob = new Blob(['%PDF'], { type: 'application/pdf' });

describe('PdfPassageViewer', () => {
  beforeEach(() => {
    vi.mocked(loadPdf).mockReset();
  });

  it('구절의 쪽과 앞뒤 쪽만 렌더하고 쪽을 넘는 구절도 칠한다', async () => {
    const doc = fakeDoc();
    vi.mocked(loadPdf).mockResolvedValue(doc);
    render(
      <PdfPassageViewer blob={blob} passages={[passage(2)]} texts={['담보는 감정가로 평가한다']} index={0} onFallback={vi.fn()} />,
    );
    await waitFor(() => expect(document.querySelectorAll('mark').length).toBeGreaterThan(0));
    expect(doc.renderPage.mock.calls.map((c) => c[0])).toEqual([1, 2, 3]);
    const text = [...document.querySelectorAll('mark')].map((m) => m.textContent).join('');
    expect(text).toBe('담보는 감정가로평가한다');
  });

  it('위치를 못 찾으면 그 쪽을 보여 주고 안내한다', async () => {
    vi.mocked(loadPdf).mockResolvedValue(fakeDoc());
    render(
      <PdfPassageViewer blob={blob} passages={[passage(3)]} texts={['없는 문장']} index={0} onFallback={vi.fn()} />,
    );
    expect(await screen.findByText(/정확한 위치를 찾지 못해 3쪽을 보여 줍니다/)).toBeInTheDocument();
  });

  it('PDF 를 열지 못하면 onFallback', async () => {
    vi.mocked(loadPdf).mockImplementation(async () => {
      throw new Error('bad pdf');
    });
    const onFallback = vi.fn();
    render(<PdfPassageViewer blob={blob} passages={[passage(1)]} texts={['x']} index={0} onFallback={onFallback} />);
    await waitFor(() => expect(onFallback).toHaveBeenCalledWith('render'));
  });

  it('쪽 정보가 없으면 앞쪽부터 상한까지 렌더한다', async () => {
    const doc = fakeDoc();
    vi.mocked(loadPdf).mockResolvedValue(doc);
    render(<PdfPassageViewer blob={blob} passages={[passage(null)]} texts={['평가한다']} index={0} onFallback={vi.fn()} />);
    await waitFor(() => expect(document.querySelectorAll('mark').length).toBe(1));
    expect(doc.renderPage.mock.calls.map((c) => c[0])).toEqual([1, 2, 3]);
  });
});
