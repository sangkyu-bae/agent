// eval-hub: 평가 실행 생성 폼 — 대상/테스트셋/메트릭/모델 (Design §3.5)
// 검증은 인라인 에러 방식 (jsdom noValidate 선례 — 브라우저 제약 검증 미사용)
import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useEvalMetrics, useStartBatchEval, useTestsets } from '@/hooks/useEval';
import { useMyBuilderAgents } from '@/hooks/useAgentBuilder';
import { useKnowledgeBases } from '@/hooks/useKnowledgeBases';
import { useLlmModels } from '@/hooks/useLlmModels';
import type { EvalTargetType } from '@/types/eval';

const TARGETS: { key: EvalTargetType; label: string; hint: string }[] = [
  { key: 'agent', label: '에이전트', hint: '에이전트를 실제 실행해 답변 품질 평가' },
  { key: 'rag', label: 'RAG', hint: 'KB 검색 + 답변 생성 파이프라인 평가' },
  { key: 'retrieval', label: '검색', hint: 'KB 검색 품질만 평가' },
];

/** 재실행 프리필 — failed run의 config에서 복원 (G-02) */
export interface RunPrefill {
  target_type: EvalTargetType;
  testset_id?: string;
  agent_id?: string;
  collection_name?: string;
  metrics?: string[];
  llm_model?: string;
  top_k?: number;
  sample_ratio?: number;
}

interface CreateRunModalProps {
  onClose: () => void;
  prefill?: RunPrefill | null;
}

