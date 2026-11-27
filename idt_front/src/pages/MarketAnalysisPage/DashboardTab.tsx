// stock-analysis-agents §9.4 대시보드 — KPI 8개 · 올해 시장(market-index-ytd-chart §5) · 누적 수익률 차트 · 최근 회차.
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import { useIndexChart, useMarketDashboard } from '@/hooks/useMarketAnalysis';
import {
  MARKET_INDEXES,
  REGIME_LABELS,
  ROUND_KIND_LABELS,
  ROUND_SKIP_LABELS,
  ROUND_STATUS_LABELS,
  type MarketAnalysisDashboardResponse,
} from '@/types/marketAnalysis';
import { formatKst, formatRate, formatUsd, rateTone } from '@/utils/marketAnalysis';
import { cn } from '@/utils/cn';
import {
  formatMonthDay,
  lastConfirmedDate,
  latestIndexPoint,
  toIndexChartRows,
} from '@/utils/marketIndexChart';
import EquityChart from './EquityChart';
import IndexYtdChart from './IndexYtdChart';
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

// 대시보드 조회와 따로 불러 첫 조회의 연초 적재가 KPI 표시를 막지 않는다
const IndexYtdCard = () => {
  const query = useIndexChart();
  const data = query.data;
  const rows = data ? toIndexChartRows(data) : [];
  const latest = data
    ? MARKET_INDEXES.map((index) => ({ index, point: latestIndexPoint(data.series[index]) }))
    : [];
  const live = latest.find((l) => l.point?.provisional)?.point;
  // gap G-I1 — 한쪽 지수만 비었으면 응답이 unavailable 이어도 행이 있다. 빠진 지수를 밝힌다
  const missing = latest.filter((l) => !l.point).map((l) => l.index);
  // gap G-M6 — 저장 데이터 기준일은 미확정(장중) 점이 아니라 마지막 확정 점
  const savedUntil = lastConfirmedDate(rows);

  let body;
  if (query.isLoading) body = <p className="py-10 text-center text-sm text-fg-muted">지수 흐름을 불러오는 중…</p>;
  else if (query.isError) body = <ErrorBox error={query.error} fallback="올해 지수 흐름을 불러오지 못했습니다." />;
  else if (!data) body = null;
  else if (rows.length === 0)
    body =
      data.source_status === 'unavailable' ? (
        <Empty>지수 시세를 받을 수 없습니다. KIS 서버 설정을 확인하세요.</Empty>
      ) : (
        <Empty>올해 첫 거래일 이후에 표시됩니다.</Empty>
      );
  else
    body = (
      <>
        <p className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
          {latest.map(({ index, point }) =>
            point ? (
              <span key={index} className={cn('font-semibold tabular-nums', rateTone(point.rate))}>
                {`${index} ${formatRate(point.rate)}`}
              </span>
            ) : null,
          )}
          {live && <span className="text-xs text-fg-subtle">{`(${formatMonthDay(live.date)} 미확정)`}</span>}
        </p>
        <IndexYtdChart rows={rows} />
        <p className="mt-2 text-xs text-fg-subtle">
          연초 첫 거래일 종가 대비 등락률입니다. 점은 시장 체제가 기록된 날입니다.
        </p>
        {missing.length > 0 ? (
          <p className="mt-1 text-xs text-warning">
            {`${missing.join('·')} 시세를 받지 못했습니다. 잠시 후 다시 확인하세요.`}
          </p>
        ) : (
          data.source_status !== 'ok' &&
          savedUntil && (
            <p className="mt-1 text-xs text-warning">
              {`최신 시세를 받지 못해 ${formatMonthDay(savedUntil)}까지의 저장 데이터로 표시합니다.`}
            </p>
          )
        )}
      </>
    );

  return (
    <Card title="올해 시장" label="올해 시장">
      {body}
    </Card>
  );
};

// market-index-ytd-chart G-M4 — 차트 카드는 대시보드 조회를 기다리지 않고 같이 요청·표시한다.
// 대시보드가 로딩 중이거나 실패해도 카드는 그대로 보인다.
const DashboardTab = ({ onOpenRounds }: DashboardTabProps) => {
  const query = useMarketDashboard();
  const d = query.data;

  let summary;
  if (query.isLoading) summary = <Loading />;
  else if (query.isError) summary = <ErrorBox error={query.error} fallback="대시보드를 불러오지 못했습니다." />;
  else if (d) summary = <KpiGrid d={d} />;

  return (
    <div className="space-y-5">
      {summary}
      <IndexYtdCard />
      {d && !query.isError && <DashboardDetails d={d} onOpenRounds={onOpenRounds} />}
    </div>
  );
};

const KpiGrid = ({ d }: { d: MarketAnalysisDashboardResponse }) => {
  const k = d.kpi;
  return (
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
  );
};

const DashboardDetails = ({
  d,
  onOpenRounds,
}: {
  d: MarketAnalysisDashboardResponse;
  onOpenRounds: () => void;
}) => {
  const round = d.last_round;
  return (
    <>
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
    </>
  );
};

export default DashboardTab;
