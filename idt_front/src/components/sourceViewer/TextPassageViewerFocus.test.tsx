// answer-citation-verification §5.2 FR-14 — 텍스트 뷰어: 근거 문장 진하게, 청크 나머지 옅게.
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import type { KbDocumentChunksResponse } from '@/types/knowledgeBase';
import type { SourceViewerRef } from '@/types/sourceViewer';

import TextPassageViewer from './TextPassageViewer';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_CHUNKS('kb-1', 'doc-1')}`;
const CHUNK = '총량 목표를 경상성장률 이내로 관리한다. 은행은 분기별로 제출한다.';
const response: KbDocumentChunksResponse = {
  source: 'qdrant', search_mode: null, document_id: 'doc-1', filename: 'a.pdf',
  chunk_strategy: 'parent_child', total_chunks: 1, parents: null,
  chunks: [{ chunk_id: 'c1', chunk_index: 0, chunk_type: 'child', content: CHUNK, metadata: {} }],
};
const viewer = (focus: string | null): SourceViewerRef => ({
  document_id: 'doc-1', kb_id: 'kb-1', original: null,
  passages: [{ chunk_id: 'c1', parent_id: null, page: null, excerpt: '', focus }],
});

describe('TextPassageViewer — 근거 문장', () => {
  it('근거 문장은 진한 현재 음영, 같은 청크 나머지는 옅은 음영', async () => {
    server.use(http.get(URL, () => HttpResponse.json(response)));
    const { container } = render(
      <TextPassageViewer viewer={viewer('경상성장률 이내로 관리한다')} index={0} />,
      { wrapper: createWrapper() },
    );
    await screen.findByText('경상성장률 이내로 관리한다');
    const focus = container.querySelector('mark[data-spv-focus]');
    expect(focus?.textContent).toBe('경상성장률 이내로 관리한다');
    expect(focus).toHaveAttribute('aria-current', 'true');
    const light = [...container.querySelectorAll('mark:not([data-spv-focus])')];
    expect(light.map((m) => m.textContent).join('')).toContain('은행은 분기별로');
    expect(light.every((m) => !m.hasAttribute('aria-current'))).toBe(true);
  });

  it('근거 문장이 없으면 기존처럼 청크 전체가 현재 음영', async () => {
    server.use(http.get(URL, () => HttpResponse.json(response)));
    const { container } = render(<TextPassageViewer viewer={viewer(null)} index={0} />, {
      wrapper: createWrapper(),
    });
    await screen.findByText(CHUNK);
    expect(container.querySelector('mark[data-spv-focus]')).toBeNull();
    expect(container.querySelector('mark[aria-current]')?.textContent).toBe(CHUNK);
  });
});
