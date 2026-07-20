import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { KbDocumentInfo } from '@/types/knowledgeBase';
import KbStatusCards from './KbStatusCards';

const doc = (id: string, chunkCount: number): KbDocumentInfo => ({
  document_id: id,
  filename: `${id}.pdf`,
  chunk_count: chunkCount,
  chunking_strategy: 'parent_child',
  created_at: '2026-07-18T00:00:00Z',
});

describe('KbStatusCards — kb-retrieval-test FR-07', () => {
  it('chunk_count 기준으로 준비완료/처리중을 판정한다', () => {
    render(
      <KbStatusCards
        documents={[doc('a', 12), doc('b', 0), doc('c', 3)]}
        total={3}
      />,
    );

    expect(screen.getByText('전체 문서').nextSibling).toHaveTextContent('3');
    expect(screen.getByText('준비 완료')).toBeInTheDocument();
    expect(screen.getByTestId('kb-ready-count')).toHaveTextContent('2');
    expect(screen.getByTestId('kb-processing-count')).toHaveTextContent('1');
    expect(screen.getByTestId('kb-error-count')).toHaveTextContent('0');
  });

  it('문서가 없으면 모두 0으로 표시한다', () => {
    render(<KbStatusCards documents={[]} total={0} />);

    expect(screen.getByTestId('kb-total-count')).toHaveTextContent('0');
    expect(screen.getByTestId('kb-ready-count')).toHaveTextContent('0');
    expect(screen.getByTestId('kb-processing-count')).toHaveTextContent('0');
  });
});
