import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import type { KnowledgeBaseInfo } from '@/types/ragToolConfig';
import { RagConfigSummaryBadge } from './LeftConfigPanel';

const KBS: KnowledgeBaseInfo[] = [
  {
    kb_id: 'kb-1',
    name: '전사 규정',
    scope: 'PUBLIC',
    collection_name: 'admin-coll-01',
  },
];

describe('RagConfigSummaryBadge — kb-rag-filter', () => {
  it('kb_id가 있으면 KB 이름이 라벨로 표시된다', () => {
    render(
      <RagConfigSummaryBadge
        config={{ ...DEFAULT_RAG_CONFIG, kb_id: 'kb-1' }}
        knowledgeBases={KBS}
      />,
    );
    expect(screen.getByText(/전사 규정/)).toBeInTheDocument();
  });

  it('kb_id가 목록에 없으면 kb_id 원문을 표시한다', () => {
    render(
      <RagConfigSummaryBadge
        config={{ ...DEFAULT_RAG_CONFIG, kb_id: 'kb-unknown' }}
        knowledgeBases={KBS}
      />,
    );
    expect(screen.getByText(/kb-unknown/)).toBeInTheDocument();
  });

  it('kb_id가 없으면 기존 컬렉션 라벨 로직을 따른다', () => {
    render(<RagConfigSummaryBadge config={{ ...DEFAULT_RAG_CONFIG }} />);
    expect(screen.getByText(/전체/)).toBeInTheDocument();
  });
});
