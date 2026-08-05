// eval-hub: 평가 실행 상세 — 요약 점수·error_message 표면화·케이스별 결과
import { useState } from 'react';
import { useEvalRunDetail, useEvalRunResults } from '@/hooks/useEval';

const PAGE_SIZE = 10;

interface RunDetailPanelProps {
  runId: string;
  /** failed run 재실행 — run.config를 실행 폼에 프리필 (G-02) */
  onRerun?: (config: Record<string, unknown>, targetType: string) => void;
}

const RunDetailPanel = ({ runId, onRerun }: RunDetailPanelProps) => {
  const [page, setPage] = useState(0);
  const { data: run } = useEvalRunDetail(runId);
  const { data: results } = useEvalRunResults(runId, {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  if (!run) return null;

  const totalPages = Math.ceil((results?.total ?? 0) / PAGE_SIZE);

  return (
    <div className="mt-4 rounded-2xl border border-zinc-200 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="text-[13px] font-semibold text-zinc-800">실행 상세</span>
        <span className="text-[12px] text-zinc-400">
          {run.total_cases}케이스 · {new Date(run.created_at).toLocaleString('ko-KR')}
        </span>
      </div>

      {run.status === 'failed' && run.error_message && (
        <div className="mb-3 flex items-start justify-between gap-3 rounded-lg bg-red-50 px-3 py-2">
          <p role="alert" className="text-[12.5px] text-red-600">
            실행 실패: {run.error_message}
          </p>
          {onRerun && (
            <button
              onClick={() => onRerun(run.config, run.target_type)}
              className="shrink-0 rounded-lg border border-red-200 px-2.5 py-1 text-[12px] font-medium text-red-600 hover:bg-red-100"
            >
              동일 조건 재실행
            </button>
          )}
        </div>
      )}

      {Object.keys(run.summary).length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {Object.entries(run.summary).map(([metric, score]) => (
            <div
              key={metric}
              className="rounded-xl border border-zinc-100 bg-zinc-50 px-3 py-2"
            >
              <p className="text-[11px] uppercase tracking-wider text-zinc-400">{metric}</p>
              <p className="text-[15px] font-semibold text-zinc-800">
                {score.toFixed(3)}
              </p>
            </div>
          ))}
        </div>
      )}

      {(results?.items ?? []).length > 0 && (
        <div className="space-y-2">
          {(results?.items ?? []).map((r) => (
            <details key={r.id} className="rounded-xl border border-zinc-100 px-3 py-2">
              <summary className="cursor-pointer text-[13px] text-zinc-700">
                {r.question}
                <span className="ml-2 text-[11.5px] text-zinc-400">
                  {Object.entries(r.scores)
                    .map(([k, v]) => `${k} ${v.toFixed(2)}`)
                    .join(' · ')}
                </span>
              </summary>
              <div className="mt-2 space-y-1.5 text-[12.5px] leading-relaxed">
                {r.answer && (
                  <p><span className="font-medium text-zinc-600">답변:</span> {r.answer}</p>
                )}
                {r.ground_truth && (
                  <p className="text-zinc-500">
                    <span className="font-medium text-zinc-600">정답:</span> {r.ground_truth}
                  </p>
                )}
                {r.contexts.length > 0 && (
                  <p className="text-zinc-400">검색 컨텍스트 {r.contexts.length}건 사용</p>
                )}
              </div>
            </details>
          ))}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2 text-[12.5px]">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                className="rounded-lg border border-zinc-200 px-2.5 py-1 disabled:opacity-40"
              >
                이전
              </button>
              <span className="text-zinc-500">{page + 1} / {totalPages}</span>
              <button
                disabled={page + 1 >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-lg border border-zinc-200 px-2.5 py-1 disabled:opacity-40"
              >
                다음
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RunDetailPanel;