const CreateRunModal = ({ onClose, prefill }: CreateRunModalProps) => {
  const [targetType, setTargetType] = useState<EvalTargetType>(
    prefill?.target_type ?? 'agent',
  );
  const [testsetId, setTestsetId] = useState(prefill?.testset_id ?? '');
  const [agentId, setAgentId] = useState(prefill?.agent_id ?? '');
  const [collectionName, setCollectionName] = useState(
    prefill?.collection_name ?? '',
  );
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(
    prefill?.metrics ?? [],
  );
  const [llmModel, setLlmModel] = useState(prefill?.llm_model ?? 'gpt-4o-mini');
  const [topK, setTopK] = useState(String(prefill?.top_k ?? 5));
  const [sampleRatio, setSampleRatio] = useState(
    String(prefill?.sample_ratio ?? 1),
  );
  const [error, setError] = useState('');

  const { data: testsets } = useTestsets();
  const { data: metrics } = useEvalMetrics();
  const { data: agentList } = useMyBuilderAgents();
  const { data: knowledgeBases } = useKnowledgeBases();
  const { data: llmModels } = useLlmModels();
  const startMutation = useStartBatchEval();

  const targetMetrics = (metrics ?? []).filter((m) =>
    m.target_types.includes(targetType),
  );

  const toggleMetric = (key: string) => {
    setSelectedMetrics((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const switchTarget = (t: EvalTargetType) => {
    setTargetType(t);
    setSelectedMetrics([]); // 대상 변경 시 비호환 메트릭 해제
    setError('');
  };

  const handleSubmit = () => {
    if (!testsetId) return setError('테스트셋을 선택하세요.');
    if (targetType === 'agent' && !agentId)
      return setError('평가할 에이전트를 선택하세요.');
    if (targetType !== 'agent' && !collectionName)
      return setError('평가할 지식 베이스를 선택하세요.');
    if (selectedMetrics.length === 0)
      return setError('메트릭을 1개 이상 선택하세요.');
    const ratio = Number(sampleRatio);
    if (!(ratio > 0 && ratio <= 1))
      return setError('샘플 비율은 0 초과 1 이하여야 합니다.');
    setError('');

    startMutation.mutate(
      {
        target_type: targetType,
        metrics: selectedMetrics,
        testset_id: testsetId,
        llm_model: llmModel,
        top_k: Number(topK) || 5,
        sample_ratio: ratio,
        ...(targetType === 'agent'
          ? { agent_id: agentId }
          : { collection_name: collectionName }),
      },
      { onSuccess: onClose, onError: (e) => setError(e.message) },
    );
  };

  return (
    <div
      role="dialog"
      aria-label="평가 실행"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="flex max-h-[85vh] w-full max-w-xl flex-col rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-100 px-6 py-4">
          <h2 className="text-[15px] font-semibold text-zinc-900">평가 실행</h2>
          <button onClick={onClose} aria-label="닫기" className="text-zinc-400 hover:text-zinc-600">
            ✕
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
          <div>
            <p className="mb-1.5 text-[12.5px] font-medium text-zinc-600">평가 대상</p>
            <div className="grid grid-cols-3 gap-2">
              {TARGETS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => switchTarget(t.key)}
                  className={`rounded-xl border px-3 py-2.5 text-left ${
                    targetType === t.key
                      ? 'border-violet-400 bg-violet-50/50'
                      : 'border-zinc-200 hover:border-zinc-300'
                  }`}
                >
                  <p className="text-[13px] font-medium text-zinc-800">{t.label}</p>
                  <p className="mt-0.5 text-[11px] leading-snug text-zinc-400">{t.hint}</p>
                </button>
              ))}
            </div>
          </div>

          {targetType === 'agent' ? (
            <div>
              <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-600" htmlFor="run-agent">
                에이전트
              </label>
              <select
                id="run-agent"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
              >
                <option value="">선택하세요</option>
                {(agentList?.agents ?? []).map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-600" htmlFor="run-kb">
                지식 베이스
              </label>
              <select
                id="run-kb"
                value={collectionName}
                onChange={(e) => setCollectionName(e.target.value)}
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
              >
                <option value="">선택하세요</option>
                {(knowledgeBases ?? []).map((kb) => (
                  <option key={kb.kb_id} value={kb.collection_name}>{kb.name}</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-600" htmlFor="run-testset">
              테스트셋
            </label>
            <select
              id="run-testset"
              value={testsetId}
              onChange={(e) => setTestsetId(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
            >
              <option value="">선택하세요</option>
              {(testsets?.items ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} (QA {t.case_count}건)
                </option>
              ))}
            </select>
          </div>

          <div>
            <p className="mb-1.5 text-[12.5px] font-medium text-zinc-600">메트릭</p>
            <div className="space-y-1.5">
              {targetMetrics.map((m) => (
                <label
                  key={m.key}
                  className="flex cursor-pointer items-start gap-2 rounded-lg border border-zinc-100 px-3 py-2 hover:bg-zinc-50"
                >
                  <input
                    type="checkbox"
                    checked={selectedMetrics.includes(m.key)}
                    onChange={() => toggleMetric(m.key)}
                    className="mt-0.5"
                  />
                  <span className="text-[12.5px]">
                    <span className="font-medium text-zinc-800">{m.name}</span>
                    {m.requires_ground_truth && (
                      <span className="ml-1.5 rounded bg-amber-50 px-1.5 py-0.5 text-[10.5px] text-amber-600">
                        정답 필요
                      </span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-600" htmlFor="run-model">
                평가 LLM
              </label>
              <select
                id="run-model"
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
              >
                <option value="gpt-4o-mini">gpt-4o-mini (기본)</option>
                {(llmModels ?? [])
                  .filter((m) => m.model_name !== 'gpt-4o-mini')
                  .map((m) => (
                    <option key={m.id} value={m.model_name}>{m.model_name}</option>
                  ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-600" htmlFor="run-topk">
                검색 Top-K
              </label>
              <input
                id="run-topk"
                value={topK}
                onChange={(e) => setTopK(e.target.value.replace(/\D/g, ''))}
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-600" htmlFor="run-sample">
                샘플 비율 (0~1)
              </label>
              <input
                id="run-sample"
                value={sampleRatio}
                onChange={(e) =>
                  setSampleRatio(e.target.value.replace(/[^0-9.]/g, ''))
                }
                className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px]"
              />
            </div>
          </div>

          {error && (
            <p role="alert" className="text-[12.5px] text-red-500">{error}</p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-zinc-100 px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-xl border border-zinc-200 px-4 py-2 text-[13px] text-zinc-600 hover:bg-zinc-50"
          >
            취소
          </button>
          <LoadingButton
            isPending={startMutation.isPending}
            pendingText="시작 중..."
            onClick={handleSubmit}
            className="rounded-xl bg-zinc-900 px-4 py-2 text-[13px] font-medium text-white hover:bg-zinc-800 disabled:opacity-60"
          >
            평가 시작
          </LoadingButton>
        </div>
      </div>
    </div>
  );
};

export default CreateRunModal;
