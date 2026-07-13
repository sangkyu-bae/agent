import { render, screen } from '@testing-library/react';
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
import CreateKnowledgeBaseModal from './CreateKnowledgeBaseModal';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderModal = (onSubmit = vi.fn()) => {
  render(
    <CreateKnowledgeBaseModal
      isOpen
      onClose={vi.fn()}
      onSubmit={onSubmit}
      isPending={false}
      error={null}
    />,
    { wrapper: createWrapper() },
  );
  return onSubmit;
};

describe('CreateKnowledgeBaseModal — kb-management-ui', () => {
  it('부서 scope 선택 시 부서 드롭다운이 노출된다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_DEPARTMENTS}`, () =>
        HttpResponse.json({
          departments: [
            {
              id: 'dept-1',
              name: '여신심사부',
              description: null,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          ],
        }),
      ),
    );
    renderModal();

    expect(
      screen.queryByRole('combobox', { name: '부서 선택' }),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('radio', { name: /부서/ }));

    expect(
      await screen.findByRole('combobox', { name: '부서 선택' }),
    ).toBeInTheDocument();
  });

  it('컬렉션이 없으면 관리자 요청 안내를 보여준다 (R2)', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.COLLECTIONS}`, () =>
        HttpResponse.json({ collections: [], total: 0 }),
      ),
    );
    renderModal();

    expect(
      await screen.findByText(/관리자에게 컬렉션 생성을 요청해주세요/),
    ).toBeInTheDocument();
  });

  it('고급 옵션의 조항 청킹 토글이 제출값에 반영된다 (Q3)', async () => {
    const onSubmit = renderModal();

    await userEvent.type(
      screen.getByPlaceholderText('여신 규정집'),
      '규정 KB',
    );
    await userEvent.click(
      await screen.findByRole('combobox', { name: '대상 컬렉션' }),
    );
    await userEvent.click(
      await screen.findByRole('option', { name: /documents/ }),
    );

    await userEvent.click(
      screen.getByRole('button', { name: /고급 옵션/ }),
    );
    await userEvent.click(
      screen.getByRole('checkbox', { name: /조항 단위 청킹 사용/ }),
    );
    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '규정 KB',
        collection_name: 'documents',
        use_clause_chunking: true,
        scope: 'PERSONAL',
      }),
    );
  });
});
