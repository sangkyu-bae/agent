// stock-analysis-agents §9.4 리포트 목록 — 일자·종목·신호 배지·상태·미확정·비용. 행을 누르면 상세.
import { useState } from 'react';
import Badge from '@/components/ui/Badge';
import Input from '@/components/ui/Input';
import { useMarketReports } from '@/hooks/useMarketAnalysis';
import {
  MARKET_ANALYSIS_PAGE_SIZE,
  REPORT_STATUS_LABELS,
  SIGNAL_RULE_LABELS,
} from '@/types/marketAnalysis';
import { formatUsd, rowProps } from '@/utils/marketAnalysis';
import ReportDetail from './ReportDetail';
import { Empty, ErrorBox, Loading, Pager, Table, Td, Th } from './parts';

interface ReportsTabProps {
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}

const ReportsTab = ({ selectedId, onSelect }: ReportsTabProps) => {
  const [page, setPage] = useState(1);
  const [symbol, setSymbol] = useState('');
  const [date, setDate] = useState('');
  const query = useMarketReports({
    symbol: symbol.trim() || undefined,
    date: date || undefined,
    page,
  });

  if (selectedId !== null) {
    return <ReportDetail id={selectedId} onBack={() => onSelect(null)} />;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <Input
          label="종목코드"
          size="sm"
          value={symbol}
          onChange={(e) => {
            setSymbol(e.target.value);
            setPage(1);
          }}
          placeholder="예: 005930"
        />
        <Input
          label="일자"
          size="sm"
          type="date"
          value={date}
          onChange={(e) => {
            setDate(e.target.value);
            setPage(1);
          }}
        />
      </div>

      {query.isLoading && <Loading />}
      {query.isError && <ErrorBox error={query.error} fallback="리포트를 불러오지 못했습니다." />}
      {query.data && query.data.items.length === 0 && <Empty>리포트가 없습니다.</Empty>}
      {query.data && query.data.items.length > 0 && (
        <>
          <Table label="리포트">
            <thead>
              <tr>
                <Th>일자</Th>
                <Th>종목</Th>
                <Th>신호</Th>
                <Th>상태</Th>
                <Th right>비용</Th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((r) => (
                <tr key={r.id} {...rowProps(() => onSelect(r.id), `${r.name ?? r.symbol} 리포트`)}>
                  <Td>{r.trade_date}</Td>
                  <Td>
                    <span className="font-medium">{r.name ?? r.symbol}</span>{' '}
                    <span className="text-xs text-fg-muted">{r.symbol}</span>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {r.signals.map((s, i) => (
                        <Badge key={`${s.rule}-${i}`} tone="brand">
                          {SIGNAL_RULE_LABELS[s.rule ?? ''] ?? s.rule}
                        </Badge>
                      ))}
                    </div>
                  </Td>
                  <Td>
                    <Badge tone={r.status === 'done' ? 'success' : r.status === 'failed' ? 'danger' : 'warning'}>
                      {REPORT_STATUS_LABELS[r.status] ?? r.status}
                    </Badge>
                    {r.provisional && (
                      <Badge tone="warning" className="ml-1">
                        미확정
                      </Badge>
                    )}
                  </Td>
                  <Td right>{formatUsd(r.cost_usd)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pager page={page} total={query.data.total} size={MARKET_ANALYSIS_PAGE_SIZE} onChange={setPage} />
        </>
      )}
    </div>
  );
};

export default ReportsTab;
