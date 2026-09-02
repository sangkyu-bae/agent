// agent-model-benchmark Design §5.1/§5.4: 행=모델 / 열=지표 매트릭스.
// 핵심 계약 2가지:
//   1) null은 "측정 불가(N/A)"라 반드시 "—"로 렌더한다. 0으로 표시하면 성능이
//      0점인 모델과 구분이 안 돼 의사결정을 망친다 (Design §3.5 / G6).
//   2) judge 모델은 항상 병기한다 — judge가 다르면 점수를 비교할 수 없다 (Plan R-2).
import { useSweepDetail } from '@/hooks/useSweeps';
import { useLlmModels } from '@/hooks/useLlmModels';
import {
  SWEEP_AVAILABLE_METRICS,
  SWEEP_LOWER_IS_BETTER,
  SWEEP_STATUS_BADGE,
} from '@/types/sweep';
import type { SweepRow } from '@/types/sweep';

const NA = '—';

interface Column {
  key: string;
  label: string;
  value: (row: SweepRow) => number | null;
  format: (v: number) => string;
}

const metricLabel = (key: string) =>
  SWEEP_AVAILABLE_METRICS.find((m) => m.key === key)?.label ?? key;

const buildColumns = (metrics: string[]): Column[] => [
  ...metrics.map((key) => ({
    key,
    label: metricLabel(key),
    value: (row: SweepRow) => row.quality?.[key] ?? null,
    format: (v: number) => v.toFixed(3),
  })),
  {
    key: 'cost_usd',
    label: '비용',
    value: (row: SweepRow) => (row.cost_usd == null ? null : Number(row.cost_usd)),
    format: (v: number) => `$${v.toFixed(4)}`,
  },
  {
    key: 'latency_p50_ms',
    label: 'p50',
    value: (row: SweepRow) => row.latency_p50_ms,
    format: (v: number) => `${(v / 1000).toFixed(1)}s`,
  },
  {
    key: 'latency_p95_ms',
    label: 'p95',
    value: (row: SweepRow) => row.latency_p95_ms,
    format: (v: number) => `${(v / 1000).toFixed(1)}s`,
  },
  {
    key: 'tool_f1',
    label: '도구 F1',
    value: (row: SweepRow) => row.tool_f1,
    format: (v: number) => v.toFixed(2),
  },
];

/** 지표별 최고값. 유효 표본이 없으면 null — 아무 행도 하이라이트하지 않는다. */
const bestValue = (rows: SweepRow[], col: Column): number | null => {
  const values = rows
    .map((r) => col.value(r))
    .filter((v): v is number => v != null);
  if (values.length === 0) return null;
  const lowerIsBetter = (SWEEP_LOWER_IS_BETTER as readonly string[]).includes(
    col.key,
  );
  return lowerIsBetter ? Math.min(...values) : Math.max(...values);
};

/** 추정 대비 실제 비용 오차율(%). 어느 한쪽이라도 없거나 추정이 0이면 null. */
const deltaPercent = (
  estimated: string | null,
  actual: string | null,
): number | null => {
  if (estimated == null || actual == null) return null;
  const est = Number(estimated);
  if (!Number.isFinite(est) || est === 0) return null;
  return ((Number(actual) - est) / est) * 100;
};

interface Props {
  sweepId: string;
  onClose: () => void;
}

