import { useMemo } from 'react';
import type { ChartPayload } from '@/types/chart';
import { useChart } from '@/hooks/useChart';
import { isValidChartPayload, toChartConfiguration } from '@/utils/chartValidator';

interface ChartRendererProps {
  payload: ChartPayload;
  /** 차트 컨테이너 높이 (px). 기본 320 */
  height?: number;
}

const ChartRenderer = ({ payload, height = 320 }: ChartRendererProps) => {
  const valid = isValidChartPayload(payload);
  const config = useMemo(
    () => (valid ? toChartConfiguration(payload) : null),
    [valid, payload],
  );
  const canvasRef = useChart(config);

  if (!valid) {
    return (
      <div className="mt-3 rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-[13px] text-zinc-500">
        차트를 표시할 수 없습니다. (지원하지 않는 형식)
      </div>
    );
  }

  return (
    <div
      className="mt-3 rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm"
      style={{ height }}
    >
      <canvas ref={canvasRef} />
    </div>
  );
};

export default ChartRenderer;
