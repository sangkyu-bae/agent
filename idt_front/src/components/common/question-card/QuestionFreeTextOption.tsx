interface QuestionFreeTextOptionProps {
  /** radio group name — 같은 질문의 옵션들과 공유 */
  name: string;
  /** 행 레이블 — 기본값은 목표 디자인(ask.png)의 문구 */
  label?: string;
  selected: boolean;
  disabled?: boolean;
  compact?: boolean;
  /** 입력 텍스트 — 미선택 시에도 보존된다 */
  value: string;
  /** 확장 입력의 aria-label — 여러 카드가 공존할 때 질문별로 구분 */
  inputAriaLabel?: string;
  onSelect: () => void;
  onChange: (value: string) => void;
}

/**
 * Design Ref: question-card §5.1 — "직접 입력" 라디오 행.
 * 선택 시에만 행 아래로 텍스트 입력이 확장되고, 해제해도 입력값은 보존된다.
 * (기본 레이블은 default parameter — .tsx 런타임 상수 export 금지 규칙)
 */
const QuestionFreeTextOption = ({
  name,
  label = '직접 입력 (원하는 내용을 자유롭게 작성)',
  selected,
  disabled = false,
  compact = false,
  value,
  inputAriaLabel = '직접 입력',
  onSelect,
  onChange,
}: QuestionFreeTextOptionProps) => (
  <div>
    <label
      // relative 필수 — sr-only(absolute) 라디오의 클리핑 탈출 방지
      // (QuestionOptionItem 의 상세 주석 참조).
      className={`relative flex w-full items-center gap-3 rounded-xl border bg-white transition-colors ${
        compact ? 'px-3 py-2.5 text-[13px]' : 'px-4 py-3.5 text-[14px]'
      } ${
        selected
          ? 'border-violet-400 bg-violet-50/60 text-zinc-900'
          : 'border-zinc-200 text-zinc-700'
      } ${
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:border-violet-300'
      }`}
    >
      <input
        type="radio"
        name={name}
        checked={selected}
        disabled={disabled}
        onChange={onSelect}
        className="sr-only"
      />
      <span
        aria-hidden="true"
        className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border-2 bg-white ${
          selected ? 'border-violet-500' : 'border-zinc-300'
        }`}
      >
        {selected && <span className="h-2 w-2 rounded-full bg-violet-500" />}
      </span>
      <span>{label}</span>
    </label>

    {selected && (
      <input
        type="text"
        value={value}
        disabled={disabled}
        // Design §5.1 — 선택으로 확장되는 순간에만 마운트되므로 autoFocus가 그 시점에 동작
        autoFocus
        onChange={(e) => onChange(e.target.value)}
        placeholder="원하는 내용을 입력하세요"
        aria-label={inputAriaLabel}
        className={`mt-2 block w-full rounded-lg border border-zinc-300 bg-white placeholder-zinc-400 outline-none transition-colors focus:border-violet-400 disabled:cursor-not-allowed disabled:bg-zinc-50 ${
          compact ? 'px-2.5 py-1.5 text-[12.5px]' : 'px-3 py-2 text-[13.5px]'
        }`}
      />
    )}
  </div>
);

export default QuestionFreeTextOption;
