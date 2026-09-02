// eval-hub: 평가 실행 탭 — 목록(상태 폴링)·실행 생성·상세
import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useDeleteEvalRun, useEvalRuns } from '@/hooks/useEval';
import type { EvalRunStatus, EvalTargetType } from '@/types/eval';
import CreateRunModal, { type RunPrefill } from './CreateRunModal';
import RunDetailPanel from './RunDetailPanel';
// agent-model-benchmark: 모델 스윕
import CreateSweepModal from './CreateSweepModal';
import SweepMatrixPanel from './SweepMatrixPanel';
import { useSweeps } from '@/hooks/useSweeps';
import { SWEEP_STATUS_BADGE } from '@/types/sweep';
import type { SweepSummary } from '@/types/sweep';

const STATUS_BADGE: Record<EvalRunStatus, { label: string; cls: string }> = {
  pending: { label: '대기', cls: 'bg-zinc-100 text-zinc-500' },
  running: { label: '실행 중', cls: 'bg-blue-50 text-blue-600' },
  completed: { label: '완료', cls: 'bg-emerald-50 text-emerald-600' },
  failed: { label: '실패', cls: 'bg-red-50 text-red-600' },
};

const TARGET_LABEL: Record<EvalTargetType, string> = {
  agent: '에이전트',
  rag: 'RAG',
  retrieval: '검색',
};

