import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PeriodFilter, {
  resolvePeriod,
  type PeriodValue,
} from '@/components/common/PeriodFilter';
import {
  useAdminRuns,
  useAdminUsageSummary,
  useAdminUsageTimeseries,
} from '@/hooks/useAgentRunAdmin';
import {
  useDashboardRefresh,
  useDashboardStats,
  useKbBreakdown,
  useRecentDocuments,
  useStorageHealth,
} from '@/hooks/useAdminDashboard';
import SummaryCards from '@/pages/AdminAgentRunsPage/components/SummaryCards';
import TimeseriesChart from '@/pages/AdminAgentRunsPage/components/TimeseriesChart';
import StatCardsRow from './components/StatCardsRow';
import HealthBadges from './components/HealthBadges';
import KbBreakdownTable from './components/KbBreakdownTable';
import RecentDocumentsTable from './components/RecentDocumentsTable';
import RecentRunsPanel from './components/RecentRunsPanel';

const initialPeriod: PeriodValue = (() => {
  const r = resolvePeriod('30d');
  return { preset: '30d', from: r.from, to: r.to };
})();

const AdminDashboardPage = () => {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<PeriodValue>(initialPeriod);
  const refresh = useDashboardRefresh();

  const periodParams = useMemo(
    () => ({ from: period.from, to: period.to }),
    [period.from, period.to],
  );

  // 누적 현황 + 헬스 (기간 무관 — 신규 API)
  const statsQ = useDashboardStats();
  const healthQ = useStorageHealth();
  const kbQ = useKbBreakdown();
  const docsQ = useRecentDocuments(10);

  // 기간 지표 (기존 usage API 재사용 — D1)
  const summaryQ = useAdminUsageSummary(periodParams);
  const tsQ = useAdminUsageTimeseries(periodParams);
  const recentRunsQ = useAdminRuns({ ...periodParams, limit: 5 });
  const failedRunsQ = useAdminRuns({
    ...periodParams,
    status: 'FAILED',
    limit: 5,
  });

  return (
    <div className="flex flex-col gap-5 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">운영 대시보드</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            문서 적재량·질문 사용량·비용·저장소 상태 통합 현황
          </p>
        </div>
        <div className="flex items-center gap-2">
          <PeriodFilter value={period} onChange={setPeriod} />
          <button
            type="button"
            onClick={refresh}
            className="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-600 transition hover:bg-zinc-50"
          >
            새로고침
          </button>
        </div>
      </header>

      <HealthBadges
        components={healthQ.data?.components}
        loading={healthQ.isLoading}
      />

      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          적재 현황 (누적)
        </h2>
        <StatCardsRow stats={statsQ.data} loading={statsQ.isLoading} />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          질문 사용량 (선택 기간)
        </h2>
        <SummaryCards
          totalRuns={summaryQ.data?.total_runs}
          successRate={summaryQ.data?.success_rate}
          totalTokens={summaryQ.data?.total_tokens}
          totalCostUsd={summaryQ.data?.total_cost_usd}
          loading={summaryQ.isLoading}
        />
      </section>

      <TimeseriesChart points={tsQ.data?.points} loading={tsQ.isLoading} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="flex flex-col gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            KB별 현황
          </h2>
          <KbBreakdownTable rows={kbQ.data?.rows} loading={kbQ.isLoading} />
        </section>
        <section className="flex flex-col gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            최근 업로드
          </h2>
          <RecentDocumentsTable
            rows={docsQ.data?.rows}
            loading={docsQ.isLoading}
          />
        </section>
      </div>

      <RecentRunsPanel
        recentRows={recentRunsQ.data?.rows}
        failedRows={failedRunsQ.data?.rows}
        loading={recentRunsQ.isLoading || failedRunsQ.isLoading}
        onRowClick={(runId) => navigate(`/admin/agent-runs/${runId}`)}
      />
    </div>
  );
};

export default AdminDashboardPage;
