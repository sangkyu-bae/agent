// Design Ref: source-passage-viewer §5.5 Panel, §8.3 #6~8 — 텍스트 뷰어·구절 이동·오류 안내
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { useSourceViewerStore } from '@/store/sourceViewerStore';
import type { KbDocumentChunksResponse } from '@/types/knowledgeBase';
import type { SourceViewerRef } from '@/types/sourceViewer';

import SourceViewerPanel from './SourceViewerPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const CHUNKS_URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_CHUNKS('kb-1', 'doc-1')}`;

const chunk = (id: string, idx: number, content: string) => ({
  chunk_id: id, chunk_index: idx, chunk_type: 'child', content, metadata: {},
});

const response: KbDocumentChunksResponse = {
  source: 'qdrant', search_mode: null, document_id: 'doc-1', filename: '여신규정.pdf',
  chunk_strategy: 'parent_child', total_chunks: 3, parents: null,
  chunks: [
    chunk('c1', 0, '제1조 이 규정은 여신 심사 기준을 정한다.'),
    chunk('c2', 1, '제2조 담보는 감정가로 평가한다.'),
    chunk('c3', 2, '제3조 부칙.'),
  ],
};

const viewer = (passages: SourceViewerRef['passages']): SourceViewerRef => ({
  document_id: 'doc-1', kb_id: 'kb-1', original: null, passages,
});

const open = (v: SourceViewerRef) =>
  useSourceViewerStore.getState().open({ viewer: v, filename: '여신규정.pdf' });

const renderPanel = () => render(<SourceViewerPanel />, { wrapper: createWrapper() });

describe('SourceViewerPanel', () => {
  beforeEach(() => {
    useSourceViewerStore.getState().close();
    server.use(http.get(CHUNKS_URL, () => HttpResponse.json(response)));
  });

  it('문서 전문을 보여 주고 인용 청크에 음영을 칠한다', async () => {
    open(viewer([{ chunk_id: 'c2', parent_id: null, page: 4, excerpt: '담보' }]));
    renderPanel();
    expect(screen.getByRole('complementary', { name: '여신규정.pdf 원문' })).toBeInTheDocument();
    const mark = await screen.findByText('제2조 담보는 감정가로 평가한다.', { selector: 'mark' });
    expect(mark).toHaveAttribute('aria-current', 'true');
    expect(screen.getByText(/제1조 이 규정은/)).toBeInTheDocument();
    expect(screen.getByText('p.4')).toBeInTheDocument();
  });

  it('구절 여러 개를 모두 칠하고 이전/다음으로 이동한다', async () => {
    open(viewer([
      { chunk_id: 'c1', parent_id: null, page: null, excerpt: '' },
      { chunk_id: 'c3', parent_id: null, page: null, excerpt: '' },
    ]));
    renderPanel();
    await screen.findAllByText(/제/, { selector: 'mark' });
    expect(screen.getAllByText(/제/, { selector: 'mark' })).toHaveLength(2);
    expect(screen.getByText('구절 1 / 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '이전 구절' })).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: '다음 구절' }));
    expect(screen.getByText('구절 2 / 2')).toBeInTheDocument();
    expect(screen.getByText('제3조 부칙.', { selector: 'mark' })).toHaveAttribute('aria-current', 'true');
    expect(screen.getByRole('button', { name: '다음 구절' })).toBeDisabled();
  });

  it('위치를 찾지 못한 구절은 안내와 발췌를 보여 준다', async () => {
    open(viewer([{ chunk_id: 'zzz', parent_id: null, page: null, excerpt: '없는 문장입니다' }]));
    renderPanel();
    expect(await screen.findByText('원문에서 정확한 위치를 찾지 못했습니다.')).toBeInTheDocument();
    expect(screen.getByText('없는 문장입니다')).toBeInTheDocument();
  });

  it('권한이 없으면 403 안내', async () => {
    server.use(http.get(CHUNKS_URL, () => HttpResponse.json({ detail: 'no' }, { status: 403 })));
    open(viewer([{ chunk_id: 'c1', parent_id: null, page: null, excerpt: '' }]));
    renderPanel();
    expect(await screen.findByText('이 문서를 볼 권한이 없습니다.')).toBeInTheDocument();
  });

  it('문서가 없으면 404 안내', async () => {
    server.use(http.get(CHUNKS_URL, () => HttpResponse.json({ detail: 'not found' }, { status: 404 })));
    open(viewer([{ chunk_id: 'c1', parent_id: null, page: null, excerpt: '' }]));
    renderPanel();
    expect(await screen.findByText(/문서를 찾을 수 없습니다/)).toBeInTheDocument();
  });

  it('닫기 버튼과 Esc 로 닫힌다', async () => {
    open(viewer([{ chunk_id: 'c1', parent_id: null, page: null, excerpt: '' }]));
    const { unmount } = renderPanel();
    await userEvent.click(screen.getByRole('button', { name: '원문 패널 닫기' }));
    expect(useSourceViewerStore.getState().target).toBeNull();
    unmount();

    open(viewer([{ chunk_id: 'c1', parent_id: null, page: null, excerpt: '' }]));
    renderPanel();
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(useSourceViewerStore.getState().target).toBeNull());
  });
});
