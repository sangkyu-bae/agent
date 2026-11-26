// stock-analysis-agents §9.4 인사이트 — 원칙(활성 토글은 manage 만) · 최근 저널 · 신호 규칙별 성과.
// 원칙 후보는 꺼진 상태로 쌓인다(DD9) — 운영자가 켜야 판단 입력에 들어간다.
import Badge from '@/components/ui/Badge';
import { useMarketInsights, usePatchPrinciple } from '@/hooks/useMarketAnalysis';
import {
  PRIORITY_LABELS,
  SCOPE_LABELS,
  SIGNAL_RULE_LABELS,
} from '@/types/marketAnalysis';
import {
  formatRate,
  marketAnalysisErrorMessage,
  rateTone,
} from '@/utils/marketAnalysis';
import { Card, Empty, ErrorBox, Loading, Table, Td, Th } from './parts';

interface InsightsTabProps {
  canManage: boolean;
}

const InsightsTab = ({ canManage }: InsightsTabProps) => {
  const query = useMarketInsights();
  const patch = usePatchPrinciple();

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="인사이트를 불러오지 못했습니다." />;
  const data = query.data;
  if (!data) return null;

  return (
    <div className="space-y-5">
      <Card title="매매 원칙">
        <p className="mb-3 text-xs text-fg-subtle">
          청산 저널에서 나온 후보입니다. 켠 원칙만 매수·매도 판단 입력에 들어갑니다.
        </p>
        {patch.isError && (
          <p role="alert" className="mb-3 text-sm text-danger">
            {marketAnalysisErrorMessage(patch.error, '원칙을 바꾸지 못했습니다.')}
          </p>
        )}
        {data.principles.length === 0 ? (
          <Empty>아직 원칙이 없습니다. 거래가 청산되면 저널에서 후보가 생깁니다.</Empty>
        ) : (
          <Table label="매매 원칙">
            <thead>
              <tr>
                <Th>조건</Th>
                <Th>행동</Th>
                <Th>적용</Th>
                <Th right>근거 거래</Th>
                <Th right>확신도</Th>
                <Th>우선순위</Th>
                <Th>활성</Th>
              </tr>
            </thead>
            <tbody>
              {data.principles.map((p) => (
                <tr key={p.id}>
                  <Td className="max-w-xs whitespace-normal">{p.condition}</Td>
                  <Td className="max-w-xs whitespace-normal">{p.action}</Td>
                  <Td>{SCOPE_LABELS[p.scope] ?? p.scope}</Td>
                  <Td right>{p.supporting_count}건</Td>
                  <Td right>{p.confidence}</Td>
                  <Td>{PRIORITY_LABELS[p.priority] ?? p.priority}</Td>
                  <Td>
                    <label className="inline-flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={p.is_active}
                        disabled={!canManage || patch.isPending}
                        onChange={(e) =>
                          patch.mutate({ id: p.id, body: { is_active: e.target.checked } })
                        }
                        aria-label={`${p.condition} 원칙 ${p.is_active ? '끄기' : '켜기'}`}
                      />
                      {p.is_active ? '켜짐' : '꺼짐'}
                    </label>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card title="최근 저널">
        {data.journals.length === 0 ? (
          <Empty>아직 저널이 없습니다.</Empty>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {data.journals.map((j) => (
              <li key={j.id} className="rounded-xl border border-border p-3 text-sm">
                <p className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-fg">{j.name ?? j.symbol ?? `포지션 ${j.position_id}`}</span>
                  {j.profit_rate !== undefined && (
                    <span className={rateTone(j.profit_rate)}>{formatRate(j.profit_rate)}</span>
                  )}
                </p>
                <p className="mt-1 text-fg">{j.one_line ?? '요약 없음'}</p>
                {j.lessons.length > 0 && (
                  <ul className="mt-1 list-disc pl-5 text-fg-secondary">
                    {j.lessons.map((l) => <li key={l}>{l}</li>)}
                  </ul>
                )}
                <div className="mt-2 flex flex-wrap gap-1">
                  {j.tags.map((t) => <Badge key={t} tone="brand">{t}</Badge>)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="신호 규칙별 성과">
        {data.rule_performance.length === 0 ? (
          <Empty>청산한 거래가 쌓이면 규칙별 승률이 나옵니다.</Empty>
        ) : (
          <Table label="신호 규칙별 성과">
            <thead>
              <tr>
                <Th>규칙</Th>
                <Th right>진입 수</Th>
                <Th right>승률</Th>
                <Th right>평균 수익률</Th>
              </tr>
            </thead>
            <tbody>
              {data.rule_performance.map((r) => (
                <tr key={r.rule}>
                  <Td>{SIGNAL_RULE_LABELS[r.rule] ?? r.rule}</Td>
                  <Td right>{r.trades}</Td>
                  <Td right>{r.win_rate.toFixed(1)}%</Td>
                  <Td right className={rateTone(r.avg_profit_rate)}>{formatRate(r.avg_profit_rate)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
};

export default InsightsTab;
