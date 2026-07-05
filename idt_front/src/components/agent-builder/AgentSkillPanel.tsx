import { useSkills } from '@/hooks/useSkills';
import { MAX_ATTACHED_SKILLS } from '@/constants/agentSkill';

interface AgentSkillPanelProps {
  /** 현재 부착된 스킬 id (form.skills — 단일 진실원) */
  selectedIds: string[];
  /** 토글 핸들러 (상위 form 상태만 변경, 저장 버튼으로 일괄 반영) */
  onToggle: (skillId: string) => void;
}

/**
 * 에이전트에 부착할 Skill을 온/오프 토글로 선택하는 패널 (agent-skill-toggle).
 *
 * 생성·수정 모드 모두에서 동작한다. 토글은 form.skills 로컬 상태만 바꾸고,
 * 실제 부착/해제는 상위 저장 버튼(create/update 요청의 skill_ids)으로 일괄 반영된다.
 * 부착한 Skill의 instruction만 에이전트 프롬프트에 주입되며 script는 실행되지 않는다.
 */
const AgentSkillPanel = ({ selectedIds, onToggle }: AgentSkillPanelProps) => {
  const { data, isLoading } = useSkills({ scope: 'all', size: 100 });
  const candidates = data?.skills ?? [];
  const atMax = selectedIds.length >= MAX_ATTACHED_SKILLS;

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <label className="text-[13px] font-semibold text-zinc-700">스킬 선택</label>
        <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10.5px] font-medium text-violet-500">
          {selectedIds.length}/{MAX_ATTACHED_SKILLS}
        </span>
      </div>
      <p className="mb-3 text-[12px] text-zinc-400">에이전트에서 사용할 스킬을 선택하세요</p>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-[64px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
          ))}
        </div>
      ) : candidates.length > 0 ? (
        <ul className="space-y-2">
          {candidates.map((s) => {
            const isOn = selectedIds.includes(s.id);
            const disabled = !isOn && atMax;
            return (
              <li
                key={s.id}
                className={`flex items-start gap-3 rounded-xl border px-4 py-3 transition-colors ${
                  isOn ? 'border-violet-300 bg-violet-50/40' : 'border-zinc-200 bg-white'
                } ${disabled ? 'opacity-50' : ''}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[13px] font-medium text-zinc-800">{s.name}</span>
                    {s.script_type !== 'none' && (
                      <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-600">
                        ⚠ script 미실행
                      </span>
                    )}
                  </div>
                  {s.description && (
                    <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-relaxed text-zinc-400">
                      {s.description}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={isOn}
                  aria-label={`${s.name} 토글`}
                  disabled={disabled}
                  title={disabled ? `최대 ${MAX_ATTACHED_SKILLS}개까지 선택할 수 있습니다` : undefined}
                  onClick={() => onToggle(s.id)}
                  className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors ${
                    isOn ? 'bg-violet-600' : 'bg-zinc-300'
                  } ${disabled ? 'cursor-not-allowed' : ''}`}
                >
                  <span
                    className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${
                      isOn ? 'left-[18px]' : 'left-0.5'
                    }`}
                  />
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="rounded-xl border border-zinc-200 bg-zinc-50 py-4 text-center text-[12.5px] text-zinc-400">
          사용 가능한 스킬이 없습니다
        </p>
      )}

      <p className="mt-3 text-[11.5px] leading-relaxed text-zinc-400">
        부착한 Skill의 지시문(instruction)만 에이전트 프롬프트에 합쳐집니다. script는 현재 실행되지 않습니다.
      </p>
    </div>
  );
};

export default AgentSkillPanel;
