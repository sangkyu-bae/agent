// Design Ref: sidebar-agent-list §5 — 2줄 압축 항목 + 그룹 접기(persist) + 헤더 새로고침.
// 로딩·오류·빈 상태 문구와 항목 클릭 동작은 기존 AppSidebar와 같다.
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, RotateCw, Sparkles, Star } from 'lucide-react';
import { useLayoutStore } from '@/store/layoutStore';
import { SHOW_AGENT_AVATAR } from '@/constants/sidebar';
import { cn } from '@/utils/cn';
import { SIDEBAR_AGENT_GROUP, type MyAgent, type SidebarAgentGroupKey } from '@/types/agent';

interface AgentListProps {
  agents: MyAgent[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  /** 이름 첫 글자 아바타. 기본값은 SHOW_AGENT_AVATAR 상수 */
  showAvatar?: boolean;
}

const GROUP_LABEL: Record<SidebarAgentGroupKey, string> = {
  pinned: '고정됨',
  owned: '내 에이전트',
  subscribed: '구독',
  forked: '포크',
};

const groupOf = (agent: MyAgent): SidebarAgentGroupKey =>
  agent.is_pinned ? SIDEBAR_AGENT_GROUP.PINNED : agent.source_type;

interface AgentRowProps {
  agent: MyAgent;
  isSelected: boolean;
  showAvatar: boolean;
  onClick: () => void;
}

const AgentRow = ({ agent, isSelected, showAvatar, onClick }: AgentRowProps) => (
  <button
    type="button"
    onClick={onClick}
    title={agent.description || undefined}
    aria-current={isSelected ? 'true' : undefined}
    className={cn(
      'relative flex w-full items-start gap-2.5 rounded-md py-1.5 pl-3 pr-2 text-left transition-colors duration-150',
      isSelected ? 'bg-sidebar-active' : 'hover:bg-sidebar-hover',
    )}
  >
    {isSelected && (
      <span
        aria-hidden="true"
        className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-linear-to-b from-brand-500 to-brand-800"
      />
    )}
    {showAvatar && (
      <span
        aria-hidden="true"
        className="mt-0.5 flex h-5.5 w-5.5 shrink-0 items-center justify-center rounded-md bg-brand-500/15 text-xs font-semibold text-brand-300"
      >
        {agent.name.trim().charAt(0) || '?'}
      </span>
    )}
    <span className="min-w-0 flex-1">
      <span className="flex items-center gap-1">
        <span className="truncate text-sm font-medium leading-snug text-sidebar-fg">{agent.name}</span>
        {agent.is_pinned && (
          <Star className="h-3 w-3 shrink-0 fill-current text-brand-400" aria-label="고정됨" />
        )}
      </span>
      {agent.description && (
        <span data-slot="agent-desc" className="block truncate text-xs leading-snug text-sidebar-fg-muted">
          {agent.description}
        </span>
      )}
    </span>
  </button>
);

const AgentList = ({
  agents,
  selectedAgentId,
  onSelectAgent,
  isLoading = false,
  isError = false,
  onRetry,
  showAvatar = SHOW_AGENT_AVATAR,
}: AgentListProps) => {
  const navigate = useNavigate();
  const collapsedGroups = useLayoutStore((s) => s.collapsedAgentGroups);
  const toggleAgentGroup = useLayoutStore((s) => s.toggleAgentGroup);

  const groups = useMemo(
    () =>
      Object.values(SIDEBAR_AGENT_GROUP)
        .map((key) => ({ key, agents: agents.filter((a) => groupOf(a) === key) }))
        .filter((g) => g.agents.length > 0),
    [agents],
  );

  const renderBody = () => {
    if (isError) {
      return (
        <div className="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-center">
          <p className="text-xs text-danger-border">에이전트 목록을 불러오지 못했습니다</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-2 rounded-md border border-sidebar-border px-3 py-1 text-xs text-sidebar-fg-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-fg"
            >
              다시 시도
            </button>
          )}
        </div>
      );
    }
    if (isLoading) {
      return (
        <div className="space-y-1" aria-label="불러오는 중" role="status">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex w-full flex-col items-start rounded-md px-3 py-2">
              <span className="h-3 w-3/4 animate-pulse rounded-md bg-sidebar-active" />
              <span className="mt-2 h-2 w-1/2 animate-pulse rounded-md bg-sidebar-hover" />
            </div>
          ))}
        </div>
      );
    }
    if (agents.length === 0) {
      return (
        <div className="mt-6 text-center">
          <p className="text-xs text-sidebar-fg-muted">등록된 에이전트가 없습니다</p>
          <button
            type="button"
            onClick={() => navigate('/agent-builder')}
            className="mt-3 rounded-md border border-brand-500/40 px-3 py-1.5 text-xs text-brand-300 transition-colors hover:bg-brand-500/10"
          >
            에이전트 만들기
          </button>
        </div>
      );
    }
    return groups.map((group) => {
      const isCollapsed = collapsedGroups.includes(group.key);
      return (
        <div key={group.key} className="mb-1.5">
          <button
            type="button"
            onClick={() => toggleAgentGroup(group.key)}
            aria-expanded={!isCollapsed}
            className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-sidebar-fg-muted transition-colors duration-150 hover:bg-sidebar-hover hover:text-sidebar-fg"
          >
            <ChevronDown
              className={cn('h-3 w-3 shrink-0 transition-transform duration-150', isCollapsed && '-rotate-90')}
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <span>{GROUP_LABEL[group.key]}</span>{' '}
            <span className="tabular-nums">{group.agents.length}</span>
          </button>
          {!isCollapsed && (
            <div className="mt-0.5 space-y-px">
              {group.agents.map((agent) => (
                <AgentRow
                  key={agent.agent_id}
                  agent={agent}
                  isSelected={agent.agent_id === selectedAgentId}
                  showAvatar={showAvatar}
                  onClick={() => {
                    onSelectAgent(agent.agent_id);
                    navigate('/chatpage');
                  }}
                />
              ))}
            </div>
          )}
        </div>
      );
    });
  };

  return (
    <>
      <div className="flex items-center justify-between py-1 pl-4 pr-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-brand-400" strokeWidth={1.75} aria-hidden="true" />
          <span className="text-sm font-medium text-sidebar-fg">에이전트</span>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            aria-label="에이전트 목록 새로고침"
            title="에이전트 목록 새로고침"
            className="flex h-7 w-7 items-center justify-center rounded-md text-sidebar-fg-muted transition-colors duration-150 hover:bg-sidebar-hover hover:text-sidebar-fg"
          >
            <RotateCw className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
          </button>
        )}
      </div>
      <div className="mt-1 px-2">{renderBody()}</div>
    </>
  );
};

export default AgentList;
