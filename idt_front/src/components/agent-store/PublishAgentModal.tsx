import { useState } from 'react';
import Modal from '@/components/common/Modal';
import { useMyAgents, usePublishAgent } from '@/hooks/useAgentStore';
import type { MyAgentSummary } from '@/types/agentStore';

interface PublishAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const PublishAgentModal = ({ isOpen, onClose }: PublishAgentModalProps) => {
  const { data } = useMyAgents({ filter: 'owned' });
  const publishMutation = usePublishAgent();

  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [visibility, setVisibility] = useState<'public' | 'department'>('public');

  if (!isOpen) return null;

  const privateAgents =
    data?.agents.filter((a: MyAgentSummary) => a.visibility === 'private') ?? [];

  const handlePublish = () => {
    if (!selectedAgentId) return;
    publishMutation.mutate(
      { agentId: selectedAgentId, body: { visibility } },
      {
        onSuccess: () => {
          setSelectedAgentId(null);
          setVisibility('public');
          onClose();
        },
      },
    );
  };

  return (
    <Modal
      title="내 에이전트 스토어 등록"
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button
            onClick={onClose}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            취소
          </button>
          <button
            onClick={handlePublish}
            disabled={!selectedAgentId || publishMutation.isPending}
            className="rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
          >
            {publishMutation.isPending ? '등록 중...' : '등록하기'}
          </button>
        </>
      }
    >
      {/* Agent selection */}
      <section>
        <h3 className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
          등록할 에이전트 선택
        </h3>
        <p className="mt-1 text-[12px] text-zinc-400">
          비공개(private) 에이전트만 표시됩니다
        </p>
        <div className="mt-3 max-h-48 space-y-2 overflow-y-auto">
          {privateAgents.length === 0 ? (
            <p className="py-4 text-center text-[13px] text-zinc-400">
              등록 가능한 에이전트가 없습니다
            </p>
          ) : (
            privateAgents.map((agent: MyAgentSummary) => (
              <label
                key={agent.agent_id}
                className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-all ${
                  selectedAgentId === agent.agent_id
                    ? 'border-violet-400 bg-violet-50'
                    : 'border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50'
                }`}
              >
                <input
                  type="radio"
                  name="publish-agent"
                  checked={selectedAgentId === agent.agent_id}
                  onChange={() => setSelectedAgentId(agent.agent_id)}
                  className="accent-violet-600"
                />
                <div>
                  <p className="text-[13.5px] font-medium text-zinc-800">
                    {agent.name}
                  </p>
                  <p className="mt-0.5 text-[12px] text-zinc-400">
                    {agent.description || '설명 없음'}
                  </p>
                </div>
              </label>
            ))
          )}
        </div>
      </section>

      {/* Visibility */}
      <section className="mt-6">
        <h3 className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
          공개 범위
        </h3>
        <div className="mt-3 space-y-2">
          <label
            className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-all ${
              visibility === 'public'
                ? 'border-violet-400 bg-violet-50'
                : 'border-zinc-200 hover:border-zinc-300'
            }`}
          >
            <input
              type="radio"
              name="visibility"
              checked={visibility === 'public'}
              onChange={() => setVisibility('public')}
              className="accent-violet-600"
            />
            <div>
              <p className="text-[13.5px] font-medium text-zinc-800">전체 공개</p>
              <p className="text-[12px] text-zinc-400">모든 사용자가 볼 수 있습니다</p>
            </div>
          </label>
          <label
            className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-all ${
              visibility === 'department'
                ? 'border-violet-400 bg-violet-50'
                : 'border-zinc-200 hover:border-zinc-300'
            }`}
          >
            <input
              type="radio"
              name="visibility"
              checked={visibility === 'department'}
              onChange={() => setVisibility('department')}
              className="accent-violet-600"
            />
            <div>
              <p className="text-[13.5px] font-medium text-zinc-800">부서 공개</p>
              <p className="text-[12px] text-zinc-400">같은 부서 사용자만 볼 수 있습니다</p>
            </div>
          </label>
        </div>
      </section>

      {/* Error */}
      {publishMutation.isError && (
        <p className="mt-4 text-[12px] text-red-500">
          {publishMutation.error.message}
        </p>
      )}
    </Modal>
  );
};

export default PublishAgentModal;
