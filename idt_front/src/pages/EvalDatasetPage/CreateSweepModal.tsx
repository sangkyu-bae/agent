// agent-model-benchmark Design §5.4: 스윕 생성 폼.
// 화면이 지켜야 할 게이트 2가지:
//   1) 모델은 최대 SWEEP_MAX_MODELS개 — 초과 선택 자체를 막는다.
//   2) 예상 비용을 확인하기 전에는 [실행]을 누를 수 없다. 스윕은 케이스 수 ×
//      모델 수만큼 과금되므로 금액을 모른 채 시작하게 두면 안 된다 (Plan R-3).
import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useMyBuilderAgents } from '@/hooks/useAgentBuilder';
import { useLlmModels } from '@/hooks/useLlmModels';
import { useTestsets } from '@/hooks/useEval';
import { useCreateSweep, useEstimateSweep } from '@/hooks/useSweeps';
import {
  SWEEP_AVAILABLE_METRICS,
  SWEEP_FIXED_TEMPERATURE,
  SWEEP_MAX_MODELS,
} from '@/types/sweep';
import type { SweepEstimate } from '@/types/sweep';

interface Props {
  onClose: () => void;
  onCreated: (sweepId: string) => void;
}

const CreateSweepModal = ({ onClose, onCreated }: Props) => {
  const [name, setName] = useState('');
  const [agentId, setAgentId] = useState('');
  const [testsetId, setTestsetId] = useState('');
  const [modelIds, setModelIds] = useState<string[]>([]);
  const [judgeId, setJudgeId] = useState('');
  const [metrics, setMetrics] = useState<string[]>(['answer_relevancy']);
  const [estimate, setEstimate] = useState<SweepEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: agentList } = useMyBuilderAgents();
  const { data: testsets } = useTestsets();
  const { data: models } = useLlmModels();
  const estimateMutation = useEstimateSweep();
  const createMutation = useCreateSweep();

  const activeModels = (models ?? []).filter((m) => m.is_active);
  const modelLimitReached = modelIds.length >= SWEEP_MAX_MODELS;
  const baseFilled = !!agentId && !!testsetId && modelIds.length > 0 && !!judgeId;

  // 조건이 바뀌면 이전 추정치는 더 이상 유효하지 않다 — 다시 확인하게 만든다.
  const invalidateEstimate = () => setEstimate(null);

  const toggleModel = (id: string) => {
    invalidateEstimate();
    setModelIds((prev) =>
      prev.includes(id)
        ? prev.filter((m) => m !== id)
        : prev.length >= SWEEP_MAX_MODELS
          ? prev
          : [...prev, id],
    );
  };

  const toggleMetric = (key: string) => {
    invalidateEstimate();
    setMetrics((prev) =>
      prev.includes(key) ? prev.filter((m) => m !== key) : [...prev, key],
    );
  };

  const payload = {
    agent_id: agentId,
    testset_id: testsetId,
    model_ids: modelIds,
    judge_llm_model_id: judgeId || null,
    metrics,
  };

  const handleEstimate = async () => {
    setError(null);
    try {
      setEstimate(await estimateMutation.mutateAsync(payload));
    } catch (e) {
      setError(e instanceof Error ? e.message : '비용 추정에 실패했습니다');
    }
  };

  const handleCreate = async () => {
    setError(null);
    try {
      const res = await createMutation.mutateAsync({ ...payload, name });
      onCreated(res.sweep_id);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : '스윕 생성에 실패했습니다');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6">
        <h3 className="mb-5 text-[16px] font-semibold text-zinc-900">모델 스윕</h3>

        <div className="space-y-4">
          <div>
            <label
              className="mb-1.5 block text-[12.5px] font-medium text-zinc-600"
              htmlFor="sweep-name"
            >
              이름
            </label>
            <input
              id="sweep-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="여신심사봇 모델 비교"
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
            />
          </div>

          <div>
            <label
              className="mb-1.5 block text-[12.5px] font-medium text-zinc-600"
              htmlFor="sweep-agent"
            >
              에이전트
            </label>
            <select
              id="sweep-agent"
              value={agentId}
              onChange={(e) => {
                invalidateEstimate();
                setAgentId(e.target.value);
              }}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
            >
              <option value="">선택하세요</option>
              {(agentList?.agents ?? []).map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              className="mb-1.5 block text-[12.5px] font-medium text-zinc-600"
              htmlFor="sweep-testset"
            >
              테스트셋
            </label>
            <select
              id="sweep-testset"
              value={testsetId}
              onChange={(e) => {
                invalidateEstimate();
                setTestsetId(e.target.value);
              }}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
            >
              <option value="">선택하세요</option>
              {(testsets?.items ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.case_count}건)
                </option>
              ))}
            </select>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[12.5px] font-medium text-zinc-600">
                비교할 모델
              </span>
              <span className="text-[12px] text-zinc-400">
                {modelIds.length}/{SWEEP_MAX_MODELS}
              </span>
            </div>
            <div
              data-testid="sweep-model-list"
              className="grid grid-cols-2 gap-2 rounded-lg border border-zinc-200 p-3"
            >
              {activeModels.map((m) => {
                const checked = modelIds.includes(m.id);
                return (
                  <label
                    key={m.id}
                    className="flex items-center gap-2 text-[13px] text-zinc-700"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      // 상한 도달 시 미선택 항목은 아예 못 누르게 한다
                      disabled={!checked && modelLimitReached}
                      onChange={() => toggleModel(m.id)}
                      className="h-4 w-4 rounded border-zinc-300 text-violet-600"
                    />
                    {m.display_name}
                  </label>
                );
              })}
            </div>
            {modelLimitReached && (
              <p className="mt-1.5 text-[12px] text-amber-600">
                모델은 최대 {SWEEP_MAX_MODELS}개까지 선택할 수 있습니다
              </p>
            )}
          </div>

          <div>
            <label
              className="mb-1.5 block text-[12.5px] font-medium text-zinc-600"
              htmlFor="sweep-judge"
            >
              채점 모델 (judge)
            </label>
            <select
              id="sweep-judge"
              value={judgeId}
              onChange={(e) => {
                invalidateEstimate();
                setJudgeId(e.target.value);
              }}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
            >
              <option value="">선택하세요</option>
              {activeModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <span className="mb-1.5 block text-[12.5px] font-medium text-zinc-600">
              평가 지표
            </span>
            <div className="flex flex-wrap gap-3 rounded-lg border border-zinc-200 p-3">
              {SWEEP_AVAILABLE_METRICS.map((m) => (
                <label
                  key={m.key}
                  className="flex items-center gap-2 text-[13px] text-zinc-700"
                >
                  <input
                    type="checkbox"
                    checked={metrics.includes(m.key)}
                    onChange={() => toggleMetric(m.key)}
                    className="h-4 w-4 rounded border-zinc-300 text-violet-600"
                  />
                  {m.label}
                </label>
              ))}
            </div>
          </div>

          <div className="rounded-lg bg-zinc-50 px-3 py-2 text-[12.5px] text-zinc-500">
            temperature <strong>{SWEEP_FIXED_TEMPERATURE}</strong> 고정 — 같은
            실험을 다시 돌렸을 때 같은 결론이 나오도록 서버가 강제합니다
          </div>

          <div>
            <LoadingButton
              type="button"
              onClick={handleEstimate}
              disabled={!baseFilled}
              isPending={estimateMutation.isPending}
              className="rounded-lg border border-zinc-200 px-4 py-2 text-[13px] text-zinc-700"
            >
              예상 비용 확인
            </LoadingButton>

            {estimate && (
              <div
                data-testid="sweep-estimate"
                className="mt-3 rounded-lg border border-violet-100 bg-violet-50/50 p-3 text-[13px]"
              >
                <div className="font-medium text-violet-700">
                  예상 ${estimate.estimated_cost_usd} · 약{' '}
                  {estimate.estimated_minutes}분{' '}
                  <span className="font-normal text-violet-500">(추정치)</span>
                </div>
                <div className="mt-1 text-[12px] text-zinc-500">
                  케이스 {estimate.case_count}건 × 모델 {estimate.model_count}개 ={' '}
                  {estimate.total_calls}회 호출
                </div>
                <ul className="mt-2 space-y-0.5 text-[12px] text-zinc-500">
                  {estimate.per_model.map((p) => (
                    <li key={p.llm_model_id}>
                      {p.display_name}: ${p.estimated_cost_usd}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {error && (
            <p role="alert" className="text-[12.5px] text-red-600">
              {error}
            </p>
          )}
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-[13px] text-zinc-500"
          >
            취소
          </button>
          <LoadingButton
            type="button"
            onClick={handleCreate}
            // 비용을 확인하지 않았거나 이름이 없으면 실행 불가
            disabled={!estimate || !name.trim()}
            isPending={createMutation.isPending}
            className="rounded-lg bg-violet-600 px-4 py-2 text-[13px] font-medium text-white disabled:opacity-40"
          >
            실행
          </LoadingButton>
        </div>
      </div>
    </div>
  );
};

export default CreateSweepModal;
