// progress-card: 상태 배지 — 기본 라벨·오버라이드·상태별 색상.
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import StatusBadge from './StatusBadge';

describe('StatusBadge', () => {
  it('T1: status별 기본 한글 라벨을 렌더링한다', () => {
    const { rerender } = render(<StatusBadge status="completed" />);
    expect(screen.getByText('완료')).toBeInTheDocument();

    rerender(<StatusBadge status="in_progress" />);
    expect(screen.getByText('진행중')).toBeInTheDocument();

    rerender(<StatusBadge status="pending" />);
    expect(screen.getByText('대기중')).toBeInTheDocument();

    rerender(<StatusBadge status="error" />);
    expect(screen.getByText('실패')).toBeInTheDocument();
  });

  it('T2: label prop이 기본 라벨을 오버라이드한다', () => {
    render(<StatusBadge status="completed" label="Phase 완료" />);
    expect(screen.getByText('Phase 완료')).toBeInTheDocument();
    expect(screen.queryByText('완료')).not.toBeInTheDocument();
  });

  // ui-redesign-chat: 색상 클래스는 디자인 토큰(Badge tone)으로 매핑된다 — completed→brand, in_progress→info, pending→neutral, error→danger
  it('T3: status별 색상 클래스가 적용된다', () => {
    const { rerender } = render(<StatusBadge status="completed" />);
    expect(screen.getByText('완료').className).toContain('text-brand-700');

    rerender(<StatusBadge status="in_progress" />);
    expect(screen.getByText('진행중').className).toContain('text-info');

    rerender(<StatusBadge status="pending" />);
    expect(screen.getByText('대기중').className).toContain('text-fg-muted');

    rerender(<StatusBadge status="error" />);
    expect(screen.getByText('실패').className).toContain('text-danger');
  });

  it('T4: label이 빈 문자열이면 기본 라벨로 폴백한다', () => {
    render(<StatusBadge status="pending" label="" />);
    expect(screen.getByText('대기중')).toBeInTheDocument();
  });
});
