import { useEffect, useRef } from 'react';
import { Chart, type ChartConfiguration } from 'chart.js';
import { ensureChartRegistered } from '@/lib/chartSetup';

/**
 * Chart.js 인스턴스 lifecycle을 캡슐화하는 공통 훅.
 * - config 변경 시 인스턴스를 destroy 후 재생성한다
 *   (패스스루 config는 type/scale이 바뀔 수 있어 update보다 재생성이 안전)
 * - 언마운트 시 destroy하여 메모리 누수를 방지한다
 *
 * Design: docs/02-design/features/chat-chart-rendering.design.md §11.3
 *
 * @param config chart.js ChartConfiguration (null이면 렌더하지 않음)
 * @returns canvas 엘리먼트에 부착할 ref
 */
export const useChart = (config: ChartConfiguration | null) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    ensureChartRegistered();
    const canvas = canvasRef.current;
    if (!canvas || !config) return;

    chartRef.current?.destroy();
    chartRef.current = new Chart(canvas, {
      ...config,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        ...config.options,
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [config]);

  return canvasRef;
};
