// stock-analysis-agents §9.4 실행 현황 — 회차 표·상세(종목별 상태·오류·리포트) · "지금 실행"(manage, 확인창).
import { useState } from 'react';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useMarketRound, useMarketRounds, useRunNow } from '@/hooks/useMarketAnalysis';
import {
  ITEM_STATUS_LABELS,
  MARKET_ANALYSIS_PAGE_SIZE,
  ROUND_KIND_LABELS,
  ROUND_SKIP_LABELS,
  ROUND_STATUS_LABELS,
} from '@/types/marketAnalysis';
import {
  formatKst,
  formatUsd,
  marketAnalysisErrorMessage,
  rowProps,
  translateSkipReason,
} from '@/utils/marketAnalysis';
import { BackButton, Empty, ErrorBox, Loading, Pager, Table, Td, Th } from './parts';

interface RoundsTabProps {
  canManage: boolean;
  onOpenReport: (id: number) => void;
}

const statusTone = (status: string) =>
  status === 'done' ? 'success' : status === 'failed' ? 'danger' : status === 'running' ? 'info' : 'neutral';

const RoundDetail = ({
  id,
  onBack,
  onOpenReport,
}: {
  id: number;
  onBack: () => void;
  onOpenReport: (id: number) => void;
}) => {
  const query = useMarketRound(id);
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="회차를 불러오지 못했습니다." />;
  const r = query.data;
  if (!r) return null;
  return (
    <div className="space-y-3">
      <BackButton onClick={onBack} />
      <p className="text-sm text-fg">
        {r.trade_date} {r.slot} · {ROUND_KIND_LABELS[r.kind] ?? r.kind} ·{' '}
        {ROUND_STATUS_LABELS[r.status] ?? r.status}
        {r.error && <span className="ml-2 text-danger">{r.error}</span>}
      </p>
      {r.items.length === 0 ? (
        <Empty>이 회차에서 다룬 종목이 없습니다.</Empty>
      ) : (
        <Table label="회차 종목">
          <thead>
            <tr>
              <Th>종목</Th>
              <Th>상태</Th>
              <Th>오류</Th>
              <Th right>토큰</Th>
              <Th right>비용</Th>
              <Th>리포트</Th>
            </tr>
          </thead>
          <tbody>
            {r.items.map((i) => (
              <tr key={i.id}>
                <Td>
                  <span className="font-medium">{i.name ?? i.symbol}</span>{' '}
                  <span className="text-xs text-fg-muted">{i.symbol}</span>
                </Td>
                <Td>
                  <Badge tone={statusTone(i.status)}>{ITEM_STATUS_LABELS[i.status] ?? i.status}</Badge>
                </Td>
                <Td className="text-xs text-fg-muted">{i.error ?? '-'}</Td>
                <Td right>{i.tokens.toLocaleString()}</Td>
                <Td right>{formatUsd(i.cost_usd)}</Td>
                <Td>
                  {i.report_id !== null ? (
                    <button
                      type="button"
                      className="text-sm text-brand-600 hover:text-brand-700"
                      onClick={() => onOpenReport(i.report_id as number)}
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
    </div>
  );
};

const RoundsTab = ({ canManage, onOpenReport }: RoundsTabProps) => {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);
  const query = useMarketRounds(page);
  const runNow = useRunNow();

  if (selected !== null) {
    return <RoundDetail id={selected} onBack={() => setSelected(null)} onOpenReport={onOpenReport} />;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-fg-muted">회차마다 대상 수·성공·실패와 토큰 비용을 남깁니다.</p>
        {canManage && (
          <Button size="sm" onClick={() => setConfirm(true)}>
            지금 실행
          </Button>
        )}
      </div>
      {runNow.isSuccess && (
        <p role="status" className="text-sm text-success">
          회차 #{runNow.data.round_id}를 시작했습니다.
        </p>
      )}

      {query.isLoading && <Loading />}
      {query.isError && <ErrorBox error={query.error} fallback="실행 현황을 불러오지 못했습니다." />}
      {query.data && query.data.items.length === 0 && <Empty>아직 실행한 회차가 없습니다.</Empty>}
      {query.data && query.data.items.length > 0 && (
        <>
          <Table label="회차">
            <thead>
              <tr>
                <Th>일자</Th>
                <Th>시각</Th>
                <Th>종류</Th>
                <Th>트리거</Th>
                <Th>상태</Th>
                <Th right>후보</Th>
                <Th right>신호</Th>
                <Th right>분석</Th>
                <Th right>초과</Th>
                <Th right>실패</Th>
                <Th right>토큰</Th>
                <Th right>비용</Th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((r) => (
                <tr key={r.id} {...rowProps(() => setSelected(r.id), `회차 ${r.trade_date} ${r.slot} 상세`)}>
                  <Td>{r.trade_date}</Td>
                  <Td>{r.slot}</Td>
                  <Td>{ROUND_KIND_LABELS[r.kind] ?? r.kind}</Td>
                  <Td>{r.trigger === 'manual' ? '수동' : '자동'}</Td>
                  <Td>
                    <Badge tone={statusTone(r.status)}>{ROUND_STATUS_LABELS[r.status] ?? r.status}</Badge>
                    {r.skip_reason && (
                      <span className="ml-1 text-xs text-fg-muted">
                        {ROUND_SKIP_LABELS[r.skip_reason] ?? r.skip_reason}
                      </span>
                    )}
                    {r.error && (
                      <span className="ml-1 text-xs text-danger">
                        {translateSkipReason(r.error).join(', ') || r.error}
                      </span>
                    )}
                  </Td>
                  <Td right>{r.candidates}</Td>
                  <Td right>{r.signaled}</Td>
                  <Td right>{r.analyzed}</Td>
                  <Td right>{r.over_cap}</Td>
                  <Td right>{r.failed}</Td>
                  <Td right>{r.tokens.toLocaleString()}</Td>
                  <Td right>{formatUsd(r.cost_usd)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p className="text-xs text-fg-subtle">시작 시각은 서울 기준입니다. 최근 회차 시작: {formatKst(query.data.items[0]?.started_at)}</p>
          <Pager page={page} total={query.data.total} size={MARKET_ANALYSIS_PAGE_SIZE} onChange={setPage} />
        </>
      )}

      <ConfirmDialog
        isOpen={confirm}
        title="지금 회차 실행"
        description="자동 분석 스위치와 관계없이 장 마감 회차를 한 번 실행합니다. 상한은 그대로 적용되고 에이전트 비용이 듭니다."
        confirmLabel="실행"
        variant="info"
        isPending={runNow.isPending}
        error={
          runNow.isError
            ? marketAnalysisErrorMessage(runNow.error, '회차를 시작하지 못했습니다.')
            : null
        }
        onClose={() => {
          setConfirm(false);
          runNow.reset();
        }}
        onConfirm={() => runNow.mutate('close', { onSuccess: () => setConfirm(false) })}
      />
    </div>
  );
};

export default RoundsTab;
