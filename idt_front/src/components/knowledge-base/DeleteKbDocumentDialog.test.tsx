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

// document-revision §4.2 #9 — 최신 버전 삭제 시 이전 버전 복귀 선택
describe('DeleteKbDocumentDialog — 이전 버전 복귀', () => {
  it('이전 버전이 있으면 체크박스를 보여주고 변경을 알린다', async () => {
    const onRestorePreviousChange = vi.fn();
    render(
      <DeleteKbDocumentDialog
        {...baseProps}
        previousVersionNo={1}
        restorePrevious
        onRestorePreviousChange={onRestorePreviousChange}
      />,
    );
    const box = screen.getByRole('checkbox', { name: /이전 버전\(v1\)을 다시 검색에 사용/ });
    expect(box).toBeChecked();
    await userEvent.click(box);
    expect(onRestorePreviousChange).toHaveBeenCalledWith(false);
  });

  it('체크를 끄면 계보 전체가 검색에서 빠진다고 경고한다', () => {
    render(
      <DeleteKbDocumentDialog
        {...baseProps}
        previousVersionNo={1}
        restorePrevious={false}
        onRestorePreviousChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/이 문서의 모든 버전이 검색에서 빠집니다/)).toBeInTheDocument();
  });

  it('이전 버전이 없으면 체크박스가 없다', () => {
    render(<DeleteKbDocumentDialog {...baseProps} />);
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
});
