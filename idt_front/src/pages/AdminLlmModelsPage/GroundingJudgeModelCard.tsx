// Design Ref: answer-citation-verification §5.1·§5.4 — LLM 모델 관리 페이지 상단의 근거 판정 모델 카드.
// 관리자가 고른 모델이 답변 근거 판정과 인용 검증에 함께 쓰인다. "설정 안 함"이면 서버 환경 설정 모델.
import { useState } from 'react';
import { useLlmModels } from '@/hooks/useLlmModels';
import {
  useGroundingJudgeSetting,
  useUpdateGroundingJudgeSetting,
} from '@/hooks/useGroundingJudgeSetting';
import { JUDGE_MODEL_SOURCE_LABEL } from '@/types/groundingJudge';
import { filterChatModels } from '@/utils/llmModelKind';

const UNSET = '';

const errorMessage = (err: unknown): string =>
  err instanceof Error && err.message ? err.message : '판정 모델 저장에 실패했습니다.';

const GroundingJudgeModelCard = () => {
  const { data: setting, isLoading } = useGroundingJudgeSetting();
  const { data: models } = useLlmModels(false);
  const update = useUpdateGroundingJudgeSetting();
  // null = 사용자가 아직 바꾸지 않음 → 서버 값을 그대로 보여 준다
  const [draft, setDraft] = useState<string | null>(null);

  const saved = setting?.judge_llm_model_id ?? UNSET;
  const value = draft ?? saved;
  const dirty = draft !== null && draft !== saved;
  const options = filterChatModels(models).filter((m) => m.is_active);

  const handleSave = () => {
    update.mutate(
      { judge_llm_model_id: value === UNSET ? null : value },
      { onSuccess: () => setDraft(null) }
    );
  };

  return (
    <section className="mb-6 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold text-zinc-900">근거 판정 모델</h2>
          <p className="mt-1 text-[12.5px] text-zinc-500">
            답변 근거 판정과 인용 검증에 함께 쓰입니다. 판정 품질은 모델에 따라 크게 달라집니다
            (예: gpt-4o-mini는 근거가 있는 문장을 근거 없음으로 잘못 판정한 기록이 있습니다).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            aria-label="근거 판정 모델"
            value={value}
            disabled={isLoading || update.isPending}
            onChange={(e) => setDraft(e.target.value)}
            className="min-w-56 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] text-zinc-800 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          >
            <option value={UNSET}>설정 안 함 (서버 환경 설정 사용)</option>
            {options.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name} ({m.model_name})
              </option>
            ))}
          </select>
          <button
            type="button"
            aria-label="판정 모델 저장"
            onClick={handleSave}
            disabled={!dirty || update.isPending}
            className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {update.isPending ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
      {setting && (
        <p className="mt-3 text-[12.5px] text-zinc-600">
          {setting.effective ? (
            <>
              현재 적용:{' '}
              <strong className="font-semibold text-zinc-900">
                {`${setting.effective.display_name} · ${setting.effective.model_name}`}
              </strong>{' '}
              <span className="text-zinc-400">({JUDGE_MODEL_SOURCE_LABEL[setting.effective.source]})</span>
            </>
          ) : (
            '현재 적용: 판정 모델을 찾지 못했습니다. 활성 채팅 모델을 등록하세요.'
          )}
        </p>
      )}
      {update.isError && (
        <p role="alert" className="mt-2 text-[12.5px] text-red-600">
          {errorMessage(update.error)}
        </p>
      )}
    </section>
  );
};

export default GroundingJudgeModelCard;
