import { describe, it, expect } from 'vitest';
import { isValidChartPayload, toChartConfiguration } from './chartValidator';
import type { ChartPayload } from '@/types/chart';

const validBar: ChartPayload = {
  type: 'bar',
  data: {
    labels: ['1월', '2월', '3월'],
    datasets: [{ label: '매출', data: [12, 19, 7] }],
  },
};

describe('isValidChartPayload', () => {
  it('정상 bar payload는 통과한다', () => {
    expect(isValidChartPayload(validBar)).toBe(true);
  });

  it('지원하지 않는 type은 거부한다', () => {
    expect(isValidChartPayload({ ...validBar, type: 'bubble3d' })).toBe(false);
  });

  it('data가 없으면 거부한다', () => {
    expect(isValidChartPayload({ type: 'bar' })).toBe(false);
  });

  it('datasets가 누락되면 거부한다', () => {
    expect(isValidChartPayload({ type: 'bar', data: { labels: [] } })).toBe(false);
  });

  it('datasets가 빈 배열이면 거부한다', () => {
    expect(isValidChartPayload({ type: 'bar', data: { datasets: [] } })).toBe(false);
  });

  it('null/원시값은 거부한다', () => {
    expect(isValidChartPayload(null)).toBe(false);
    expect(isValidChartPayload(undefined)).toBe(false);
    expect(isValidChartPayload('bar')).toBe(false);
  });
});

describe('toChartConfiguration', () => {
  it('payload를 chart.js ChartConfiguration으로 매핑한다', () => {
    const config = toChartConfiguration(validBar);
    expect(config.type).toBe('bar');
    expect(config.data).toBe(validBar.data);
    expect(config.options).toBeUndefined();
  });

  it('options를 보존한다', () => {
    const withOptions: ChartPayload = {
      ...validBar,
      options: { plugins: { title: { display: true, text: 'T' } } },
    };
    expect(toChartConfiguration(withOptions).options).toBe(withOptions.options);
  });
});
