// eval-hub: 평가기 탭 — RAGAS 메트릭 카탈로그 읽기전용 (커스텀 평가기는 후속)
import { useEvalMetrics } from '@/hooks/useEval';
import type { EvalTargetType } from '@/types/eval';

const TARGET_LABEL: Record<EvalTargetType, string> = {
  agent: '에이전트',
  rag: 'RAG',
  retrieval: '검색',
};

const EvaluatorsTab = () => {
  const { data: metrics, isLoading } = useEvalMetrics();

  return (
    <div className="mx-auto max-w-5xl px-6 py-5">
      <p className="mb-4 text-[13px] text-zinc-500">
        평가 실행에서 사용할 수 있는 내장 평가기(메트릭) 목록입니다. 커스텀 평가기 등록은 추후 지원됩니다.
      </p>

      {isLoading && (
        <p className="py-16 text-center text-[13px] text-zinc-400">불러오는 중...</p>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {(metrics ?? []).map((m) => (
          <div key={m.key} className="rounded-2xl border border-zinc-200 p-4">
            <div className="mb-1.5 flex items-center justify-between">
              <p className="text-[13.5px] font-semibold text-zinc-800">{m.name}</p>
              {m.requires_ground_truth && (
                <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10.5px] text-amber-600">
                  정답 필요
                </span>
              )}
            </div>
            <p className="mb-2.5 text-[12.5px] leading-relaxed text-zinc-500">
              {m.description}
            </p>
            <div className="flex gap-1.5">
              {m.target_types.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-500"
                >
                  {TARGET_LABEL[t]}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EvaluatorsTab;
