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

describe('KnowledgeBaseDetailPage — kb-document-management', () => {
  const DOC_DELETE = `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_DETAIL(':kbId', ':docId')}`;
  const DOCS = `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(':kbId')}`;

  const doc1 = {
    document_id: 'doc-1', filename: '여신규정.pdf', chunk_count: 12,
    chunking_strategy: 'clause_aware', created_at: '2026-07-09T10:00:00Z',
    can_delete: true,
  };
  const doc2 = {
    document_id: 'doc-2', filename: '내규집.pdf', chunk_count: 8,
    chunking_strategy: 'parent_child', created_at: '2026-07-08T09:00:00Z',
    can_delete: false,
  };

  /** 삭제 요청 수를 세고, 삭제 뒤에는 목록에서 doc-1을 뺀다. */
  const useStatefulDocuments = (deleteDelayMs = 0) => {
    const state = { deleteCalls: 0, deleted: false };
    server.use(
      http.get(DOCS, ({ params }) => {
        const documents = state.deleted ? [doc2] : [doc1, doc2];
        return HttpResponse.json({
          kb_id: params.kbId, kb_name: '전사 규정', documents,
          total: documents.length, offset: 0, limit: 20,
        });
      }),
      http.delete(DOC_DELETE, async ({ params }) => {
        state.deleteCalls += 1;
        if (deleteDelayMs) {
          await new Promise((resolve) => setTimeout(resolve, deleteDelayMs));
        }
        state.deleted = true;
        return HttpResponse.json({
          kb_id: params.kbId, document_id: params.docId, filename: '여신규정.pdf',
          deleted_qdrant_chunks: 12, deleted_es_chunks: 12, status: 'deleted',
        });
      }),
    );
    return state;
  };

  const openDeleteDialog = async () => {
    await userEvent.click(
      await screen.findByRole('button', { name: '여신규정.pdf 삭제' }),
    );
    expect(screen.getByText('문서 삭제')).toBeInTheDocument();
  };

  it('삭제 권한이 있는 문서에만 삭제 버튼이 보인다', async () => {
    renderPage();
    await screen.findByText('내규집.pdf');

    expect(
      screen.getByRole('button', { name: '여신규정.pdf 삭제' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '내규집.pdf 삭제' }),
    ).not.toBeInTheDocument();
  });

  it('삭제 성공 시 목록에서 빠지고 드릴다운·검색 범위가 해제된다', async () => {
    const state = useStatefulDocuments();
    renderPage();
    await userEvent.click(await screen.findByText('여신규정.pdf'));
    await userEvent.click(
      screen.getAllByRole('button', { name: '이 문서에서 검색' })[0],
    );
    expect(screen.getByText(/여신규정\.pdf에서 검색/)).toBeInTheDocument();

    await openDeleteDialog();
    await userEvent.click(screen.getByRole('button', { name: '삭제' }));

    await waitFor(() =>
      expect(screen.queryByText('여신규정.pdf')).not.toBeInTheDocument(),
    );
    expect(state.deleteCalls).toBe(1);
    expect(screen.queryByText('문서 삭제')).not.toBeInTheDocument();
    expect(screen.getByText('KB 전체에서 검색')).toBeInTheDocument();
    expect(screen.getByText('내규집.pdf')).toBeInTheDocument();
  });

  it('409이면 서버 메시지를 보여주고 다이얼로그를 유지한다', async () => {
    server.use(
      http.delete(DOC_DELETE, () =>
        HttpResponse.json(
          {
            detail:
              '섹션 요약이 진행 중인 문서는 삭제할 수 없습니다. 요약이 끝난 뒤 다시 시도해 주세요.',
          },
          { status: 409 },
        ),
      ),
    );
    renderPage();
    await openDeleteDialog();

    await userEvent.click(screen.getByRole('button', { name: '삭제' }));

    expect(
      await screen.findByText(/섹션 요약이 진행 중인 문서는 삭제할 수 없습니다/),
    ).toBeInTheDocument();
    expect(screen.getByText('문서 삭제')).toBeInTheDocument();
    expect(screen.getAllByText('여신규정.pdf').length).toBeGreaterThan(0);
  });

  it('다시 열면 이전 오류가 남아 있지 않다', async () => {
    server.use(
      http.delete(DOC_DELETE, () =>
        HttpResponse.json(
          { detail: '저장소에서 문서를 삭제하지 못했습니다.' },
          { status: 503 },
        ),
      ),
    );
    renderPage();
    await openDeleteDialog();
    await userEvent.click(screen.getByRole('button', { name: '삭제' }));
    await screen.findByText(/저장소에서 문서를 삭제하지 못했습니다/);

    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    await openDeleteDialog();

    expect(
      screen.queryByText(/저장소에서 문서를 삭제하지 못했습니다/),
    ).not.toBeInTheDocument();
  });

  it('대기 중에는 중복 요청과 닫기를 막는다', async () => {
    // 지연은 클릭 두 번보다 충분히 길어야 대기 상태를 검증할 수 있다
    const state = useStatefulDocuments(1500);
    renderPage();
    await openDeleteDialog();

    const confirm = screen.getByRole('button', { name: '삭제' });
    await userEvent.click(confirm);
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '취소' }));

    expect(screen.getByText('문서 삭제')).toBeInTheDocument();
    await waitFor(
      () => expect(screen.queryByText('문서 삭제')).not.toBeInTheDocument(),
      { timeout: 4000 },
    );
    expect(state.deleteCalls).toBe(1);
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
