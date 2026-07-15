import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import type { KbDocumentChunksResponse } from '@/types/knowledgeBase';
import KbChunkList from './KbChunkList';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const CHUNKS_URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_CHUNKS('kb-1', 'doc-1')}`;

const child = (id: string, idx: number, content: string) => ({
  chunk_id: id,
  chunk_index: idx,
  chunk_type: 'child',
  content,
  metadata: { kb_id: 'kb-1', document_id: 'doc-1', parent_id: 'par1' },
});

const flatResponse = (
  over: Partial<KbDocumentChunksResponse> = {},
): KbDocumentChunksResponse => ({
  source: 'qdrant',
  search_mode: null,
  document_id: 'doc-1',
  filename: 'a.pdf',
  chunk_strategy: 'parent_child',
  total_chunks: 3,
  chunks: [child('ch1', 0, '심사역은 상환능력을 본다'), child('ch2', 1, '담보평가 기준')],
  parents: null,
  ...over,
});

const hierarchyResponse = (): KbDocumentChunksResponse => ({
  ...flatResponse(),
  chunks: [],
  parents: [
    {
      chunk_id: 'par1',
      chunk_index: 0,
      chunk_type: 'parent',
      content: '여신심사 일반기준 전체',
      children: [child('ch1', 0, '심사역은 상환능력을 본다')],
    },
  ],
});

const renderList = () =>
  render(<KbChunkList kbId="kb-1" documentId="doc-1" source="qdrant" />, {
    wrapper: createWrapper(),
  });

describe('KbChunkList — kb-content-browser', () => {
  it('계층 응답이면 parent 카드와 child 카드를 함께 그린다', async () => {
    server.use(http.get(CHUNKS_URL, () => HttpResponse.json(hierarchyResponse())));
    renderList();

    expect(await screen.findByText('여신심사 일반기준 전체')).toBeInTheDocument();
    expect(screen.getByText('심사역은 상환능력을 본다')).toBeInTheDocument();
    expect(screen.getByText('parent')).toBeInTheDocument();
  });

  it('검색 입력은 debounce 후 q 파라미터로 전달되고 search_mode 배지를 보여준다', async () => {
    let lastQ: string | null = null;
    server.use(
      http.get(CHUNKS_URL, ({ request }) => {
        const url = new URL(request.url);
        lastQ = url.searchParams.get('q');
        if (lastQ) {
          return HttpResponse.json(
            flatResponse({
              search_mode: 'contains',
              total_chunks: 1,
              chunks: [child('ch2', 1, '담보평가 기준')],
            }),
          );
        }
        return HttpResponse.json(flatResponse());
      }),
    );
    renderList();
    await screen.findByText('심사역은 상환능력을 본다');

    await userEvent.type(screen.getByLabelText('청크 검색'), '담보');

    await waitFor(() => expect(lastQ).toBe('담보'), { timeout: 3000 });
    expect(
      await screen.findByText('단순 포함 검색 (Qdrant)'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByText('심사역은 상환능력을 본다'),
      ).not.toBeInTheDocument(),
    );
  });

  it('긴 본문은 접힌 상태로 시작하고 펼치기로 전체를 보여준다', async () => {
    const longContent = '가'.repeat(200);
    server.use(
      http.get(CHUNKS_URL, () =>
        HttpResponse.json(
          flatResponse({ chunks: [child('ch1', 0, longContent)], total_chunks: 1 }),
        ),
      ),
    );
    renderList();

    const toggle = await screen.findByRole('button', { name: '펼치기 ▼' });
    expect(screen.queryByText(longContent)).not.toBeInTheDocument();

    await userEvent.click(toggle);
    expect(screen.getByText(longContent)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '접기 ▲' })).toBeInTheDocument();
  });

  it('메타 토글로 payload 필드를 노출한다', async () => {
    server.use(http.get(CHUNKS_URL, () => HttpResponse.json(flatResponse())));
    renderList();
    await screen.findByText('심사역은 상환능력을 본다');

    expect(screen.queryByText('parent_id')).not.toBeInTheDocument();
    await userEvent.click(
      screen.getAllByRole('button', { name: 'ⓘ 메타 보기' })[0],
    );
    expect(screen.getByText('parent_id')).toBeInTheDocument();
    expect(screen.getByText('kb_id')).toBeInTheDocument();
  });

  it('7개 이상이면 페이지네이션을 보여준다', async () => {
    const many = Array.from({ length: 8 }, (_, i) =>
      child(`ch${i}`, i, `청크 본문 ${i}`),
    );
    server.use(
      http.get(CHUNKS_URL, () =>
        HttpResponse.json(flatResponse({ chunks: many, total_chunks: 8 })),
      ),
    );
    renderList();

    expect(await screen.findByText('청크 본문 0')).toBeInTheDocument();
    expect(screen.queryByText('청크 본문 7')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '다음' }));
    expect(screen.getByText('청크 본문 7')).toBeInTheDocument();
  });

  it('빈 결과는 안내 문구를 보여준다', async () => {
    server.use(
      http.get(CHUNKS_URL, () =>
        HttpResponse.json(
          flatResponse({ chunks: [], parents: null, total_chunks: 0 }),
        ),
      ),
    );
    renderList();
    expect(
      await screen.findByText('저장된 청크가 없습니다'),
    ).toBeInTheDocument();
  });
});
