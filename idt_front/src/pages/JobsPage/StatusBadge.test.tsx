import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from './StatusBadge';

describe('StatusBadge', () => {
  it('기존 상태 라벨', () => {
    render(<StatusBadge status="success" />);
    expect(screen.getByText('완료')).toBeInTheDocument();
  });

  // firewall-agent design §2.2 — 바쁨 판정으로 건너뛴 스케줄 회차가 작업함 이력에 섞여 온다
  it('건너뛴 스케줄 회차는 "건너뜀" 회색 배지로 표시한다', () => {
    render(<StatusBadge status="skipped" />);
    const label = screen.getByText('건너뜀');
    expect(label.closest('span')).toHaveClass('text-zinc-500');
  });
});
