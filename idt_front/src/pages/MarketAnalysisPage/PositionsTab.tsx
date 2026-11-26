// stock-analysis-agents §9.4 보유 / 거래 내역 — 같은 표 컴포넌트를 status 로 나눈다.
import { useState } from 'react';
import { useMarketPositions } from '@/hooks/useMarketAnalysis';
import { EXIT_REASON_LABELS, MARKET_ANALYSIS_PAGE_SIZE } from '@/types/marketAnalysis';
import { formatKst, formatPrice, formatRate, rateTone, rowProps } from '@/utils/marketAnalysis';
import PositionDetail from './PositionDetail';
import { Empty, ErrorBox, Loading, Pager, Table, Td, Th } from './parts';

interface PositionsTabProps {
  status: 'open' | 'closed';
  onOpenReport: (id: number) => void;
}

const holdingDays = (iso: string | null): string => {
  if (!iso) return '-';
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return `${Math.max(0, days)}일`;
};

const PositionsTab = ({ status, onOpenReport }: PositionsTabProps) => {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const query = useMarketPositions(status, page);

  if (selected !== null) {
    return (
      <PositionDetail id={selected} onBack={() => setSelected(null)} onOpenReport={onOpenReport} />
    );
  }
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="포지션을 불러오지 못했습니다." />;
  const data = query.data;
  if (!data || data.items.length === 0) {
    return <Empty>{status === 'open' ? '보유 중인 종목이 없습니다.' : '청산한 거래가 없습니다.'}</Empty>;
  }

  return (
    <>
      <Table label={status === 'open' ? '보유 종목' : '거래 내역'}>
        <thead>
          <tr>
            <Th>종목</Th>
            {status === 'open' && <Th>섹터</Th>}
            <Th right>진입가</Th>
            {status === 'open' ? (
              <>
                <Th right>현재가</Th>
                <Th right>평가 수익률</Th>
                <Th right>목표가</Th>
                <Th right>손절가</Th>
                <Th right>보유일</Th>
                <Th>진입일</Th>
              </>
            ) : (
              <>
                <Th right>청산가</Th>
                <Th right>수익률</Th>
                <Th right>보유일</Th>
                <Th>청산 사유</Th>
                <Th>청산일</Th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {data.items.map((p) => (
            <tr key={p.id} {...rowProps(() => setSelected(p.id), `${p.name ?? p.symbol} 상세`)}>
              <Td>
                <span className="font-medium">{p.name ?? p.symbol}</span>{' '}
                <span className="text-xs text-fg-muted">{p.symbol}</span>
              </Td>
              {status === 'open' && <Td>{p.sector ?? '-'}</Td>}
              <Td right>{formatPrice(p.entry_price)}</Td>
              {status === 'open' ? (
                <>
                  <Td right>{p.current_price === null || p.current_price === undefined ? '시세 없음' : formatPrice(p.current_price)}</Td>
                  <Td right className={rateTone(p.unrealized_rate)}>{formatRate(p.unrealized_rate)}</Td>
                  <Td right>{formatPrice(p.target_price)}</Td>
                  <Td right>{formatPrice(p.stop_loss)}</Td>
                  <Td right>{holdingDays(p.entry_at)}</Td>
                  <Td>{formatKst(p.entry_at)}</Td>
                </>
              ) : (
                <>
                  <Td right>{formatPrice(p.exit_price)}</Td>
                  <Td right className={rateTone(p.profit_rate)}>{formatRate(p.profit_rate)}</Td>
                  <Td right>{p.holding_days ?? '-'}일</Td>
                  <Td>{p.exit_reason ? (EXIT_REASON_LABELS[p.exit_reason] ?? p.exit_reason) : '-'}</Td>
                  <Td>{formatKst(p.exit_at)}</Td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </Table>
      <Pager page={page} total={data.total} size={MARKET_ANALYSIS_PAGE_SIZE} onChange={setPage} />
    </>
  );
};

export default PositionsTab;
