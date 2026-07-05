import { useSkills } from '@/hooks/useSkills';
import { MAX_ATTACHED_SKILLS } from '@/constants/agentSkill';
import Modal from '@/components/common/Modal';

interface SkillPickerModalProps {
  isOpen: boolean;
  selectedIds: string[];
  onToggle: (skillId: string) => void;
  onClose: () => void;
}

/**
 * 스킬 추가 팝업 (agent-skill-toggle). ToolPickerModal과 동일한 토글 패턴.
 * useSkills(scope:'all') = 접근 가능 스킬만 반환 → 저장 시 권한 오류 없음.
 * 최대 개수 도달 시 미선택 항목은 비활성화된다.
 */
const SkillPickerModal = ({
  isOpen,
  selectedIds,
  onToggle,
  onClose,
}: SkillPickerModalProps) => {
  const { data, isLoading } = useSkills({ scope: 'all', size: 100 });
  const candidates = data?.skills ?? [];
  const atMax = selectedIds.length >= MAX_ATTACHED_SKILLS;

  if (!isOpen) return null;

  return (
    <Modal
      title={
        <span className="flex items-center gap-2">
          스킬 추가
          <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10.5px] font-medium text-violet-500">
            {selectedIds.length}/{MAX_ATTACHED_SKILLS}
          </span>
        </span>
      }
      size="lg"
      scroll="body"
      onClose={onClose}
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl bg-zinc-900 px-5 py-2.5 text-[13.5px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
        >
          완료
        </button>
      }
    >
      <>
          {isLoading ? (
            <div className="grid grid-cols-1 gap-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-[56px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
              ))}
            </div>
          ) : candidates.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {candidates.map((s) => {
                const isSelected = selectedIds.includes(s.id);
                const disabled = !isSelected && atMax;
                return (
                  <button
                    key={s.id}
                    type="button"
                    role="switch"
                    aria-checked={isSelected}
                    onClick={() => !disabled && onToggle(s.id)}
                    disabled={disabled}
                    title={disabled ? `최대 ${MAX_ATTACHED_SKILLS}개까지 선택할 수 있습니다` : undefined}
                    className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all ${
                      disabled
                        ? 'cursor-not-allowed border-zinc-200 bg-zinc-50 opacity-50'
                        : isSelected
                          ? 'border-violet-300 bg-violet-50'
                          : 'border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[13px] font-medium ${isSelected ? 'text-violet-700' : 'text-zinc-700'}`}>
                          {s.name}
                        </span>
                        {s.script_type !== 'none' && (
                          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-600">⚠ script</span>
                        )}
                      </div>
                      {s.description && (
                        <p className="mt-0.5 line-clamp-1 text-[11.5px] text-zinc-400">{s.description}</p>
                      )}
                    </div>
                    {isSelected && (
                      <svg className="h-4 w-4 shrink-0 text-violet-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 py-8 text-center">
              <p className="text-[13px] text-zinc-400">사용 가능한 스킬이 없습니다</p>
            </div>
          )}
      </>
    </Modal>
  );
};

export default SkillPickerModal;
