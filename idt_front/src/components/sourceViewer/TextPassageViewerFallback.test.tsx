// Design Ref: source-passage-viewer §12 M17·M18 (module-7 실측) — Qdrant 저장이 실패한 partial 문서도
// ES 청크로 텍스트 뷰어를 그린다. 깨진 문자(U+FFFD)는 안내 발췌에서 지운다.
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

const response = (source: 'qdrant' | 'es', content: string | null): KbDocumentChunksResponse => ({
  source, search_mode: null, document_id: 'doc-1', filename: 'a.pdf', chunk_strategy: 'parent_child',
  total_chunks: content ? 1 : 0, parents: null,
  chunks: content ? [{ chunk_id: 'c1', chunk_index: 0, chunk_type: 'child', content, metadata: {} }] : [],
});

const viewer = (excerpt = ''): SourceViewerRef => ({
  document_id: 'doc-1', kb_id: 'kb-1', original: null,
  passages: [{ chunk_id: 'c1', parent_id: null, page: null, excerpt }],
});

describe('TextPassageViewer — 저장소 대체', () => {
  it('Qdrant 청크가 비어 있으면 ES 청크로 그린다', async () => {
    server.use(
      http.get(URL, ({ request }) => {
        const src = new globalThis.URL(request.url).searchParams.get('source');
        return HttpResponse.json(src === 'es' ? response('es', 'ES 에만 있는 본문') : response('qdrant', null));
      }),
    );
    render(<TextPassageViewer viewer={viewer()} index={0} />, { wrapper: createWrapper() });
    expect(await screen.findByText('ES 에만 있는 본문', { selector: 'mark' })).toBeInTheDocument();
  });

  it('Qdrant 에 청크가 있으면 ES 를 부르지 않는다', async () => {
    const sources: string[] = [];
    server.use(
      http.get(URL, ({ request }) => {
        sources.push(new globalThis.URL(request.url).searchParams.get('source') ?? '');
        return HttpResponse.json(response('qdrant', 'Qdrant 본문'));
      }),
    );
    render(<TextPassageViewer viewer={viewer()} index={0} />, { wrapper: createWrapper() });
    await screen.findByText('Qdrant 본문', { selector: 'mark' });
    expect(sources).toEqual(['qdrant']);
  });

  it('안내 발췌에서 깨진 문자를 지운다', async () => {
    server.use(http.get(URL, () => HttpResponse.json(response('qdrant', '다른 본문'))));
    render(
      <TextPassageViewer
        viewer={{ ...viewer('��LTV 0%'), passages: [{ chunk_id: 'zz', parent_id: null, page: null, excerpt: '��LTV 0%' }] }}
        index={0}
      />,
      { wrapper: createWrapper() },
    );
    expect(await screen.findByText('LTV 0%')).toBeInTheDocument();
  });
});
