// Design Ref: agent-token-limit §5.3 D12 — 반복 한도·토큰 예산이 공유하는 숫자 입력.
// 입력은 로컬 문자열로 자유 타이핑을 허용하고 blur/Enter 확정 시점에 [min, max]로
// clamp한다. 빈 값·비숫자는 이전 값 복원 (agent-settings-tab Design D2·D3 규칙 유지).
import { useEffect, useState } from 'react';

interface LimitNumberFieldProps {
  id: string;
  label: string;
  /** 확정된 현재 값 (상위 폼이 단일 진실원) */
  value: number;
  min: number;
  max: number;
  defaultValue: number;
  /** clamp 완료된 값만 올라온다 — 상위는 검증 불필요 */
  onChange: (value: number) => void;
  /** 기본값 안내 뒤에 붙는 보조 문장 */
  hint?: string;
}

const LimitNumberField = ({
  id,
  label,
  value,
  min,
  max,
  defaultValue,
  onChange,
  hint,
}: LimitNumberFieldProps) => {
  const [draft, setDraft] = useState(String(value));

  // 상위 값 변경(edit 프라임·복원 버튼) 시 로컬 입력 동기화
  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const commitDraft = () => {
    const parsed = Number.parseInt(draft, 10);
    if (Number.isNaN(parsed)) {
      setDraft(String(value));
      return;
    }
    const clamped = Math.min(max, Math.max(min, parsed));
    setDraft(String(clamped));
    onChange(clamped);
  };

  return (
    <div className="mt-3">
      <label htmlFor={id} className="text-[13px] font-semibold text-zinc-700">
        {label}
      </label>
      <div className="mt-1.5 flex items-center gap-2">
        <input
          id={id}
          type="number"
          value={draft}
          min={min}
          max={max}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitDraft}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitDraft();
          }}
          className="w-28 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-[13px] text-zinc-900 outline-none transition-colors focus:border-violet-400"
        />
        <button
          type="button"
          aria-label="기본값으로 복원"
          title="기본값으로 복원"
          onClick={() => onChange(defaultValue)}
          className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3" />
          </svg>
        </button>
        <span className="text-[12px] text-zinc-400">
          (범위: {min} - {max})
        </span>
      </div>
      <p className="mt-2 text-[12px] text-zinc-400">
        기본값: {defaultValue}.{hint ? ` ${hint}` : ''}
      </p>
    </div>
  );
};

export default LimitNumberField;
