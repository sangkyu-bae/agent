import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Button from './Button';

describe('Button', () => {
  it('기본값은 primary · md 이며 클릭 시 onClick이 호출된다', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>저장</Button>);
    const button = screen.getByRole('button', { name: '저장' });
    expect(button.className).toContain('bg-brand-600');
    expect(button.className).toContain('h-10');
    expect(button).toHaveAttribute('type', 'button');
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('variant·size 클래스를 적용한다', () => {
    const { rerender } = render(
      <Button variant="secondary" size="sm">
        취소
      </Button>,
    );
    let button = screen.getByRole('button', { name: '취소' });
    expect(button.className).toContain('border-border');
    expect(button.className).toContain('h-8');

    rerender(<Button variant="ghost">닫기</Button>);
    button = screen.getByRole('button', { name: '닫기' });
    expect(button.className).toContain('hover:bg-surface-sunken');

    rerender(<Button variant="danger">삭제</Button>);
    button = screen.getByRole('button', { name: '삭제' });
    expect(button.className).toContain('text-danger');
  });

  it('isPending이면 disabled + 스피너 + pendingText를 표시하고 클릭을 막는다', () => {
    const onClick = vi.fn();
    render(
      <Button isPending pendingText="저장 중…" onClick={onClick}>
        저장
      </Button>,
    );
    const button = screen.getByRole('button', { name: '저장 중…' });
    expect(button).toBeDisabled();
    expect(button.querySelector('svg.animate-spin')).toBeInTheDocument();
    expect(screen.queryByText('저장')).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('disabled prop이 단독으로도 적용된다', () => {
    render(<Button disabled>저장</Button>);
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });

  it('leadingIcon·trailingIcon 슬롯을 렌더링한다', () => {
    render(
      <Button leadingIcon={<span data-testid="lead" />} trailingIcon={<span data-testid="trail" />}>
        등록
      </Button>,
    );
    expect(screen.getByTestId('lead')).toBeInTheDocument();
    expect(screen.getByTestId('trail')).toBeInTheDocument();
  });

  it('unstyled이면 variant/size 클래스 없이 className만 적용한다', () => {
    render(
      <Button unstyled className="legacy-class">
        저장
      </Button>,
    );
    const button = screen.getByRole('button', { name: '저장' });
    expect(button.className).toBe('legacy-class');
  });
});
