import type { ChartConfiguration } from 'chart.js';
import { SUPPORTED_CHART_TYPES } from '@/types/chart';
import type { ChartPayload } from '@/types/chart';

/**
 * 차트 페이로드가 렌더 가능한 형태인지 검증한다.
 * - type이 화이트리스트에 포함
 * - data.datasets가 비어있지 않은 배열
 *
 * Design: docs/02-design/features/chat-chart-rendering.design.md §6.1
 */
export const isValidChartPayload = (payload: unknown): payload is ChartPayload => {
  if (!payload || typeof payload !== 'object') return false;

  const { type, data } = payload as Record<string, unknown>;
  if (!SUPPORTED_CHART_TYPES.includes(type as never)) return false;
  if (!data || typeof data !== 'object') return false;

  const datasets = (data as { datasets?: unknown }).datasets;
  return Array.isArray(datasets) && datasets.length > 0;
};

/** ChartPayload → chart.js ChartConfiguration 변환 (패스스루) */
export const toChartConfiguration = (payload: ChartPayload): ChartConfiguration =>
  ({
    type: payload.type,
    data: payload.data,
    options: payload.options,
  }) as ChartConfiguration;
