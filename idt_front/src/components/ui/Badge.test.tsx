import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import Badge from './Badge';

describe('Badge', () => {
  it('기본 tone은 neutral이고 텍스트를 렌더링한다', () => {
    render(<Badge>대기중</Badge>);
    const badge = screen.getByText('대기중');
    expect(badge.className).toContain('text-fg-muted');
    expect(screen.queryByTestId('badge-dot')).not.toBeInTheDocument();
  });

  it('tone별 클래스를 적용한다', () => {
    const { rerender } = render(<Badge tone="success">활성</Badge>);
    expect(screen.getByText('활성').className).toContain('text-success');
    rerender(<Badge tone="danger">실패</Badge>);
    expect(screen.getByText('실패').className).toContain('text-danger');
    rerender(<Badge tone="brand">완료</Badge>);
    expect(screen.getByText('완료').className).toContain('text-brand-700');
    rerender(<Badge tone="info">진행중</Badge>);
    expect(screen.getByText('진행중').className).toContain('text-info');
    rerender(<Badge tone="warning">미설정</Badge>);
    expect(screen.getByText('미설정').className).toContain('text-warning');
  });

  it('dot과 pulse를 렌더링한다', () => {
    render(
      <Badge tone="success" dot pulse>
        온라인
      </Badge>,
    );
    const dot = screen.getByTestId('badge-dot');
    expect(dot).toHaveAttribute('aria-hidden', 'true');
    expect(dot.className).toContain('animate-pulse');
  });

  it('className을 덧붙인다', () => {
    render(<Badge className="ml-2">x</Badge>);
    expect(screen.getByText('x').className).toContain('ml-2');
  });
});
