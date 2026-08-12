// doc-generator Design §5-2: 문서 유형 편집기 (이름·설명·섹션·포맷·MCP 도구)
import type {
  DocumentGeneratorDraft,
  GeneratorOutputFormat,
} from '@/types/documentGenerator';
import {
  EMPTY_GENERATOR_DRAFT,
  MAX_SECTIONS,
  PDF_KOREAN_FONT_WARNING,
  SOURCE_GUIDANCE_NOTICE,
} from '@/types/documentGenerator';

interface DocumentGeneratorConfigPanelProps {
  draft: DocumentGeneratorDraft | null;
  onChange: (draft: DocumentGeneratorDraft) => void;
}

const inputClass =
  'w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] ' +
  'text-zinc-800 outline-none transition-colors focus:border-violet-400';

/**
 * 문서생성기 설정 패널. 로컬 검증만 수행(빈 제목 행은 저장 유틸이 아니라
 * 백엔드 SectionPolicy가 최종 차단) — 저장은 에이전트 저장에 편승.
 */
const DocumentGeneratorConfigPanel = ({
  draft,
  onChange,
}: DocumentGeneratorConfigPanelProps) => {
  const value = draft ?? EMPTY_GENERATOR_DRAFT;

  const patch = (partial: Partial<DocumentGeneratorDraft>) =>
    onChange({ ...value, ...partial });

  const patchSection = (
    index: number,
    field: 'title' | 'guidance',
    text: string,
  ) => {
    const sections = value.sections.map((s, i) =>
      i === index ? { ...s, [field]: text } : s,
    );
    patch({ sections });
  };

  const addSection = () => {
    if (value.sections.length >= MAX_SECTIONS) return;
    patch({ sections: [...value.sections, { title: '', guidance: '' }] });
  };

  const removeSection = (index: number) =>
    patch({ sections: value.sections.filter((_, i) => i !== index) });

  const moveSection = (index: number, delta: -1 | 1) => {
    const target = index + delta;
    if (target < 0 || target >= value.sections.length) return;
    const sections = [...value.sections];
    [sections[index], sections[target]] = [sections[target], sections[index]];
    patch({ sections });
  };

  return (
    <div className="space-y-5">
      {/* 유형 이름/설명 */}
      <div className="space-y-3">
        <div>
          <label htmlFor="docgen-name" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
            문서 유형명
          </label>
          <input
            id="docgen-name"
            type="text"
            value={value.name}
            maxLength={100}
            placeholder="예: 시장조사 보고서"
            onChange={(e) => patch({ name: e.target.value })}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="docgen-description" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
            용도 설명 (선택)
          </label>
          <textarea
            id="docgen-description"
            value={value.description}
            maxLength={500}
            rows={2}
            placeholder="이 문서가 언제, 무엇을 위해 작성되는지"
            onChange={(e) => patch({ description: e.target.value })}
            className={inputClass}
          />
        </div>
      </div>

      {/* 섹션 아웃라인 */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[12.5px] font-semibold text-zinc-600">
            섹션 아웃라인 ({value.sections.length}/{MAX_SECTIONS})
          </span>
          <button
            type="button"
            onClick={addSection}
            disabled={value.sections.length >= MAX_SECTIONS}
            className="rounded-lg bg-zinc-900 px-2.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            + 섹션 추가
          </button>
        </div>
        {value.sections.length === 0 ? (
          <p className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-4 text-center text-[12.5px] text-zinc-400">
            섹션을 추가해 문서 뼈대를 정의하세요 (예: 개요 → 현황 → 시사점)
          </p>
        ) : (
          <ul className="space-y-2">
            {value.sections.map((section, index) => (
              <li
                key={index}
                className="rounded-xl border border-zinc-200 bg-white p-3"
              >
                <div className="flex items-center gap-2">
                  <span className="w-5 shrink-0 text-center text-[12px] font-semibold text-zinc-400">
                    {index + 1}
                  </span>
                  <input
                    type="text"
                    value={section.title}
                    maxLength={100}
                    placeholder="섹션 제목"
                    aria-label={`섹션 ${index + 1} 제목`}
                    onChange={(e) => patchSection(index, 'title', e.target.value)}
                    className={inputClass}
                  />
                  <button
                    type="button"
                    onClick={() => moveSection(index, -1)}
                    disabled={index === 0}
                    aria-label={`섹션 ${index + 1} 위로`}
                    className="rounded-lg px-1.5 py-1 text-[12px] text-zinc-400 hover:bg-zinc-100 disabled:opacity-30"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => moveSection(index, 1)}
                    disabled={index === value.sections.length - 1}
                    aria-label={`섹션 ${index + 1} 아래로`}
                    className="rounded-lg px-1.5 py-1 text-[12px] text-zinc-400 hover:bg-zinc-100 disabled:opacity-30"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    onClick={() => removeSection(index)}
                    aria-label={`섹션 ${index + 1} 삭제`}
                    className="rounded-lg px-2 py-1 text-[12px] font-medium text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
                  >
                    삭제
                  </button>
                </div>
                <textarea
                  value={section.guidance}
                  maxLength={500}
                  rows={1}
                  placeholder="작성 지침 (선택) — 예: 웹서치 근거 위주로 최근 동향 정리"
                  aria-label={`섹션 ${index + 1} 지침`}
                  onChange={(e) => patchSection(index, 'guidance', e.target.value)}
                  className={`${inputClass} mt-2`}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 출력 포맷 (D4: DOCX 기본 + PDF 경고) */}
      <div>
        <span className="mb-2 block text-[12.5px] font-semibold text-zinc-600">출력 포맷</span>
        <div className="flex gap-4">
          {(['docx', 'pdf'] as GeneratorOutputFormat[]).map((fmt) => (
            <label key={fmt} className="flex items-center gap-1.5 text-[13px] text-zinc-700">
              <input
                type="radio"
                name="docgen-output-format"
                value={fmt}
                checked={value.outputFormat === fmt}
                onChange={() => patch({ outputFormat: fmt })}
              />
              {fmt === 'docx' ? 'Word (DOCX) — 권장' : 'PDF'}
            </label>
          ))}
        </div>
        {value.outputFormat === 'pdf' && (
          <p className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-700">
            ⚠ {PDF_KOREAN_FONT_WARNING}
          </p>
        )}
      </div>

      {/* MCP 변환 도구 (D5: 미지정 시 서버 기본값) */}
      <div>
        <label htmlFor="docgen-mcp-tool" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
          변환 MCP 도구 id (선택)
        </label>
        <input
          id="docgen-mcp-tool"
          type="text"
          value={value.mcpHtmlToDocToolId}
          placeholder="비워두면 서버 기본값 사용"
          onChange={(e) => patch({ mcpHtmlToDocToolId: e.target.value })}
          className={inputClass}
        />
      </div>

      {/* 근거 소스 안내 (D1·D3) */}
      <p className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-[12.5px] leading-[1.6] text-zinc-500">
        {SOURCE_GUIDANCE_NOTICE}
      </p>
    </div>
  );
};

export default DocumentGeneratorConfigPanel;
