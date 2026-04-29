import { useState } from 'react';
import type { Tool, ToolCategory } from '@/types/tool';
import { TOOL_CATEGORY, TOOL_CATEGORY_LABEL } from '@/types/tool';

// ─── Mock Data ─────────────────────────────────────────────────────────────

const MOCK_TOOLS: Tool[] = [
  {
    id: 'web-search',
    name: '웹 검색',
    description: '인터넷에서 최신 정보를 검색하여 에이전트에 제공합니다.',
    category: TOOL_CATEGORY.search,
    icon: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z',
    enabled: true,
    version: 'v1.2',
  },
  {
    id: 'news-search',
    name: '뉴스 검색',
    description: '국내외 최신 뉴스 기사를 검색하고 요약합니다.',
    category: TOOL_CATEGORY.search,
    icon: 'M12 7.5h1.5m-1.5 3h1.5m-7.5 3h7.5m-7.5 3h7.5m3-9h3.375c.621 0 1.125.504 1.125 1.125V18a2.25 2.25 0 0 1-2.25 2.25M16.5 7.5V18a2.25 2.25 0 0 0 2.25 2.25M16.5 7.5V4.875c0-.621-.504-1.125-1.125-1.125H4.125C3.504 3.75 3 4.254 3 4.875V18a2.25 2.25 0 0 0 2.25 2.25h13.5M6 7.5h3v3H6v-3Z',
    enabled: true,
    version: 'v1.0',
  },
  {
    id: 'code-execution',
    name: '코드 실행',
    description: 'Python 코드를 안전한 샌드박스 환경에서 실행합니다.',
    category: TOOL_CATEGORY.execution,
    icon: 'M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5',
    enabled: false,
    version: 'v2.1',
  },
  {
    id: 'file-reader',
    name: '파일 읽기',
    description: '업로드된 파일의 내용을 읽어 에이전트에 전달합니다.',
    category: TOOL_CATEGORY.execution,
    icon: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
    enabled: false,
    version: 'v1.3',
  },
  {
    id: 'calculator',
    name: '계산기',
    description: '수학적 연산, 수식 계산, 통계 처리를 수행합니다.',
    category: TOOL_CATEGORY.execution,
    icon: 'M15.75 15.75V18m-7.5-6.75h.008v.008H8.25v-.008Zm0 2.25h.008v.008H8.25V13.5Zm0 2.25h.008v.008H8.25v-.008Zm0 2.25h.008v.008H8.25V18Zm2.498-6.75h.007v.008h-.007v-.008Zm0 2.25h.007v.008h-.007V13.5Zm0 2.25h.007v.008h-.007v-.008Zm0 2.25h.007v.008h-.007V18Zm2.504-6.75h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V13.5Zm0 2.25h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V18Zm2.498-6.75h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V13.5ZM8.25 6h7.5v2.25h-7.5V6ZM12 2.25c-1.892 0-3.758.11-5.593.322C5.307 2.7 4.5 3.65 4.5 4.757V19.5a2.25 2.25 0 0 0 2.25 2.25h10.5a2.25 2.25 0 0 0 2.25-2.25V4.757c0-1.108-.806-2.057-1.907-2.185A48.507 48.507 0 0 0 12 2.25Z',
    enabled: true,
    version: 'v1.1',
  },
  {
    id: 'http-request',
    name: 'HTTP 요청',
    description: '외부 REST API에 GET/POST/PUT 등의 HTTP 요청을 전송합니다.',
    category: TOOL_CATEGORY.api,
    icon: 'M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418',
    enabled: true,
    version: 'v1.4',
  },
  {
    id: 'email',
    name: '이메일 전송',
    description: '사용자를 대신해 이메일을 작성하고 전송합니다.',
    category: TOOL_CATEGORY.api,
    icon: 'M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75',
    enabled: false,
    version: 'v1.0',
  },
  {
    id: 'sql-query',
    name: 'SQL 쿼리',
    description: '연결된 데이터베이스에 SQL 쿼리를 실행하고 결과를 반환합니다.',
    category: TOOL_CATEGORY.data,
    icon: 'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125',
    enabled: true,
    version: 'v2.0',
  },
  {
    id: 'vector-search',
    name: '벡터 검색',
    description: '벡터 데이터베이스에서 의미적으로 유사한 문서를 검색합니다.',
    category: TOOL_CATEGORY.data,
    icon: 'M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 1-6.23-.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5',
    enabled: false,
    version: 'v1.5',
  },
];

// ─── Category Style Map ─────────────────────────────────────────────────────

const CATEGORY_STYLE: Record<ToolCategory, { bg: string; text: string; dot: string }> = {
  search: { bg: 'bg-sky-50', text: 'text-sky-600', dot: 'bg-sky-400' },
  execution: { bg: 'bg-amber-50', text: 'text-amber-600', dot: 'bg-amber-400' },
  api: { bg: 'bg-emerald-50', text: 'text-emerald-600', dot: 'bg-emerald-400' },
  data: { bg: 'bg-violet-50', text: 'text-violet-600', dot: 'bg-violet-400' },
};

// ─── Toggle Switch ──────────────────────────────────────────────────────────

interface ToggleSwitchProps {
  enabled: boolean;
  onToggle: () => void;
}

const ToggleSwitch = ({ enabled, onToggle }: ToggleSwitchProps) => (
  <button
    onClick={(e) => { e.stopPropagation(); onToggle(); }}
    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none ${
      enabled ? 'bg-violet-600' : 'bg-zinc-200'
    }`}
    aria-label={enabled ? '비활성화' : '활성화'}
  >
    <span
      className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
        enabled ? 'translate-x-6' : 'translate-x-1'
      }`}
    />
  </button>
);

