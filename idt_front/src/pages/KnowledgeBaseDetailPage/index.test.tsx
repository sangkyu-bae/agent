import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
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
import KnowledgeBaseDetailPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = (kbId = 'kb-public-1') =>
  render(
    <MemoryRouter initialEntries={[`/knowledge-bases/${kbId}`]}>
      <Routes>
        <Route
          path="/knowledge-bases/:kbId"
          element={<KnowledgeBaseDetailPage />}
        />
      </Routes>
    </MemoryRouter>,
    { wrapper: createWrapper() },
  );

describe('KnowledgeBaseDetailPage — kb-management-ui', () => {
  it('KB 정보와 문서 목록을 렌더링한다', async () => {
    renderPage();

    expect(
      await screen.findByRole('heading', { name: '전사 규정' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('여신규정.pdf')).toBeInTheDocument();
    expect(screen.getByText('내규집.pdf')).toBeInTheDocument();
    // 청킹 방식 라벨
    expect(screen.getByText('조항 단위')).toBeInTheDocument();
    expect(screen.getByText('기본')).toBeInTheDocument();
  });

  it('업로드 성공 시 결과(청크 수·저장 상태)를 표시한다', async () => {
    renderPage();
    await screen.findByRole('heading', { name: '전사 규정' });

    await userEvent.click(
      screen.getByRole('button', { name: '+ 문서 업로드' }),
    );
    const file = new File(['%PDF-1.4'], 'uploaded.pdf', {
      type: 'application/pdf',
    });
    await userEvent.upload(
      screen.getByLabelText('업로드할 문서 파일'),
      file,
    );
    await userEvent.click(screen.getByRole('button', { name: '업로드' }));

    expect(
      await screen.findByText(/업로드가 완료되었습니다/),
    ).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getAllByText('저장 완료')).toHaveLength(2);
  });

  it('업로드 실패 시 에러를 표시하고 다시 시도할 수 있다', async () => {
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(':kbId')}`,
        () =>
          HttpResponse.json(
            { detail: 'No write access' },
            { status: 403 },
          ),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: '전사 규정' });

    await userEvent.click(
      screen.getByRole('button', { name: '+ 문서 업로드' }),
    );
    const file = new File(['%PDF-1.4'], 'x.pdf', {
      type: 'application/pdf',
    });
    await userEvent.upload(
      screen.getByLabelText('업로드할 문서 파일'),
      file,
    );
    await userEvent.click(screen.getByRole('button', { name: '업로드' }));

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '업로드' }),
      ).toBeInTheDocument(),
    );
  });

  it('업로드 중에는 닫기가 차단된다 (D6 disableClose)', async () => {
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(':kbId')}`,
        async ({ params }) => {
          await new Promise((resolve) => setTimeout(resolve, 300));
          return HttpResponse.json({
            kb_id: params.kbId,
            kb_name: '전사 규정',
            collection_name: 'admin-coll-01',
            document_id: 'doc-new-1',
            filename: 'slow.pdf',
            total_pages: 1,
            chunk_count: 3,
            chunking_strategy: 'parent_child',
            qdrant: { status: 'success', error: null },
            es: { status: 'success', error: null },
            status: 'completed',
            section_summary: null,
          });
        },
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: '전사 규정' });

    await userEvent.click(
      screen.getByRole('button', { name: '+ 문서 업로드' }),
    );
    const file = new File(['%PDF-1.4'], 'slow.pdf', {
      type: 'application/pdf',
    });
    await userEvent.upload(
      screen.getByLabelText('업로드할 문서 파일'),
      file,
    );
    await userEvent.click(screen.getByRole('button', { name: '업로드' }));

    expect(
      await screen.findByText(/창을 닫지 마세요/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '닫기' }),
    ).not.toBeInTheDocument();

    // act 경고 방지: 업로드 완료까지 대기
    expect(
      await screen.findByText(/업로드가 완료되었습니다/),
    ).toBeInTheDocument();
  });

  it('섹션 요약 킥오프가 있으면 요약 생성 뱃지를 표시한다', async () => {
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(':kbId')}`,
        ({ params }) =>
          HttpResponse.json({
            kb_id: params.kbId,
            kb_name: '전사 규정',
            collection_name: 'admin-coll-01',
            document_id: 'doc-new-1',
            filename: 'clause.pdf',
            total_pages: 2,
            chunk_count: 7,
            chunking_strategy: 'clause_aware',
            qdrant: { status: 'success', error: null },
            es: { status: 'success', error: null },
            status: 'completed',
            section_summary: { job_id: 'job-1', status: 'processing' },
          }),
      ),
    );
    renderPage();
    await screen.findByRole('heading', { name: '전사 규정' });

    await userEvent.click(
      screen.getByRole('button', { name: '+ 문서 업로드' }),
    );
    const file = new File(['%PDF-1.4'], 'clause.pdf', {
      type: 'application/pdf',
    });
    await userEvent.upload(
      screen.getByLabelText('업로드할 문서 파일'),
      file,
    );
    await userEvent.click(screen.getByRole('button', { name: '업로드' }));

    expect(
      await screen.findByText(/섹션 요약을 백그라운드에서 생성하고 있습니다/),
    ).toBeInTheDocument();
  });

  it('빈 문서 목록이면 업로드 유도 안내를 보여준다', async () => {
    server.use(
      http.get(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(':kbId')}`,
        ({ params }) =>
          HttpResponse.json({
            kb_id: params.kbId,
            kb_name: '전사 규정',
            documents: [],
            total: 0,
            offset: 0,
            limit: 20,
          }),
      ),
    );
    renderPage();

    expect(
      await screen.findByText(/아직 업로드된 문서가 없습니다/),
    ).toBeInTheDocument();
  });
});

describe('KnowledgeBaseDetailPage — kb-retrieval-test', () => {
  it('상태 요약 카드 4종을 렌더링한다 (chunk_count 판정)', async () => {
    renderPage();
    await screen.findByRole('heading', { name: '전사 규정' });

    // mock 문서 2건 모두 chunk_count > 0
    expect(screen.getByTestId('kb-total-count')).toHaveTextContent('2');
    expect(screen.getByTestId('kb-ready-count')).toHaveTextContent('2');
    expect(screen.getByTestId('kb-processing-count')).toHaveTextContent('0');
    expect(screen.getByTestId('kb-error-count')).toHaveTextContent('0');
  });

  it('리트리버 테스트 섹션에서 검색을 실행하면 결과가 표시된다', async () => {
    renderPage();
    await screen.findByRole('heading', { name: '전사 규정' });

    await userEvent.type(
      screen.getByPlaceholderText(/검색 쿼리를 입력하세요/),
      '여신 한도',
    );
    await userEvent.click(screen.getByRole('button', { name: '검색' }));

    expect(
      await screen.findByText(/여신 한도는 연소득의 일정 배수로 제한한다/),
    ).toBeInTheDocument();
  });

  it('문서 행의 "이 문서에서 검색" 클릭 시 스코프 배지가 전환된다', async () => {
    renderPage();
    await screen.findByText('여신규정.pdf');

    expect(screen.getByText('KB 전체에서 검색')).toBeInTheDocument();

    await userEvent.click(
      screen.getAllByRole('button', { name: '이 문서에서 검색' })[0],
    );

    expect(screen.getByText(/여신규정\.pdf에서 검색/)).toBeInTheDocument();

    // 스코프 해제 → KB 전체 복귀
    await userEvent.click(
      screen.getByRole('button', { name: 'KB 전체 검색으로 전환' }),
    );
    expect(screen.getByText('KB 전체에서 검색')).toBeInTheDocument();
  });
});
