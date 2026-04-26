import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import UpdateScopeModal from './UpdateScopeModal';

const baseProps = {
  isOpen: true,
  collectionName: 'my-docs',
  currentScope: 'PERSONAL' as const,
  onClose: vi.fn(),
  onSubmit: vi.fn(),
  isPending: false,
  error: null,
};

describe('UpdateScopeModal', () => {
  it('컬렉션 이름과 현재 scope를 표시한다', () => {
    render(<UpdateScopeModal {...baseProps} />);
    expect(screen.getByText('my-docs')).toBeInTheDocument();
    expect(screen.getAllByText('개인')).toHaveLength(2);
  });

  it('scope 선택 후 변경 버튼 클릭 시 onSubmit이 호출된다', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<UpdateScopeModal {...baseProps} onSubmit={onSubmit} />);

    await user.click(screen.getByDisplayValue('PUBLIC'));
    await user.click(screen.getByRole('button', { name: '변경' }));

    expect(onSubmit).toHaveBeenCalledWith({
      scope: 'PUBLIC',
      department_id: undefined,
    });
  });

  it('DEPARTMENT 선택 시 부서 ID 입력 필드가 표시된다', async () => {
    const user = userEvent.setup();
    render(<UpdateScopeModal {...baseProps} />);

    expect(screen.queryByPlaceholderText('dept-uuid')).not.toBeInTheDocument();

    await user.click(screen.getByDisplayValue('DEPARTMENT'));

    expect(screen.getByPlaceholderText('dept-uuid')).toBeInTheDocument();
  });

  it('DEPARTMENT 선택 + 부서 ID 입력 후 제출 시 department_id가 포함된다', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<UpdateScopeModal {...baseProps} onSubmit={onSubmit} />);

    await user.click(screen.getByDisplayValue('DEPARTMENT'));
    await user.type(screen.getByPlaceholderText('dept-uuid'), 'dept-001');
    await user.click(screen.getByRole('button', { name: '변경' }));

    expect(onSubmit).toHaveBeenCalledWith({
      scope: 'DEPARTMENT',
      department_id: 'dept-001',
    });
  });

  it('에러 메시지가 표시된다', () => {
    render(
      <UpdateScopeModal {...baseProps} error="권한 변경 권한이 없습니다" />,
    );
    expect(screen.getByText('권한 변경 권한이 없습니다')).toBeInTheDocument();
  });

  it('isOpen=false이면 렌더링하지 않는다', () => {
    render(<UpdateScopeModal {...baseProps} isOpen={false} />);
    expect(screen.queryByText('접근 범위 변경')).not.toBeInTheDocument();
  });
});
