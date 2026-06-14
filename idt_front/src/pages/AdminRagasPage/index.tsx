import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminRagasService } from '@/services/adminRagasService';
import { queryKeys } from '@/lib/queryKeys';
import type { AdminRagasRunsParams, EvalRunDetail } from '@/types/adminRagas';

const STATUS_LABELS: Record<string, string> = {
  pending: '대기',
  running: '실행 중',
  completed: '완료',
  failed: '실패',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-zinc-100 text-zinc-600',
  running: 'bg-blue-50 text-blue-600',
  completed: 'bg-emerald-50 text-emerald-600',
  failed: 'bg-red-50 text-red-600',
};

const TARGET_LABELS: Record<string, string> = {
  rag: 'RAG',
  agent: 'Agent',
  retrieval: 'Retrieval',
};

function scoreColor(score: number): string {
  if (score >= 0.8) return 'text-emerald-600';
  if (score >= 0.5) return 'text-amber-600';
  return 'text-red-600';
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatScore(score: number): string {
  return (score * 100).toFixed(1) + '%';
}

const AdminRagasPage = () => {
  const [filters, setFilters] = useState<AdminRagasRunsParams>({
    limit: 20,
    offset: 0,
  });
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const { data: dashboard, isLoading: isDashboardLoading } = useQuery({
    queryKey: queryKeys.admin.ragasDashboard(),
    queryFn: () => adminRagasService.getDashboard(),
  });

  const { data: runsData, isLoading: isRunsLoading } = useQuery({
    queryKey: queryKeys.admin.ragasRuns(filters),
    queryFn: () => adminRagasService.getRuns(filters),
  });

  const { data: runDetail, isLoading: isDetailLoading } = useQuery({
    queryKey: queryKeys.admin.ragasRunDetail(selectedRunId ?? ''),
    queryFn: () => adminRagasService.getRunDetail(selectedRunId!),
    enabled: !!selectedRunId,
  });

  const handleFilterChange = (key: keyof AdminRagasRunsParams, value: string) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value || undefined,
      offset: 0,
    }));
  };

  const handlePageChange = (newOffset: number) => {
    setFilters((prev) => ({ ...prev, offset: newOffset }));
  };

  const totalPages = runsData ? Math.ceil(runsData.total / (filters.limit ?? 20)) : 0;
  const currentPage = Math.floor((filters.offset ?? 0) / (filters.limit ?? 20)) + 1;

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      {/* Header */}
      <div className="mb-6">
        <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
          Admin
        </p>
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">RAGAS 평가</h1>
        <p className="mt-1 text-[13px] text-zinc-400">
          RAG 시스템 평가 결과를 확인하고 품질을 모니터링합니다.
        </p>
      </div>

      {/* Stats Cards */}
      {isDashboardLoading ? (
        <div className="mb-8 grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-2xl bg-zinc-100" />
          ))}
        </div>
      ) : dashboard ? (
        <div className="mb-8 grid grid-cols-4 gap-4">
          <StatCard
            label="총 평가 실행"
            value={dashboard.total_runs}
            sub={`완료 ${dashboard.status_counts.completed ?? 0} / 실패 ${dashboard.status_counts.failed ?? 0}`}
            color="violet"
          />
          <StatCard
            label="완료율"
            value={
              dashboard.total_runs > 0
                ? `${(((dashboard.status_counts.completed ?? 0) / dashboard.total_runs) * 100).toFixed(0)}%`
                : '-'
            }
            sub={`${dashboard.status_counts.pending ?? 0}건 대기 중`}
            color="emerald"
          />
          <StatCard
            label="평균 Faithfulness"
            value={
              dashboard.avg_metrics.faithfulness != null
                ? formatScore(dashboard.avg_metrics.faithfulness)
                : '-'
            }
            sub="답변 충실도"
            color="blue"
          />
          <StatCard
            label="평균 Answer Relevancy"
            value={
              dashboard.avg_metrics.answer_relevancy != null
                ? formatScore(dashboard.avg_metrics.answer_relevancy)
                : '-'
            }
            sub="답변 관련성"
            color="amber"
          />
        </div>
      ) : null}

      {/* Filters */}
      <div className="mb-4 flex items-center gap-3">
        <select
          value={filters.target_type ?? ''}
          onChange={(e) => handleFilterChange('target_type', e.target.value)}
          className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] text-zinc-700 outline-none focus:border-violet-300"
        >
          <option value="">전체 대상</option>
          <option value="rag">RAG</option>
          <option value="agent">Agent</option>
          <option value="retrieval">Retrieval</option>
        </select>
        <select
          value={filters.eval_type ?? ''}
          onChange={(e) => handleFilterChange('eval_type', e.target.value)}
          className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] text-zinc-700 outline-none focus:border-violet-300"
        >
          <option value="">전체 유형</option>
          <option value="batch">Batch</option>
          <option value="realtime">Realtime</option>
        </select>
        <select
          value={filters.status ?? ''}
          onChange={(e) => handleFilterChange('status', e.target.value)}
          className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] text-zinc-700 outline-none focus:border-violet-300"
        >
          <option value="">전체 상태</option>
          <option value="completed">완료</option>
          <option value="running">실행 중</option>
          <option value="pending">대기</option>
          <option value="failed">실패</option>
        </select>
        {runsData && (
          <span className="ml-auto text-[12px] text-zinc-400">
            총 {runsData.total}건
          </span>
        )}
      </div>

      {/* Runs Table */}
      {isRunsLoading ? (
        <div className="flex h-48 items-center justify-center text-zinc-400">로딩 중...</div>
      ) : !runsData || runsData.items.length === 0 ? (
        <div className="flex h-48 items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-50 text-[14px] text-zinc-400">
          평가 실행 데이터가 없습니다.
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-100 bg-zinc-50">
                  <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                    유형
                  </th>
                  <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                    대상
                  </th>
                  <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                    상태
                  </th>
                  <th className="px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                    케이스
                  </th>
                  <th className="px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                    평균 점수
                  </th>
                  <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                    실행일
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {runsData.items.map((run) => {
                  const avgScore =
                    Object.values(run.summary).length > 0
                      ? Object.values(run.summary).reduce((a, b) => a + b, 0) /
                        Object.values(run.summary).length
                      : null;
                  const isSelected = selectedRunId === run.id;

                  return (
                    <tr
                      key={run.id}
                      onClick={() => setSelectedRunId(isSelected ? null : run.id)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-violet-50' : 'hover:bg-zinc-50/50'
                      }`}
                    >
                      <td className="px-5 py-4 text-[13px] font-medium text-zinc-700">
                        {run.eval_type}
                      </td>
                      <td className="px-5 py-4">
                        <span className="inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-0.5 text-[11px] font-medium text-zinc-600">
                          {TARGET_LABELS[run.target_type] ?? run.target_type}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${STATUS_COLORS[run.status] ?? ''}`}
                        >
                          {STATUS_LABELS[run.status] ?? run.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-right text-[13px] text-zinc-600">
                        {run.total_cases}
                      </td>
                      <td className="px-5 py-4 text-right">
                        {avgScore != null ? (
                          <span className={`text-[13px] font-semibold ${scoreColor(avgScore)}`}>
                            {formatScore(avgScore)}
                          </span>
                        ) : (
                          <span className="text-[13px] text-zinc-300">-</span>
                        )}
                      </td>
                      <td className="px-5 py-4 text-[13px] text-zinc-400">
                        {formatDate(run.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <button
                onClick={() => handlePageChange(Math.max(0, (filters.offset ?? 0) - (filters.limit ?? 20)))}
                disabled={currentPage <= 1}
                className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[12px] text-zinc-500 transition-all hover:bg-zinc-50 disabled:opacity-30"
              >
                이전
              </button>
              <span className="text-[12px] text-zinc-400">
                {currentPage} / {totalPages}
              </span>
              <button
                onClick={() => handlePageChange((filters.offset ?? 0) + (filters.limit ?? 20))}
                disabled={currentPage >= totalPages}
                className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[12px] text-zinc-500 transition-all hover:bg-zinc-50 disabled:opacity-30"
              >
                다음
              </button>
            </div>
          )}
        </>
      )}

      {/* Run Detail Panel */}
      {selectedRunId && (
        <RunDetailPanel detail={runDetail ?? null} isLoading={isDetailLoading} />
      )}
    </div>
  );
};

// ── Sub Components ─────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number;
  sub: string;
  color: 'violet' | 'emerald' | 'blue' | 'amber';
}) {
  const borderColors = {
    violet: 'border-l-violet-500',
    emerald: 'border-l-emerald-500',
    blue: 'border-l-blue-500',
    amber: 'border-l-amber-500',
  };

  return (
    <div
      className={`rounded-2xl border border-zinc-200 border-l-4 bg-white px-5 py-4 shadow-sm ${borderColors[color]}`}
    >
      <p className="text-[11.5px] font-medium text-zinc-400">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight text-zinc-900">{value}</p>
      <p className="mt-0.5 text-[11.5px] text-zinc-400">{sub}</p>
    </div>
  );
}

