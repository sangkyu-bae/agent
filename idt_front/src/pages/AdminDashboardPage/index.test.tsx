import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import {
  beforeAll,
  beforeEach,
  afterEach,
  afterAll,
  describe,
  it,
  expect,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AdminDashboardPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const statsBody = {
  kb: { total: 3, active: 2, by_scope: { PERSONAL: 1, PUBLIC: 2 } },
  documents: { total: 340, with_kb: 310, without_kb: 30 },
  chunks: { total: 15820 },
  users: { total: 25, approved: 20, pending: 4, admins: 2 },
};

const healthBody = {
  components: [
    { name: 'mysql', status: 'ok', latency_ms: 4, error: null },
    { name: 'qdrant', status: 'ok', latency_ms: 12, error: null },
    {
      name: 'elasticsearch',
      status: 'fail',
      latency_ms: null,
      error: 'timeout(3s)',
    },
  ],
};

const kbBreakdownBody = {
  rows: [
    {
      kb_id: 'kb-1',
      name: '여신 규정집',
      scope: 'PUBLIC',
      status: 'active',
      document_count: 42,
      chunk_count: 1830,
      last_uploaded_at: '2026-07-17T09:12:00',
    },
    {
      kb_id: 'kb-2',
      name: '빈 KB',
      scope: 'PERSONAL',
      status: 'active',
      document_count: 0,
      chunk_count: 0,
      last_uploaded_at: null,
    },
  ],
};

const recentDocsBody = {
  rows: [
    {
      document_id: 'd1',
      filename: '규정개정.pdf',
      kb_id: 'kb-1',
      kb_name: '여신 규정집',
      collection_name: 'kb_main',
      chunk_count: 45,
      chunk_strategy: 'clause_aware',
      created_at: '2026-07-18T08:30:00',
    },
  ],
};

const usageSummaryBody = {
  from_dt: '2026-06-18T00:00:00',
  to_dt: '2026-07-18T00:00:00',
  total_runs: 128,
  success_runs: 120,
  failed_runs: 8,
  success_rate: 0.9375,
  total_tokens: 50000,
  total_cost_usd: '1.2345',
};

const failedRun = {
  id: 'run-2',
  user_id: 'u1',
  agent_id: 'super',
  conversation_id: 'c1',
  status: 'FAILED',
  started_at: '2026-07-18T09:00:00',
  ended_at: null,
  latency_ms: 900,
  total_tokens: 10,
  total_cost_usd: '0.001',
  llm_call_count: 1,
  error_message: 'LLM timeout 발생',
};

const successRun = {
  ...failedRun,
  id: 'run-1',
  status: 'SUCCESS',
  error_message: null,
};

beforeEach(() => {
  server.use(
    http.get('*/api/v1/admin/dashboard/stats', () =>
      HttpResponse.json(statsBody),
    ),
    http.get('*/api/v1/admin/dashboard/health', () =>
      HttpResponse.json(healthBody),
    ),
    http.get('*/api/v1/admin/dashboard/kb-breakdown', () =>
      HttpResponse.json(kbBreakdownBody),
    ),
    http.get('*/api/v1/admin/dashboard/recent-documents', () =>
      HttpResponse.json(recentDocsBody),
    ),
    http.get('*/api/v1/admin/usage/summary', () =>
      HttpResponse.json(usageSummaryBody),
    ),
    http.get('*/api/v1/admin/usage/timeseries', () =>
      HttpResponse.json({
        from_dt: '2026-06-18T00:00:00',
        to_dt: '2026-07-18T00:00:00',
        bucket: 'day',
        points: [],
      }),
    ),
    http.get('*/api/v1/admin/runs', ({ request }) => {
      const url = new URL(request.url);
      const isFailed = url.searchParams.get('status') === 'FAILED';
      return HttpResponse.json({
        from_dt: null,
        to_dt: null,
        limit: 5,
        offset: 0,
        total: 1,
        rows: [isFailed ? failedRun : successRun],
      });
    }),
  );
});

const renderPage = () => {
  const Wrapper = createWrapper();
  return render(
    <MemoryRouter>
      <Wrapper>
        <AdminDashboardPage />
      </Wrapper>
    </MemoryRouter>,
  );
};

describe('AdminDashboardPage', () => {
  it('적재 KPI 카드 — KB/문서/청크/사용자 수치 렌더', async () => {
    renderPage();
    expect(await screen.findByText('340')).toBeInTheDocument(); // 문서
    expect(screen.getByText('15,820')).toBeInTheDocument(); // 청크
    expect(screen.getByText('25')).toBeInTheDocument(); // 사용자
    expect(screen.getByText('지식 베이스')).toBeInTheDocument();
  });

  it('헬스 배지 — 부분 실패(ES fail) 표시, 나머지 ok', async () => {
    renderPage();
    expect(await screen.findByText('timeout(3s)')).toBeInTheDocument();
    expect(screen.getByText('MySQL')).toBeInTheDocument();
    expect(screen.getByText('Qdrant')).toBeInTheDocument();
  });

  it('KB별 현황 테이블 — 문서 0건 KB 포함 렌더', async () => {
    renderPage();
    // KB 테이블 + 최근 업로드 양쪽에 노출될 수 있어 복수 매칭 허용
    expect((await screen.findAllByText('여신 규정집')).length).toBeGreaterThan(0);
    expect(screen.getByText('빈 KB')).toBeInTheDocument();
    expect(screen.getByText('1,830')).toBeInTheDocument();
  });

  it('최근 업로드·최근 실패 목록 렌더', async () => {
    renderPage();
    expect(await screen.findByText('규정개정.pdf')).toBeInTheDocument();
    expect(await screen.findByText('LLM timeout 발생')).toBeInTheDocument();
  });

  it('기간 사용량 카드 — 기존 usage API 수치 렌더', async () => {
    renderPage();
    expect(await screen.findByText('128')).toBeInTheDocument(); // 총 Run
    expect(screen.getByText('93.8%')).toBeInTheDocument(); // 성공률
  });

  it('새로고침 버튼 존재', async () => {
    renderPage();
    expect(
      await screen.findByRole('button', { name: '새로고침' }),
    ).toBeInTheDocument();
  });
});
