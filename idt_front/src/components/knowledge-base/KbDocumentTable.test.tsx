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
  },
  {
    document_id: 'doc-2',
    filename: '심사기준.pdf',
    chunk_count: 10,
    chunking_strategy: 'clause_aware',
    created_at: null,
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
