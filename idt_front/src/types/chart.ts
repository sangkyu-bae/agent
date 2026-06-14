import type { ChartType, ChartData, ChartOptions } from 'chart.js';

/**
 * 백엔드 → 프론트 차트 계약.
 * Chart.js 네이티브 config(`{ type, data, options }`)를 그대로 패스스루한다.
 *
 * Design: docs/02-design/features/chat-chart-rendering.design.md §3.1
 */
export interface ChartPayload {
  type: ChartType;
  data: ChartData;
  options?: ChartOptions;
}

/** 프론트에서 허용하는 차트 타입 화이트리스트 (검증 기준) */
export const SUPPORTED_CHART_TYPES = [
  'bar',
  'line',
  'pie',
  'doughnut',
  'scatter',
  'radar',
] as const;

export type SupportedChartType = (typeof SUPPORTED_CHART_TYPES)[number];
