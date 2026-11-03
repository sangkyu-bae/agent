import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { KbDocumentInfo } from '@/types/knowledgeBase';
import KbDocumentTable from './KbDocumentTable';

const docs: KbDocumentInfo[] = [
  {
    document_id: 'doc-1',
    filename: '여신규정.pdf',
    chunk_count: 42,
    chunking_strategy: 'parent_child',
    created_at: '2026-07-14T00:00:00Z',
    can_delete: true,
  },
  {
    document_id: 'doc-2',
    filename: '심사기준.pdf',
    chunk_count: 10,
    chunking_strategy: 'clause_aware',
    created_at: null,
    can_delete: false,
  },
];

describe('KbDocumentTable — kb-content-browser 행 클릭', () => {
  it('행 클릭 시 onRowClick에 해당 문서를 전달한다', async () => {
    const onRowClick = vi.fn();
    render(
      <KbDocumentTable
        documents={docs}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
        onRowClick={onRowClick}
        selectedId={null}
      />,
    );

    await userEvent.click(screen.getByText('여신규정.pdf'));
    expect(onRowClick).toHaveBeenCalledWith(
      expect.objectContaining({ document_id: 'doc-1' }),
    );
  });

  it('선택된 행은 aria-selected로 하이라이트된다', () => {
    render(
      <KbDocumentTable
        documents={docs}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
        onRowClick={vi.fn()}
        selectedId="doc-2"
      />,
    );

    const selectedRow = screen.getByText('심사기준.pdf').closest('tr');
    expect(selectedRow).toHaveAttribute('aria-selected', 'true');
    const otherRow = screen.getByText('여신규정.pdf').closest('tr');
    expect(otherRow).toHaveAttribute('aria-selected', 'false');
  });
});

describe('KbDocumentTable — kb-document-management 행 삭제', () => {
  it('can_delete=true 행에만 삭제 버튼을 보여준다', () => {
    render(
      <KbDocumentTable
        documents={docs}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
        onDeleteDocument={vi.fn()}
      />,
    );

    expect(screen.getByRole('columnheader', { name: '관리' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '여신규정.pdf 삭제' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '심사기준.pdf 삭제' }),
    ).not.toBeInTheDocument();
  });

  it('삭제 클릭은 onDeleteDocument만 호출하고 행 드릴다운을 열지 않는다', async () => {
    const onDeleteDocument = vi.fn();
    const onRowClick = vi.fn();
    render(
      <KbDocumentTable
        documents={docs}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
        onRowClick={onRowClick}
        onDeleteDocument={onDeleteDocument}
      />,
    );

    await userEvent.click(
      screen.getByRole('button', { name: '여신규정.pdf 삭제' }),
    );

    expect(onDeleteDocument).toHaveBeenCalledWith(
      expect.objectContaining({ document_id: 'doc-1' }),
    );
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('onDeleteDocument가 없으면 관리 열을 그리지 않는다', () => {
    render(
      <KbDocumentTable
        documents={docs}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole('columnheader', { name: '관리' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /삭제$/ }),
    ).not.toBeInTheDocument();
  });
});
