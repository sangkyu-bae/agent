// stock-analysis-agents §9.4 대시보드 — KPI 8개 · 누적 수익률 차트 · 최근 회차.
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import { useMarketDashboard } from '@/hooks/useMarketAnalysis';
import {
  REGIME_LABELS,
  ROUND_KIND_LABELS,
  ROUND_SKIP_LABELS,
  ROUND_STATUS_LABELS,
} from '@/types/marketAnalysis';
import { formatKst, formatRate, formatUsd, rateTone } from '@/utils/marketAnalysis';
import { cn } from '@/utils/cn';
import EquityChart from './EquityChart';
import { Card, Empty, ErrorBox, Loading } from './parts';

interface DashboardTabProps {
  onOpenRounds: () => void;
}

const Kpi = ({ label, value, tone }: { label: string; value: string; tone?: string }) => (
  <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
    <p className="text-xs text-fg-muted">{label}</p>
    <p className={cn('mt-1 text-lg font-semibold tabular-nums text-fg', tone)}>{value}</p>
  </div>
);

const DashboardTab = ({ onOpenRounds }: DashboardTabProps) => {
  const query = useMarketDashboard();
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="대시보드를 불러오지 못했습니다." />;
  const d = query.data;
  if (!d) return null;
  const k = d.kpi;
  const round = d.last_round;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="보유 종목" value={`${k.open_positions}종목`} />
        <Kpi label="슬롯 사용" value={`${k.used_slots}/${k.slot_count}`} />
        <Kpi label="청산 거래" value={`${k.closed_trades}건`} />
        <Kpi label="승률" value={`${k.win_rate.toFixed(1)}%`} />
        <Kpi label="평균 수익률" value={formatRate(k.avg_profit_rate)} tone={rateTone(k.avg_profit_rate)} />
        <Kpi label="평균 보유일" value={`${k.avg_holding_days.toFixed(1)}일`} />
        <Kpi
          label="누적 실현 수익률"
          value={formatRate(k.realized_cum_rate)}
          tone={rateTone(k.realized_cum_rate)}
        />
        <Kpi
          label="시장 체제"
          value={d.regime ? (REGIME_LABELS[d.regime.value] ?? d.regime.value) : '데이터 없음'}
        />
      </div>

      <Card title="누적 수익률">
        {d.equity.length > 0 ? (
          <EquityChart points={d.equity} />
        ) : (
          <Empty>아직 성과 기록이 없습니다. 장 마감 회차가 끝나면 하루 한 점씩 쌓입니다.</Empty>
        )}
        <p className="mt-2 text-xs text-fg-subtle">
          가상 계좌는 청산한 거래의 실현 수익만 더합니다. 지수는 첫 기록일 대비 누적 수익률입니다.
        </p>
      </Card>

      <Card
        title="최근 회차"
        actions={
          <Button variant="ghost" size="sm" onClick={onOpenRounds}>
            실행 현황 보기
          </Button>
        }
      >
        {round ? (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
            <div>
              <dt className="text-xs text-fg-muted">시각</dt>
              <dd className="text-fg">
                {round.trade_date} {round.slot} · {ROUND_KIND_LABELS[round.kind] ?? round.kind}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-fg-muted">상태</dt>
              <dd>
                <Badge tone={round.status === 'failed' ? 'danger' : round.status === 'done' ? 'success' : 'neutral'}>
                  {ROUND_STATUS_LABELS[round.status] ?? round.status}
                  {round.skip_reason ? ` · ${ROUND_SKIP_LABELS[round.skip_reason] ?? round.skip_reason}` : ''}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-fg-muted">분석 · 초과 · 실패</dt>
              <dd className="tabular-nums text-fg">
                {round.analyzed} · {round.over_cap} · {round.failed}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-fg-muted">비용</dt>
              <dd className="tabular-nums text-fg">{formatUsd(round.cost_usd)}</dd>
            </div>
            <div className="col-span-2 md:col-span-4">
              <dt className="sr-only">시작</dt>
              <dd className="text-xs text-fg-subtle">시작 {formatKst(round.started_at)}</dd>
            </div>
          </dl>
        ) : (
          <Empty>아직 실행한 회차가 없습니다.</Empty>
        )}
      </Card>
    </div>
  );
};

export default DashboardTab;
