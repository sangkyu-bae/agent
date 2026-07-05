import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Dropdown from '@/components/common/Dropdown';
import PeriodFilter, {
  resolvePeriod,
  type PeriodValue,
} from '@/components/common/PeriodFilter';
import {
  useAdminRuns,
  useAdminUsageSummary,
  useAdminUsageTimeseries,
  useUsageByLlm,
  useUsageByNode,
  useUsageByUser,
} from '@/hooks/useAgentRunAdmin';
import type { RunStatus } from '@/types/agentRunAdmin';
import SummaryCards from './components/SummaryCards';
import TimeseriesChart from './components/TimeseriesChart';
import RunListTable from './components/RunListTable';
import {
  UsageByLlmTab,
  UsageByNodeTab,
  UsageByUserTab,
} from './components/UsageTabs';

type Tab = 'user' | 'llm' | 'node' | 'runs';

const TAB_LABELS: Record<Tab, string> = {
  user: '사용자별',
  llm: 'LLM별',
  node: '노드별',
  runs: 'Run 목록',
};

const STATUS_OPTIONS: Array<{ value: '' | RunStatus; label: string }> = [
  { value: '', label: '전체' },
  { value: 'RUNNING', label: 'RUNNING' },
  { value: 'SUCCESS', label: 'SUCCESS' },
  { value: 'FAILED', label: 'FAILED' },
  { value: 'CANCELLED', label: 'CANCELLED' },
];

const initialPeriod: PeriodValue = (() => {
  const r = resolvePeriod('30d');
  return { preset: '30d', from: r.from, to: r.to };
})();

const AdminAgentRunsPage = () => {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<PeriodValue>(initialPeriod);
  const [tab, setTab] = useState<Tab>('runs');
  const [statusFilter, setStatusFilter] = useState<'' | RunStatus>('');
  const [userIdFilter, setUserIdFilter] = useState('');
  const [agentIdFilter, setAgentIdFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const LIMIT = 20;

  const periodParams = useMemo(
    () => ({ from: period.from, to: period.to }),
    [period.from, period.to],
  );

  const summaryQ = useAdminUsageSummary(periodParams);
  const tsQ = useAdminUsageTimeseries(periodParams);
  const byUserQ = useUsageByUser(periodParams);
  const byLlmQ = useUsageByLlm(periodParams);
  const byNodeQ = useUsageByNode(periodParams);

  const runsParams = useMemo(
    () => ({
      ...periodParams,
      status: statusFilter || undefined,
      user_id: userIdFilter || undefined,
      agent_id: agentIdFilter || undefined,
      limit: LIMIT,
      offset,
    }),
    [periodParams, statusFilter, userIdFilter, agentIdFilter, offset],
  );
  const runsQ = useAdminRuns(runsParams);

  const handlePeriod = (next: PeriodValue) => {
    setPeriod(next);
    setOffset(0);
  };

  return (
    <div className="flex flex-col gap-5 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Agent Run 관측성</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            관리자 전용 — LLM 비용·토큰·실행 상태 통합 대시보드
          </p>
        </div>
        <PeriodFilter value={period} onChange={handlePeriod} />
      </header>

      <SummaryCards
        totalRuns={summaryQ.data?.total_runs}
        successRate={summaryQ.data?.success_rate}
        totalTokens={summaryQ.data?.total_tokens}
        totalCostUsd={summaryQ.data?.total_cost_usd}
        loading={summaryQ.isLoading}
      />

      <TimeseriesChart points={tsQ.data?.points} loading={tsQ.isLoading} />

      {/* 탭 */}
      <div className="flex items-center gap-1 border-b border-zinc-200">
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => {
          const active = tab === t;
          return (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={[
                'border-b-2 px-4 py-2 text-sm font-medium transition',
                active
                  ? 'border-violet-600 text-violet-700'
                  : 'border-transparent text-zinc-500 hover:text-zinc-700',
              ].join(' ')}
            >
              {TAB_LABELS[t]}
            </button>
          );
        })}
      </div>

      {/* 탭 콘텐츠 */}
      {tab === 'user' && (
        <UsageByUserTab data={byUserQ.data} loading={byUserQ.isLoading} />
      )}
      {tab === 'llm' && (
        <UsageByLlmTab data={byLlmQ.data} loading={byLlmQ.isLoading} />
      )}
      {tab === 'node' && (
        <UsageByNodeTab data={byNodeQ.data} loading={byNodeQ.isLoading} />
      )}
      {tab === 'runs' && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <input
              type="text"
              placeholder="user_id"
              value={userIdFilter}
              onChange={(e) => {
                setUserIdFilter(e.target.value);
                setOffset(0);
              }}
              className="rounded-md border border-zinc-200 px-2 py-1"
            />
            <input
              type="text"
              placeholder="agent_id"
              value={agentIdFilter}
              onChange={(e) => {
                setAgentIdFilter(e.target.value);
                setOffset(0);
              }}
              className="rounded-md border border-zinc-200 px-2 py-1"
            />
            <Dropdown
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v as '' | RunStatus);
                setOffset(0);
              }}
              options={STATUS_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              className="w-40"
            />
          </div>
          <RunListTable
            data={runsQ.data}
            loading={runsQ.isLoading}
            onRowClick={(runId) => navigate(`/admin/agent-runs/${runId}`)}
            onPageChange={setOffset}
          />
        </div>
      )}
    </div>
  );
};

export default AdminAgentRunsPage;
