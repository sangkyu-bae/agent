// progress-card: 단계 1행 — 상태 아이콘·커넥터·라벨 강조·배지 전달.
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ProgressStep } from './ProgressCard';
import ProgressStepItem from './ProgressStepItem';

const step = (over: Partial<ProgressStep> = {}): ProgressStep => ({
  label: 'Phase 1: 프로젝트 초기화',
  status: 'completed',
  ...over,
});

const renderItem = (s: ProgressStep, isLast = false) =>
  render(
    <ol>
      <ProgressStepItem step={s} isLast={isLast} />
    </ol>,
  );

describe('ProgressStepItem', () => {
  it('T1: 라벨 텍스트를 렌더링한다', () => {
    renderItem(step());
    expect(screen.getByText('Phase 1: 프로젝트 초기화')).toBeInTheDocument();
  });

  it('T2: in_progress 라벨은 font-semibold로 강조된다', () => {
    renderItem(step({ status: 'in_progress', label: 'Phase 2: 의도 수집' }));
    expect(screen.getByText('Phase 2: 의도 수집').className).toContain('font-semibold');
  });

  it('T3: pending 라벨은 강조되지 않는다', () => {
    renderItem(step({ status: 'pending', label: 'Phase 3: 도구 추천' }));
    expect(screen.getByText('Phase 3: 도구 추천').className).not.toContain('font-semibold');
  });

  it('T4: isLast=false면 커넥터가 존재한다', () => {
    renderItem(step(), false);
    expect(screen.getByTestId('step-connector')).toBeInTheDocument();
  });

  it('T5: isLast=true면 커넥터가 없다', () => {
    renderItem(step(), true);
    expect(screen.queryByTestId('step-connector')).not.toBeInTheDocument();
  });

  it('T6: completed 단계의 커넥터는 violet, pending 단계는 zinc 색이다', () => {
    const { unmount } = renderItem(step({ status: 'completed' }));
    expect(screen.getByTestId('step-connector').className).toContain('bg-violet-400');
    unmount();

    renderItem(step({ status: 'pending' }));
    expect(screen.getByTestId('step-connector').className).toContain('bg-zinc-200');
  });

  it('T7: badgeLabel이 배지에 전달된다', () => {
    renderItem(step({ badgeLabel: '3/7 완료' }));
    expect(screen.getByText('3/7 완료')).toBeInTheDocument();
    expect(screen.queryByText('완료')).not.toBeInTheDocument();
  });

  it('T8: 상태 아이콘 SVG는 aria-hidden 처리된다', () => {
    const { container } = renderItem(step());
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('aria-hidden', 'true');
  });
});
