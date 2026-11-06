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

  const fillRequiredFields = async () => {
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
  };

  it('고급 옵션의 조항 청킹 radio가 제출값에 반영된다 (Q3)', async () => {
    const onSubmit = renderModal();
    await fillRequiredFields();

    await userEvent.click(
      screen.getByRole('button', { name: /고급 옵션/ }),
    );
    await userEvent.click(
      screen.getByRole('radio', { name: /조항 단위 청킹/ }),
    );
    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '규정 KB',
        collection_name: 'documents',
        use_clause_chunking: true,
        use_custom_chunking: false,
        scope: 'PERSONAL',
      }),
    );
  });

  // ── kb-profile-selector Design §8.3 ──────────────────────────

  const chooseClauseMode = async () => {
    await userEvent.click(
      screen.getByRole('button', { name: /고급 옵션/ }),
    );
    await userEvent.click(
      screen.getByRole('radio', { name: /조항 단위 청킹/ }),
    );
  };

  const chooseProfile = async (name: string) => {
    await userEvent.click(
      await screen.findByRole('combobox', { name: '청킹 프로파일' }),
    );
    await userEvent.click(screen.getByRole('option', { name }));
  };

  it('M1: 조항 모드에서 고른 프로파일 ID를 제출한다', async () => {
    const onSubmit = renderModal();
    await fillRequiredFields();
    await chooseClauseMode();
    await chooseProfile('계약서');

    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        use_clause_chunking: true,
        chunking_profile_id: 'prof-contract',
      }),
    );
  });

  it('M2: 기본 프로파일 따름이면 null을 제출한다', async () => {
    const onSubmit = renderModal();
    await fillRequiredFields();
    await chooseClauseMode();
    await screen.findByText(/경계 규칙 2개/);

    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        use_clause_chunking: true,
        chunking_profile_id: null,
      }),
    );
  });

  it('M3: 조항 모드가 아니면 프로파일 ID를 보내지 않는다', async () => {
    const onSubmit = renderModal();
    await fillRequiredFields();
    await chooseClauseMode();
    await chooseProfile('계약서');
    await userEvent.click(
      screen.getByRole('radio', { name: /기본 청킹/ }),
    );

    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit.mock.calls[0][0].chunking_profile_id).toBeUndefined();
  });

  it('M4: 조항 모드를 고르기 전에는 프로파일 목록을 조회하지 않는다', async () => {
    let calls = 0;
    server.use(
      http.get(`*${API_ENDPOINTS.CHUNKING_PROFILES}`, () => {
        calls += 1;
        return HttpResponse.json({ profiles: [], total: 0 });
      }),
    );
    renderModal();

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(calls).toBe(0);
  });

  it('M5: 닫으면 선택값을 초기화한다', async () => {
    renderModal();
    await chooseClauseMode();
    await chooseProfile('계약서');

    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    await chooseClauseMode();

    expect(
      await screen.findByRole('combobox', { name: '청킹 프로파일' }),
    ).toHaveTextContent('기본 프로파일 따름');
  });

  it('M5-1: 닫혔다가 다시 열리면(isOpen false→true) 선택값을 초기화한다', async () => {
    const props = {
      onClose: vi.fn(),
      onSubmit: vi.fn(),
      isPending: false,
      error: null,
    };
    const { rerender } = render(
      <CreateKnowledgeBaseModal isOpen {...props} />,
      { wrapper: createWrapper() },
    );
    await chooseClauseMode();
    await chooseProfile('계약서');

    rerender(<CreateKnowledgeBaseModal isOpen={false} {...props} />);
    rerender(<CreateKnowledgeBaseModal isOpen {...props} />);

    expect(
      screen.queryByRole('radio', { name: /조항 단위 청킹/ }),
    ).not.toBeInTheDocument();
    await chooseClauseMode();
    expect(
      await screen.findByRole('combobox', { name: '청킹 프로파일' }),
    ).toHaveTextContent('기본 프로파일 따름');
  });

  // ── kb-custom-chunking §6.1 ──────────────────────────────────

  it('커스텀 청킹 radio 선택 시 설정 폼이 열리고 제출값에 config가 담긴다', async () => {
    const onSubmit = renderModal();
    await fillRequiredFields();

    await userEvent.click(
      screen.getByRole('button', { name: /고급 옵션/ }),
    );
    await userEvent.click(
      screen.getByRole('radio', { name: /커스텀 청킹/ }),
    );

    const sizeInput = screen.getByLabelText(/^청크 크기/);
    await userEvent.clear(sizeInput);
    await userEvent.type(sizeInput, '1200');

    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        use_clause_chunking: false,
        use_custom_chunking: true,
        custom_chunking_config: expect.objectContaining({
          version: 1,
          strategy: 'parent_child',
          chunk_size: 1200,
          chunk_overlap: 50,
        }),
      }),
    );
  });

  it('커스텀 청킹 값이 범위를 벗어나면 제출이 차단되고 에러가 보인다', async () => {
    const onSubmit = renderModal();
    await fillRequiredFields();

    await userEvent.click(
      screen.getByRole('button', { name: /고급 옵션/ }),
    );
    await userEvent.click(
      screen.getByRole('radio', { name: /커스텀 청킹/ }),
    );

    const sizeInput = screen.getByLabelText(/^청크 크기/);
    await userEvent.clear(sizeInput);
    await userEvent.type(sizeInput, '50');

    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText('청크 크기는 100~4000 사이여야 합니다'),
    ).toBeInTheDocument();
  });
});
