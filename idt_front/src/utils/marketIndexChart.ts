// market-index-ytd-chart Design §5.3 — 지수 차트 응답을 화면 행·문장으로 바꾸는 순수 함수.
// 등락률 계산은 백엔드가 한다. 여기서는 합치고 표시 문장만 만든다.
import {
  REGIME_LABELS,
  type IndexChartPoint,
  type IndexChartResponse,
  type IndexChartRow,
  type IndexChartSeries,
} from '@/types/marketAnalysis';
import { formatPrice, formatRate } from '@/utils/marketAnalysis';

const emptyRow = (date: string): IndexChartRow => ({
  date,
  kospi: null,
  kosdaq: null,
  kospi_close: null,
  kosdaq_close: null,
  provisional: false,
  regime: null,
});

/** 두 지수를 날짜로 합친다. 체제는 지수 봉이 있는 날에만 붙인다. */
export const toIndexChartRows = (res: IndexChartResponse): IndexChartRow[] => {
  const byDate = new Map<string, IndexChartRow>();
  const put = (p: IndexChartPoint, rateKey: 'kospi' | 'kosdaq', closeKey: 'kospi_close' | 'kosdaq_close') => {
    const row = byDate.get(p.date) ?? emptyRow(p.date);
    row[rateKey] = p.rate;
    row[closeKey] = p.close;
    row.provisional = row.provisional || p.provisional;
    byDate.set(p.date, row);
  };
  res.series.KOSPI.points.forEach((p) => put(p, 'kospi', 'kospi_close'));
  res.series.KOSDAQ.points.forEach((p) => put(p, 'kosdaq', 'kosdaq_close'));
  for (const r of res.regimes) {
    const row = byDate.get(r.date);
    if (row) row.regime = r.value;
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
};

export const latestIndexPoint = (series: IndexChartSeries): IndexChartPoint | null =>
  series.points.at(-1) ?? null;

/** 툴팁 문장 — 색만으로 의미를 전하지 않도록 값·미확정·체제를 글로 */
export const describeIndexRow = (row: IndexChartRow): string[] => {
  const lines: string[] = [];
  if (row.kospi !== null) lines.push(`KOSPI ${formatPrice(row.kospi_close)} (${formatRate(row.kospi)})`);
  if (row.kosdaq !== null) lines.push(`KOSDAQ ${formatPrice(row.kosdaq_close)} (${formatRate(row.kosdaq)})`);
  if (row.provisional) lines.push('미확정 (장중)');
  if (row.regime) lines.push(`시장 체제: ${REGIME_LABELS[row.regime] ?? row.regime}`);
  return lines;
};

/** 마지막 확정(장중 아님) 행의 날짜 — 저장 데이터 기준일 */
export const lastConfirmedDate = (rows: IndexChartRow[]): string | null =>
  rows.findLast((r) => !r.provisional)?.date ?? null;

/** 'YYYY-MM-DD' → 'MM/DD' */
export const formatMonthDay = (date: string): string => `${date.slice(5, 7)}/${date.slice(8, 10)}`;
