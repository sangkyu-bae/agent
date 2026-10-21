import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import PageHeader from './PageHeader';

describe('PageHeader', () => {
  it('제목을 h1으로 렌더링하고 부제·액션·탭·leading 슬롯을 노출한다', () => {
    render(
      <PageHeader
        title="컬렉션 관리"
        subtitle="문서를 모아 관리합니다"
        leading={<span data-testid="lead" />}
        actions={<button>새 컬렉션</button>}
        tabs={<div role="tablist" aria-label="탭" />}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: '컬렉션 관리' })).toBeInTheDocument();
    expect(screen.getByText('문서를 모아 관리합니다')).toBeInTheDocument();
    expect(screen.getByTestId('lead')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새 컬렉션' })).toBeInTheDocument();
    expect(screen.getByRole('tablist', { name: '탭' })).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('compact이면 고정 높이 클래스를, 아니면 py-4를 적용한다', () => {
    const { rerender } = render(<PageHeader title="채팅" compact />);
    const row = screen.getByRole('heading', { level: 1 }).closest('div')!.parentElement!;
    expect(row.className).toContain('h-13');
    rerender(<PageHeader title="채팅" />);
    const row2 = screen.getByRole('heading', { level: 1 }).closest('div')!.parentElement!;
    expect(row2.className).toContain('py-4');
  });
});
