// market-index-ytd-chart Design §5.3 — KOSPI·KOSDAQ 연초 대비 등락률 겹침 차트.
// 체제가 기록된 날은 KOSPI 선 위에 점, 툴팁은 값·미확정·체제를 글로 보인다.
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { IndexChartRow } from '@/types/marketAnalysis';
import { describeIndexRow, formatMonthDay } from '@/utils/marketIndexChart';

interface IndexYtdChartProps {
  rows: IndexChartRow[];
}

interface DotProps {
  cx?: number;
  cy?: number;
  index?: number;
  payload?: IndexChartRow;
}

// 체제 기록일에만 점을 찍는다 — 나머지 날은 빈 그룹
const RegimeDot = ({ cx, cy, index, payload }: DotProps) =>
  payload?.regime && cx !== undefined && cy !== undefined ? (
    <circle
      key={`regime-${index}`}
      cx={cx}
      cy={cy}
      r={4}
      fill="var(--color-brand-600)"
      stroke="var(--color-surface)"
      strokeWidth={1.5}
    />
  ) : (
    <g key={`regime-${index}`} />
  );

interface TooltipProps {
  active?: boolean;
  payload?: { payload?: IndexChartRow }[];
}

const IndexTooltip = ({ active, payload }: TooltipProps) => {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2 text-xs text-fg shadow-sm">
      <p className="font-medium">{row.date}</p>
      {describeIndexRow(row).map((line) => (
        <p key={line} className="text-fg-secondary">
          {line}
        </p>
      ))}
    </div>
  );
};

const IndexYtdChart = ({ rows }: IndexYtdChartProps) => (
  <div className="h-64" role="img" aria-label="올해 KOSPI·KOSDAQ 등락률">
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="date" tick={{ fontSize: 12 }} tickFormatter={formatMonthDay} minTickGap={24} />
        <YAxis tick={{ fontSize: 12 }} unit="%" width={48} />
        <ReferenceLine y={0} stroke="var(--color-border-strong)" />
        <Tooltip content={<IndexTooltip />} />
        {/* 기본 정렬(이름순)이면 KOSDAQ 이 먼저 — 요약 줄과 같게 선언 순서(KOSPI→KOSDAQ)로 */}
        <Legend itemSorter={null} />
        <Line
          type="monotone"
          dataKey="kospi"
          name="KOSPI"
          stroke="var(--color-fg-muted)"
          strokeWidth={1.75}
          dot={(props: DotProps) => <RegimeDot {...props} />}
          activeDot={{ r: 3 }}
          connectNulls
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="kosdaq"
          name="KOSDAQ"
          stroke="var(--color-info)"
          strokeWidth={1.75}
          dot={false}
          activeDot={{ r: 3 }}
          connectNulls
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  </div>
);

export default IndexYtdChart;
