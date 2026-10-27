// Design Ref: agent-opener §5.1 — 오프너 탭. 폼 staged(openers 배열)만 편집하고
// 저장은 StudioHeader 저장 버튼에 통합된다(탭 내 저장 없음). 빈 행은 저장 시
// 페이지가 조용히 제거한다. 상한 상수는 constants/agentOpener.ts (백엔드 미러).
import { useEffect, useRef, useState } from 'react';
import { Plus, X } from 'lucide-react';
import Button from '@/components/ui/Button';
import IconButton from '@/components/ui/IconButton';
import { OPENER_LIMITS } from '@/constants/agentOpener';

interface OpenerPanelProps {
  /** form.openers — 단일 진실원 (빈 행 포함 가능) */
  openers: string[];
  onChange: (next: string[]) => void;
}

interface OpenerRowProps {
  index: number;
  value: string;
  autoFocus: boolean;
  onChange: (value: string) => void;
  onRemove: () => void;
}

const OpenerRow = ({ index, value, autoFocus, onChange, onRemove }: OpenerRowProps) => {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  return (
    <li className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 shadow-sm transition-colors duration-150 focus-within:border-brand-200">
      <span
        aria-hidden="true"
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-xs font-medium text-fg-muted"
      >
        {index + 1}
      </span>
      <input
        ref={inputRef}
        type="text"
        value={value}
        maxLength={OPENER_LIMITS.MAX_LENGTH}
        placeholder="예시 질문을 입력하세요"
        aria-label={`오프너 ${index + 1}`}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 flex-1 bg-transparent text-base text-fg outline-none placeholder:text-fg-subtle"
      />
      <IconButton aria-label={`오프너 ${index + 1} 삭제`} size="sm" tone="danger" onClick={onRemove}>
        <X className="h-4 w-4" strokeWidth={1.75} />
      </IconButton>
    </li>
  );
};

/**
 * 오프너(대화 시작 예시 질문) 편집 패널.
 * 안내문 + `n/12` 카운터 + 추가 버튼 + 번호 배지·입력·삭제 행 목록.
 */
const OpenerPanel = ({ openers, onChange }: OpenerPanelProps) => {
  // 추가 직후 새 행에만 포커스 — 추가 시점의 인덱스를 상태로 기억한다
  const [justAddedIndex, setJustAddedIndex] = useState(-1);

  const isFull = openers.length >= OPENER_LIMITS.MAX_COUNT;

  const handleAdd = () => {
    if (isFull) return;
    setJustAddedIndex(openers.length);
    onChange([...openers, '']);
  };

  const handleRowChange = (index: number, value: string) => {
    onChange(openers.map((text, i) => (i === index ? value : text)));
  };

  const handleRemove = (index: number) => {
    onChange(openers.filter((_, i) => i !== index));
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
        <p className="text-sm text-fg-muted">사용자가 대화를 시작할 수 있는 예시 질문을 설정하세요</p>
        <div className="flex shrink-0 items-center gap-3">
          <span className="text-sm text-fg-subtle">
            {openers.length}/{OPENER_LIMITS.MAX_COUNT}
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleAdd}
            disabled={isFull}
            title={isFull ? `최대 ${OPENER_LIMITS.MAX_COUNT}개` : undefined}
            leadingIcon={<Plus className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
          >
            추가
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {openers.length === 0 ? (
          <p className="py-10 text-center text-sm text-fg-subtle">
            아직 등록된 오프너가 없습니다. + 추가로 시작하세요.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {openers.map((text, index) => (
              <OpenerRow
                // 순서가 식별자(정렬 UI 없음) — 인덱스 키 사용
                key={index}
                index={index}
                value={text}
                autoFocus={index === justAddedIndex}
                onChange={(value) => handleRowChange(index, value)}
                onRemove={() => handleRemove(index)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default OpenerPanel;
