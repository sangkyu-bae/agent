// stock-analysis-agents §9.4 관심종목 — 매수 보류 판단. 보류 사유(게이트 코드)를 한글로 푼다.
import { useState } from 'react';
import Badge from '@/components/ui/Badge';
import { useMarketWatchlist } from '@/hooks/useMarketAnalysis';
import {
  MARKET_ANALYSIS_PAGE_SIZE,
  REGIME_LABELS,
  WATCHLIST_PERIOD_LABELS,
  WATCHLIST_PERIODS,
  type WatchlistPeriod,
} from '@/types/marketAnalysis';
import {
  formatKst,
  formatPrice,
  translateSkipReason,
  withinPeriod,
} from '@/utils/marketAnalysis';
import { cn } from '@/utils/cn';
import { Empty, ErrorBox, Loading, Pager, Table, Td, Th } from './parts';

interface WatchlistTabProps {
  onOpenReport: (id: number) => void;
}

/** 게이트 사유 `SCORE_BELOW_MIN(6<7, bear)` 에서 최소 점수를 꺼낸다 */
const minScore = (reason: string | null): string | null => {
  const m = /SCORE_BELOW_MIN\(\d+<(\d+)/.exec(reason ?? '');
  return m ? m[1] : null;
};

const WatchlistTab = ({ onOpenReport }: WatchlistTabProps) => {
  const [page, setPage] = useState(1);
  const [period, setPeriod] = useState<WatchlistPeriod>('7d');
  const query = useMarketWatchlist(page);

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="관심종목을 불러오지 못했습니다." />;
  const data = query.data;
  // 기간 필터는 받은 페이지 안에서 거른다 (서버는 최신순)
  const items = (data?.items ?? []).filter((d) => withinPeriod(d.created_at, period));

  return (
    <div className="space-y-3">
      <div role="group" aria-label="기간" className="flex gap-1">
        {WATCHLIST_PERIODS.map((p) => (
          <button
            key={p}
            type="button"
            aria-pressed={period === p}
            onClick={() => setPeriod(p)}
            className={cn(
              'rounded-full border px-3 py-1 text-sm transition-colors duration-150',
              period === p
                ? 'border-brand-200 bg-brand-50 text-brand-700'
                : 'border-border text-fg-muted hover:bg-surface-muted',
            )}
          >
            {WATCHLIST_PERIOD_LABELS[p]}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <Empty>이 기간에 보류한 종목이 없습니다.</Empty>
      ) : (
        <Table label="관심종목">
          <thead>
            <tr>
              <Th>종목</Th>
              <Th>분석 일시</Th>
              <Th right>점수 / 최소</Th>
              <Th>보류 사유</Th>
              <Th right>목표가</Th>
              <Th right>손절가</Th>
              <Th>체제</Th>
              <Th>리포트</Th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id}>
                <Td>
                  <span className="font-medium">{d.name ?? d.symbol}</span>{' '}
                  <span className="text-xs text-fg-muted">{d.symbol}</span>
                  {d.provisional && (
                    <Badge tone="warning" className="ml-1">
                      미확정
                    </Badge>
                  )}
                </Td>
                <Td>{formatKst(d.created_at)}</Td>
                <Td right>
                  {d.score ?? '-'} / {minScore(d.skip_reason) ?? '-'}
                </Td>
                <Td className="max-w-md">
                  <ul className="space-y-0.5">
                    {translateSkipReason(d.skip_reason).map((r) => (
                      <li key={r} className="text-sm">
                        {r}
                      </li>
                    ))}
                  </ul>
                </Td>
                <Td right>{formatPrice(d.target_price)}</Td>
                <Td right>{formatPrice(d.stop_loss)}</Td>
                <Td>{d.regime ? (REGIME_LABELS[d.regime] ?? d.regime) : '-'}</Td>
                <Td>
                  {d.report_id !== null ? (
                    <button
                      type="button"
                      className="text-sm text-brand-600 hover:text-brand-700"
                      onClick={() => onOpenReport(d.report_id as number)}
                    >
                      보기
                    </button>
                  ) : (
                    '-'
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {data && (
        <Pager page={page} total={data.total} size={MARKET_ANALYSIS_PAGE_SIZE} onChange={setPage} />
      )}
    </div>
  );
};

export default WatchlistTab;
