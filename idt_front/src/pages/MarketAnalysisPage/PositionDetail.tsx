// stock-analysis-agents §9.4 — 포지션 상세: 매수 판단(점수·근거·게이트) · 매도 판단 이력 · 저널 · 리포트 링크.
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import { useMarketPosition } from '@/hooks/useMarketAnalysis';
import { DECISION_LABELS, EXIT_REASON_LABELS, REGIME_LABELS } from '@/types/marketAnalysis';
import {
  formatKst,
  formatPrice,
  formatRate,
  rateTone,
  translateSkipReason,
} from '@/utils/marketAnalysis';
import { BackButton, Card, Empty, ErrorBox, Loading } from './parts';

interface PositionDetailProps {
  id: number;
  onBack: () => void;
  onOpenReport: (id: number) => void;
}

const PositionDetail = ({ id, onBack, onOpenReport }: PositionDetailProps) => {
  const query = useMarketPosition(id);
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="포지션을 불러오지 못했습니다." />;
  const p = query.data;
  if (!p) return null;
  const buy = p.buy_decision;
  const gate = buy?.gate;

  return (
    <div className="space-y-4">
      <BackButton onClick={onBack} />
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-fg">
          {p.name ?? p.symbol} <span className="text-sm font-normal text-fg-muted">{p.symbol}</span>
        </h2>
        <Badge tone={p.status === 'open' ? 'info' : 'neutral'}>{p.status === 'open' ? '보유 중' : '청산'}</Badge>
        {p.exit_reason && <Badge tone="neutral">{EXIT_REASON_LABELS[p.exit_reason] ?? p.exit_reason}</Badge>}
        {p.report_id !== null && (
          <Button variant="secondary" size="sm" onClick={() => onOpenReport(p.report_id as number)}>
            근거 리포트 보기
          </Button>
        )}
      </div>

      <Card>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
          <div><dt className="text-xs text-fg-muted">진입가</dt><dd className="tabular-nums">{formatPrice(p.entry_price)}</dd></div>
          <div><dt className="text-xs text-fg-muted">목표가</dt><dd className="tabular-nums">{formatPrice(p.target_price)}</dd></div>
          <div><dt className="text-xs text-fg-muted">손절가</dt><dd className="tabular-nums">{formatPrice(p.stop_loss)}</dd></div>
          <div><dt className="text-xs text-fg-muted">진입일</dt><dd>{formatKst(p.entry_at)}</dd></div>
          {p.status === 'closed' && (
            <>
              <div><dt className="text-xs text-fg-muted">청산가</dt><dd className="tabular-nums">{formatPrice(p.exit_price)}</dd></div>
              <div><dt className="text-xs text-fg-muted">수익률</dt><dd className={rateTone(p.profit_rate)}>{formatRate(p.profit_rate)}</dd></div>
              <div><dt className="text-xs text-fg-muted">보유일</dt><dd>{p.holding_days ?? '-'}일</dd></div>
              <div><dt className="text-xs text-fg-muted">청산일</dt><dd>{formatKst(p.exit_at)}</dd></div>
            </>
          )}
        </dl>
      </Card>

      <Card title="매수 판단">
        {buy ? (
          <div className="space-y-2 text-sm">
            <p>
              점수 <strong className="tabular-nums">{buy.score ?? '-'}</strong> · 판단가{' '}
              {formatPrice(buy.price_at_decision)} · 체제{' '}
              {buy.regime ? (REGIME_LABELS[buy.regime] ?? buy.regime) : '-'}
              {buy.provisional && ' · 장중 미확정 봉 기준'}
            </p>
            {gate && (
              <p className="text-fg-secondary">
                게이트 {gate.passed ? '통과' : '미통과'} · 손익비 {gate.rr ?? '-'} · 손절폭{' '}
                {gate.stop_pct ? `${gate.stop_pct}%` : '-'}
              </p>
            )}
            <p className="whitespace-pre-wrap text-fg">{buy.rationale || '근거 없음'}</p>
          </div>
        ) : (
          <Empty>매수 판단 기록이 없습니다.</Empty>
        )}
      </Card>

      <Card title="매도 판단 이력">
        {p.sell_decisions.length === 0 ? (
          <Empty>아직 매도 판단이 없습니다.</Empty>
        ) : (
          <ul className="space-y-3">
            {p.sell_decisions.map((d) => (
              <li key={d.id} className="rounded-md border border-border px-3 py-2 text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <Badge tone={d.decision === 'sell' ? 'danger' : 'neutral'}>
                    {DECISION_LABELS[d.decision] ?? d.decision}
                  </Badge>
                  <span className="text-fg-muted">{formatKst(d.created_at)}</span>
                  {d.confidence !== null && <span className="text-fg-muted">확신도 {d.confidence}</span>}
                  {d.price_at_decision !== null && (
                    <span className="text-fg-muted">판단가 {formatPrice(d.price_at_decision)}</span>
                  )}
                </p>
                {d.rationale && <p className="mt-1 whitespace-pre-wrap text-fg">{d.rationale}</p>}
                {translateSkipReason(d.skip_reason).map((r) => (
                  <p key={r} className="mt-1 text-xs text-warning">{r}</p>
                ))}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="저널">
        {p.journal ? (
          <div className="space-y-2 text-sm">
            {p.journal.one_line && <p className="font-medium text-fg">{p.journal.one_line}</p>}
            {p.journal.situation && <p className="whitespace-pre-wrap text-fg-secondary">{p.journal.situation}</p>}
            {p.journal.evaluation && <p className="whitespace-pre-wrap text-fg-secondary">{p.journal.evaluation}</p>}
            {p.journal.lessons.length > 0 && (
              <ul className="list-disc pl-5 text-fg">
                {p.journal.lessons.map((l) => <li key={l}>{l}</li>)}
              </ul>
            )}
            {p.journal.raw_answer && (
              <p className="whitespace-pre-wrap text-fg-muted">{p.journal.raw_answer}</p>
            )}
            <div className="flex flex-wrap gap-1">
              {p.journal.tags.map((t) => <Badge key={t} tone="brand">{t}</Badge>)}
            </div>
          </div>
        ) : (
          <Empty>{p.status === 'open' ? '청산되면 저널이 생깁니다.' : '저널이 없습니다.'}</Empty>
        )}
      </Card>
    </div>
  );
};

export default PositionDetail;
