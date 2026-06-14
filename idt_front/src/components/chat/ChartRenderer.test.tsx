import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ChartRenderer from './ChartRenderer';
import type { ChartPayload } from '@/types/chart';

// useChart는 chart.js canvas에 의존하므로 모킹: ref만 반환
vi.mock('@/hooks/useChart', () => ({
  useChart: () => ({ current: null }),
}));

const validBar: ChartPayload = {
  type: 'bar',
  data: { labels: ['a', 'b'], datasets: [{ label: '매출', data: [1, 2] }] },
};

describe('ChartRenderer', () => {
  it('유효한 payload면 canvas를 렌더한다', () => {
    const { container } = render(<ChartRenderer payload={validBar} />);
    expect(container.querySelector('canvas')).not.toBeNull();
  });

  it('무효한 payload면 fallback 메시지를 렌더한다', () => {
    const invalid = { type: 'unknown', data: {} } as unknown as ChartPayload;
    render(<ChartRenderer payload={invalid} />);
    expect(screen.getByText(/차트를 표시할 수 없습니다/)).toBeInTheDocument();
  });
});
