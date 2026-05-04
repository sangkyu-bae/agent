import type { StoreAgentSummary } from '@/types/agentStore';

interface AgentStoreCardProps {
  agent: StoreAgentSummary;
  onClick: (agentId: string) => void;
  onSubscribe: (agentId: string) => void;
  onFork: (agentId: string) => void;
  isSubscribing?: boolean;
  isForking?: boolean;
}

const AVATAR_COLORS = [
  'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)',
  'linear-gradient(135deg, #2563eb 0%, #0891b2 100%)',
  'linear-gradient(135deg, #059669 0%, #10b981 100%)',
  'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
  'linear-gradient(135deg, #dc2626 0%, #f43f5e 100%)',
  'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)',
];

const getAvatarColor = (agentId: string) => {
  let hash = 0;
  for (let i = 0; i < agentId.length; i++) {
    hash = agentId.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
};

const getInitials = (name: string) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase() || '??';

const VISIBILITY_LABEL: Record<string, string> = {
  public: '공개',
  department: '부서',
  private: '비공개',
};

const AgentStoreCard = ({
  agent,
  onClick,
  onSubscribe,
  onFork,
  isSubscribing = false,
  isForking = false,
}: AgentStoreCardProps) => {
  return (
    <div
      role="article"
      onClick={() => onClick(agent.agent_id)}
      className="group relative flex cursor-pointer flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-transparent hover:shadow-lg"
    >
      {/* Header */}
      <div className="flex items-start gap-3 p-4 pb-0">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-[13px] font-bold text-white shadow-md"
          style={{ background: getAvatarColor(agent.agent_id) }}
        >
          {getInitials(agent.name)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-semibold text-zinc-900">
            {agent.name}
          </p>
          <p className="mt-0.5 truncate text-[12px] text-zinc-400">
            {agent.owner_email ? `@${agent.owner_email.split('@')[0]}` : agent.owner_user_id}
            {' · '}
            {VISIBILITY_LABEL[agent.visibility] ?? agent.visibility}
          </p>
        </div>
      </div>

      {/* Description */}
      <div className="flex-1 px-4 pt-3">
        <p className="line-clamp-2 text-[13px] leading-relaxed text-zinc-600">
          {agent.description || '설명이 없습니다.'}
        </p>
      </div>

      {/* Meta */}
      <div className="flex items-center gap-2 px-4 pt-3">
        {agent.department_name && (
          <span className="rounded-md bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-600">
            {agent.department_name}
          </span>
        )}
        <span className="text-[11.5px] text-zinc-400">
          temp {agent.temperature}
        </span>
      </div>

      {/* Actions */}
      <div className="mt-3 flex items-center gap-2 border-t border-zinc-100 px-4 py-3">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSubscribe(agent.agent_id);
          }}
          disabled={isSubscribing}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-violet-300 hover:bg-violet-50 hover:text-violet-600 disabled:opacity-50"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          구독
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onFork(agent.agent_id);
          }}
          disabled={isForking}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-violet-300 hover:bg-violet-50 hover:text-violet-600 disabled:opacity-50"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" />
          </svg>
          포크
        </button>
      </div>
    </div>
  );
};

export default AgentStoreCard;
