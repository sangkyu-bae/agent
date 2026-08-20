interface QuestionOptionItemProps {
  /** radio group name — 같은 질문의 옵션들이 공유 (질문 id 권장) */
  name: string;
  label: string;
  selected: boolean;
  disabled?: boolean;
  compact?: boolean;
  onSelect: () => void;
}

/**
 * Design Ref: question-card §5.1 — 전체 폭 라디오 행 (제어 컴포넌트).
 * 네이티브 <input type="radio">를 시각적으로만 숨겨 접근성·키보드 조작을 유지한다.
 */
const QuestionOptionItem = ({
  name,
  label,
  selected,
  disabled = false,
  compact = false,
  onSelect,
}: QuestionOptionItemProps) => (
  <label
    className={`flex w-full items-center gap-3 rounded-xl border bg-white transition-colors ${
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
);

export default QuestionOptionItem;
