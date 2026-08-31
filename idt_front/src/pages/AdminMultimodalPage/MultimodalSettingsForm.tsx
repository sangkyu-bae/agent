// Design Ref: multimodal-extractor §5.1/§5.4 설정 탭 — 전역 설정 폼 + 연결 테스트
// 범위 검증은 MULTIMODAL_LIMITS(도메인 VO와 동일 숫자); 서버 400/404/409 메시지는 그대로 노출.
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import LoadingButton from '@/components/common/LoadingButton';
import { useLlmModels } from '@/hooks/useLlmModels';
import {
  useMultimodalSettings,
  useTestMultimodalConnection,
  useUpdateMultimodalSettings,
} from '@/hooks/useMultimodalSettings';
import {
  DETAIL_LEVELS,
  MULTIMODAL_LIMITS,
  OUTPUT_LANGUAGES,
  type ConnectionTestResponse,
  type DetailLevel,
  type MultimodalSettingsRequest,
  type MultimodalSettingsResponse,
  type OutputLanguage,
} from '@/types/multimodal';
import {
  validateMultimodalNumeric,
  type MultimodalNumericKey,
} from '@/utils/multimodalValidators';

const inputCls =
  'w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100';
const labelCls = 'mb-1.5 block text-[13px] font-medium text-zinc-700';

const getErrorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;

interface FormState {
  enabled: boolean;
  vision_model_id: string; // '' = 미선택
  max_images_per_doc: string;
  min_image_px: string;
  min_area_ratio: string;
  concurrency: string;
  timeout_sec: string;
  output_language: OutputLanguage;
  detail_level: DetailLevel;
}

const fromResponse = (s: MultimodalSettingsResponse): FormState => ({
  enabled: s.enabled,
  vision_model_id: s.vision_model_id ?? '',
  max_images_per_doc: String(s.max_images_per_doc),
  min_image_px: String(s.min_image_px),
  min_area_ratio: String(s.min_area_ratio),
  concurrency: String(s.concurrency),
  timeout_sec: String(s.timeout_sec),
  output_language: s.output_language,
  detail_level: s.detail_level,
});

type NumericKey = MultimodalNumericKey;

const NUMERIC_FIELDS: { key: NumericKey; label: string; integer: boolean; hint: string }[] = [
  { key: 'max_images_per_doc', label: '문서당 최대 이미지', integer: true, hint: '초과분은 skipped 로 표시' },
  { key: 'min_image_px', label: '최소 픽셀(가로·세로)', integer: true, hint: '아이콘·로고 제외용' },
  { key: 'min_area_ratio', label: '최소 면적 비율', integer: false, hint: '페이지 면적 대비 (0~1)' },
  { key: 'concurrency', label: '동시 호출 수', integer: true, hint: '' },
  { key: 'timeout_sec', label: '건당 타임아웃(초)', integer: true, hint: '' },
];

const toRequest = (f: FormState): MultimodalSettingsRequest => ({
  enabled: f.enabled,
  vision_model_id: f.vision_model_id || null,
  max_images_per_doc: Number(f.max_images_per_doc),
  min_image_px: Number(f.min_image_px),
  min_area_ratio: Number(f.min_area_ratio),
  concurrency: Number(f.concurrency),
  timeout_sec: Number(f.timeout_sec),
  output_language: f.output_language,
  detail_level: f.detail_level,
});

