/**
 * SummaryCards unit tests — M5 dashboard.
 *
 * C1: 정상 값 렌더 (totalRuns, successRate, totalTokens, totalCostUsd)
 * C2: undefined 시 "—" 표시
 * C3: successRate=0 일 때 "0.0%" 표시 (zero division 방지 확인)
 * C4: loading=true 시 스켈레톤 4개 렌더
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import SummaryCards from './SummaryCards';

describe('SummaryCards', () => {
  it('C1: 정상 값을 카드에 렌더한다', () => {
    render(
      <SummaryCards
        totalRuns={421}
        successRate={0.9739}
        totalTokens={1284203}
        totalCostUsd="12.834201"
      />,
    );
    expect(screen.getByText('421')).toBeInTheDocument();
    // 97.4% — toFixed(1)
    expect(screen.getByText('97.4%')).toBeInTheDocument();
    expect(screen.getByText('1,284,203')).toBeInTheDocument();
    expect(screen.getByText('$12.8342')).toBeInTheDocument();
  });

  it('C2: undefined 값은 "—" 로 표시', () => {
    render(
      <SummaryCards
        totalRuns={undefined}
        successRate={undefined}
        totalTokens={undefined}
        totalCostUsd={undefined}
      />,
    );
    expect(screen.getAllByText('—').length).toBe(4);
  });

  it('C3: successRate=0 → "0.0%"', () => {
    render(
      <SummaryCards
        totalRuns={0}
        successRate={0}
        totalTokens={0}
        totalCostUsd="0"
      />,
    );
    expect(screen.getByText('0.0%')).toBeInTheDocument();
  });

  it('C4: loading=true → 스켈레톤 4개 렌더', () => {
    const { container } = render(
      <SummaryCards
        totalRuns={undefined}
        successRate={undefined}
        totalTokens={undefined}
        totalCostUsd={undefined}
        loading
      />,
    );
    // 스켈레톤은 .animate-pulse div × 4
    expect(container.querySelectorAll('.animate-pulse').length).toBe(4);
  });
});
