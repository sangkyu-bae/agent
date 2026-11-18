// Design Ref: graph-rag-foundation §4.2 stage·§5.1 — 전체 공개 전환은 RAGAS 실행 2건 또는 강제 사유(10자 이상)
import { useState } from 'react';
import { useChangeGraphRagStage } from '@/hooks/useGraphRag';
import { useEvalRuns } from '@/hooks/useEval';
import { GRAPH_RAG_STAGE_LABELS, type GraphRagStage } from '@/types/graphRag';

const MIN_FORCE_REASON = 10;

interface StageChangeDialogProps {
  current: GraphRagStage;
  target: GraphRagStage;
  onClose: () => void;
}

const StageChangeDialog = ({ current, target, onClose }: StageChangeDialogProps) => {
  const toGeneral = target === 'general';
  const { data: runs } = useEvalRuns({ limit: 50 });
  // module-7: 완료된 agent 평가만. 끔/켬은 실행 설정 allow_supplemental 로 나눈다
  const completed = (runs?.items ?? []).filter(
    (r) => r.status === 'completed' && r.target_type === 'agent'
  );
  const graphOnRun = (r: (typeof completed)[number]) => r.config?.allow_supplemental === true;
  const offRuns = completed.filter((r) => !graphOnRun(r));
  const onRuns = completed.filter(graphOnRun);
  const [baseline, setBaseline] = useState('');
  const [graph, setGraph] = useState('');
  const [reason, setReason] = useState('');
  const change = useChangeGraphRagStage();

  const hasEval = !!baseline && !!graph && baseline !== graph;
  const forced = toGeneral && !hasEval;
  const canSubmit = !change.isPending && (!forced || reason.trim().length >= MIN_FORCE_REASON);

  const submit = () =>
    change.mutate(
      {
        to_stage: target,
        eval_baseline_run_id: toGeneral && hasEval ? baseline : null,
        eval_graph_run_id: toGeneral && hasEval ? graph : null,
        force_reason: forced ? reason.trim() : null,
      },
      { onSuccess: onClose }
    );

  const runSelect = (
    label: string,
    value: string,
    set: (v: string) => void,
    options: typeof completed
  ) => (
    <label className="block text-[13px] text-zinc-700">
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(e) => set(e.target.value)}
        className="mt-1 w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-[13px]"
      >
        <option value="">— 선택 안 함 —</option>
        {options.map((r) => (
          <option key={r.id} value={r.id}>
            {r.created_at.slice(0, 16).replace('T', ' ')} · {r.eval_type} · {r.total_cases}건
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="stage-dialog-title"
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
      >
        <h2 id="stage-dialog-title" className="text-[16px] font-semibold text-zinc-900">
          노출 단계 변경
        </h2>
        <p className="mt-2 text-[13px] text-zinc-600">
          {GRAPH_RAG_STAGE_LABELS[current]} → <strong>{GRAPH_RAG_STAGE_LABELS[target]}</strong>
        </p>
        {toGeneral ? (
          <div className="mt-4 space-y-3">
            <p className="text-[12.5px] text-zinc-500">
              전체 공개는 그래프 끄기·켜기 RAGAS 평가 두 건이 근거로 필요합니다. 고르지 않으면
              사유를 남기고 강제로 전환합니다.
            </p>
            {runSelect('기준 평가(그래프 끔)', baseline, setBaseline, offRuns)}
            {runSelect('비교 평가(그래프 켬)', graph, setGraph, onRuns)}
            {forced && (
              <label className="block text-[13px] text-zinc-700">
                강제 전환 사유
                <textarea
                  aria-label="강제 전환 사유"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-[13px]"
                  placeholder={`${MIN_FORCE_REASON}자 이상`}
                />
              </label>
            )}
          </div>
        ) : (
          <p className="mt-3 text-[12.5px] text-zinc-500">
            {target === 'off'
              ? '끄면 대화 검색에서 그래프를 쓰지 않습니다. 저장된 그래프는 그대로 둡니다.'
              : '관리자가 대화할 때만 그래프 검색이 실행됩니다.'}
          </p>
        )}
        {change.error && (
          <p role="alert" className="mt-3 text-[12.5px] text-red-600">
            {change.error.message}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-[13px] text-zinc-600 hover:bg-zinc-100"
          >
            취소
          </button>
          <button
            type="button"
            disabled={!canSubmit}
            onClick={submit}
            className={`rounded-lg px-3 py-1.5 text-[13px] font-medium text-white disabled:opacity-40 ${
              forced ? 'bg-red-600 hover:bg-red-700' : 'bg-violet-600 hover:bg-violet-700'
            }`}
          >
            {forced ? '강제 전환' : '변경'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default StageChangeDialog;
