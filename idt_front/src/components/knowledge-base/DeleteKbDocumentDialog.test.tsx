import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import DeleteKbDocumentDialog from './DeleteKbDocumentDialog';

const baseProps = {
  isOpen: true,
  filename: '여신규정.pdf',
  onClose: vi.fn(),
  onConfirm: vi.fn(),
  isPending: false,
  error: null,
};

describe('DeleteKbDocumentDialog — kb-document-management §5.4', () => {
  it('파일명과 복구 불가 안내를 보여준다', () => {
    render(<DeleteKbDocumentDialog {...baseProps} />);

    expect(screen.getByText('문서 삭제')).toBeInTheDocument();
    expect(screen.getByText('여신규정.pdf')).toBeInTheDocument();
    expect(screen.getByText(/복구할 수 없으며/)).toBeInTheDocument();
    expect(screen.getByText(/검색에서 제외됩니다/)).toBeInTheDocument();
  });

  it('삭제 버튼이 onConfirm을 호출한다', async () => {
    const onConfirm = vi.fn();
    render(<DeleteKbDocumentDialog {...baseProps} onConfirm={onConfirm} />);

    await userEvent.click(screen.getByRole('button', { name: '삭제' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('서버 오류 메시지를 표시한다', () => {
    render(
      <DeleteKbDocumentDialog
        {...baseProps}
        error="섹션 요약이 진행 중인 문서는 삭제할 수 없습니다."
      />,
    );

    expect(screen.getByText(/섹션 요약이 진행 중/)).toBeInTheDocument();
  });

  it('닫혀 있으면 아무것도 그리지 않는다', () => {
    render(<DeleteKbDocumentDialog {...baseProps} isOpen={false} />);

    expect(screen.queryByText('문서 삭제')).not.toBeInTheDocument();
  });
});
