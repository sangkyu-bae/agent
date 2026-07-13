import { useState } from 'react';
import Modal from '@/components/common/Modal';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import {
  useLlmModels,
  useCreateLlmModel,
  useUpdateLlmModel,
  useUpdateLlmModelPricing,
  useDeactivateLlmModel,
} from '@/hooks/useLlmModels';
import { formatDate } from '@/utils/formatters';
import { LLM_PROVIDER } from '@/types/llmModel';
import type {
  CreateLlmModelRequest,
  LlmModel,
  UpdateLlmModelRequest,
} from '@/types/llmModel';

const inputCls =
  'w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100';
const readonlyCls =
  'w-full rounded-xl border border-zinc-200 bg-zinc-100 px-4 py-2.5 text-[14px] text-zinc-500';
const labelCls = 'mb-1.5 block text-[13px] font-medium text-zinc-700';

/** authClient가 detail을 ApiError(message, status)로 정규화한다 */
const getErrorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;

// ── 등록/수정 폼 모달 ─────────────────────────────────────

interface FormState {
  provider: string;
  model_name: string;
  display_name: string;
  api_key_env: string;
  description: string;
  max_tokens: string;
  base_url: string;
  is_active: boolean;
  is_default: boolean;
}

const emptyForm: FormState = {
  provider: LLM_PROVIDER.OPENAI,
  model_name: '',
  display_name: '',
  api_key_env: '',
  description: '',
  max_tokens: '',
  base_url: '',
  is_active: true,
  is_default: false,
};

const fromModel = (m: LlmModel): FormState => ({
  provider: m.provider,
  model_name: m.model_name,
  display_name: m.display_name,
  api_key_env: '', // write-only — 응답에 노출되지 않음
  description: m.description ?? '',
  max_tokens: m.max_tokens != null ? String(m.max_tokens) : '',
  base_url: m.base_url ?? '',
  is_active: m.is_active,
  is_default: m.is_default,
});

interface FormModalProps {
  isOpen: boolean;
  model: LlmModel | null; // null = 등록
  onClose: () => void;
  onSubmitCreate: (req: CreateLlmModelRequest) => void;
  onSubmitUpdate: (req: UpdateLlmModelRequest) => void;
  isPending: boolean;
  error: string | null;
  setError: (msg: string | null) => void;
}