const RunsTab = () => {
  const [showCreate, setShowCreate] = useState(false);
  const [prefill, setPrefill] = useState<RunPrefill | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [showSweepCreate, setShowSweepCreate] = useState(false);
  const [selectedSweepId, setSelectedSweepId] = useState<string | null>(null);
  const { data: sweepData } = useSweeps();

  const { data, isLoading } = useEvalRuns();
  const deleteMutation = useDeleteEvalRun();

  const runs = data?.items ?? [];

  const handleRerun = (config: Record<string, unknown>, targetType: string) => {
    setPrefill({
      target_type: targetType as RunPrefill['target_type'],
      testset_id: (config.testset_id as string) ?? undefined,
      agent_id: (config.agent_id as string) ?? undefined,
      collection_name: (config.collection_name as string) ?? undefined,
      metrics: (config.metrics as string[]) ?? undefined,
      llm_model: (config.llm_model as string) ?? undefined,
      top_k: (config.top_k as number) ?? undefined,
      sample_ratio: (config.sample_ratio as number) ?? undefined,
    });
    setShowCreate(true);
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-[13px] text-zinc-500">
          총 <span className="font-medium text-zinc-700">{data?.total ?? 0}</span>건의 평가 실행
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSweepCreate(true)}
            className="rounded-xl border border-zinc-200 px-3.5 py-2 text-[13px] font-medium text-zinc-700 hover:border-violet-300 hover:text-violet-600"
          >
            + 모델 스윕
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="rounded-xl bg-zinc-900 px-3.5 py-2 text-[13px] font-medium text-white hover:bg-zinc-800"
          >
            + 평가 실행
          </button>
        </div>
      </div>

      {/* agent-model-benchmark: 모델 스윕 목록 + 매트릭스 */}
      <SweepSection
        sweeps={sweepData?.items ?? []}
        selectedSweepId={selectedSweepId}
        onSelect={setSelectedSweepId}
      />

      {isLoading && (
        <p className="py-16 text-center text-[13px] text-zinc-400">불러오는 중...</p>
      )}

      {!isLoading && runs.length === 0 && (
        <div className="flex flex-col items-center py-24">
          <p className="text-[13.5px] text-zinc-500">아직 평가 실행이 없습니다.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 rounded-xl border border-zinc-200 px-4 py-2 text-[13px] text-zinc-600 hover:border-violet-300 hover:text-violet-600"
          >
            + 데이터셋을 선택해 첫 평가를 실행하세요.
          </button>
        </div>
      )}

      {runs.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-zinc-200">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50 text-[11.5px] uppercase tracking-widest text-zinc-400">
                <th className="px-4 py-2.5">상태</th>
                <th className="px-4 py-2.5">대상</th>
                <th className="px-4 py-2.5">케이스</th>
                <th className="px-4 py-2.5">시작</th>
                <th className="px-4 py-2.5">평균 점수</th>
                <th className="w-16 px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-50">
              {runs.map((run) => {
                const badge = STATUS_BADGE[run.status];
                const scores = Object.values(run.summary);
                const avg =
                  scores.length > 0
                    ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(3)
                    : '—';
                return (
                  <tr
                    key={run.id}
                    className={`cursor-pointer hover:bg-violet-50/30 ${
                      selectedRunId === run.id ? 'bg-violet-50/40' : ''
                    }`}
                    onClick={() =>
                      setSelectedRunId(selectedRunId === run.id ? null : run.id)
                    }
                  >
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-[11.5px] font-medium ${badge.cls}`}>
                        {badge.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[13px] text-zinc-700">
                      {TARGET_LABEL[run.target_type]}
                    </td>
                    <td className="px-4 py-3 text-[13px] text-zinc-500">{run.total_cases}</td>
                    <td className="px-4 py-3 text-[12.5px] text-zinc-500">
                      {new Date(run.created_at).toLocaleString('ko-KR')}
                    </td>
                    <td className="px-4 py-3 text-[13px] font-medium text-zinc-700">{avg}</td>
                    <td className="px-4 py-3">
                      <LoadingButton
                        isPending={
                          deleteMutation.isPending && deleteMutation.variables === run.id
                        }
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteMutation.mutate(run.id, {
                            onSuccess: () => {
                              if (selectedRunId === run.id) setSelectedRunId(null);
                            },
                          });
                        }}
                        aria-label="실행 삭제"
                        className="rounded-lg px-2 py-1 text-[12px] text-zinc-400 hover:bg-red-50 hover:text-red-500"
                      >
                        삭제
                      </LoadingButton>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedRunId && (
        <RunDetailPanel runId={selectedRunId} onRerun={handleRerun} />
      )}

      {showCreate && (
        <CreateRunModal
          prefill={prefill}
          onClose={() => {
            setShowCreate(false);
            setPrefill(null);
          }}
        />
      )}

      {showSweepCreate && (
        <CreateSweepModal
          onClose={() => setShowSweepCreate(false)}
          onCreated={setSelectedSweepId}
        />
      )}
    </div>
  );
};

// agent-model-benchmark Design §5.1: 스윕 목록 + 선택 시 매트릭스.
// 스윕이 없으면 아무것도 렌더하지 않는다 — 기존 평가 실행 화면을 가리지 않기 위함.
interface SweepSectionProps {
  sweeps: SweepSummary[];
  selectedSweepId: string | null;
  onSelect: (sweepId: string | null) => void;
}

const SweepSection = ({
  sweeps,
  selectedSweepId,
  onSelect,
}: SweepSectionProps) => {
  if (sweeps.length === 0) return null;

  return (
    <section className="mb-6" data-testid="sweep-section">
      <h3 className="mb-2 text-[13px] font-medium text-zinc-700">모델 스윕</h3>
      <div className="space-y-2">
        {sweeps.map((sw) => {
          const badge = SWEEP_STATUS_BADGE[sw.status];
          const selected = sw.id === selectedSweepId;
          return (
            <button
              key={sw.id}
              type="button"
              onClick={() => onSelect(selected ? null : sw.id)}
              className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left ${
                selected
                  ? 'border-violet-300 bg-violet-50/30'
                  : 'border-zinc-200 hover:border-violet-200'
              }`}
            >
              <span className="text-[13.5px] font-medium text-zinc-800">
                {sw.name}
              </span>
              <span className="flex items-center gap-2">
                <span className="text-[12px] text-zinc-400">
                  {sw.completed_runs}/{sw.total_runs}
                </span>
                <span
                  className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}
                >
                  {badge.label}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {selectedSweepId && (
        <div className="mt-3">
          <SweepMatrixPanel
            sweepId={selectedSweepId}
            onClose={() => onSelect(null)}
          />
        </div>
      )}
    </section>
  );
};

export default RunsTab;
