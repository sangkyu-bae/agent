import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  beforeAll,
  afterEach,
  afterAll,
  describe,
  it,
  expect,
  vi,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/constants/api';
import CreateCollectionModal from './CreateCollectionModal';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderModal = (props?: Partial<React.ComponentProps<typeof CreateCollectionModal>>) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSubmit: vi.fn(),
    isPending: false,
    error: null,
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <CreateCollectionModal {...defaultProps} {...props} />
    </QueryClientProvider>,
  );
};

const getModelSelect = () => screen.getByLabelText('임베딩 모델');

describe('CreateCollectionModal — 임베딩 모델 드롭다운', () => {
  it('모델 목록 로딩 시 로딩 상태를 표시한다', () => {
    renderModal();
    expect(screen.getByText('모델 목록을 불러오는 중...')).toBeInTheDocument();
  });

  it('모델 목록 조회 성공 시 드롭다운에 모델이 표시된다', async () => {
    renderModal();
    await waitFor(() => expect(getModelSelect()).toBeInTheDocument());
    const select = getModelSelect();
    const options = within(select).getAllByRole('option');
    expect(options).toHaveLength(3); // placeholder + 2 models
    expect(options[1].textContent).toBe('OpenAI Embedding 3 Small');
    expect(options[2].textContent).toBe('OpenAI Embedding 3 Large');
  });

  it('모델 선택 시 vector_dimension이 참고 표시된다', async () => {
    const user = userEvent.setup();
    renderModal();
    await waitFor(() => expect(getModelSelect()).toBeInTheDocument());
    await user.selectOptions(getModelSelect(), 'text-embedding-3-small');
    expect(screen.getByText('1536차원')).toBeInTheDocument();
  });

  it('생성 버튼 클릭 시 embedding_model이 포함된 데이터로 onSubmit이 호출된다', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderModal({ onSubmit });

    await waitFor(() => expect(getModelSelect()).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('my-collection'), 'test-col');
    await user.selectOptions(getModelSelect(), 'text-embedding-3-small');
    await user.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'test-col',
      embedding_model: 'text-embedding-3-small',
      distance: 'Cosine',
      scope: 'PERSONAL',
      department_id: undefined,
    });
  });

  it('scope=DEPARTMENT 선택 시 부서 ID 입력 필드가 표시되고 onSubmit에 포함된다', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderModal({ onSubmit });

    await waitFor(() => expect(getModelSelect()).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('my-collection'), 'dept-col');
    await user.selectOptions(getModelSelect(), 'text-embedding-3-small');

    expect(screen.queryByPlaceholderText('dept-uuid')).not.toBeInTheDocument();

    await user.click(screen.getByDisplayValue('DEPARTMENT'));

    const deptInput = screen.getByPlaceholderText('dept-uuid');
    expect(deptInput).toBeInTheDocument();
    await user.type(deptInput, 'dept-123');

    await user.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'dept-col',
      embedding_model: 'text-embedding-3-small',
      distance: 'Cosine',
      scope: 'DEPARTMENT',
      department_id: 'dept-123',
    });
  });

  it('모델 목록 조회 실패 시 vector_size 직접 입력 fallback이 표시된다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.EMBEDDING_MODELS}`, () =>
        HttpResponse.json({ detail: 'server error' }, { status: 500 }),
      ),
    );
    renderModal();
    await waitFor(() =>
      expect(
        screen.getByText('모델 목록을 불러올 수 없습니다'),
      ).toBeInTheDocument(),
    );
    expect(screen.getByDisplayValue('1536')).toBeInTheDocument();
  });

  it('fallback 모드에서 생성 시 vector_size가 포함된 데이터로 onSubmit이 호출된다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.EMBEDDING_MODELS}`, () =>
        HttpResponse.json({ detail: 'server error' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderModal({ onSubmit });

    await waitFor(() =>
      expect(
        screen.getByText('모델 목록을 불러올 수 없습니다'),
      ).toBeInTheDocument(),
    );

    await user.type(screen.getByPlaceholderText('my-collection'), 'test-col');
    await user.click(screen.getByRole('button', { name: '생성' }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'test-col',
      vector_size: 1536,
      distance: 'Cosine',
      scope: 'PERSONAL',
      department_id: undefined,
    });
  });
});