const SweepMatrixPanel = ({ sweepId, onClose }: Props) => {
  const { data: sweep, isLoading } = useSweepDetail(sweepId);
  const { data: models } = useLlmModels(true);

  if (isLoading || !sweep) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-6 text-[13px] text-zinc-400">
        스윕을 불러오는 중…
      </div>
    );
  }

  const columns = buildColumns(sweep.metrics);
  const bests = new Map(columns.map((c) => [c.key, bestValue(sweep.rows, c)]));
  const judgeName =
    models?.find((m) => m.id === sweep.judge_llm_model_id)?.display_name ??
    sweep.judge_llm_model_id ??
    NA;
  const badge = SWEEP_STATUS_BADGE[sweep.status];
  // 추정 대비 실제 오차율 — Plan NFR은 ±30% 이내를 요구한다. 벗어나면 강조한다.
  const costDelta = deltaPercent(sweep.estimated_cost_usd, sweep.actual_cost_usd);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white">
      <div className="flex items-start justify-between border-b border-zinc-100 px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-[15px] font-semibold text-zinc-900">{sweep.name}</h3>
            <span
              className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}
            >
              {badge.label}
            </span>
            <span className="text-[12px] text-zinc-400">
              {sweep.completed_runs}/{sweep.total_runs}
            </span>
          </div>
          {/* 실험 조건 — 무엇을 무엇으로 쟀는지 (G-2) */}
          <div className="mt-1 text-[12px] text-zinc-500" data-testid="sweep-conditions">
            <span>{sweep.agent_name ?? sweep.agent_id}</span>
            <span className="mx-1.5">·</span>
            <span>
              {sweep.testset_name ?? sweep.testset_id} ({sweep.case_count}건)
            </span>
          </div>
          <div className="mt-0.5 text-[12px] text-zinc-500">
            {/* judge 병기 — 이게 없으면 서로 다른 judge의 점수를 같은 표에서 비교하게 된다 */}
            <span data-testid="sweep-judge">judge: {judgeName}</span>
            <span className="mx-1.5">·</span>
            <span>temp {sweep.temperature}</span>
          </div>
          {/* 예상 vs 실제 대조 — 추정 정확도를 눈으로 확인하는 유일한 지점 (G-1) */}
          <div className="mt-1 text-[12px]" data-testid="sweep-cost">
            <span className="text-zinc-400">예상 ${sweep.estimated_cost_usd ?? NA}</span>
            <span className="mx-1.5 text-zinc-300">→</span>
            <span className="font-medium text-zinc-700">
              실제 {sweep.actual_cost_usd == null ? NA : `$${sweep.actual_cost_usd}`}
            </span>
            {costDelta !== null && (
              <span
                className={`ml-1.5 ${
                  Math.abs(costDelta) > 30 ? 'text-amber-600' : 'text-zinc-400'
                }`}
              >
                ({costDelta > 0 ? '+' : ''}
                {costDelta.toFixed(0)}%)
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-[13px] text-zinc-400 hover:text-zinc-600"
        >
          닫기
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-zinc-50/60">
            <tr>
              <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                모델
              </th>
              {columns.map((c) => (
                <th
                  key={c.key}
                  className="px-4 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400"
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {sweep.rows.map((row) => (
              <tr key={row.run_id} data-testid={`sweep-row-${row.run_id}`}>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <span className="text-[14px] font-medium text-zinc-900">
                      {row.llm_model_name ?? row.llm_model_id ?? NA}
                    </span>
                    {row.status === 'failed' && (
                      <span
                        className="rounded-md bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-600"
                        title={row.error_message ?? undefined}
                      >
                        실패
                      </span>
                    )}
                  </div>
                  <div className="text-[12px] text-zinc-400">
                    측정 {row.measured_cases}건
                    {row.failed_cases > 0 && ` · 실패 ${row.failed_cases}건`}
                  </div>
                </td>
                {columns.map((c) => {
                  const v = c.value(row);
                  const best = bests.get(c.key);
                  const isBest = v != null && best != null && v === best;
                  return (
                    <td
                      key={c.key}
                      data-testid={`cell-${row.run_id}-${c.key}`}
                      className={`px-4 py-4 text-right text-[13px] tabular-nums ${
                        isBest
                          ? 'font-semibold text-violet-600'
                          : 'text-zinc-700'
                      }`}
                    >
                      {v == null ? NA : c.format(v)}
                      {isBest && <span aria-hidden="true"> ★</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="border-t border-zinc-100 px-5 py-3 text-[12px] text-zinc-400">
        ★ 지표별 최고값 · {NA} 측정 불가(N/A)
      </p>
    </div>
  );
};

export default SweepMatrixPanel;