function RunDetailPanel({
  detail,
  isLoading,
}: {
  detail: EvalRunDetail | null;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="mt-6 flex h-32 items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-400">
        상세 정보 로딩 중...
      </div>
    );
  }

  if (!detail) return null;

  return (
    <div className="mt-6 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
      {/* Header */}
      <div className="border-b border-zinc-100 bg-zinc-50 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-[15px] font-semibold text-zinc-900">
              평가 상세 — {detail.eval_type} / {TARGET_LABELS[detail.target_type] ?? detail.target_type}
            </h3>
            <p className="mt-0.5 text-[12px] text-zinc-400">
              {formatDate(detail.created_at)} | {detail.total_cases}개 케이스 | {detail.results_total}개 결과
            </p>
          </div>
          {Object.keys(detail.summary).length > 0 && (
            <div className="flex gap-4">
              {Object.entries(detail.summary).map(([key, val]) => (
                <div key={key} className="text-right">
                  <p className="text-[10.5px] font-medium uppercase tracking-wider text-zinc-400">
                    {key}
                  </p>
                  <p className={`text-[16px] font-bold ${scoreColor(val)}`}>
                    {formatScore(val)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Results Table */}
      {detail.results.length > 0 && (
        <div className="max-h-[400px] overflow-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-zinc-100">
                <th className="w-12 px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                  #
                </th>
                <th className="w-2/5 px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                  질문
                </th>
                <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                  답변
                </th>
                {Object.keys(detail.results[0]?.scores ?? {}).map((metric) => (
                  <th
                    key={metric}
                    className="px-4 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wider text-zinc-400"
                  >
                    {metric}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-50">
              {detail.results.map((r, idx) => (
                <tr key={r.id} className="transition-colors hover:bg-zinc-50/50">
                  <td className="px-4 py-3 align-top text-[12px] font-medium text-zinc-400">
                    {idx + 1}
                  </td>
                  <td className="px-4 py-3 align-top text-[13px] leading-relaxed text-zinc-800">
                    {r.question}
                  </td>
                  <td className="px-4 py-3 align-top text-[13px] leading-relaxed text-zinc-600">
                    {r.answer.length > 120 ? r.answer.slice(0, 120) + '...' : r.answer}
                  </td>
                  {Object.entries(r.scores).map(([metric, val]) => (
                    <td
                      key={metric}
                      className={`px-4 py-3 text-right align-top text-[13px] font-semibold ${scoreColor(val)}`}
                    >
                      {formatScore(val)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default AdminRagasPage;
