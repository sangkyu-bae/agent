import { useState } from 'react';
import {
  useAgentDetail,
  useForkStats,
  useSubscribeAgent,
  useUnsubscribeAgent,
  useForkAgent,
} from '@/hooks/useAgentStore';
import { useAuthStore } from '@/store/authStore';

interface AgentDetailModalProps {
  agentId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

const VISIBILITY_LABEL: Record<string, string> = {
  public: '전체 공개',
  department: '부서 공개',
  private: '비공개',
};

const AgentDetailModal = ({ agentId, isOpen, onClose }: AgentDetailModalProps) => {
  const { user } = useAuthStore();
  const { data: agent, isLoading, isError } = useAgentDetail(isOpen ? agentId : null);
  const { data: stats } = useForkStats(
    isOpen && agent?.can_edit ? agentId : null,
  );
  const subscribeMutation = useSubscribeAgent();
  const unsubscribeMutation = useUnsubscribeAgent();
  const forkMutation = useForkAgent();

  const [showForkInput, setShowForkInput] = useState(false);
  const [forkName, setForkName] = useState('');

  if (!isOpen) return null;

  const isOwner = agent && user && agent.owner_user_id === String(user.id);

  const handleSubscribe = () => {
    if (!agentId) return;
    subscribeMutation.mutate(agentId);
  };

  const handleUnsubscribe = () => {
    if (!agentId) return;
    unsubscribeMutation.mutate(agentId);
  };

  const handleFork = () => {
    if (!agentId) return;
    forkMutation.mutate(
      { agentId, name: forkName || undefined },
      {
        onSuccess: () => {
          setShowForkInput(false);
          setForkName('');
        },
      },
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        className="relative mx-4 max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>

        {isLoading && (
          <div className="space-y-4 p-8">
            <div className="h-10 w-48 animate-pulse rounded-lg bg-zinc-100" />
            <div className="h-4 w-32 animate-pulse rounded bg-zinc-100" />
            <div className="h-24 animate-pulse rounded-lg bg-zinc-100" />
            <div className="h-32 animate-pulse rounded-lg bg-zinc-100" />
          </div>
        )}

        {isError && (
          <div className="flex flex-col items-center gap-2 p-12 text-center">
            <svg className="h-10 w-10 text-zinc-300" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
            </svg>
            <p className="text-[14px] text-zinc-500">에이전트를 찾을 수 없습니다</p>
          </div>
        )}

        {agent && (
          <div className="p-8">
            {/* Header */}
            <div className="flex items-start gap-4">
              <div
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-[15px] font-bold text-white shadow-md"
                style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
              >
                {agent.name.slice(0, 2).toUpperCase()}
              </div>
              <div>
                <h2 className="text-[18px] font-bold text-zinc-900">{agent.name}</h2>
                <p className="mt-0.5 text-[13px] text-zinc-400">
                  @{agent.owner_user_id} · {VISIBILITY_LABEL[agent.visibility] ?? agent.visibility}
                </p>
                {agent.department_name && (
                  <p className="mt-1 text-[12px] text-zinc-500">
                    부서: {agent.department_name}
                  </p>
                )}
              </div>
            </div>

            {/* Description */}
            <section className="mt-6">
              <h3 className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                설명
              </h3>
              <p className="mt-2 text-[14px] leading-relaxed text-zinc-700">
                {agent.description || '설명이 없습니다.'}
              </p>
            </section>

            {/* System Prompt */}
            <section className="mt-6">
              <h3 className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                시스템 프롬프트
              </h3>
              <div className="mt-2 max-h-48 overflow-y-auto rounded-xl bg-zinc-50 p-4">
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-600">
                  {agent.system_prompt || '—'}
                </p>
              </div>
            </section>

            {/* Workers / Tools */}
            {agent.workers.length > 0 && (
              <section className="mt-6">
                <h3 className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                  연결된 도구
                </h3>
                <div className="mt-2 flex flex-wrap gap-2">
                  {agent.workers.map((w) => (
                    <span
                      key={w.worker_id}
                      className="rounded-lg bg-zinc-100 px-2.5 py-1 text-[12px] font-medium text-zinc-600"
                    >
                      {w.description || w.worker_id}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* Settings */}
            <section className="mt-6">
              <h3 className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                설정
              </h3>
              <div className="mt-2 flex gap-6 text-[13px] text-zinc-600">
                <span>모델: <strong className="text-zinc-800">{agent.llm_model_id}</strong></span>
                <span>Temperature: <strong className="text-zinc-800">{agent.temperature}</strong></span>
              </div>
            </section>

            {/* Stats (owner only) */}
            {isOwner && stats && (
              <section className="mt-6">
                <h3 className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                  통계
                </h3>
                <div className="mt-2 flex gap-6 text-[13px] text-zinc-600">
                  <span>구독 <strong className="text-zinc-800">{stats.subscriber_count}명</strong></span>
                  <span>포크 <strong className="text-zinc-800">{stats.fork_count}회</strong></span>
                </div>
              </section>
            )}

            {/* Actions */}
            <div className="mt-8 flex items-center gap-3 border-t border-zinc-100 pt-6">
              {isOwner ? (
                <p className="text-[13px] text-zinc-400">내 에이전트입니다</p>
              ) : (
                <>
                  <button
                    onClick={handleSubscribe}
                    disabled={subscribeMutation.isPending}
                    className="flex items-center justify-center rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
                  >
                    {subscribeMutation.isPending ? '구독 중...' : '구독하기'}
                  </button>
                  <button
                    onClick={handleUnsubscribe}
                    disabled={unsubscribeMutation.isPending}
                    className="flex items-center rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 disabled:opacity-50"
                  >
                    {unsubscribeMutation.isPending ? '해제 중...' : '구독 해제'}
                  </button>
                  <div className="relative">
                    {showForkInput ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={forkName}
                          onChange={(e) => setForkName(e.target.value)}
                          placeholder="포크 이름 (선택)"
                          className="rounded-lg border border-zinc-300 px-3 py-2 text-[13px] text-zinc-800 outline-none focus:border-violet-400"
                        />
                        <button
                          onClick={handleFork}
                          disabled={forkMutation.isPending}
                          className="rounded-lg bg-violet-600 px-3 py-2 text-[13px] font-medium text-white hover:bg-violet-700 disabled:opacity-50"
                        >
                          {forkMutation.isPending ? '...' : '확인'}
                        </button>
                        <button
                          onClick={() => { setShowForkInput(false); setForkName(''); }}
                          className="rounded-lg px-2 py-2 text-[13px] text-zinc-400 hover:text-zinc-600"
                        >
                          취소
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setShowForkInput(true)}
                        className="flex items-center rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
                      >
                        포크하기
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>

            {/* Error messages */}
            {subscribeMutation.isError && (
              <p className="mt-2 text-[12px] text-red-500">{subscribeMutation.error.message}</p>
            )}
            {forkMutation.isError && (
              <p className="mt-2 text-[12px] text-red-500">{forkMutation.error.message}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentDetailModal;
