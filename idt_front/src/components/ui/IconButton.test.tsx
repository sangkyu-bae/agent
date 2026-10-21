import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import IconButton from './IconButton';

describe('IconButton', () => {
  it('aria-label이 접근 가능한 이름이 되고 title도 같은 값으로 채워진다', () => {
    render(
      <IconButton aria-label="삭제">
        <svg />
      </IconButton>,
    );
    const button = screen.getByRole('button', { name: '삭제' });
    expect(button).toHaveAttribute('title', '삭제');
    expect(button).toHaveAttribute('type', 'button');
  });

  it('size·tone 클래스를 적용한다', () => {
    const { rerender } = render(<IconButton aria-label="x" size="sm" />);
    expect(screen.getByRole('button').className).toContain('h-8');
    rerender(<IconButton aria-label="x" tone="danger" />);
    expect(screen.getByRole('button').className).toContain('hover:text-danger');
    expect(screen.getByRole('button').className).toContain('h-9');
  });

  it('isActive이면 활성 클래스와 aria-pressed를 적용한다', () => {
    render(<IconButton aria-label="고정" isActive />);
    const button = screen.getByRole('button', { name: '고정' });
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(button.className).toContain('bg-surface-sunken');
  });

  it('title을 직접 주면 그 값이 우선한다', () => {
    render(<IconButton aria-label="다운로드" title="대화 내보내기" />);
    expect(screen.getByRole('button', { name: '다운로드' })).toHaveAttribute('title', '대화 내보내기');
  });
});
