import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { UsageTimeseriesPoint } from '@/types/agentRunAdmin';

interface Props {
  points: UsageTimeseriesPoint[] | undefined;
  loading?: boolean;
}

interface ChartData {
  bucket: string;
  cost: number;
  runs: number;
  tokens: number;
}

function toChartData(points: UsageTimeseriesPoint[]): ChartData[] {
  return points.map((p) => ({
    bucket: p.bucket,
    cost:
      typeof p.total_cost_usd === 'string'
        ? parseFloat(p.total_cost_usd)
        : p.total_cost_usd,
    runs: p.run_count,
    tokens: p.total_tokens,
  }));
}

const TimeseriesChart = ({ points, loading }: Props) => {
  if (loading || !points) {
    return (
      <div className="flex h-64 animate-pulse items-center justify-center rounded-lg border border-zinc-100 bg-zinc-50 text-sm text-zinc-400">
        차트 로딩 중...
      </div>
    );
  }

  if (points.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-zinc-100 bg-white text-sm text-zinc-400">
        선택한 기간에 데이터가 없습니다
      </div>
    );
  }

  const data = toChartData(points);

  return (
    <div className="h-64 w-full rounded-lg border border-zinc-100 bg-white p-3">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
          <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => `$${v.toFixed(2)}`}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fontSize: 11 }}
            allowDecimals={false}
          />
          <Tooltip
            formatter={(value, name) => {
              const v = typeof value === 'number' ? value : Number(value ?? 0);
              if (name === 'cost') return [`$${v.toFixed(4)}`, '비용'];
              if (name === 'runs') return [v, 'Run 수'];
              return [v, String(name)];
            }}
          />
          <Legend
            formatter={(v) => (v === 'cost' ? '비용' : v === 'runs' ? 'Run 수' : v)}
            wrapperStyle={{ fontSize: 12 }}
          />
          <Bar
            yAxisId="right"
            dataKey="runs"
            fill="#a78bfa"
            barSize={20}
            radius={[4, 4, 0, 0]}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="cost"
            stroke="#10b981"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

export default TimeseriesChart;
