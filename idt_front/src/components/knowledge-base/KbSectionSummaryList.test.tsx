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
import type {
  KbSectionSummaryListResponse,
  SectionSummaryStatusResponse,
} from '@/types/knowledgeBase';
import KbSectionSummaryList from './KbSectionSummaryList';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const SUMMARIES_URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARIES('kb-1', 'doc-1')}`;
const STATUS_URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARY_STATUS('kb-1', 'doc-1')}`;
const RETRY_URL = `*${API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARY_RETRY('kb-1', 'doc-1')}`;

const jobStatus = (
  over: Partial<SectionSummaryStatusResponse> = {},
): SectionSummaryStatusResponse => ({
  job_id: 'job-1',
  document_id: 'doc-1',
  status: 'completed',
  total_sections: 20,
  done_sections: 20,
  failed_sections: 0,
  is_stale: false,
  error: null,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-14T00:00:00Z',
  ...over,
});

const summaries = (): KbSectionSummaryListResponse => ({
  source: 'qdrant',
  document_id: 'doc-1',
  total: 1,
  items: [
    {
      chunk_id: 'ss-1',
      section_ref: 'ref-1',
      clause_title: '제3장 여신심사',
      chunk_index: 0,
      summary_text: '여신심사 기준 요약 본문',
      keywords: ['여신', '심사'],
      metadata: { kb_id: 'kb-1', chunk_type: 'section_summary' },
    },
  ],
});

const renderList = () =>
  render(
    <KbSectionSummaryList kbId="kb-1" documentId="doc-1" source="qdrant" />,
    { wrapper: createWrapper() },
  );

describe('KbSectionSummaryList — kb-content-browser', () => {
  it('섹션 요약 목록(제목/본문/키워드)을 그린다', async () => {
    server.use(
      http.get(STATUS_URL, () => HttpResponse.json(jobStatus())),
      http.get(SUMMARIES_URL, () => HttpResponse.json(summaries())),
    );
    renderList();

    expect(await screen.findByText('제3장 여신심사')).toBeInTheDocument();
    expect(screen.getByText('여신심사 기준 요약 본문')).toBeInTheDocument();
    expect(screen.getByText('여신')).toBeInTheDocument();
  });

  it('completed 잡은 진행률 배너를 그리지 않는다', async () => {
    server.use(
      http.get(STATUS_URL, () => HttpResponse.json(jobStatus())),
      http.get(SUMMARIES_URL, () => HttpResponse.json(summaries())),
    );
    renderList();
    await screen.findByText('제3장 여신심사');
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('processing 잡은 진행률 바를 보여준다 (D9)', async () => {
    server.use(
      http.get(STATUS_URL, () =>
        HttpResponse.json(
          jobStatus({ status: 'processing', done_sections: 12 }),
        ),
      ),
      http.get(SUMMARIES_URL, () => HttpResponse.json(summaries())),
    );
    renderList();

    expect(
      await screen.findByText(/섹션 요약 생성 중 — 12\/20 섹션 완료/),
    ).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '재시도' }),
    ).not.toBeInTheDocument();
  });

  it('failed 잡은 재시도 버튼을 보여주고 클릭 시 retry API를 호출한다', async () => {
    let retried = false;
    server.use(
      http.get(STATUS_URL, () =>
        HttpResponse.json(
          jobStatus({ status: 'failed', done_sections: 5, failed_sections: 3 }),
        ),
      ),
      http.get(SUMMARIES_URL, () => HttpResponse.json(summaries())),
      http.post(RETRY_URL, () => {
        retried = true;
        return HttpResponse.json(jobStatus({ status: 'processing' }), {
          status: 202,
        });
      }),
    );
    renderList();

    await userEvent.click(
      await screen.findByRole('button', { name: '재시도' }),
    );
    await waitFor(() => expect(retried).toBe(true));
  });

  it('잡 상태 404(요약 비활성 문서)면 배너 없이 목록만 그린다', async () => {
    server.use(
      http.get(STATUS_URL, () =>
        HttpResponse.json({ detail: 'not found' }, { status: 404 }),
      ),
      http.get(SUMMARIES_URL, () => HttpResponse.json(summaries())),
    );
    renderList();

    expect(await screen.findByText('제3장 여신심사')).toBeInTheDocument();
    expect(screen.queryByText(/섹션 요약 생성 중/)).not.toBeInTheDocument();
  });

  it('빈 목록은 안내 문구를 보여준다', async () => {
    server.use(
      http.get(STATUS_URL, () => HttpResponse.json(jobStatus())),
      http.get(SUMMARIES_URL, () =>
        HttpResponse.json({
          source: 'qdrant',
          document_id: 'doc-1',
          total: 0,
          items: [],
        }),
      ),
    );
    renderList();
    expect(
      await screen.findByText('저장된 섹션 요약이 없습니다'),
    ).toBeInTheDocument();
  });
});
