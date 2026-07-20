// agent-workspace-view: 에이전트 구성을 폴더처럼 열람하는 읽기 전용 워크스페이스.
// 백엔드 무변경 — AgentDetail·스킬·위키 트리 기존 훅 조립. 편집은 agent-builder 담당.
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { useAgentDetail } from '@/hooks/useAgentStore';
import { useAgentSkills } from '@/hooks/useAgentSkills';
import { useToolCatalog } from '@/hooks/useToolCatalog';
import { useWikiTree } from '@/hooks/useWiki';
import { mapDraftToolIdsToCatalog } from '@/utils/draftToolMapping';
import type { AgentDetail, WorkerInfo } from '@/types/agentStore';

type SectionKey = 'prompt' | 'tools' | 'subAgents' | 'skills' | 'knowledge' | 'info';

const SECTIONS: { key: SectionKey; icon: string; label: string }[] = [
  { key: 'prompt', icon: '📄', label: '지침' },
  { key: 'tools', icon: '🔧', label: '도구' },
  { key: 'subAgents', icon: '👥', label: '서브에이전트' },
  { key: 'skills', icon: '🧩', label: '스킬' },
  { key: 'knowledge', icon: '📖', label: '지식' },
  { key: 'info', icon: 'ℹ️', label: '정보' },
];

const VISIBILITY_LABELS: Record<string, string> = {
  private: '비공개',
  department: '부서 공개',
  public: '전체 공개',
};

const SectionError = ({ what }: { what: string }) => (
  <p className="text-sm text-zinc-400">{what}을(를) 불러올 수 없습니다.</p>
);

/** tool_config의 알려진 RAG 키만 안전 접근해 라벨로 변환 */
const ragConfigLabels = (config: Record<string, unknown> | null): string[] => {
  if (!config) return [];
  const labels: string[] = [];
  if (typeof config.collection_name === 'string' && config.collection_name) {
    labels.push(`컬렉션: ${config.collection_name}`);
  }
  if (typeof config.kb_id === 'string' && config.kb_id) {
    labels.push(`지식베이스: ${config.kb_id}`);
  }
  if (config.use_wiki_first === true) labels.push('위키 우선 검색');
  if (config.use_routed_search === true) labels.push('라우팅 검색');
  return labels;
};

