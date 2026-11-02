// Design Ref: image-generation-tool §5.1 — 이미지 생성 워커 설정 (모델·기본 크기·품질), 발표자료 패널 동형
import { useMemo } from 'react';
import { useLlmModels } from '@/hooks/useLlmModels';
import {
  EMPTY_IMAGE_GENERATION_DRAFT,
  IMAGE_QUALITY_OPTIONS,
  IMAGE_SIZE_OPTIONS,
  type ImageGenerationDraft,
} from '@/types/imageGeneration';
import { filterActiveImageModels } from '@/utils/llmModelKind';
import { validateImageGenerationDraft } from '@/utils/imageGeneration';

interface ImageGenerationConfigPanelProps {
  draft: ImageGenerationDraft | null;
  onChange: (draft: ImageGenerationDraft) => void;
}

const inputClass =
  'w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] ' +
  'text-zinc-800 outline-none transition-colors focus:border-violet-400';

/**
 * 이미지 생성 설정 패널 (PresentationGeneratorConfigPanel 동형).
 * 모델 후보는 model_kind==='image' && is_active 만 (Design §5.1 / D-05).
 * 로컬 검증만 — 최종 검증은 백엔드(IMAGE_MODEL_INVALID / IMAGE_CONFIG_INVALID). 저장은 에이전트 저장에 편승.
 */
const ImageGenerationConfigPanel = ({ draft, onChange }: ImageGenerationConfigPanelProps) => {
  const value = draft ?? EMPTY_IMAGE_GENERATION_DRAFT;
  const models = useLlmModels();
  const imageModels = useMemo(() => filterActiveImageModels(models.data), [models.data]);
  const selected = imageModels.find((m) => m.id === value.llmModelId);
  const patch = (partial: Partial<ImageGenerationDraft>) => onChange({ ...value, ...partial });
  const error = models.data ? validateImageGenerationDraft(value, { hasImageModels: imageModels.length > 0 }) : null;

  return (
    <div className="space-y-5">
      <div>
        <label htmlFor="img-gen-model" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
          이미지 모델
        </label>
        <select
          id="img-gen-model"
          value={value.llmModelId}
          onChange={(e) => patch({ llmModelId: e.target.value })}
          className={inputClass}
          disabled={models.isLoading || imageModels.length === 0}
        >
          <option value="">선택하세요</option>
          {imageModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name} ({m.provider})
            </option>
          ))}
        </select>
        {models.isError && (
          <p role="alert" className="mt-1 text-[12px] text-red-600">
            {models.error.message}
          </p>
        )}
      </div>

      <fieldset>
        <legend className="mb-1 text-[12.5px] font-semibold text-zinc-600">기본 크기</legend>
        <div className="flex flex-wrap gap-4 text-[13px] text-zinc-700">
          {IMAGE_SIZE_OPTIONS.map((opt) => (
            <label key={opt.value} className="flex items-center gap-1.5">
              <input
                type="radio"
                name="img-gen-size"
                value={opt.value}
                checked={value.defaultSize === opt.value}
                onChange={() => patch({ defaultSize: opt.value })}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-1 text-[12.5px] font-semibold text-zinc-600">품질</legend>
        <div className="flex gap-4 text-[13px] text-zinc-700">
          {IMAGE_QUALITY_OPTIONS.map((opt) => (
            <label key={opt.value} className="flex items-center gap-1.5">
              <input
                type="radio"
                name="img-gen-quality"
                value={opt.value}
                checked={value.quality === opt.value}
                onChange={() => patch({ quality: opt.value })}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </fieldset>

      <p className="rounded-lg bg-zinc-50 px-3 py-2 text-[12px] text-zinc-500">
        단가{' '}
        {selected?.price_per_image_usd != null ? `$${selected.price_per_image_usd}/장` : '미설정(비용 0 으로 기록)'}
        {' · '}턴당 최대 생성 장수는 서버 설정을 따릅니다. 이번 턴에 첨부한 이미지가 있으면 편집 요청에 사용됩니다.
      </p>

      {error && (
        <p role="alert" className="text-[12px] text-amber-600">
          {error}
        </p>
      )}
    </div>
  );
};

export default ImageGenerationConfigPanel;
