import { useMemo, useState } from 'react';
import { useAvailableSubAgents } from '@/hooks/useAgentBuilder';
import type { LlmModel } from '@/types/llmModel';
import type { SubAgentCandidate, SubAgentConfig } from '@/types/agentBuilder';
import Modal from '@/components/common/Modal';

const MAX_SUB_AGENTS = 3;

interface SubAgentManagerModalProps {
  isOpen: boolean;
  /** 현재 편집 중인 에이전트 ID — 자기 자신은 후보에서 제외 */
  currentAgentId: string | null;
  selected: SubAgentConfig[];
  models?: LlmModel[];
  onAdd: (candidate: SubAgentCandidate) => void;
  onRemove: (refAgentId: string) => void;
  onClose: () => void;
}

/**
 * 서브에이전트 관리 모달.
 * 좌측: 현재 서브에이전트 / 우측: 사용 가능한 에이전트(소유+전체공개+부서공개) 검색·추가.
 * 사용 가능 목록은 현재 편집 에이전트와 이미 추가된 항목을 제외한다.
 */
const SubAgentManagerModal = ({
  isOpen,
  currentAgentId,
  selected,
  models,
  onAdd,
  onRemove,
  onClose,
}: SubAgentManagerModalProps) => {
  const [search, setSearch] = useState('');
  const { data, isLoading, isError } = useAvailableSubAgents(isOpen);

  const selectedIds = useMemo(
    () => new Set(selected.map((s) => s.ref_agent_id)),
    [selected],
  );

  const candidates = useMemo(() => {
    const all = data?.agents ?? [];
    const q = search.trim().toLowerCase();
    return all.filter((c) => {
      if (c.agent_id === currentAgentId) return false;
      if (selectedIds.has(c.agent_id)) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q)
      );
    });
  }, [data, search, currentAgentId, selectedIds]);

  const modelLabel = (modelId?: string | null) => {
    if (!modelId) return null;
    const m = models?.find((x) => x.id === modelId);
    return m ? `${m.provider}:${m.model_name}` : null;
  };

  const isFull = selected.length >= MAX_SUB_AGENTS;

  if (!isOpen) return null;

  return (
    <Modal
      title="👥 서브에이전트 관리"
      subtitle="이 에이전트가 작업을 위임할 수 있는 서브에이전트를 추가하거나 제거합니다."
      size="3xl"
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
      <div className="grid grid-cols-2 gap-5">
          {/* 좌: 현재 서브에이전트 */}
          <div className="flex flex-col overflow-hidden">
            <h3 className="mb-2 text-[13px] font-semibold text-zinc-700">
              현재 서브에이전트 ({selected.length})
            </h3>
            <div className="flex-1 overflow-y-auto">
              {selected.length === 0 ? (
                <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-zinc-200 py-10 text-center text-[12.5px] text-zinc-400">
                  서브에이전트가 없습니다
                </div>
              ) : (
                <ul className="space-y-2">
                  {selected.map((s) => (
                    <li
                      key={s.ref_agent_id}
                      className="flex items-center gap-2 rounded-xl border border-violet-200 bg-violet-50/40 px-3 py-2.5"
                    >
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-zinc-800">
                        {s.name}
                      </span>
                      <button
                        type="button"
                        onClick={() => onRemove(s.ref_agent_id)}
                        aria-label={`${s.name} 제거`}
                        className="rounded-lg px-2 py-1 text-[12px] font-medium text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
                      >
                        제거
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* 우: 사용 가능한 에이전트 */}
          <div className="flex flex-col overflow-hidden">
            <h3 className="mb-2 text-[13px] font-semibold text-zinc-700">사용 가능한 에이전트</h3>
            <div className="relative mb-2">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="🔍 에이전트 검색..."
                aria-label="에이전트 검색"
                className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
              />
            </div>
            {isFull && (
              <p className="mb-2 rounded-lg bg-amber-50 px-3 py-1.5 text-[11.5px] text-amber-700">
                서브에이전트는 최대 {MAX_SUB_AGENTS}개까지 추가할 수 있습니다.
              </p>
            )}
            <div className="flex-1 overflow-y-auto">
              {isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-[68px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
                  ))}
                </div>
              ) : isError ? (
                <div className="rounded-xl border border-zinc-200 bg-zinc-50 py-8 text-center text-[13px] text-zinc-500">
                  목록을 불러올 수 없습니다
                </div>
              ) : candidates.length === 0 ? (
                <div className="rounded-xl border border-zinc-200 bg-zinc-50 py-8 text-center text-[13px] text-zinc-400">
                  추가할 수 있는 에이전트가 없습니다
                </div>
              ) : (
                <ul className="space-y-2">
                  {candidates.map((c) => {
                    const label = modelLabel(c.llm_model_id);
                    return (
                      <li
                        key={c.agent_id}
                        className="flex items-start gap-3 rounded-xl border border-zinc-200 bg-white px-4 py-3"
                      >
                        <span className="mt-0.5 text-zinc-400">👤</span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium text-zinc-800">{c.name}</p>
                          <p className="mt-0.5 line-clamp-1 text-[11.5px] text-zinc-400">
                            {c.description || '에이전트 설명을 입력하세요'}
                          </p>
                          {label && (
                            <span className="mt-1 inline-block rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[10.5px] text-violet-600">
                              {label}
                            </span>
                          )}
                        </div>
                        <button
                          type="button"
                          disabled={isFull}
                          onClick={() => onAdd(c)}
                          title={isFull ? `최대 ${MAX_SUB_AGENTS}개` : undefined}
                          className={`shrink-0 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-all ${
                            isFull
                              ? 'cursor-not-allowed bg-zinc-100 text-zinc-300'
                              : 'bg-zinc-900 text-white hover:bg-zinc-800 active:scale-95'
                          }`}
                        >
                          추가
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
      </div>
    </Modal>
  );
};

export default SubAgentManagerModal;