// ─── Tool Card ──────────────────────────────────────────────────────────────

interface ToolCardProps {
  tool: Tool;
  onToggle: (id: string) => void;
}

const ToolCard = ({ tool, onToggle }: ToolCardProps) => {
  const catStyle = CATEGORY_STYLE[tool.category];

  return (
    <div
      className={`group relative flex flex-col overflow-hidden rounded-2xl border bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${
        tool.enabled ? 'border-violet-200' : 'border-zinc-200'
      }`}
    >
      {/* 활성 표시선 */}
      {tool.enabled && (
        <div
          className="absolute inset-x-0 top-0 h-0.5 rounded-t-2xl"
          style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
        />
      )}

      {/* 상단: 아이콘 + 토글 */}
      <div className="flex items-start justify-between">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all ${
            tool.enabled
              ? 'shadow-md'
              : 'bg-zinc-100'
          }`}
          style={tool.enabled ? { background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' } : {}}
        >
          <svg
            className={`h-5 w-5 ${tool.enabled ? 'text-white' : 'text-zinc-400'}`}
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d={tool.icon} />
          </svg>
        </div>
        <ToggleSwitch enabled={tool.enabled} onToggle={() => onToggle(tool.id)} />
      </div>

      {/* 이름 + 설명 */}
      <div className="mt-3 flex-1">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-semibold text-zinc-900">{tool.name}</h3>
          {tool.version && (
            <span className="text-[10.5px] text-zinc-300">{tool.version}</span>
          )}
        </div>
        <p className="mt-1 text-[12.5px] leading-[1.6] text-zinc-500">{tool.description}</p>
      </div>

      {/* 카테고리 배지 */}
      <div className="mt-3.5 flex items-center gap-2">
        <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${catStyle.bg} ${catStyle.text}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${catStyle.dot}`} />
          {TOOL_CATEGORY_LABEL[tool.category]}
        </span>
        {tool.enabled && (
          <span className="flex items-center gap-1 text-[11px] text-emerald-500">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            활성
          </span>
        )}
      </div>
    </div>
  );
};

// ─── Page ───────────────────────────────────────────────────────────────────

type FilterType = 'all' | ToolCategory;

const FILTER_TABS: { key: FilterType; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: TOOL_CATEGORY.search, label: '검색' },
  { key: TOOL_CATEGORY.execution, label: '실행' },
  { key: TOOL_CATEGORY.api, label: 'API' },
  { key: TOOL_CATEGORY.data, label: '데이터' },
];

const ToolConnectionPage = () => {
  const [tools, setTools] = useState<Tool[]>(MOCK_TOOLS);
  const [activeFilter, setActiveFilter] = useState<FilterType>('all');

  const enabledCount = tools.filter((t) => t.enabled).length;

  const filtered = activeFilter === 'all'
    ? tools
    : tools.filter((t) => t.category === activeFilter);

  const handleToggle = (id: string) => {
    setTools((prev) =>
      prev.map((t) => (t.id === id ? { ...t, enabled: !t.enabled } : t)),
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#fff' }}>
        {/* 헤더 */}
        <header className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z" />
              </svg>
            </div>
            <div>
              <h1 className="text-[15px] font-semibold text-zinc-900">도구 연결</h1>
              <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                Tool Connection
              </p>
            </div>
          </div>

          {/* 활성 도구 카운트 */}
          <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
            <span className="text-[13px] font-medium text-zinc-700">
              {enabledCount}개 도구 활성화됨
            </span>
            <span className="text-[12px] text-zinc-400">/ {tools.length}개</span>
          </div>
        </header>

        {/* 콘텐츠 */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ maxWidth: '1024px', margin: '0 auto', padding: '1.5rem' }}>

            {/* 필터 탭 */}
            <div className="mb-6 flex items-center gap-1.5">
              {FILTER_TABS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setActiveFilter(key)}
                  className={`rounded-xl px-4 py-2 text-[13px] font-medium transition-all ${
                    activeFilter === key
                      ? 'bg-violet-600 text-white shadow-sm'
                      : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 hover:text-zinc-800'
                  }`}
                >
                  {label}
                  <span className={`ml-1.5 text-[11px] ${activeFilter === key ? 'text-violet-200' : 'text-zinc-400'}`}>
                    {key === 'all'
                      ? tools.length
                      : tools.filter((t) => t.category === key).length}
                  </span>
                </button>
              ))}
            </div>

            {/* 도구 카드 그리드 */}
            <div className="grid grid-cols-3 gap-4">
              {filtered.map((tool) => (
                <ToolCard key={tool.id} tool={tool} onToggle={handleToggle} />
              ))}
            </div>

            {/* 활성 도구 목록 요약 */}
            {enabledCount > 0 && (
              <div className="mt-8 rounded-2xl border border-zinc-200 bg-zinc-50/60 p-5">
                <p className="mb-3 text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                  활성화된 도구
                </p>
                <div className="flex flex-wrap gap-2">
                  {tools
                    .filter((t) => t.enabled)
                    .map((t) => {
                      const style = CATEGORY_STYLE[t.category];
                      return (
                        <div
                          key={t.id}
                          className={`flex items-center gap-2 rounded-xl border px-3 py-2 ${style.bg} border-transparent`}
                        >
                          <svg
                            className={`h-3.5 w-3.5 ${style.text}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={2}
                            stroke="currentColor"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d={t.icon} />
                          </svg>
                          <span className={`text-[12.5px] font-medium ${style.text}`}>{t.name}</span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        </div>
    </div>
  );
};

export default ToolConnectionPage;
