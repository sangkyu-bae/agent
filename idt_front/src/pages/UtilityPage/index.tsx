import { useState } from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { useToolCatalog } from '@/hooks/useToolCatalog';
import { useLlmModels } from '@/hooks/useLlmModels';
import { useSkills } from '@/hooks/useSkills';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import type { SkillSummary } from '@/types/skill';
import UtilityCard from './UtilityCard';
import type { UtilityBadge } from './UtilityCard';

// ─── 탭 / 필터 정의 ─────────────────────────────────────────────────────────

const TABS = [
  { key: 'tools', label: '도구' },
  { key: 'models', label: '모델' },
  { key: 'middleware', label: '미들웨어' },
  { key: 'skills', label: '스킬' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

type ToolKind = 'built-in' | 'custom' | 'mcp';
type ToolFilter = 'all' | ToolKind;

const TOOL_FILTERS: { key: ToolFilter; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'built-in', label: 'built-in' },
  { key: 'custom', label: 'custom' },
  { key: 'mcp', label: 'mcp' },
];

const toolKind = (t: CatalogTool): ToolKind =>
  t.source === 'mcp' ? 'mcp' : t.is_builtin ? 'built-in' : 'custom';

const TOOL_KIND_TONE: Record<ToolKind, UtilityBadge['tone']> = {
  'built-in': 'sky',
  custom: 'violet',
  mcp: 'amber',
};

const matches = (q: string, ...fields: (string | null | undefined)[]) => {
  const query = q.trim().toLowerCase();
  return query === '' || fields.some((f) => f?.toLowerCase().includes(query));
};

// ─── 카드 매핑 ──────────────────────────────────────────────────────────────

const toolMeta = (t: CatalogTool): string | undefined => {
  const parts: string[] = [];
  if (t.mcp_server_name) parts.push(`MCP 서버: ${t.mcp_server_name}`);
  if (t.requires_env.length > 0) parts.push(`환경변수 필요: ${t.requires_env.join(', ')}`);
  return parts.length > 0 ? parts.join(' · ') : undefined;
};

const ToolCards = ({ tools }: { tools: CatalogTool[] }) => (
  <>
    {tools.map((t) => {
      const kind = toolKind(t);
      return (
        <UtilityCard
          key={t.tool_id}
          title={t.name}
          description={t.description}
          badges={[{ label: kind, tone: TOOL_KIND_TONE[kind] }]}
          meta={toolMeta(t)}
        />
      );
    })}
  </>
);

const modelBadges = (m: LlmModel): UtilityBadge[] => {
  const badges: UtilityBadge[] = [{ label: m.provider, tone: 'violet' }];
  if (m.is_default) badges.push({ label: '기본', tone: 'emerald' });
  if (!m.is_active) badges.push({ label: '비활성', tone: 'zinc' });
  return badges;
};

const ModelCards = ({ models }: { models: LlmModel[] }) => (
  <>
    {models.map((m) => (
      <UtilityCard
        key={m.id}
        title={m.display_name}
        description={m.description ?? m.model_name}
        badges={modelBadges(m)}
        dimmed={!m.is_active}
      />
    ))}
  </>
);

const skillBadges = (s: SkillSummary): UtilityBadge[] => {
  const badges: UtilityBadge[] = [];
  if (s.script_type !== 'none') badges.push({ label: s.script_type, tone: 'amber' });
  badges.push({ label: s.visibility, tone: 'sky' });
  return badges;
};

const SkillCards = ({ skills }: { skills: SkillSummary[] }) => (
  <>
    {skills.map((s) => (
      <UtilityCard
        key={s.id}
        title={s.name}
        description={s.description}
        badges={skillBadges(s)}
      />
    ))}
  </>
);

// ─── 그리드 상태 래퍼 ───────────────────────────────────────────────────────

interface GridSectionProps {
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  isEmpty: boolean;
  searching: boolean;
  children: ReactNode;
}

const GridSection = ({ isLoading, isError, onRetry, isEmpty, searching, children }: GridSectionProps) => {
  if (isLoading) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-36 animate-pulse rounded-2xl border border-zinc-100 bg-zinc-50" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50/60 py-14">
        <p className="text-[13.5px] text-zinc-500">목록을 불러오지 못했습니다</p>
        <button
          onClick={onRetry}
          className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
        >
          다시 시도
        </button>
      </div>
    );
  }
  if (isEmpty) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-zinc-50/60 py-14 text-center">
        <p className="text-[13.5px] text-zinc-500">
          {searching ? '검색 결과가 없습니다' : '표시할 항목이 없습니다'}
        </p>
      </div>
    );
  }
  return <div className="grid grid-cols-3 gap-4">{children}</div>;
};

const MiddlewareEmptyState = () => (
  <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-zinc-300 bg-zinc-50/60 py-16">
    <p className="text-[14px] font-medium text-zinc-600">준비 중입니다</p>
    <p className="text-[12.5px] text-zinc-400">미들웨어 카탈로그는 곧 제공됩니다</p>
  </div>
);

