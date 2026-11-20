// Design Ref: source-passage-viewer §2.2 칩 클릭, §5.4 단계적 대체 — 원본 우선, 실패 시 텍스트 뷰어.
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { loadPdf } from '@/lib/pdfRenderer';
import { useSourceViewerStore } from '@/store/sourceViewerStore';
import type { KbDocumentChunksResponse } from '@/types/knowledgeBase';
import type { OriginalKind } from '@/types/sourceViewer';

import SourceViewerPanel from './SourceViewerPanel';

vi.mock('@/lib/pdfRenderer', () => ({ loadPdf: vi.fn() }));

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const CHUNKS_URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_CHUNKS('kb-1', 'doc-1')}`;
const ORIGINAL_URL = `*${API_ENDPOINTS.SOURCE_VIEWER_ORIGINAL('kb-1', 'doc-1')}`;

const chunks: KbDocumentChunksResponse = {
  source: 'qdrant', search_mode: null, document_id: 'doc-1', filename: '규정.pdf',
  chunk_strategy: 'parent_child', total_chunks: 1, parents: null,
  chunks: [{ chunk_id: 'c1', chunk_index: 0, chunk_type: 'child', content: '담보는 감정가로 평가한다.', metadata: {} }],
};

const fakePdf = () => ({
  numPages: 1,
  renderPage: vi.fn(async (_n: number, container: HTMLElement) => {
    const layer = document.createElement('div');
    layer.innerHTML = '<span>제2조 담보는 감정가로</span><span>평가한다.</span>';
    container.appendChild(layer);
    return layer;
  }),
  destroy: vi.fn(),
});

const open = (original: OriginalKind | null) =>
  useSourceViewerStore.getState().open({
    filename: '규정.pdf',
    viewer: {
      document_id: 'doc-1', kb_id: 'kb-1', original,
      passages: [{ chunk_id: 'c1', parent_id: null, page: 1, excerpt: '담보는' }],
    },
  });

const renderPanel = () => render(<SourceViewerPanel />, { wrapper: createWrapper() });

describe('SourceViewerPanel — 원본/텍스트 전환', () => {
  beforeEach(() => {
    useSourceViewerStore.getState().close();
    vi.mocked(loadPdf).mockReset();
    server.use(
      http.get(CHUNKS_URL, () => HttpResponse.json(chunks)),
      http.get(ORIGINAL_URL, () =>
        new HttpResponse(new Uint8Array([37, 80, 68, 70]), { headers: { 'Content-Type': 'application/pdf' } }),
      ),
    );
  });

  it('원본이 있으면 원본으로 열고 청크 전문으로 음영을 칠한다', async () => {
    vi.mocked(loadPdf).mockResolvedValue(fakePdf());
    open('pdf');
    renderPanel();
    expect(screen.getByRole('button', { name: '원본' })).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() =>
      expect([...document.querySelectorAll('mark')].map((m) => m.textContent).join('')).toBe('담보는 감정가로평가한다.'),
    );
  });

  it('원본이 없으면(null) 텍스트로 열고 원본 버튼은 비활성', async () => {
    open(null);
    renderPanel();
    expect(screen.getByRole('button', { name: '원본' })).toBeDisabled();
    expect(await screen.findByText('담보는 감정가로 평가한다.', { selector: 'mark' })).toBeInTheDocument();
  });

  it('원본 API 가 404 면 텍스트로 바꾸고 안내한다', async () => {
    server.use(http.get(ORIGINAL_URL, () => HttpResponse.json({ detail: 'ORIGINAL_NOT_AVAILABLE' }, { status: 404 })));
    open('pdf');
    renderPanel();
    expect(await screen.findByText('원본 파일을 열 수 없어 텍스트로 보여 줍니다.')).toBeInTheDocument();
    expect(await screen.findByText('담보는 감정가로 평가한다.', { selector: 'mark' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '텍스트' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('PDF 렌더 실패도 텍스트로 바꾼다', async () => {
    vi.mocked(loadPdf).mockRejectedValue(new Error('broken'));
    open('pdf');
    renderPanel();
    expect(await screen.findByText('원본 파일을 열 수 없어 텍스트로 보여 줍니다.')).toBeInTheDocument();
  });

  it('사용자가 텍스트↔원본을 바꿀 수 있다', async () => {
    vi.mocked(loadPdf).mockResolvedValue(fakePdf());
    open('pdf');
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: '텍스트' }));
    expect(await screen.findByText('담보는 감정가로 평가한다.', { selector: 'mark' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '원본' }));
    expect(screen.getByRole('button', { name: '원본' })).toHaveAttribute('aria-pressed', 'true');
  });
});