const ToolsSection = ({ agent }: { agent: AgentDetail }) => {
  const { data: catalog } = useToolCatalog();
  const toolWorkers = agent.workers.filter(
    (w) => (w.worker_type ?? 'tool') === 'tool',
  );

  // useToolCatalog는 CatalogTool[] 배열을 직접 반환한다
  const catalogLabel = (toolId: string): string => {
    const mapped = mapDraftToolIdsToCatalog([toolId], catalog);
    const entry = (catalog ?? []).find((t) => mapped.includes(t.tool_id));
    return entry ? entry.name : toolId; // 미매칭은 원문 표시 (FR-03)
  };

  if (toolWorkers.length === 0) {
    return <p className="text-sm text-zinc-400">연결된 도구가 없습니다.</p>;
  }
  return (
    <ul className="space-y-2">
      {toolWorkers.map((w) => (
        <li key={w.worker_id} className="rounded-2xl border border-zinc-200 bg-white p-4">
          <p className="text-sm font-medium text-zinc-800">{w.description}</p>
          <p className="mt-0.5 text-[12px] text-zinc-400">{catalogLabel(w.tool_id)}</p>
          {ragConfigLabels(w.tool_config).length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {ragConfigLabels(w.tool_config).map((label) => (
                <span
                  key={label}
                  className="rounded bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-600"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
};

const SubAgentsSection = ({ workers }: { workers: WorkerInfo[] }) => {
  const subAgents = workers.filter((w) => w.worker_type === 'sub_agent');
  if (subAgents.length === 0) {
    return <p className="text-sm text-zinc-400">서브에이전트가 없습니다.</p>;
  }
  return (
    <ul className="space-y-2">
      {subAgents.map((w) => (
        <li key={w.worker_id} className="rounded-2xl border border-zinc-200 bg-white p-4">
          <p className="text-sm font-medium text-zinc-800">
            {w.ref_agent_name ?? w.description}
          </p>
          <p className="mt-0.5 text-[12px] text-zinc-400">{w.description}</p>
        </li>
      ))}
    </ul>
  );
};

const SkillsSection = ({ agentId }: { agentId: string }) => {
  const { data, isLoading, isError } = useAgentSkills(agentId);
  if (isLoading) return <p className="text-sm text-zinc-500">불러오는 중…</p>;
  if (isError || !data) return <SectionError what="스킬 목록" />;
  if (data.skills.length === 0) {
    return <p className="text-sm text-zinc-400">부착된 스킬이 없습니다.</p>;
  }
  return (
    <ul className="space-y-2">
      {data.skills.map((s) => (
        <li key={s.skill_id} className="rounded-2xl border border-zinc-200 bg-white p-4">
          <p className="text-sm font-medium text-zinc-800">{s.name}</p>
          <p className="mt-0.5 text-[12px] text-zinc-400">{s.description}</p>
        </li>
      ))}
    </ul>
  );
};

const KnowledgeSection = ({ agentId }: { agentId: string }) => {
  const { data, isLoading, isError } = useWikiTree(agentId);
  if (isLoading) return <p className="text-sm text-zinc-500">불러오는 중…</p>;
  if (isError || !data) return <SectionError what="지식 목록" />;
  return (
    <div>
      {data.groups.length === 0 ? (
        <p className="text-sm text-zinc-400">등록된 지식이 없습니다.</p>
      ) : (
        <ul className="space-y-1.5">
          {data.groups.map((g) => (
            <li
              key={g.path ?? '(미분류)'}
              className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white px-4 py-2.5"
            >
              <span className="text-sm text-zinc-700">📁 {g.path ?? '미분류'}</span>
              <span className="text-[12px] text-zinc-400">{g.items.length}건</span>
            </li>
          ))}
        </ul>
      )}
      <Link
        to={`/agents/${agentId}/knowledge`}
        className="mt-3 inline-block text-sm text-violet-600 hover:underline"
      >
        전체 지식 보기 →
      </Link>
    </div>
  );
};

const InfoSection = ({ agent }: { agent: AgentDetail }) => (
  <dl className="space-y-2 text-sm">
    {[
      ['모델', agent.llm_model_id],
      ['Temperature', String(agent.temperature)],
      ['공개 범위', VISIBILITY_LABELS[agent.visibility] ?? agent.visibility],
      ['소유자', agent.owner_user_id],
      ['부서', agent.department_name ?? '(없음)'],
      ['생성일', agent.created_at.slice(0, 10)],
      ['최근 수정', agent.updated_at.slice(0, 10)],
    ].map(([label, value]) => (
      <div key={label} className="flex gap-3 rounded-xl border border-zinc-200 bg-white px-4 py-2.5">
        <dt className="w-28 shrink-0 text-zinc-400">{label}</dt>
        <dd className="text-zinc-700">{value}</dd>
      </div>
    ))}
  </dl>
);

const AgentWorkspacePage = () => {
  const { agentId } = useParams<{ agentId: string }>();
  const { data: agent, isLoading, isError } = useAgentDetail(agentId ?? null);
  const [section, setSection] = useState<SectionKey>('prompt');

  if (isLoading) {
    return <div className="p-8 text-sm text-zinc-500">불러오는 중…</div>;
  }
  if (isError || !agent) {
    return (
      <div className="p-8 text-sm text-zinc-500">
        에이전트를 찾을 수 없습니다. 삭제되었거나 접근 권한이 없습니다.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div className="border-b border-zinc-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h1 className="text-[15px] font-semibold text-zinc-900">{agent.name}</h1>
            <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-500">
              {VISIBILITY_LABELS[agent.visibility] ?? agent.visibility}
            </span>
          </div>
          {agent.can_edit && (
            <Link
              to="/agent-builder"
              className="rounded-xl border border-zinc-200 px-3 py-1.5 text-[12px] text-zinc-600 hover:bg-zinc-50"
            >
              수정하기
            </Link>
          )}
        </div>
        <p className="mt-0.5 text-[12px] text-zinc-400">{agent.description}</p>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* 폴더 nav */}
        <nav className="w-52 shrink-0 overflow-y-auto border-r border-zinc-200 p-3">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setSection(s.key)}
              className={`mb-0.5 flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-[13.5px] transition-all ${
                section === s.key
                  ? 'bg-violet-50 font-medium text-violet-700'
                  : 'text-zinc-600 hover:bg-zinc-50'
              }`}
            >
              <span>{s.icon}</span>
              {s.label}
            </button>
          ))}
        </nav>

        {/* 콘텐츠 */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="mx-auto max-w-3xl px-6 py-6">
            {section === 'prompt' && (
              <div className="prose prose-sm max-w-none rounded-2xl border border-zinc-200 bg-white p-5 text-[14px] leading-6 text-zinc-800">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {agent.system_prompt}
                </ReactMarkdown>
              </div>
            )}
            {section === 'tools' && <ToolsSection agent={agent} />}
            {section === 'subAgents' && <SubAgentsSection workers={agent.workers} />}
            {section === 'skills' && <SkillsSection agentId={agent.agent_id} />}
            {section === 'knowledge' && <KnowledgeSection agentId={agent.agent_id} />}
            {section === 'info' && <InfoSection agent={agent} />}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentWorkspacePage;
