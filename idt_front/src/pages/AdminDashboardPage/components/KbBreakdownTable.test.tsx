import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import KbBreakdownTable from './KbBreakdownTable';
import type { KbBreakdownRow } from '@/types/adminDashboard';

const rows: KbBreakdownRow[] = [
  {
    kb_id: 'kb-1',
    name: '규정집',
    scope: 'PUBLIC',
    status: 'active',
    document_count: 5,
    chunk_count: 120,
    last_uploaded_at: '2026-07-17T09:12:00',
  },
  {
    kb_id: 'kb-2',
    name: '빈 KB',
    scope: 'PERSONAL',
    status: 'archived',
    document_count: 0,
    chunk_count: 0,
    last_uploaded_at: null,
  },
];

describe('KbBreakdownTable', () => {
  it('행 렌더 — scope 라벨·수치·최근 업로드', () => {
    render(<KbBreakdownTable rows={rows} />);
    expect(screen.getByText('규정집')).toBeInTheDocument();
    expect(screen.getByText('전체 공개')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('2026-07-17 09:12')).toBeInTheDocument();
  });

  it('문서 0건 KB — last_uploaded_at 없음은 — 표시, 비활성 status 뱃지', () => {
    render(<KbBreakdownTable rows={rows} />);
    expect(screen.getByText('빈 KB')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('archived')).toBeInTheDocument();
  });

  it('빈 목록은 안내 문구', () => {
    render(<KbBreakdownTable rows={[]} />);
    expect(
      screen.getByText('등록된 지식 베이스가 없습니다'),
    ).toBeInTheDocument();
  });
});
