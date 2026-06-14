import { render, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChartConfiguration } from 'chart.js';
import { useChart } from './useChart';

// chart.js의 Chart 생성자를 모킹하여 lifecycle(생성/파괴)만 검증한다.
// jsdom은 canvas 2D context를 지원하지 않으므로 실제 렌더는 검증하지 않는다.
const { ctorSpy, destroySpy } = vi.hoisted(() => ({
  ctorSpy: vi.fn(),
  destroySpy: vi.fn(),
}));

vi.mock('chart.js', () => ({
  Chart: class {
    destroy = destroySpy;
    constructor(canvas: unknown, config: unknown) {
      ctorSpy(canvas, config);
    }
  },
}));

vi.mock('@/lib/chartSetup', () => ({
  ensureChartRegistered: vi.fn(),
}));

const Harness = ({ config }: { config: ChartConfiguration | null }) => {
  const ref = useChart(config);
  return <canvas ref={ref} data-testid="cv" />;
};

const barConfig: ChartConfiguration = {
  type: 'bar',
  data: { labels: ['a'], datasets: [{ label: 'x', data: [1] }] },
};

beforeEach(() => {
  ctorSpy.mockClear();
  destroySpy.mockClear();
});
afterEach(() => cleanup());

describe('useChart', () => {
  it('마운트 + config 존재 시 Chart를 1회 생성한다', () => {
    render(<Harness config={barConfig} />);
    expect(ctorSpy).toHaveBeenCalledTimes(1);
  });

  it('config가 null이면 생성하지 않는다', () => {
    render(<Harness config={null} />);
    expect(ctorSpy).not.toHaveBeenCalled();
  });

  it('config 변경 시 이전 인스턴스를 destroy 후 재생성한다', () => {
    const { rerender } = render(<Harness config={barConfig} />);
    expect(ctorSpy).toHaveBeenCalledTimes(1);

    const lineConfig: ChartConfiguration = { ...barConfig, type: 'line' };
    rerender(<Harness config={lineConfig} />);

    expect(destroySpy).toHaveBeenCalledTimes(1);
    expect(ctorSpy).toHaveBeenCalledTimes(2);
  });

  it('언마운트 시 destroy를 호출한다', () => {
    const { unmount } = render(<Harness config={barConfig} />);
    unmount();
    expect(destroySpy).toHaveBeenCalledTimes(1);
  });

  it('responsive/maintainAspectRatio 기본 options를 주입한다', () => {
    render(<Harness config={barConfig} />);
    const [, passedConfig] = ctorSpy.mock.calls[0] as [unknown, ChartConfiguration];
    expect(passedConfig.options?.responsive).toBe(true);
    expect(passedConfig.options?.maintainAspectRatio).toBe(false);
  });
});
