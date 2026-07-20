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
import KbSearchSection from './KbSearchSection';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderSection = (
  props: Partial<React.ComponentProps<typeof KbSearchSection>> = {},
) =>
  render(
    <KbSearchSection
      kbId="kb-public-1"
      scopeDoc={null}
      onClearScope={() => {}}
      {...props}
    />,
    { wrapper: createWrapper() },
  );

describe('KbSearchSection — kb-retrieval-test FR-08/09/10', () => {
  it('검색 실행 시 결과를 렌더링한다', async () => {
    renderSection();

    await userEvent.type(
      screen.getByPlaceholderText(/검색 쿼리를 입력하세요/),
      '여신 한도',
    );
    await userEvent.click(screen.getByRole('button', { name: '검색' }));

    expect(
      await screen.findByText(/여신 한도는 연소득의 일정 배수로 제한한다/),
    ).toBeInTheDocument();
  });

  it('기본 스코프 배지는 KB 전체 검색이다', () => {
    renderSection();

    expect(screen.getByText('KB 전체에서 검색')).toBeInTheDocument();
  });

  it('문서 스코프가 지정되면 배지에 파일명이 표시되고 검색에 document_id가 전달된다', async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_SEARCH(':kbId')}`,
        async ({ request }) => {
          capturedBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({
            query: 'q',
            kb_id: 'kb-public-1',
            kb_name: '전사 규정',
            collection_name: 'admin-coll-01',
            results: [],
            total_found: 0,
            bm25_weight: 0.5,
            vector_weight: 0.5,
            request_id: 'req-x',
            document_id: 'doc-1',
          });
        },
      ),
    );
    renderSection({
      scopeDoc: { document_id: 'doc-1', filename: '여신규정.pdf' },
    });

    expect(
      screen.getByText(/여신규정\.pdf에서 검색/),
    ).toBeInTheDocument();

    await userEvent.type(
      screen.getByPlaceholderText(/검색 쿼리를 입력하세요/),
      '한도',
    );
    await userEvent.click(screen.getByRole('button', { name: '검색' }));

    await waitFor(() =>
      expect(capturedBody).toMatchObject({ document_id: 'doc-1' }),
    );
  });

  it('스코프 해제 버튼이 onClearScope를 호출한다', async () => {
    const onClearScope = vi.fn();
    renderSection({
      scopeDoc: { document_id: 'doc-1', filename: '여신규정.pdf' },
      onClearScope,
    });

    await userEvent.click(
      screen.getByRole('button', { name: 'KB 전체 검색으로 전환' }),
    );

    expect(onClearScope).toHaveBeenCalled();
  });

  it('히스토리 행 클릭 시 검색 조건이 입력폼에 재적용된다', async () => {
    renderSection();

    await userEvent.click(
      screen.getByRole('button', { name: /검색 히스토리/ }),
    );
    await userEvent.click(await screen.findByText('연체 기준'));

    expect(
      screen.getByPlaceholderText(/검색 쿼리를 입력하세요/),
    ).toHaveValue('연체 기준');
  });

  it('검색 실패 시 에러 상태를 표시한다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_SEARCH(':kbId')}`, () =>
        HttpResponse.json(
          { detail: 'Cannot determine embedding model' },
          { status: 422 },
        ),
      ),
    );
    renderSection();

    await userEvent.type(
      screen.getByPlaceholderText(/검색 쿼리를 입력하세요/),
      '한도',
    );
    await userEvent.click(screen.getByRole('button', { name: '검색' }));

    expect(
      await screen.findByText(/검색 중 오류가 발생했습니다/),
    ).toBeInTheDocument();
  });
});