// ─── 페이지 ─────────────────────────────────────────────────────────────────

const UtilityPage = () => {
  const [activeTab, setActiveTab] = useState<TabKey>('tools');
  const [search, setSearch] = useState('');
  const [toolFilter, setToolFilter] = useState<ToolFilter>('all');

  const queryClient = useQueryClient();
  const toolsQuery = useToolCatalog();
  const modelsQuery = useLlmModels(true);
  const skillsQuery = useSkills({ scope: 'all', size: 100 });

  const tools = (toolsQuery.data ?? []).filter(
    (t) =>
      (toolFilter === 'all' || toolKind(t) === toolFilter) &&
      matches(search, t.name, t.description),
  );
  const models = (modelsQuery.data ?? []).filter((m) =>
    matches(search, m.display_name, m.model_name, m.description),
  );
  const skills = (skillsQuery.data?.skills ?? []).filter((s) =>
    matches(search, s.name, s.description),
  );
  const skillsTotal = skillsQuery.data?.total ?? 0;

  const tabCount: Record<TabKey, number | null> = {
    tools: toolsQuery.data?.length ?? 0,
    models: modelsQuery.data?.length ?? 0,
    middleware: null,
    skills: skillsQuery.data?.skills.length ?? 0,
  };

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.toolCatalog.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.llmModels.all });
    queryClient.invalidateQueries({ queryKey: [...queryKeys.admin.all, 'skills'] });
  };

  const searching = search.trim() !== '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#fff' }}>
      {/* 헤더 */}
      <header className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
        <div>
          <h1 className="text-[17px] font-bold text-zinc-900">유틸리티</h1>
          <p className="mt-0.5 text-[12.5px] text-zinc-500">
            사용 가능한 도구, 모델, 미들웨어를 찾아보고 추가하세요
          </p>
        </div>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-1.5 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
            />
          </svg>
          새로고침
        </button>
      </header>

      {/* 콘텐츠 */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          {/* 카테고리 탭 */}
          <div role="tablist" className="mb-4 flex items-center gap-1.5">
            {TABS.map(({ key, label }) => (
              <button
                key={key}
                role="tab"
                aria-selected={activeTab === key}
                onClick={() => setActiveTab(key)}
                className={`rounded-xl px-4 py-2 text-[13px] font-medium transition-all ${
                  activeTab === key
                    ? 'bg-zinc-900 text-white shadow-sm'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 hover:text-zinc-800'
                }`}
              >
                {label}
                {tabCount[key] !== null && (
                  <span className={`ml-1.5 text-[11px] ${activeTab === key ? 'text-zinc-400' : 'text-zinc-400'}`}>
                    {tabCount[key]}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* 검색 */}
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 transition-all focus-within:border-violet-400">
            <svg className="h-4 w-4 shrink-0 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
              />
            </svg>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="검색..."
              className="block w-full bg-transparent text-[13.5px] text-zinc-900 placeholder-zinc-400 outline-none"
            />
          </div>

          {/* 유형 필터 (도구 탭 전용) */}
          {activeTab === 'tools' && (
            <div className="mb-5 flex items-center gap-1.5">
              <span className="mr-1 text-[12px] text-zinc-400">유형</span>
              {TOOL_FILTERS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setToolFilter(key)}
                  className={`rounded-full border px-3 py-1.5 text-[12px] font-medium transition-all ${
                    toolFilter === key
                      ? 'border-zinc-900 bg-zinc-900 text-white'
                      : 'border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300 hover:bg-zinc-50'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {/* 탭별 그리드 */}
          {activeTab === 'tools' && (
            <GridSection
              isLoading={toolsQuery.isLoading}
              isError={toolsQuery.isError}
              onRetry={() => toolsQuery.refetch()}
              isEmpty={tools.length === 0}
              searching={searching || toolFilter !== 'all'}
            >
              <ToolCards tools={tools} />
            </GridSection>
          )}

          {activeTab === 'models' && (
            <GridSection
              isLoading={modelsQuery.isLoading}
              isError={modelsQuery.isError}
              onRetry={() => modelsQuery.refetch()}
              isEmpty={models.length === 0}
              searching={searching}
            >
              <ModelCards models={models} />
            </GridSection>
          )}

          {activeTab === 'skills' && (
            <>
              <GridSection
                isLoading={skillsQuery.isLoading}
                isError={skillsQuery.isError}
                onRetry={() => skillsQuery.refetch()}
                isEmpty={skills.length === 0}
                searching={searching}
              >
                <SkillCards skills={skills} />
              </GridSection>
              {skillsTotal > 100 && (
                <p className="mt-4 text-center text-[12px] text-zinc-400">
                  외 {skillsTotal - 100}개 — 관리 화면에서 전체를 볼 수 있습니다
                </p>
              )}
            </>
          )}

          {activeTab === 'middleware' && <MiddlewareEmptyState />}
        </div>
      </div>
    </div>
  );
};

export default UtilityPage;
