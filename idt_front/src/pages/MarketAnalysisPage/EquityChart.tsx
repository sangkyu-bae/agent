// stock-analysis-agents §9.4 대시보드 — 포트폴리오 누적 실현 수익률 vs KOSPI vs KOSDAQ.
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { EquityPoint } from '@/types/marketAnalysis';

interface EquityChartProps {
  points: EquityPoint[];
}

const SERIES = [
  { key: 'portfolio', name: '가상 계좌', color: 'var(--color-brand-600)' },
  { key: 'kospi', name: 'KOSPI', color: 'var(--color-fg-muted)' },
  { key: 'kosdaq', name: 'KOSDAQ', color: 'var(--color-info)' },
] as const;

const EquityChart = ({ points }: EquityChartProps) => (
  <div className="h-64" role="img" aria-label="누적 수익률: 가상 계좌와 KOSPI·KOSDAQ 비교">
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="date" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} unit="%" width={48} />
        <Tooltip formatter={(v) => (typeof v === 'number' ? `${v.toFixed(2)}%` : '-')} />
        <Legend />
        {SERIES.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={s.color}
            strokeWidth={s.key === 'portfolio' ? 2 : 1.5}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  </div>
);

export default EquityChart;
