// Design Ref: graph-rag-foundation §5.1 설정 탭·§5.4 — 전체 교체(PUT), 단계는 헤더에서만 바꾼다
import { useMemo, useState } from 'react';
import { useGraphRagSettings, useUpdateGraphRagSettings } from '@/hooks/useGraphRag';
import { useLlmModels } from '@/hooks/useLlmModels';
import {
  GRAPH_RAG_LIMITS,
  GRAPH_RAG_OTHER_TYPE,
  type GraphRagSettingsRequest,
  type GraphRagSettingsResponse,
} from '@/types/graphRag';

type NumKey =
  | 'link_threshold'
  | 'new_threshold'
  | 'concurrency'
  | 'max_llm_calls_per_doc'
  | 'candidate_top_k'
  | 'max_hops'
  | 'graph_rrf_weight'
  | 'retrieval_timeout_ms';

const NUM_FIELDS: { key: NumKey; label: string; step: string; hint?: string }[] = [
  { key: 'link_threshold', label: '연결 기준값', step: '0.01', hint: '이 확률 이상이면 기존 엔티티에 바로 연결' },
  { key: 'new_threshold', label: '신규 기준값', step: '0.01', hint: '이 확률 이하이면 새 엔티티. 사이 구간은 LLM 재판정' },
  { key: 'concurrency', label: '동시 실행 수', step: '1' },
  { key: 'max_llm_calls_per_doc', label: '문서당 LLM 호출 상한', step: '1' },
  { key: 'candidate_top_k', label: '후보 수', step: '1' },
  { key: 'max_hops', label: '최대 단계', step: '1' },
  { key: 'graph_rrf_weight', label: 'RRF 가중치', step: '0.05' },
  {
    key: 'retrieval_timeout_ms',
    label: '검색 시간 상한(ms)',
    step: '100',
    hint: '질문 주제 판정(LLM)이 1.5~2.5초 걸려 800ms면 그래프 검색이 대개 시간 초과됩니다. 관리자 테스트는 3,000~5,000 권장',
  },
];

const toNums = (s: GraphRagSettingsResponse) =>
  Object.fromEntries(NUM_FIELDS.map((f) => [f.key, String(s[f.key])])) as Record<NumKey, string>;

const rangeError = (key: NumKey, v: number): string | null => {
  const lim = (GRAPH_RAG_LIMITS as unknown as Record<string, { min: number; max: number } | undefined>)[key];
  if (!lim) return null;
  return v < lim.min || v > lim.max ? `${lim.min}~${lim.max}` : null;
};

const labelCls = 'mb-1 block text-[13px] font-medium text-zinc-700';
const inputCls = 'w-full rounded-lg border border-zinc-300 px-3 py-1.5 text-[13px]';

interface TypeChipsProps {
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
}

