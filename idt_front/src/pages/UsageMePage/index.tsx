import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PeriodFilter, {
  resolvePeriod,
  type PeriodValue,
} from '@/components/common/PeriodFilter';
import { useMyRuns, useMyTimeseries, useMyUsage } from '@/hooks/useUsageMe';
import SummaryCards from '@/pages/AdminAgentRunsPage/components/SummaryCards';
import TimeseriesChart from '@/pages/AdminAgentRunsPage/components/TimeseriesChart';
import RunListTable from '@/pages/AdminAgentRunsPage/components/RunListTable';
import type { UsageByLlmResponse } from '@/types/agentRunAdmin';

function aggregateMyCards(data: UsageByLlmResponse | undefined): {
  totalCalls: number | undefined;
  totalTokens: number | undefined;
  totalCost: number | undefined;
} {
  if (!data) return { totalCalls: undefined, totalTokens: undefined, totalCost: undefined };
  const totals = data.rows.reduce(
    (acc, r) => {
      const cost =
        typeof r.total_cost_usd === 'string'
          ? parseFloat(r.total_cost_usd)
          : r.total_cost_usd;
      return {
        calls: acc.calls + r.call_count,
        tokens: acc.tokens + r.total_tokens,
        cost: acc.cost + (Number.isNaN(cost) ? 0 : cost),
      };
    },
    { calls: 0, tokens: 0, cost: 0 },
  );
  return {
    totalCalls: totals.calls,
    totalTokens: totals.tokens,
    totalCost: totals.cost,
  };
}

const initialPeriod: PeriodValue = (() => {
  const r = resolvePeriod('30d');
  return { preset: '30d', from: r.from, to: r.to };
})();

const UsageMePage = () => {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<PeriodValue>(initialPeriod);
  const [offset, setOffset] = useState(0);
  const LIMIT = 20;

  const periodParams = useMemo(
    () => ({ from: period.from, to: period.to }),
    [period.from, period.to],
  );

  const usageQ = useMyUsage(periodParams);
  const tsQ = useMyTimeseries(periodParams);
  const runsQ = useMyRuns({ ...periodParams, limit: LIMIT, offset });

  const cards = aggregateMyCards(usageQ.data);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6 sm:px-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">내 사용량</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            내가 실행한 Agent 호출 통계
          </p>
        </div>
        <PeriodFilter
          value={period}
          onChange={(v) => {
            setPeriod(v);
            setOffset(0);
          }}
        />
      </header>

      <SummaryCards
        totalRuns={cards.totalCalls}
        successRate={undefined}
        totalTokens={cards.totalTokens}
        totalCostUsd={cards.totalCost}
        loading={usageQ.isLoading}
      />

      <TimeseriesChart points={tsQ.data?.points} loading={tsQ.isLoading} />

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-700">최근 내 Run</h2>
        <RunListTable
          data={runsQ.data}
          loading={runsQ.isLoading}
          onRowClick={(runId) => navigate(`/admin/agent-runs/${runId}`)}
          onPageChange={setOffset}
        />
      </section>
      </div>
    </div>
  );
};

export default UsageMePage;
