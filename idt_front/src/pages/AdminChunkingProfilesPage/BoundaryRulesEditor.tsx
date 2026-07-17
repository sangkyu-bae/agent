import { isValidRegex } from '@/components/knowledge-base/customChunkingForm';
import type { BoundaryRule, BoundaryRuleLevel } from '@/types/chunkingProfile';

const rowInputCls =
  'w-full rounded-lg border px-3 py-2 text-[13px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:ring-2 focus:ring-violet-100';

interface BoundaryRulesEditorProps {
  rules: BoundaryRule[];
  onChange: (rules: BoundaryRule[]) => void;
}

/** 경계 규칙(pattern·priority·level) 행 편집기 (Design D5) */
const BoundaryRulesEditor = ({ rules, onChange }: BoundaryRulesEditorProps) => {
  const update = (index: number, patch: Partial<BoundaryRule>) =>
    onChange(rules.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  const remove = (index: number) =>
    onChange(rules.filter((_, i) => i !== index));
  const add = () =>
    onChange([...rules, { pattern: '', priority: 1, level: 'child' }]);

  return (
    <div className="space-y-2">
      {rules.length === 0 && (
        <p className="rounded-lg bg-zinc-50 px-3 py-2 text-[12.5px] text-zinc-400">
          규칙이 없습니다. 조항 경계 정규식을 추가하세요.
        </p>
      )}
      {rules.map((rule, i) => {
        const invalid = rule.pattern !== '' && !isValidRegex(rule.pattern);
        return (
          <div key={i} className="flex items-start gap-2">
            <div className="flex-1">
              <input
                type="text"
                value={rule.pattern}
                onChange={(e) => update(i, { pattern: e.target.value })}
                placeholder="예: ^제\s*\d+\s*조"
                aria-label={`규칙 ${i + 1} 패턴`}
                className={`${rowInputCls} font-mono ${
                  invalid
                    ? 'border-red-300 focus:border-red-400'
                    : 'border-zinc-300 focus:border-violet-400'
                }`}
              />
              {invalid && (
                <p className="mt-1 text-[12px] text-red-500">
                  유효하지 않은 정규식
                </p>
              )}
            </div>
            <input
              type="number"
              value={rule.priority}
              onChange={(e) =>
                update(i, { priority: Number(e.target.value) || 1 })
              }
              min={1}
              aria-label={`규칙 ${i + 1} 우선순위`}
              className={`${rowInputCls} w-20 border-zinc-300 focus:border-violet-400`}
            />
            <select
              value={rule.level}
              onChange={(e) =>
                update(i, { level: e.target.value as BoundaryRuleLevel })
              }
              aria-label={`규칙 ${i + 1} 레벨`}
              className={`${rowInputCls} w-28 border-zinc-300 focus:border-violet-400`}
            >
              <option value="parent">parent</option>
              <option value="child">child</option>
            </select>
            <button
              type="button"
              onClick={() => remove(i)}
              aria-label={`규칙 ${i + 1} 삭제`}
              className="mt-1 rounded-lg p-1.5 text-zinc-400 transition-all hover:bg-red-50 hover:text-red-500"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        );
      })}
      <button
        type="button"
        onClick={add}
        aria-label="규칙 추가"
        className="rounded-lg border border-dashed border-zinc-300 px-3 py-1.5 text-[12.5px] font-medium text-zinc-500 transition-all hover:border-violet-300 hover:text-violet-600"
      >
        + 규칙 추가
      </button>
    </div>
  );
};

export default BoundaryRulesEditor;
