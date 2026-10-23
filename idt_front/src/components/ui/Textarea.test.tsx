import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import Textarea from './Textarea';

describe('Textarea', () => {
  it('label·hint·error 슬롯이 aria로 연결된다', () => {
    render(<Textarea label="메모" hint="500자 이내" />);
    const area = screen.getByLabelText('메모');
    expect(area.tagName).toBe('TEXTAREA');
    expect(area).toHaveAttribute('aria-describedby', screen.getByText('500자 이내').id);
  });

  it('error가 있으면 role=alert와 aria-invalid를 적용한다', () => {
    render(<Textarea label="메모" error="너무 깁니다" />);
    expect(screen.getByRole('alert')).toHaveTextContent('너무 깁니다');
    expect(screen.getByLabelText('메모')).toHaveAttribute('aria-invalid', 'true');
  });

  it('unstyled이면 테두리 클래스 없이 text-md만 적용한다', () => {
    render(<Textarea aria-label="메시지" unstyled />);
    const area = screen.getByLabelText('메시지');
    expect(area.className).toContain('text-md');
    expect(area.className).not.toContain('border-border-strong');
  });

  it('autoResize는 입력 시 scrollHeight에 맞춰 높이를 맞추고 maxRows 상한에서 멈춘다', () => {
    const onChange = vi.fn();
    render(<Textarea aria-label="메시지" autoResize maxRows={2} onChange={onChange} />);
    const area = screen.getByLabelText('메시지') as HTMLTextAreaElement;
    // jsdom은 레이아웃이 없으므로 scrollHeight를 직접 흉내낸다 (line-height 폴백 24px → 상한 48px)
    Object.defineProperty(area, 'scrollHeight', { configurable: true, get: () => 30 });
    fireEvent.change(area, { target: { value: '한 줄' } });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(area.style.height).toBe('30px');
    expect(area.style.overflowY).toBe('hidden');

    Object.defineProperty(area, 'scrollHeight', { configurable: true, get: () => 200 });
    fireEvent.change(area, { target: { value: '여러\n줄\n입력\n내용' } });
    expect(area.style.height).toBe('48px');
    expect(area.style.overflowY).toBe('auto');
  });
});
