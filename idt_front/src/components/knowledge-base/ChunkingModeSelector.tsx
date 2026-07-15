/**
 * 청킹 방식 radio 3택 (kb-custom-chunking Design §6.1)
 *
 * 기본/조항/커스텀을 radio로 표현해 use_clause_chunking과
 * use_custom_chunking의 동시 활성(V-07)을 UI에서 원천 차단한다.
 */
import CustomChunkingFields from './CustomChunkingFields';
import type { CustomChunkingFormState } from './customChunkingForm';

export type ChunkingMode = 'default' | 'clause' | 'custom';

const MODE_OPTIONS: {
  value: ChunkingMode;
  label: string;
  description: string;
}[] = [
  {
    value: 'default',
    label: '기본 청킹',
    description: 'Parent-Child 2000/500/50 (시스템 기본값)',
  },
  {
    value: 'clause',
    label: '조항 단위 청킹',
    description: '규정/내규 문서를 조·항 경계로 분할합니다',
  },
  {
    value: 'custom',
    label: '커스텀 청킹',
    description: '전략·크기·오버랩·경계 정규식을 직접 설정합니다',
  },
];

interface ChunkingModeSelectorProps {
  mode: ChunkingMode;
  onModeChange: (mode: ChunkingMode) => void;
  customForm: CustomChunkingFormState;
  onCustomFormChange: (form: CustomChunkingFormState) => void;
}

const ChunkingModeSelector = ({
  mode,
  onModeChange,
  customForm,
  onCustomFormChange,
}: ChunkingModeSelectorProps) => (
  <div className="space-y-2">
    {MODE_OPTIONS.map((option) => (
      <label
        key={option.value}
        className="flex cursor-pointer items-center gap-2.5"
      >
        <input
          type="radio"
          name="kb-chunking-mode"
          value={option.value}
          checked={mode === option.value}
          onChange={() => onModeChange(option.value)}
          className="h-4 w-4 accent-violet-600"
        />
        <span className="text-[13px] text-zinc-700">{option.label}</span>
        <span className="text-[12px] text-zinc-400">
          {option.description}
        </span>
      </label>
    ))}
    {mode === 'custom' && (
      <CustomChunkingFields
        value={customForm}
        onChange={onCustomFormChange}
      />
    )}
  </div>
);

export default ChunkingModeSelector;
