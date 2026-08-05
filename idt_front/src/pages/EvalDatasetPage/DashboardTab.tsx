// eval-hub: 대시보드 탭 (admin 전용) — 기존 adminRagasService 재사용
import { useAdminRagasDashboard } from '@/hooks/useEval';
import { useAuthStore } from '@/store/authStore';

const DashboardTab = () => {
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin');
  const { data, isLoading } = useAdminRagasDashboard(isAdmin);

  if (!isAdmin) return null;

  if (isLoading) {
    return (
      <p className="py-16 text-center text-[13px] text-zinc-400">불러오는 중...</p>
    );
  }
  if (!data) return null;

  return (
    <div className="mx-auto max-w-5xl px-6 py-5">
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-2xl border border-zinc-200 p-4">
          <p className="text-[11.5px] uppercase tracking-widest text-zinc-400">총 실행</p>
          <p className="mt-1 text-[22px] font-semibold text-zinc-900">{data.total_runs}</p>
        </div>
        {Object.entries(data.status_counts).map(([status, count]) => (
          <div key={status} className="rounded-2xl border border-zinc-200 p-4">
            <p className="text-[11.5px] uppercase tracking-widest text-zinc-400">{status}</p>
            <p className="mt-1 text-[22px] font-semibold text-zinc-900">{count}</p>
          </div>
        ))}
      </div>

      {Object.keys(data.target_type_counts).length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] text-zinc-500">대상 유형 분포:</span>
          {Object.entries(data.target_type_counts).map(([target, count]) => (
            <span
              key={target}
              className="rounded-full bg-zinc-100 px-2.5 py-1 text-[12px] text-zinc-600"
            >
              {target} · {count}건
            </span>
          ))}
        </div>
      )}

      {Object.keys(data.avg_metrics).length > 0 && (
        <div className="mb-4 rounded-2xl border border-zinc-200 p-4">
          <p className="mb-3 text-[13px] font-semibold text-zinc-800">평균 메트릭</p>
          <div className="space-y-2">
            {Object.entries(data.avg_metrics).map(([metric, score]) => (
              <div key={metric} className="flex items-center gap-3">
                <span className="w-40 shrink-0 text-[12.5px] text-zinc-500">{metric}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-100">
                  <div
                    className="h-full rounded-full bg-violet-500"
                    style={{ width: `${Math.min(100, score * 100)}%` }}
                  />
                </div>
                <span className="w-12 text-right text-[12.5px] font-medium text-zinc-700">
                  {score.toFixed(3)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-zinc-200 p-4">
        <p className="mb-3 text-[13px] font-semibold text-zinc-800">최근 실행</p>
        {data.recent_runs.length === 0 ? (
          <p className="py-6 text-center text-[12.5px] text-zinc-400">실행 이력이 없습니다.</p>
        ) : (
          <div className="divide-y divide-zinc-50">
            {data.recent_runs.map((run) => (
              <div key={run.id} className="flex items-center justify-between py-2.5">
                <div className="text-[12.5px] text-zinc-600">
                  <span className="font-medium text-zinc-800">{run.target_type}</span>
                  {' · '}{run.total_cases}케이스{' · '}
                  {new Date(run.created_at).toLocaleString('ko-KR')}
                </div>
                <span className="text-[12px] text-zinc-400">{run.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DashboardTab;
