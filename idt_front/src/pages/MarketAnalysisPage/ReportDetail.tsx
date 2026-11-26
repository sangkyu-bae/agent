// stock-analysis-agents §9.4 리포트 상세 — 머리 사실 · 요약 · 전략 · 섹션 6(접기) · 근거 · 연결된 판단.
// 실패·공란 섹션은 "데이터 없음" (Design U10 · L2 #4).
import Badge from '@/components/ui/Badge';
import MarkdownRenderer from '@/components/chat/MarkdownRenderer';
import { useMarketReport } from '@/hooks/useMarketAnalysis';
import {
  DECISION_LABELS,
  EVIDENCE_SOURCE_LABELS,
  REGIME_LABELS,
  REPORT_STATUS_LABELS,
  SECTION_ROLE_LABELS,
  SIGNAL_RULE_LABELS,
} from '@/types/marketAnalysis';
import { formatKst, formatUsd, translateSkipReason } from '@/utils/marketAnalysis';
import { BackButton, Card, Empty, ErrorBox, Loading } from './parts';

interface ReportDetailProps {
  id: number;
  onBack: () => void;
}

const ReportDetail = ({ id, onBack }: ReportDetailProps) => {
  const query = useMarketReport(id);
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="리포트를 불러오지 못했습니다." />;
  const r = query.data;
  if (!r) return null;
  const h = r.header_facts;

  return (
    <div className="space-y-4">
      <BackButton onClick={onBack} />
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-fg">
          {r.name ?? r.symbol} <span className="text-sm font-normal text-fg-muted">{r.symbol}</span>
        </h2>
        <Badge tone={r.status === 'done' ? 'success' : r.status === 'failed' ? 'danger' : 'warning'}>
          {REPORT_STATUS_LABELS[r.status] ?? r.status}
        </Badge>
        {r.provisional && <Badge tone="warning">장중 미확정</Badge>}
        <span className="text-sm text-fg-muted">
          {r.trade_date} · 체제 {r.regime ? (REGIME_LABELS[r.regime] ?? r.regime) : '-'} · 비용{' '}
          {formatUsd(r.cost_usd)}
        </span>
      </div>

      <Card title="머리 사실 (도구 결과 그대로)">
        {h ? (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
            <div><dt className="text-xs text-fg-muted">현재가</dt><dd className="tabular-nums">{h.price ?? '데이터 없음'}</dd></div>
            <div><dt className="text-xs text-fg-muted">등락률</dt><dd className="tabular-nums">{h.change_rate ? `${h.change_rate}%` : '데이터 없음'}</dd></div>
            <div><dt className="text-xs text-fg-muted">거래량</dt><dd className="tabular-nums">{h.volume ?? '데이터 없음'}</dd></div>
            <div><dt className="text-xs text-fg-muted">조회 시각</dt><dd>{h.as_of ?? '-'}</dd></div>
          </dl>
        ) : (
          <Empty>데이터 없음</Empty>
        )}
        <div className="mt-3 flex flex-wrap gap-1">
          {r.signals.map((s, i) => (
            <Badge key={`${s.rule}-${i}`} tone="brand">
              {SIGNAL_RULE_LABELS[s.rule ?? ''] ?? s.rule}
            </Badge>
          ))}
        </div>
      </Card>

      <Card title="핵심 요약">
        {r.summary ? <MarkdownRenderer content={r.summary} /> : <Empty>데이터 없음</Empty>}
      </Card>

      <Card title="투자 시나리오">
        {r.strategy ? <MarkdownRenderer content={r.strategy} /> : <Empty>데이터 없음</Empty>}
      </Card>

      <Card title="섹션">
        <div className="space-y-2">
          {r.sections.map((s) => {
            const ok = s.status === 'done' && !!s.content?.trim();
            return (
              <details key={s.role} className="rounded-md border border-border px-3 py-2">
                <summary className="cursor-pointer text-sm font-medium text-fg">
                  {SECTION_ROLE_LABELS[s.role] ?? s.role}
                  {!ok && <span className="ml-2 text-xs text-warning">데이터 없음</span>}
                </summary>
                <div className="mt-2 text-sm">
                  {ok ? <MarkdownRenderer content={s.content as string} /> : <p className="text-fg-muted">데이터 없음</p>}
                </div>
              </details>
            );
          })}
        </div>
      </Card>

      <Card title="근거">
        {r.evidence.length === 0 ? (
          <Empty>근거 기록이 없습니다.</Empty>
        ) : (
          <ul className="space-y-1 text-sm">
            {r.evidence.map((e, i) => (
              <li key={`${e.tool}-${i}`}>
                <details>
                  <summary className="cursor-pointer">
                    <span className="font-medium">{EVIDENCE_SOURCE_LABELS[e.source] ?? e.source}</span>{' '}
                    <code className="text-xs">{e.tool}</code>{' '}
                    <span className="text-xs text-fg-muted">{formatKst(e.fetched_at)}</span>
                    {e.is_error && (
                      <Badge tone="danger" className="ml-2">
                        오류
                      </Badge>
                    )}
                  </summary>
                  <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-surface-sunken p-2 text-xs whitespace-pre-wrap">
                    {e.payload ?? '데이터 없음'}
                  </pre>
                </details>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="판단">
        {r.decisions.length === 0 ? (
          <Empty>이 리포트로 내린 판단이 없습니다.</Empty>
        ) : (
          <ul className="space-y-2 text-sm">
            {r.decisions.map((d) => (
              <li key={d.id} className="rounded-md border border-border px-3 py-2">
                <p className="flex flex-wrap items-center gap-2">
                  <Badge tone={d.decision === 'enter' ? 'success' : 'neutral'}>
                    {DECISION_LABELS[d.decision] ?? d.decision}
                  </Badge>
                  <span className="text-fg-muted">점수 {d.score ?? '-'}</span>
                </p>
                {d.rationale && <p className="mt-1 whitespace-pre-wrap">{d.rationale}</p>}
                {translateSkipReason(d.skip_reason).map((t) => (
                  <p key={t} className="mt-1 text-xs text-warning">{t}</p>
                ))}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
};

export default ReportDetail;
