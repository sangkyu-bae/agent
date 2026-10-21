import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import Input from './Input';

describe('Input', () => {
  it('label이 input과 연결된다', () => {
    render(<Input label="이메일" />);
    const input = screen.getByLabelText('이메일');
    expect(input.tagName).toBe('INPUT');
    expect(input.className).toContain('h-10');
  });

  it('hint가 aria-describedby로 연결된다', () => {
    render(<Input label="이름" hint="2자 이상" />);
    const input = screen.getByLabelText('이름');
    const hint = screen.getByText('2자 이상');
    expect(input).toHaveAttribute('aria-describedby', hint.id);
    expect(input).not.toHaveAttribute('aria-invalid');
  });

  it('error가 있으면 role=alert · aria-invalid · danger 클래스를 적용하고 hint를 숨긴다', () => {
    render(<Input label="이름" hint="2자 이상" error="필수 항목입니다" />);
    const input = screen.getByLabelText('이름');
    const error = screen.getByRole('alert');
    expect(error).toHaveTextContent('필수 항목입니다');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.getAttribute('aria-describedby')).toContain(error.id);
    expect(input.className).toContain('border-danger');
    expect(screen.queryByText('2자 이상')).not.toBeInTheDocument();
  });

  it('size sm과 leadingIcon 패딩을 적용한다', () => {
    render(<Input aria-label="검색" size="sm" leadingIcon={<svg data-testid="icon" />} />);
    const input = screen.getByLabelText('검색');
    expect(input.className).toContain('h-8');
    expect(input.className).toContain('pl-9');
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('id를 직접 주면 그 id를 사용한다', () => {
    render(<Input id="email" label="이메일" />);
    expect(screen.getByLabelText('이메일')).toHaveAttribute('id', 'email');
  });
});
