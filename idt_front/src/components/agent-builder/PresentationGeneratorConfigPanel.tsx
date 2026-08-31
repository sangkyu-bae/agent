// golden-sample-blueprint Design §5.4 — 발표자료생성기 워커 설정 (blueprint·포맷·MCP·상한)
import { useBlueprintOptions } from '@/hooks/useBlueprints';
import {
  EMPTY_PRESENTATION_DRAFT,
  MAX_SLIDES_LIMIT,
  type PresentationGeneratorDraft,
  type PresentationOutputFormat,
} from '@/types/presentationGenerator';
import { validatePresentationDraft } from '@/utils/presentationGenerator';

interface PresentationGeneratorConfigPanelProps {
  draft: PresentationGeneratorDraft | null;
  onChange: (draft: PresentationGeneratorDraft) => void;
}

const inputClass =
  'w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] ' +
  'text-zinc-800 outline-none transition-colors focus:border-violet-400';

/**
 * 발표자료생성기 설정 패널 (DocumentGeneratorConfigPanel 동형).
 * 로컬 검증만 — 최종 검증은 백엔드 PresentationGeneratorToolConfig. 저장은 에이전트 저장에 편승.
 */
const PresentationGeneratorConfigPanel = ({
  draft,
  onChange,
}: PresentationGeneratorConfigPanelProps) => {
  const value = draft ?? EMPTY_PRESENTATION_DRAFT;
  const options = useBlueprintOptions();
  const patch = (partial: Partial<PresentationGeneratorDraft>) => onChange({ ...value, ...partial });
  const error = validatePresentationDraft(value);

  return (
    <div className="space-y-5">
      <div>
        <label htmlFor="ppt-blueprint" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
          양식 (blueprint)
        </label>
        <select
          id="ppt-blueprint"
          value={value.blueprintId}
          onChange={(e) => patch({ blueprintId: e.target.value })}
          className={inputClass}
          disabled={options.isLoading}
        >
          <option value="">선택하세요</option>
          {(options.data?.items ?? []).map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
        {options.isError && (
          <p role="alert" className="mt-1 text-[12px] text-red-600">
            {options.error.message}
          </p>
        )}
        {options.data && options.data.items.length === 0 && (
          <p className="mt-1 text-[12px] text-amber-600">
            등록된 양식이 없습니다.{' '}
            <a href="/admin/blueprints" className="underline">
              /admin/blueprints
            </a>
            에서 Golden Sample 을 먼저 등록하세요.
          </p>
        )}
      </div>

      <fieldset>
        <legend className="mb-1 text-[12.5px] font-semibold text-zinc-600">출력 포맷</legend>
        <div className="flex gap-4 text-[13px] text-zinc-700">
          {(['pptx', 'pdf'] as PresentationOutputFormat[]).map((f) => (
            <label key={f} className="flex items-center gap-1.5">
              <input
                type="radio"
                name="ppt-output-format"
                value={f}
                checked={value.outputFormat === f}
                onChange={() => patch({ outputFormat: f })}
              />
              {f.toUpperCase()}
            </label>
          ))}
        </div>
      </fieldset>

      {value.outputFormat === 'pdf' && (
        <div>
          <label htmlFor="ppt-mcp" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
            PPTX→PDF 변환 MCP 도구 id (선택)
          </label>
          <input
            id="ppt-mcp"
            value={value.mcpPptxToPdfToolId}
            placeholder="mcp_... (빈 값이면 PPTX 만 제공)"
            onChange={(e) => patch({ mcpPptxToPdfToolId: e.target.value })}
            className={inputClass}
          />
        </div>
      )}

      <div>
        <label htmlFor="ppt-max-slides" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
          최대 슬라이드 수 ({MAX_SLIDES_LIMIT.min}~{MAX_SLIDES_LIMIT.max})
        </label>
        <input
          id="ppt-max-slides"
          type="number"
          min={MAX_SLIDES_LIMIT.min}
          max={MAX_SLIDES_LIMIT.max}
          value={value.maxSlides}
          onChange={(e) => patch({ maxSlides: Number(e.target.value) })}
          className={inputClass}
        />
      </div>

      {error && (
        <p role="alert" className="text-[12px] text-red-600">
          {error}
        </p>
      )}
    </div>
  );
};

export default PresentationGeneratorConfigPanel;
