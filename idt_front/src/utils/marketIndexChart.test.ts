import { describe, expect, it } from 'vitest';
import type { IndexChartResponse } from '@/types/marketAnalysis';
import {
  describeIndexRow,
  lastConfirmedDate,
  latestIndexPoint,
  toIndexChartRows,
} from './marketIndexChart';

const RES: IndexChartResponse = {
  year: 2026,
  series: {
    KOSPI: {
      base_date: '2026-01-02',
      base_close: 2500,
      points: [
        { date: '2026-01-02', close: 2500, rate: 0, provisional: false },
        { date: '2026-01-05', close: 2600, rate: 4, provisional: false },
        { date: '2026-11-27', close: 2590.5, rate: 3.62, provisional: true },
      ],
    },
    KOSDAQ: {
      base_date: '2026-01-05',
      base_close: 700,
      points: [
        { date: '2026-01-05', close: 700, rate: 0, provisional: false },
        { date: '2026-01-06', close: 693, rate: -1, provisional: false },
      ],
    },
  },
  regimes: [
    { date: '2026-01-05', value: 'bear' },
    { date: '2026-03-01', value: 'bull' }, // 지수 봉이 없는 날 — 행을 만들지 않는다
  ],
  source_status: 'ok',
  source_error: null,
  as_of: '2026-11-27T02:00:00Z',
};

describe('toIndexChartRows', () => {
  it('두 지수를 날짜로 합치고 한쪽만 있는 날도 행을 만든다', () => {
    const rows = toIndexChartRows(RES);
    expect(rows.map((r) => r.date)).toEqual(['2026-01-02', '2026-01-05', '2026-01-06', '2026-11-27']);
    expect(rows[0]).toEqual({
      date: '2026-01-02',
      kospi: 0,
      kosdaq: null,
      kospi_close: 2500,
      kosdaq_close: null,
      provisional: false,
      regime: null,
    });
    expect(rows[1]).toMatchObject({ kospi: 4, kosdaq: 0, regime: 'bear' });
    expect(rows[2]).toMatchObject({ kospi: null, kosdaq: -1 });
  });

  it('어느 지수든 미확정이면 그 행은 미확정', () => {
    const rows = toIndexChartRows(RES);
    expect(rows.at(-1)).toMatchObject({ provisional: true, kospi: 3.62, kospi_close: 2590.5 });
    expect(rows.slice(0, -1).every((r) => !r.provisional)).toBe(true);
  });

  it('빈 응답이면 빈 목록', () => {
    const empty: IndexChartResponse = {
      ...RES,
      series: {
        KOSPI: { base_date: null, base_close: null, points: [] },
        KOSDAQ: { base_date: null, base_close: null, points: [] },
      },
      regimes: [],
    };
    expect(toIndexChartRows(empty)).toEqual([]);
  });
});

describe('latestIndexPoint', () => {
  it('마지막 점을 돌려준다', () => {
    expect(latestIndexPoint(RES.series.KOSPI)).toEqual(RES.series.KOSPI.points[2]);
    expect(latestIndexPoint({ base_date: null, base_close: null, points: [] })).toBeNull();
  });
});

describe('lastConfirmedDate', () => {
  it('미확정 행을 건너뛴 마지막 날짜', () => {
    expect(lastConfirmedDate(toIndexChartRows(RES))).toBe('2026-01-06');
    expect(lastConfirmedDate([])).toBeNull();
  });
});

describe('describeIndexRow', () => {
  it('지수 값·등락률·미확정·체제를 문장으로', () => {
    const rows = toIndexChartRows(RES);
    expect(describeIndexRow(rows[1])).toEqual([
      'KOSPI 2,600 (+4.00%)',
      'KOSDAQ 700 (0.00%)',
      '시장 체제: 하락',
    ]);
    expect(describeIndexRow(rows.at(-1)!)).toEqual(['KOSPI 2,590.5 (+3.62%)', '미확정 (장중)']);
  });
});
