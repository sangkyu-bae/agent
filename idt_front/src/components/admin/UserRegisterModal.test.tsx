import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/constants/api';
import UserRegisterModal from './UserRegisterModal';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const mockDepartments = () =>
  server.use(
    http.get(`*${API_ENDPOINTS.ADMIN_DEPARTMENTS}`, () =>
      HttpResponse.json({
        departments: [
          { id: 'd1', name: '여신팀', description: null, created_at: '', updated_at: '' },
          { id: 'd2', name: '수신팀', description: null, created_at: '', updated_at: '' },
        ],
      }),
    ),
  );

const renderModal = (props?: Partial<React.ComponentProps<typeof UserRegisterModal>>) => {
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
      <UserRegisterModal {...defaultProps} {...props} />
    </QueryClientProvider>,
  );
};

describe('UserRegisterModal', () => {
  it('isOpen=false면 렌더링되지 않는다', () => {
    mockDepartments();
    renderModal({ isOpen: false });
    expect(screen.queryByText('사용자 등록')).not.toBeInTheDocument();
  });

  it('부서 목록을 드롭다운에 표시한다', async () => {
    mockDepartments();
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByLabelText(/부서/));
    await waitFor(() => {
      // placeholder(부서 선택 안 함) + 2 부서
      expect(screen.getAllByRole('option')).toHaveLength(3);
    });
    expect(screen.getByRole('option', { name: '여신팀' })).toBeInTheDocument();
  });

  it('이메일 형식이 잘못되면 검증 에러를 표시하고 onSubmit을 호출하지 않는다', async () => {
    mockDepartments();
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    renderModal({ onSubmit });

    await user.type(screen.getByLabelText(/이메일/), 'not-email');
    await user.type(screen.getByLabelText(/비밀번호/), 'secure1234');
    await user.type(screen.getByLabelText(/이름/), '배상규');
    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(screen.getByText('올바른 이메일 형식이 아닙니다.')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('비밀번호 8자 미만이면 검증 에러를 표시한다', async () => {
    mockDepartments();
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    renderModal({ onSubmit });

    await user.type(screen.getByLabelText(/이메일/), 'a@b.com');
    await user.type(screen.getByLabelText(/비밀번호/), 'short');
    await user.type(screen.getByLabelText(/이름/), '배상규');
    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(screen.getByText('비밀번호는 8자 이상이어야 합니다.')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('유효한 입력 시 onSubmit이 정규화된 payload로 호출된다', async () => {
    mockDepartments();
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    renderModal({ onSubmit });

    await user.type(screen.getByLabelText(/이메일/), 'new@example.com');
    await user.type(screen.getByLabelText(/비밀번호/), 'secure1234');
    await user.type(screen.getByLabelText(/이름/), '배상규');
    await user.type(screen.getByLabelText(/직급/), '대리');

    await user.click(screen.getByLabelText(/권한/));
    await user.click(screen.getByRole('option', { name: '관리자' }));

    await user.click(screen.getByLabelText(/부서/));
    await user.click(await screen.findByRole('option', { name: '여신팀' }));

    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith({
      email: 'new@example.com',
      password: 'secure1234',
      display_name: '배상규',
      role: 'admin',
      position: '대리',
      department_id: 'd1',
    });
  });

  it('상위에서 전달된 error를 표시한다', () => {
    mockDepartments();
    renderModal({ error: '이미 등록된 이메일입니다.' });
    expect(screen.getByText('이미 등록된 이메일입니다.')).toBeInTheDocument();
  });

  describe('닫기 동작', () => {
    it('백드롭(바깥) 클릭으로는 닫히지 않는다', async () => {
      mockDepartments();
      const onClose = vi.fn();
      const user = userEvent.setup();
      renderModal({ onClose });

      const backdrop = screen.getByRole('dialog').parentElement as HTMLElement;
      await user.click(backdrop);

      expect(onClose).not.toHaveBeenCalled();
    });

    it('X 버튼 클릭 시 onClose가 호출된다', async () => {
      mockDepartments();
      const onClose = vi.fn();
      const user = userEvent.setup();
      renderModal({ onClose });

      await user.click(screen.getByLabelText('닫기'));

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('취소 버튼 클릭 시 onClose가 호출된다', async () => {
      mockDepartments();
      const onClose = vi.fn();
      const user = userEvent.setup();
      renderModal({ onClose });

      await user.click(screen.getByRole('button', { name: '취소' }));

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('Esc 키 입력 시 onClose가 호출된다', async () => {
      mockDepartments();
      const onClose = vi.fn();
      const user = userEvent.setup();
      renderModal({ onClose });

      await user.keyboard('{Escape}');

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('isOpen=false면 Esc 키에 반응하지 않는다', async () => {
      mockDepartments();
      const onClose = vi.fn();
      const user = userEvent.setup();
      renderModal({ isOpen: false, onClose });

      await user.keyboard('{Escape}');

      expect(onClose).not.toHaveBeenCalled();
    });
  });
});
