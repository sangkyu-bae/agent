/**
 * 커스텀 청킹 파라미터 입력 폼 (kb-custom-chunking Design §6.1, §6.3)
 *
 * 전략 select + 크기/오버랩 입력 + (boundary_pattern) 정규식 규칙 편집.
 * 전략 전환 시 미지원 필드는 숨김 + 값 초기화(resetForStrategy).
 */
import Dropdown from '@/components/common/Dropdown';
import type { ChunkingStrategy } from '@/types/knowledgeBase';
import {
  STRATEGY_OPTIONS,
  isValidRegex,
  resetForStrategy,
  supportsBoundaryRules,
  supportsMinSize,
  supportsOverlap,
  supportsParentSize,
  type CustomChunkingFormState,
} from './customChunkingForm';

interface CustomChunkingFieldsProps {
  value: CustomChunkingFormState;
  onChange: (next: CustomChunkingFormState) => void;
}

const inputClass =
  'w-full rounded-lg border border-zinc-300 px-3 py-2 text-[13.5px] ' +
  'text-zinc-900 placeholder-zinc-400 outline-none transition-all ' +
  'focus:border-violet-400';

const labelClass = 'mb-1 block text-[12px] font-medium text-zinc-500';

const CustomChunkingFields = ({
  value,
  onChange,
}: CustomChunkingFieldsProps) => {
  const strategyMeta = STRATEGY_OPTIONS.find(
    (o) => o.value === value.strategy,
  );

  const setRule = (
    index: number,
    patch: Partial<CustomChunkingFormState['rules'][number]>,
  ) => {
    const rules = value.rules.map((r, i) =>
      i === index ? { ...r, ...patch } : r,
    );
    onChange({ ...value, rules });
  };

  return (
    <div className="space-y-3 rounded-xl border border-zinc-200 bg-zinc-50 p-3">
      <div>
        <label htmlFor="custom-chunking-strategy" className={labelClass}>
          청킹 전략
        </label>
        <Dropdown
          id="custom-chunking-strategy"
          ariaLabel="청킹 전략"
          value={value.strategy}
          onChange={(s) =>
            onChange(resetForStrategy(value, s as ChunkingStrategy))
          }
          options={STRATEGY_OPTIONS.map((o) => ({
            value: o.value,
            label: o.label,
          }))}
          className="w-full"
        />
        {strategyMeta && (
          <p className="mt-1 text-[12px] text-zinc-400">
            {strategyMeta.description}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="custom-chunk-size" className={labelClass}>
            청크 크기 (100~4000)
          </label>
          <input
            id="custom-chunk-size"
            type="number"
            value={value.chunkSize}
            onChange={(e) =>
              onChange({ ...value, chunkSize: e.target.value })
            }
            className={inputClass}
          />
        </div>
        {supportsOverlap(value.strategy) && (
          <div>
            <label htmlFor="custom-chunk-overlap" className={labelClass}>
              오버랩 (0~500)
            </label>
            <input
              id="custom-chunk-overlap"
              type="number"
              value={value.chunkOverlap}
              onChange={(e) =>
                onChange({ ...value, chunkOverlap: e.target.value })
              }
              className={inputClass}
            />
          </div>
        )}
        {supportsParentSize(value.strategy) && (
          <div>
            <label htmlFor="custom-parent-size" className={labelClass}>
              부모 청크 크기 (선택, 100~8000)
            </label>
            <input
              id="custom-parent-size"
              type="number"
              value={value.parentChunkSize}
              onChange={(e) =>
                onChange({ ...value, parentChunkSize: e.target.value })
              }
              placeholder="기본 2000"
              className={inputClass}
            />
          </div>
        )}
        {supportsMinSize(value.strategy) && (
          <div>
            <label htmlFor="custom-min-size" className={labelClass}>
              최소 청크 크기 (선택, 50~2000)
            </label>
            <input
              id="custom-min-size"
              type="number"
              value={value.minChunkSize}
              onChange={(e) =>
                onChange({ ...value, minChunkSize: e.target.value })
              }
              placeholder="전략 기본값"
              className={inputClass}
            />
          </div>
        )}
      </div>

      {supportsBoundaryRules(value.strategy) && (
        <div>
          <p className={labelClass}>
            경계 규칙 (parent 레벨 1개 이상 필수)
          </p>
          <div className="space-y-2">
            {value.rules.map((rule, i) => (
              <div key={i}>
                <div className="flex items-center gap-2">
                  <select
                    aria-label={`규칙 ${i + 1} 레벨`}
                    value={rule.level}
                    onChange={(e) =>
                      setRule(i, {
                        level: e.target.value as 'parent' | 'child',
                      })
                    }
                    className="rounded-lg border border-zinc-300 px-2 py-2 text-[12.5px] text-zinc-700 outline-none"
                  >
                    <option value="parent">parent</option>
                    <option value="child">child</option>
                  </select>
                  <input
                    aria-label={`규칙 ${i + 1} 정규식`}
                    type="text"
                    value={rule.pattern}
                    onChange={(e) => setRule(i, { pattern: e.target.value })}
                    placeholder="^제\d+조"
                    className={`${inputClass} flex-1 font-mono`}
                  />
                  <input
                    aria-label={`규칙 ${i + 1} 우선순위`}
                    type="number"
                    value={rule.priority}
                    onChange={(e) => setRule(i, { priority: e.target.value })}
                    className="w-16 rounded-lg border border-zinc-300 px-2 py-2 text-[13px] text-zinc-900 outline-none"
                  />
                  <button
                    type="button"
                    aria-label={`규칙 ${i + 1} 삭제`}
                    onClick={() =>
                      onChange({
                        ...value,
                        rules: value.rules.filter((_, j) => j !== i),
                      })
                    }
                    className="rounded-lg px-2 py-1.5 text-[13px] text-zinc-400 hover:bg-zinc-100 hover:text-red-500"
                  >
                    ✕
                  </button>
                </div>
                {rule.pattern.trim() !== '' &&
                  !isValidRegex(rule.pattern) && (
                    <p className="mt-1 text-[12px] text-red-500">
                      잘못된 정규식입니다
                    </p>
                  )}
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() =>
              onChange({
                ...value,
                rules: [
                  ...value.rules,
                  { pattern: '', priority: '1', level: 'parent' },
                ],
              })
            }
            className="mt-2 rounded-lg border border-dashed border-zinc-300 px-3 py-1.5 text-[12.5px] text-zinc-500 hover:border-violet-300 hover:text-violet-600"
          >
            + 규칙 추가
          </button>
        </div>
      )}
    </div>
  );
};

export default CustomChunkingFields;