const LlmModelFormModal = ({
  isOpen,
  model,
  onClose,
  onSubmitCreate,
  onSubmitUpdate,
  isPending,
  error,
  setError,
}: FormModalProps) => {
  const isEdit = !!model;
  const [form, setForm] = useState<FormState>(emptyForm);
  const [initialized, setInitialized] = useState(false);

  // 모달이 열릴 때 1회 초기화
  if (isOpen && !initialized) {
    setForm(model ? fromModel(model) : emptyForm);
    setInitialized(true);
  }
  if (!isOpen && initialized) setInitialized(false);
  if (!isOpen) return null;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.display_name.trim()) {
      setError('표시명은 필수입니다.');
      return;
    }
    if (!isEdit && (!form.model_name.trim() || !form.api_key_env.trim())) {
      setError('모델명·API Key 환경변수명은 필수입니다.');
      return;
    }

    const maxTokens = form.max_tokens.trim()
      ? Number(form.max_tokens)
      : null;
    if (maxTokens !== null && (!Number.isInteger(maxTokens) || maxTokens <= 0)) {
      setError('최대 토큰 수는 양의 정수여야 합니다.');
      return;
    }
    const baseUrl = form.base_url.trim() || null;

    if (isEdit) {
      onSubmitUpdate({
        display_name: form.display_name.trim(),
        description: form.description.trim() || null,
        max_tokens: maxTokens,
        base_url: baseUrl,
        is_active: form.is_active,
        is_default: form.is_default,
      });
    } else {
      onSubmitCreate({
        provider: form.provider,
        model_name: form.model_name.trim(),
        display_name: form.display_name.trim(),
        api_key_env: form.api_key_env.trim(),
        description: form.description.trim() || null,
        max_tokens: maxTokens,
        base_url: baseUrl,
        is_active: form.is_active,
        is_default: form.is_default,
      });
    }
  };

  return (
    <Modal
      onClose={onClose}
      title={isEdit ? 'LLM 모델 수정' : 'LLM 모델 등록'}
      size="lg"
      scroll="content"
      showCloseButton={false}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div className="flex gap-4">
          <div className="flex-1">
            <label className={labelCls}>
              Provider {!isEdit && <span className="text-red-400">*</span>}
            </label>
            {isEdit ? (
              <div className={readonlyCls}>{form.provider}</div>
            ) : (
              <select
                value={form.provider}
                onChange={(e) => set('provider', e.target.value)}
                aria-label="Provider"
                className={inputCls}
              >
                {Object.values(LLM_PROVIDER).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="flex-1">
            <label className={labelCls}>
              모델명 {!isEdit && <span className="text-red-400">*</span>}
            </label>
            {isEdit ? (
              <div className={`${readonlyCls} font-mono text-[13px]`}>{form.model_name}</div>
            ) : (
              <input
                type="text"
                value={form.model_name}
                onChange={(e) => set('model_name', e.target.value)}
                placeholder="예: gpt-4o"
                maxLength={150}
                className={inputCls}
              />
            )}
          </div>
        </div>

        <div>
          <label className={labelCls}>
            표시명 <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={form.display_name}
            onChange={(e) => set('display_name', e.target.value)}
            placeholder="예: GPT-4o"
            maxLength={150}
            className={inputCls}
          />
        </div>

        {!isEdit && (
          <div>
            <label className={labelCls}>
              API Key 환경변수명 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.api_key_env}
              onChange={(e) => set('api_key_env', e.target.value)}
              placeholder="예: OPENAI_API_KEY"
              maxLength={100}
              className={inputCls}
            />
            <p className="mt-1 text-[12px] text-zinc-400">
              키 값이 아닌 서버 환경변수명입니다.
            </p>
          </div>
        )}

        <div>
          <label className={labelCls}>설명</label>
          <textarea
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="모델에 대한 설명 (선택)"
            rows={2}
            className={inputCls}
          />
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className={labelCls}>최대 토큰 수</label>
            <input
              type="number"
              value={form.max_tokens}
              onChange={(e) => set('max_tokens', e.target.value)}
              placeholder="비우면 제한 없음"
              min={1}
              className={inputCls}
            />
          </div>
          <div className="flex-1">
            <label className={labelCls}>Base URL</label>
            <input
              type="text"
              value={form.base_url}
              onChange={(e) => set('base_url', e.target.value)}
              placeholder="http://vllm.internal:8000/v1"
              maxLength={500}
              className={inputCls}
            />
            <p className="mt-1 text-[12px] text-zinc-400">
              self-host(vLLM 등) 엔드포인트. 비우면 provider 기본값.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <label className="flex items-center gap-2 text-[13px] text-zinc-700">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => set('is_active', e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-violet-600"
            />
            활성
          </label>
          <label className="flex items-center gap-2 text-[13px] text-zinc-700">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => set('is_default', e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-violet-600"
            />
            기본 모델
          </label>
          <span className="text-[12px] text-zinc-400">
            기본 모델 지정 시 기존 기본 모델은 자동 해제됩니다.
          </span>
        </div>

        {!isEdit && (
          <p className="rounded-lg bg-zinc-50 px-3 py-2 text-[12.5px] text-zinc-500">
            가격은 등록 후 목록의 &quot;가격&quot; 버튼으로 설정합니다.
          </p>
        )}

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
          >
            {isPending ? '저장 중...' : isEdit ? '저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  );
};

// ── 가격 변경 모달 ─────────────────────────────────────────

interface PricingModalProps {
  model: LlmModel | null;
  onClose: () => void;
  onSubmit: (input: number, output: number) => void;
  isPending: boolean;
  error: string | null;
  setError: (msg: string | null) => void;
}

const LlmModelPricingModal = ({
  model,
  onClose,
  onSubmit,
  isPending,
  error,
  setError,
}: PricingModalProps) => {
  const [inputPrice, setInputPrice] = useState('');
  const [outputPrice, setOutputPrice] = useState('');
  const [initialized, setInitialized] = useState(false);

  const isOpen = !!model;
  if (isOpen && !initialized) {
    setInputPrice(model.input_price_per_1k_usd ?? '');
    setOutputPrice(model.output_price_per_1k_usd ?? '');
    setInitialized(true);
  }
  if (!isOpen && initialized) setInitialized(false);
  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const input = parseFloat(inputPrice);
    const output = parseFloat(outputPrice);
    if (Number.isNaN(input) || Number.isNaN(output) || input < 0 || output < 0) {
      setError('0 이상의 숫자를 입력하세요');
      return;
    }
    onSubmit(input, output);
  };

  return (
    <Modal
      onClose={onClose}
      title="가격 설정"
      subtitle={`${model.display_name} · 1,000 토큰당 USD`}
      size="sm"
      showCloseButton={false}
    >
      {/* noValidate: 브라우저 기본 검증 대신 커스텀 인라인 에러로 통일 */}
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div>
          <label className={labelCls}>입력 단가 (USD/1K)</label>
          <input
            type="number"
            value={inputPrice}
            onChange={(e) => setInputPrice(e.target.value)}
            placeholder="예: 0.0025"
            min={0}
            step="0.0001"
            className={inputCls}
            autoFocus
          />
        </div>
        <div>
          <label className={labelCls}>출력 단가 (USD/1K)</label>
          <input
            type="number"
            value={outputPrice}
            onChange={(e) => setOutputPrice(e.target.value)}
            placeholder="예: 0.0100"
            min={0}
            step="0.0001"
            className={inputCls}
          />
        </div>

        {model.pricing_updated_at && (
          <p className="text-[12px] text-zinc-400">
            최종 변경: {formatDate(model.pricing_updated_at)}
          </p>
        )}

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
          >
            {isPending ? '저장 중...' : '저장'}
          </button>
        </div>
      </form>
    </Modal>
  );
};

// ── 페이지 ─────────────────────────────────────────────────

const PriceCell = ({ value }: { value?: string | null }) => {
  if (value == null) {
    return (
      <span className="rounded-md bg-amber-50 px-2 py-1 text-[11.5px] font-medium text-amber-600">
        미설정
      </span>
    );
  }
  return (
    <span className="text-[13px] text-zinc-600">
      ${value} <span className="text-[11px] text-zinc-400">/1K</span>
    </span>
  );
};

const AdminLlmModelsPage = () => {
  const [includeInactive, setIncludeInactive] = useState(false);
  const { data, isLoading, isFetching, isError, refetch } =
    useLlmModels(includeInactive);
  const models = data ?? [];

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editing, setEditing] = useState<LlmModel | null>(null);
  const [pricingTarget, setPricingTarget] = useState<LlmModel | null>(null);
  const [deactivating, setDeactivating] = useState<LlmModel | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  const createMutation = useCreateLlmModel();
  const updateMutation = useUpdateLlmModel();
  const pricingMutation = useUpdateLlmModelPricing();
  const deactivateMutation = useDeactivateLlmModel();

  const handleCreate = (req: CreateLlmModelRequest) => {
    createMutation.mutate(req, {
      onSuccess: () => setIsCreateOpen(false),
      onError: (err) =>
        setFormError(getErrorMessage(err, 'LLM 모델 등록에 실패했습니다.')),
    });
  };

  const handleUpdate = (req: UpdateLlmModelRequest) => {
    if (!editing) return;
    updateMutation.mutate(
      { id: editing.id, data: req },
      {
        onSuccess: () => setEditing(null),
        onError: (err) =>
          setFormError(getErrorMessage(err, 'LLM 모델 수정에 실패했습니다.')),
      },
    );
  };

  const handlePricing = (input: number, output: number) => {
    if (!pricingTarget) return;
    pricingMutation.mutate(
      {
        id: pricingTarget.id,
        data: { input_price_per_1k_usd: input, output_price_per_1k_usd: output },
      },
      {
        onSuccess: () => setPricingTarget(null),
        onError: (err) =>
          setPricingError(getErrorMessage(err, '가격 설정에 실패했습니다.')),
      },
    );
  };

  const handleDeactivate = () => {
    if (!deactivating) return;
    deactivateMutation.mutate(deactivating.id, {
      onSuccess: () => setDeactivating(null),
      onError: (err) =>
        setDeactivateError(getErrorMessage(err, '비활성화에 실패했습니다.')),
    });
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
            Admin
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">LLM 모델 관리</h1>
          <p className="mt-1 text-[13px] text-zinc-400">
            에이전트·요약·비용 계산이 참조하는 LLM 모델을 등록·수정·가격·비활성화 관리합니다.
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* 토글 재조회 중 미세 스피너 — keepPreviousData로 테이블은 유지된다 */}
          {isFetching && !isLoading && (
            <svg
              className="h-4 w-4 animate-spin text-violet-500"
              fill="none"
              viewBox="0 0 24 24"
              aria-label="목록 갱신 중"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          <label className="flex items-center gap-2 text-[13px] text-zinc-600">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-violet-600"
            />
            비활성 포함
          </label>
          <button
            onClick={() => {
              setFormError(null);
              setIsCreateOpen(true);
            }}
            className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            모델 등록
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center text-zinc-400">로딩 중...</div>
      ) : isError ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">LLM 모델 목록을 불러오지 못했습니다.</p>
          <button
            onClick={() => refetch()}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            다시 시도
          </button>
        </div>
      ) : models.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">등록된 LLM 모델이 없습니다.</p>
          <button
            onClick={() => {
              setFormError(null);
              setIsCreateOpen(true);
            }}
            className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
          >
            + 첫 번째 모델 등록하기
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">표시명</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">Provider</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">모델명</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">상태</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">입력 단가</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">출력 단가</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">Base URL</th>
                <th className="w-[200px] px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {models.map((m) => (
                <tr
                  key={m.id}
                  className={`transition-colors hover:bg-zinc-50/50 ${m.is_active ? '' : 'opacity-50'}`}
                >
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-medium text-zinc-900">{m.display_name}</span>
                      {m.is_default && (
                        <span className="rounded-md bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-600">
                          기본
                        </span>
                      )}
                    </div>
                    {m.description && (
                      <div className="text-[12px] text-zinc-400">{m.description}</div>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    <span className="rounded-md bg-zinc-100 px-2 py-1 text-[11.5px] font-medium text-zinc-500">
                      {m.provider}
                    </span>
                  </td>
                  <td className="px-5 py-4 font-mono text-[13px] text-zinc-500">{m.model_name}</td>
                  <td className="px-5 py-4">
                    <span
                      className={`rounded-md px-2 py-1 text-[11.5px] font-medium ${
                        m.is_active ? 'bg-emerald-50 text-emerald-600' : 'bg-zinc-100 text-zinc-400'
                      }`}
                    >
                      {m.is_active ? '활성' : '비활성'}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <PriceCell value={m.input_price_per_1k_usd} />
                  </td>
                  <td className="px-5 py-4">
                    <PriceCell value={m.output_price_per_1k_usd} />
                  </td>
                  <td
                    className="max-w-[160px] truncate px-5 py-4 font-mono text-[12px] text-zinc-500"
                    title={m.base_url ?? undefined}
                  >
                    {m.base_url ?? '–'}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => {
                          setFormError(null);
                          setEditing(m);
                        }}
                        aria-label={`${m.display_name} 수정`}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 active:scale-95"
                      >
                        수정
                      </button>
                      <button
                        onClick={() => {
                          setPricingError(null);
                          setPricingTarget(m);
                        }}
                        aria-label={`${m.display_name} 가격`}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-violet-200 hover:text-violet-600 active:scale-95"
                      >
                        가격
                      </button>
                      {m.is_active && (
                        <button
                          onClick={() => {
                            setDeactivateError(null);
                            setDeactivating(m);
                          }}
                          aria-label={`${m.display_name} 비활성화`}
                          className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-red-200 hover:bg-red-50 hover:text-red-500 active:scale-95"
                        >
                          비활성화
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 등록 모달 */}
      <LlmModelFormModal
        isOpen={isCreateOpen}
        model={null}
        onClose={() => setIsCreateOpen(false)}
        onSubmitCreate={handleCreate}
        onSubmitUpdate={() => {}}
        isPending={createMutation.isPending}
        error={formError}
        setError={setFormError}
      />

      {/* 수정 모달 */}
      <LlmModelFormModal
        isOpen={!!editing}
        model={editing}
        onClose={() => setEditing(null)}
        onSubmitCreate={() => {}}
        onSubmitUpdate={handleUpdate}
        isPending={updateMutation.isPending}
        error={formError}
        setError={setFormError}
      />

      {/* 가격 변경 모달 */}
      <LlmModelPricingModal
        model={pricingTarget}
        onClose={() => setPricingTarget(null)}
        onSubmit={handlePricing}
        isPending={pricingMutation.isPending}
        error={pricingError}
        setError={setPricingError}
      />

      {/* 비활성화 확인 */}
      <ConfirmDialog
        isOpen={!!deactivating}
        title="모델 비활성화"
        description={
          <>
            <b>{deactivating?.display_name}</b> 모델을 비활성화합니다. 이 모델을 참조 중인
            에이전트 실행·문서 요약 작업은 실행 시점에 실패할 수 있습니다. 비활성화 후에도
            수정에서 다시 활성화할 수 있습니다.
          </>
        }
        confirmLabel="비활성화"
        variant="danger"
        onClose={() => setDeactivating(null)}
        onConfirm={handleDeactivate}
        isPending={deactivateMutation.isPending}
        error={deactivateError}
      />
    </div>
  );
};

export default AdminLlmModelsPage;
