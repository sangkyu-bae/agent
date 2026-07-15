import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  KbDocumentInfo,
  KbDocumentSummaryResponse,
} from '@/types/knowledgeBase';
import KbDocumentContentPanel from './KbDocumentContentPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const SUMMARY_URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_SUMMARY('kb-1', 'doc-1')}`;
const CHUNKS_URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_CHUNKS('kb-1', 'doc-1')}`;

const doc: KbDocumentInfo = {
  document_id: 'doc-1',
  filename: '여신규정.pdf',
  chunk_count: 42,
  chunking_strategy: 'parent_child',
  created_at: '2026-07-14T00:00:00Z',
};

const summaryResponse = (
  source: string,
  over: Partial<KbDocumentSummaryResponse> = {},
): KbDocumentSummaryResponse => ({
  exists: true,
  source: source as KbDocumentSummaryResponse['source'],
  chunk_id: 'ds-1',
  summary_text: `문서 전체 요약 (${source})`,
  keywords: ['여신'],
  section_count: 3,
  filename: '여신규정.pdf',
  metadata: { kb_id: 'kb-1' },
});

const renderPanel = (onClose = vi.fn()) => {
  render(
    <KbDocumentContentPanel kbId="kb-1" document={doc} onClose={onClose} />,
    { wrapper: createWrapper() },
  );
  return onClose;
};

describe('KbDocumentContentPanel — kb-content-browser', () => {
  it('기본 탭(문서 요약)을 qdrant 소스로 조회한다 (D2 기본값)', async () => {
    let lastSource: string | null = null;
    server.use(
      http.get(SUMMARY_URL, ({ request }) => {
        lastSource = new URL(request.url).searchParams.get('source');
        return HttpResponse.json(summaryResponse(lastSource ?? 'qdrant'));
      }),
    );
    renderPanel();

    expect(
      await screen.findByText('문서 전체 요약 (qdrant)'),
    ).toBeInTheDocument();
    expect(lastSource).toBe('qdrant');
    expect(screen.getByText('섹션 3개 기반 요약')).toBeInTheDocument();
  });

  it('저장소 토글로 ES 소스를 재조회한다 (사용자 결정 ①)', async () => {
    server.use(
      http.get(SUMMARY_URL, ({ request }) => {
        const source = new URL(request.url).searchParams.get('source') ?? '';
        return HttpResponse.json(summaryResponse(source));
      }),
    );
    renderPanel();
    await screen.findByText('문서 전체 요약 (qdrant)');

    await userEvent.click(screen.getByRole('button', { name: 'Elasticsearch' }));

    expect(
      await screen.findByText('문서 전체 요약 (es)'),
    ).toBeInTheDocument();
  });

  it('요약 미생성(exists=false)이면 안내 문구를 보여준다 (D6)', async () => {
    server.use(
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          exists: false,
          source: 'qdrant',
          keywords: [],
          metadata: {},
        }),
      ),
    );
    renderPanel();
    expect(
      await screen.findByText('문서 요약이 아직 생성되지 않았습니다'),
    ).toBeInTheDocument();
  });

  it('청크 탭으로 전환하면 청크 목록을 조회한다', async () => {
    server.use(
      http.get(SUMMARY_URL, () => HttpResponse.json(summaryResponse('qdrant'))),
      http.get(CHUNKS_URL, () =>
        HttpResponse.json({
          source: 'qdrant',
          search_mode: null,
          document_id: 'doc-1',
          filename: '여신규정.pdf',
          chunk_strategy: 'parent_child',
          total_chunks: 1,
          chunks: [
            {
              chunk_id: 'ch1',
              chunk_index: 0,
              chunk_type: 'child',
              content: '청크 본문입니다',
              metadata: {},
            },
          ],
          parents: null,
        }),
      ),
    );
    renderPanel();
    await screen.findByText('문서 전체 요약 (qdrant)');

    await userEvent.click(screen.getByRole('tab', { name: '청크' }));

    expect(await screen.findByText('청크 본문입니다')).toBeInTheDocument();
  });

  it('닫기 버튼은 onClose를 호출한다', async () => {
    server.use(
      http.get(SUMMARY_URL, () => HttpResponse.json(summaryResponse('qdrant'))),
    );
    const onClose = renderPanel();
    await screen.findByText('문서 전체 요약 (qdrant)');

    await userEvent.click(
      screen.getByRole('button', { name: '저장 내용 패널 닫기' }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('요약 조회 실패 시 에러와 재시도 버튼을 보여준다', async () => {
    server.use(
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({ detail: 'error' }, { status: 500 }),
      ),
    );
    renderPanel();
    expect(
      await screen.findByText('문서 요약을 불러오지 못했습니다'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '다시 시도' }),
    ).toBeInTheDocument();
  });
});