const TypeChips = ({ label, values, onChange }: TypeChipsProps) => {
  const [draft, setDraft] = useState('');
  const name = draft.trim();
  const canAdd =
    !!name &&
    name.length <= GRAPH_RAG_LIMITS.max_type_len &&
    !values.includes(name) &&
    values.length < GRAPH_RAG_LIMITS.max_types;
  return (
    <div role="group" aria-label={label}>
      <p className={labelCls}>{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 text-[12.5px]">
            {v}
            {v !== GRAPH_RAG_OTHER_TYPE && (
              <button
                type="button"
                aria-label={`${v} 삭제`}
                onClick={() => onChange(values.filter((x) => x !== v))}
                className="text-zinc-400 hover:text-red-500"
              >
                ×
              </button>
            )}
          </span>
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <input
          aria-label={`${label} 추가`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={GRAPH_RAG_LIMITS.max_type_len}
          className={`${inputCls} max-w-xs`}
        />
        <button
          type="button"
          disabled={!canAdd}
          onClick={() => {
            onChange([...values, name]);
            setDraft('');
          }}
          className="rounded-lg border border-zinc-300 px-3 text-[13px] disabled:opacity-40"
        >
          추가
        </button>
      </div>
    </div>
  );
};

interface SettingsFormProps {
  settings: GraphRagSettingsResponse;
  saved: boolean;
  setSaved: (v: boolean) => void;
}

/** 서버 값이 바뀌면(저장 후 포함) key 로 다시 마운트해 초기값을 새로 잡는다. */
const SettingsForm = ({ settings, saved, setSaved }: SettingsFormProps) => {
  const { data: models } = useLlmModels();
  const update = useUpdateGraphRagSettings();
  const [form, setForm] = useState<GraphRagSettingsResponse>(settings);
  const [nums, setNums] = useState<Record<NumKey, string>>(() => toNums(settings));

  const chatModels = (models ?? []).filter((m) => m.is_active && m.model_kind !== 'image');

  const errors = useMemo(() => {
    const out: string[] = [];
    for (const f of NUM_FIELDS) {
      const v = Number(nums[f.key]);
      if (nums[f.key].trim() === '' || Number.isNaN(v)) out.push(`${f.label}: 숫자를 입력하세요`);
      else {
        const r = rangeError(f.key, v);
        if (r) out.push(`${f.label}: ${r} 범위`);
      }
    }
    const link = Number(nums.link_threshold);
    const nw = Number(nums.new_threshold);
    if (!(link > 0 && link <= 1)) out.push('연결 기준값: 0~1 범위');
    if (!(nw > 0 && nw < link)) out.push('신규 기준값은 연결 기준값보다 작아야 합니다(0 초과).');
    return out;
  }, [nums]);

  const request: GraphRagSettingsRequest = {
    extraction_enabled: form.extraction_enabled,
    jev_enabled: form.jev_enabled,
    extraction_llm_model_id: form.extraction_llm_model_id || null,
    rejudge_llm_model_id: form.rejudge_llm_model_id || null,
    entity_types: form.entity_types,
    relation_types: form.relation_types,
    ...(Object.fromEntries(NUM_FIELDS.map((f) => [f.key, Number(nums[f.key])])) as Record<NumKey, number>),
  };
  const baseline = pickRequest(settings);
  const dirty = (Object.keys(request) as (keyof GraphRagSettingsRequest)[]).some(
    (k) => JSON.stringify(request[k]) !== JSON.stringify(baseline[k])
  );

  const set = <K extends keyof GraphRagSettingsResponse>(k: K, v: GraphRagSettingsResponse[K]) => {
    setSaved(false);
    setForm({ ...form, [k]: v });
  };

  const modelSelect = (key: 'extraction_llm_model_id' | 'rejudge_llm_model_id', label: string) => (
    <div>
      <label htmlFor={`graph-${key}`} className={labelCls}>
        {label}
      </label>
      <select
        id={`graph-${key}`}
        value={form[key] ?? ''}
        onChange={(e) => set(key, e.target.value || null)}
        className={inputCls}
      >
        <option value="">— 기본 모델 —</option>
        {chatModels.map((m) => (
          <option key={m.id} value={m.id}>
            {m.display_name} ({m.provider}/{m.model_name})
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <form
      className="space-y-6 rounded-xl border border-zinc-200 bg-white p-6"
      onSubmit={(e) => {
        e.preventDefault();
        update.mutate(request, { onSuccess: () => setSaved(true) });
      }}
    >
      <div className="flex flex-wrap gap-6">
        <label className="flex items-center gap-2 text-[14px] font-medium text-zinc-800">
          <input
            type="checkbox"
            role="switch"
            aria-label="추출 사용"
            checked={form.extraction_enabled}
            onChange={(e) => set('extraction_enabled', e.target.checked)}
            className="h-4 w-4 accent-violet-600"
          />
          문서 업로드 시 자동 추출
        </label>
        <label className="flex items-center gap-2 text-[14px] font-medium text-zinc-800">
          <input
            type="checkbox"
            role="switch"
            aria-label="Jev 판정"
            checked={form.jev_enabled}
            onChange={(e) => set('jev_enabled', e.target.checked)}
            className="h-4 w-4 accent-violet-600"
          />
          Jev 판정(끄면 LLM 판정만 사용)
        </label>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {modelSelect('extraction_llm_model_id', '추출 모델')}
        {modelSelect('rejudge_llm_model_id', '재판정 모델')}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {NUM_FIELDS.map((f) => (
          <div key={f.key} className={f.hint && f.key === 'retrieval_timeout_ms' ? 'sm:col-span-2' : ''}>
            <label htmlFor={`graph-${f.key}`} className={labelCls}>
              {f.label}
            </label>
            <input
              id={`graph-${f.key}`}
              type="number"
              step={f.step}
              value={nums[f.key]}
              onChange={(e) => {
                setSaved(false);
                setNums({ ...nums, [f.key]: e.target.value });
              }}
              className={inputCls}
            />
            {f.hint && <p className="mt-1 text-[11.5px] text-zinc-400">{f.hint}</p>}
          </div>
        ))}
      </div>

      <TypeChips
        label="엔티티 타입"
        values={form.entity_types}
        onChange={(v) => set('entity_types', v)}
      />
      <TypeChips
        label="관계 타입"
        values={form.relation_types}
        onChange={(v) => set('relation_types', v)}
      />

      {errors.length > 0 && (
        <ul className="space-y-0.5 text-[12.5px] text-red-600">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {update.error && (
        <p role="alert" className="text-[12.5px] text-red-600">
          {update.error.message}
        </p>
      )}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!dirty || errors.length > 0 || update.isPending}
          className="rounded-lg bg-violet-600 px-4 py-2 text-[13px] font-medium text-white disabled:opacity-40"
        >
          저장
        </button>
        {saved && <span className="text-[12.5px] text-emerald-600">저장했습니다.</span>}
      </div>
    </form>
  );
};

const GraphRagSettingsTab = () => {
  const { data: settings, isLoading } = useGraphRagSettings();
  const [saved, setSaved] = useState(false);
  if (isLoading || !settings) {
    return <p className="text-[13px] text-zinc-400">설정을 불러오는 중…</p>;
  }
  return (
    <SettingsForm
      key={`${settings.updated_at ?? ''}-${settings.rollout_stage}`}
      settings={settings}
      saved={saved}
      setSaved={setSaved}
    />
  );
};

const pickRequest = (s: GraphRagSettingsResponse): GraphRagSettingsRequest => ({
  extraction_enabled: s.extraction_enabled,
  jev_enabled: s.jev_enabled,
  extraction_llm_model_id: s.extraction_llm_model_id || null,
  rejudge_llm_model_id: s.rejudge_llm_model_id || null,
  entity_types: s.entity_types,
  relation_types: s.relation_types,
  link_threshold: s.link_threshold,
  new_threshold: s.new_threshold,
  concurrency: s.concurrency,
  max_llm_calls_per_doc: s.max_llm_calls_per_doc,
  candidate_top_k: s.candidate_top_k,
  max_hops: s.max_hops,
  graph_rrf_weight: s.graph_rrf_weight,
  retrieval_timeout_ms: s.retrieval_timeout_ms,
});

export default GraphRagSettingsTab;