const MultimodalSettingsForm = () => {
  const settings = useMultimodalSettings();
  const models = useLlmModels(false);
  const update = useUpdateMultimodalSettings();
  const test = useTestMultimodalConnection();

  const [form, setForm] = useState<FormState | null>(null);
  const [syncedFrom, setSyncedFrom] = useState<MultimodalSettingsResponse | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResponse | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  // 서버 상태가 바뀌면(첫 로드·저장 성공) 폼을 재동기화 — 렌더 중 파생 상태 갱신(React 권장 패턴)
  if (settings.data && settings.data !== syncedFrom) {
    setSyncedFrom(settings.data);
    setForm(fromResponse(settings.data));
  }

  const visionModels = useMemo(
    () => (models.data ?? []).filter((m) => m.is_active && m.supports_vision === true),
    [models.data]
  );

  const errors = useMemo(() => {
    if (!form) return {} as Partial<Record<NumericKey, string>>;
    const out: Partial<Record<NumericKey, string>> = {};
    for (const f of NUMERIC_FIELDS) {
      const msg = validateMultimodalNumeric(f.key, form[f.key], f.integer);
      if (msg) out[f.key] = msg;
    }
    return out;
  }, [form]);

  const isDirty = useMemo(
    () => !!form && !!settings.data && JSON.stringify(form) !== JSON.stringify(fromResponse(settings.data)),
    [form, settings.data]
  );
  const hasErrors = Object.keys(errors).length > 0;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setSaved(false);
    setSaveError(null);
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const onSave = async () => {
    if (!form || hasErrors) return;
    setSaveError(null);
    try {
      await update.mutateAsync(toRequest(form));
      setSaved(true);
    } catch (err) {
      setSaveError(getErrorMessage(err, '저장에 실패했습니다.'));
    }
  };

  const onTest = async () => {
    setTestError(null);
    setTestResult(null);
    try {
      setTestResult(await test.mutateAsync(null));
    } catch (err) {
      setTestError(getErrorMessage(err, '연결 테스트에 실패했습니다.'));
    }
  };

  if (settings.isLoading || !form) {
    return <p className="text-[13px] text-zinc-500">설정을 불러오는 중…</p>;
  }
  if (settings.isError) {
    return (
      <p className="text-[13px] text-red-500">
        {getErrorMessage(settings.error, '설정을 불러오지 못했습니다.')}
      </p>
    );
  }

  const warnings = settings.data?.warnings ?? [];

  return (
    <div className="space-y-5">
      {warnings.length > 0 && (
        <div
          role="alert"
          className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-700"
        >
          {warnings.map((w) => (
            <div key={w}>⚠ {w}</div>
          ))}
        </div>
      )}

      <section className="rounded-2xl border border-zinc-200 bg-white p-5">
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-3 text-[14px] font-medium text-zinc-800">
            <input
              type="checkbox"
              role="switch"
              aria-label="활성화"
              checked={form.enabled}
              onChange={(e) => set('enabled', e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-violet-600"
            />
            멀티모달 추출 활성화
          </label>
        </div>

        <div className="mt-5">
          <label htmlFor="mm-vision-model" className={labelCls}>
            비전 모델
          </label>
          <select
            id="mm-vision-model"
            value={form.vision_model_id}
            onChange={(e) => set('vision_model_id', e.target.value)}
            className={inputCls}
          >
            <option value="">— 미선택 —</option>
            {visionModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name} ({m.provider}/{m.model_name})
              </option>
            ))}
          </select>
          {visionModels.length === 0 && !models.isLoading && (
            <p className="mt-1 text-[12px] text-zinc-500">
              비전 지원 모델을 먼저 등록하세요.{' '}
              <Link to="/admin/llm-models" className="text-violet-600 underline">
                LLM 모델 관리로 이동
              </Link>
            </p>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white p-5">
        <h3 className="mb-4 text-[13px] font-semibold text-zinc-800">비용 가드</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {NUMERIC_FIELDS.map((f) => {
            const lim = MULTIMODAL_LIMITS[f.key];
            return (
              <div key={f.key}>
                <label htmlFor={`mm-${f.key}`} className={labelCls}>
                  {f.label}
                </label>
                <input
                  id={`mm-${f.key}`}
                  type="number"
                  inputMode={f.integer ? 'numeric' : 'decimal'}
                  min={lim.min}
                  max={lim.max}
                  step={'step' in lim ? lim.step : 1}
                  value={form[f.key]}
                  onChange={(e) => set(f.key, e.target.value)}
                  aria-invalid={!!errors[f.key]}
                  className={inputCls}
                />
                {errors[f.key] ? (
                  <p className="mt-1 text-[12px] text-red-500">{errors[f.key]}</p>
                ) : (
                  f.hint && <p className="mt-1 text-[12px] text-zinc-400">{f.hint}</p>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white p-5">
        <h3 className="mb-4 text-[13px] font-semibold text-zinc-800">출력</h3>
        <div className="flex flex-wrap gap-8">
          <fieldset>
            <legend className={labelCls}>언어</legend>
            <div className="flex gap-4">
              {OUTPUT_LANGUAGES.map((lang) => (
                <label key={lang} className="flex items-center gap-2 text-[13px] text-zinc-700">
                  <input
                    type="radio"
                    name="output_language"
                    value={lang}
                    checked={form.output_language === lang}
                    onChange={() => set('output_language', lang)}
                  />
                  {lang === 'ko' ? '한국어 (ko)' : 'English (en)'}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className={labelCls}>상세도</legend>
            <div className="flex gap-4">
              {DETAIL_LEVELS.map((lv) => (
                <label key={lv} className="flex items-center gap-2 text-[13px] text-zinc-700">
                  <input
                    type="radio"
                    name="detail_level"
                    value={lv}
                    checked={form.detail_level === lv}
                    onChange={() => set('detail_level', lv)}
                  />
                  {lv === 'brief' ? '간략 (brief)' : '상세 (detailed)'}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <LoadingButton
          isPending={update.isPending}
          pendingText="저장 중…"
          disabled={!isDirty || hasErrors}
          onClick={onSave}
          className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white disabled:opacity-50"
        >
          저장
        </LoadingButton>
        <LoadingButton
          isPending={test.isPending}
          pendingText="호출 중…"
          onClick={onTest}
          className="rounded-xl border border-zinc-300 px-4 py-2 text-[13px] font-medium text-zinc-700 hover:bg-zinc-50"
        >
          연결 테스트
        </LoadingButton>
        {isDirty && !saved && (
          <span className="text-[12px] text-zinc-400">저장되지 않은 변경이 있습니다. 연결 테스트는 저장된 설정으로 실행됩니다.</span>
        )}
        {saved && <span className="text-[12px] text-emerald-600">저장되었습니다.</span>}
        {saveError && <span className="text-[12px] text-red-500">{saveError}</span>}
      </div>

      {testError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-600">
          {testError}
        </div>
      )}
      {testResult && (
        <div
          data-testid="mm-test-result"
          className={`rounded-xl border px-4 py-3 text-[13px] ${
            testResult.ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'
          }`}
        >
          <div className="flex flex-wrap items-center gap-2 font-medium">
            {testResult.ok ? '연결 성공' : '연결 실패'}
            <span className="font-normal text-zinc-600">
              {testResult.provider}/{testResult.model_name} · {testResult.elapsed_ms}ms
            </span>
            {testResult.degraded_output_mode && (
              <span className="rounded-md bg-orange-100 px-2 py-0.5 text-[11px] text-orange-700">degraded</span>
            )}
          </div>
          {testResult.ok && testResult.draft && (
            <p className="mt-1 text-zinc-700">
              [{testResult.draft.detected_type}] {testResult.draft.description.slice(0, 200)}
            </p>
          )}
          {!testResult.ok && testResult.error && <p className="mt-1">{testResult.error}</p>}
        </div>
      )}
    </div>
  );
};

export default MultimodalSettingsForm;
