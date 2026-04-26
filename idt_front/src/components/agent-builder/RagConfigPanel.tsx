import { useCollections, useMetadataKeys } from '@/hooks/useRagToolConfig';
import type { RagToolConfig, CollectionScope } from '@/types/ragToolConfig';

const SCOPE_LABELS: Record<CollectionScope, { label: string; color: string }> = {
  PERSONAL: { label: '개인', color: 'text-violet-600 bg-violet-50' },
  DEPARTMENT: { label: '부서', color: 'text-blue-600 bg-blue-50' },
  PUBLIC: { label: '공개', color: 'text-emerald-600 bg-emerald-50' },
};

interface RagConfigPanelProps {
  config: RagToolConfig;
  onChange: (config: RagToolConfig) => void;
}

const SEARCH_MODES = [
  { value: 'hybrid', label: '하이브리드' },
  { value: 'vector_only', label: '벡터' },
  { value: 'bm25_only', label: 'BM25' },
] as const;

const MAX_FILTERS = 10;
const MAX_TOOL_NAME = 100;
const MAX_TOOL_DESCRIPTION = 500;

const RagConfigPanel = ({ config, onChange }: RagConfigPanelProps) => {
  const { data: collections, isLoading: isCollLoading, isError: isCollError, refetch: refetchColl } = useCollections();
  const { data: metadataKeys } = useMetadataKeys(config.collection_name);

  const filterEntries = Object.entries(config.metadata_filter);

  const handleCollectionChange = (name: string) => {
    onChange({
      ...config,
      collection_name: name || undefined,
      metadata_filter: {},
    });
  };

  const handleAddFilter = () => {
    if (filterEntries.length >= MAX_FILTERS) return;
    onChange({
      ...config,
      metadata_filter: { ...config.metadata_filter, '': '' },
    });
  };

  const handleFilterChange = (oldKey: string, newKey: string, value: string, index: number) => {
    const entries = Object.entries(config.metadata_filter);
    entries[index] = [newKey, value];
    const newFilter: Record<string, string> = {};
    entries.forEach(([k, v]) => { newFilter[k] = v; });
    onChange({ ...config, metadata_filter: newFilter });
  };

  const handleRemoveFilter = (key: string) => {
    const { [key]: _, ...rest } = config.metadata_filter;
    onChange({ ...config, metadata_filter: rest });
  };

  return (
    <div className="rounded-2xl border border-violet-200 bg-violet-50/30 p-5 space-y-6">
      {/* Section 1: 컬렉션 선택 */}
      <div>
        <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">
          검색 대상 컬렉션
        </label>
        {isCollLoading ? (
          <div className="h-[42px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
        ) : isCollError ? (
          <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
            <p className="flex-1 text-[13px] text-zinc-500">컬렉션 목록을 불러올 수 없습니다</p>
            <button
              onClick={() => refetchColl()}
              className="rounded-lg bg-violet-600 px-3 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
            >
              재시도
            </button>
          </div>
        ) : (
          <select
            value={config.collection_name ?? ''}
            onChange={(e) => handleCollectionChange(e.target.value)}
            className="w-full rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[14px] text-zinc-900 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          >
            <option value="">전체 (기본)</option>
            {collections?.map((c) => {
              const scopeLabel = c.scope ? SCOPE_LABELS[c.scope]?.label : null;
              return (
                <option key={c.name} value={c.name}>
                  {scopeLabel ? `[${scopeLabel}] ` : ''}{c.display_name}{c.vectors_count != null ? ` (${c.vectors_count}건)` : ''}
                </option>
              );
            })}
          </select>
        )}
        {(() => {
          const selected = collections?.find((c) => c.name === config.collection_name);
          if (!selected?.scope || selected.scope === 'PUBLIC') return null;
          const info = SCOPE_LABELS[selected.scope];
          return (
            <p className={`mt-1.5 text-[12px] ${info.color} rounded-lg px-2 py-1 inline-block`}>
              이 컬렉션은 {info.label}용이므로 에이전트 공개 범위가 자동 제한됩니다
            </p>
          );
        })()}
      </div>

      {/* Section 2: 메타데이터 필터 */}
      <div>
        <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">
          메타데이터 필터
        </label>
        <div className="space-y-2">
          {filterEntries.map(([key, value], idx) => (
            <div key={idx} className="flex items-center gap-2">
              {metadataKeys && metadataKeys.length > 0 ? (
                <select
                  value={key}
                  onChange={(e) => handleFilterChange(key, e.target.value, value, idx)}
                  className="flex-1 rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13px] text-zinc-900 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                >
                  <option value="">키 선택</option>
                  {metadataKeys.map((mk) => (
                    <option key={mk.key} value={mk.key}>{mk.key}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={key}
                  onChange={(e) => handleFilterChange(key, e.target.value, value, idx)}
                  placeholder="키"
                  className="flex-1 rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
              )}

              {metadataKeys?.find((mk) => mk.key === key)?.sample_values ? (
                <select
                  value={value}
                  onChange={(e) => handleFilterChange(key, key, e.target.value, idx)}
                  className="flex-1 rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13px] text-zinc-900 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                >
                  <option value="">값 선택</option>
                  {metadataKeys.find((mk) => mk.key === key)!.sample_values.map((sv) => (
                    <option key={sv} value={sv}>{sv}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={value}
                  onChange={(e) => handleFilterChange(key, key, e.target.value, idx)}
                  placeholder="값"
                  className="flex-1 rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
              )}

              <button
                onClick={() => handleRemoveFilter(key)}
                className="shrink-0 rounded-lg p-1.5 text-zinc-400 transition-colors hover:text-red-500"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>

        {filterEntries.length < MAX_FILTERS ? (
          <button
            onClick={handleAddFilter}
            className="mt-2 flex items-center gap-1.5 rounded-xl bg-violet-600 px-3.5 py-2 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            필터 추가
          </button>
        ) : (
          <p className="mt-2 text-[12px] text-zinc-400">최대 {MAX_FILTERS}개까지 추가할 수 있습니다</p>
        )}
      </div>

      {/* Section 3: 검색 파라미터 */}
      <div>
        <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">검색 모드</label>
        <div className="flex gap-3">
          {SEARCH_MODES.map((mode) => (
            <label key={mode.value} className="flex cursor-pointer items-center gap-2">
              <input
                type="radio"
                name="search_mode"
                value={mode.value}
                checked={config.search_mode === mode.value}
                onChange={() => onChange({ ...config, search_mode: mode.value })}
                className="h-4 w-4 accent-violet-600"
              />
              <span className="text-[13px] text-zinc-700">{mode.label}</span>
            </label>
          ))}
        </div>

        <div className="mt-4">
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-[13px] font-semibold text-zinc-700">결과 수 (top_k)</label>
            <span className="rounded-lg bg-zinc-100 px-2.5 py-1 text-[12.5px] font-semibold tabular-nums text-zinc-700">
              {config.top_k}
            </span>
          </div>
          <input
            type="range"
            min="1"
            max="20"
            step="1"
            value={config.top_k}
            onChange={(e) => onChange({ ...config, top_k: parseInt(e.target.value) })}
            className="h-2 w-full cursor-pointer appearance-none rounded-full bg-zinc-200 accent-violet-600"
          />
          <div className="mt-1 flex justify-between text-[11px] text-zinc-400">
            <span>1</span>
            <span>10</span>
            <span>20</span>
          </div>
        </div>
      </div>

      {/* Section 4: 도구 이름/설명 */}
      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">도구 이름</label>
          <input
            type="text"
            value={config.tool_name}
            onChange={(e) => onChange({ ...config, tool_name: e.target.value })}
            maxLength={MAX_TOOL_NAME}
            placeholder="예: 금융 정책 검색"
            className="w-full rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">도구 설명</label>
          <div className="overflow-hidden rounded-2xl border border-zinc-300 bg-white transition-all focus-within:border-violet-400 focus-within:ring-2 focus-within:ring-violet-100">
            <textarea
              value={config.tool_description}
              onChange={(e) => onChange({ ...config, tool_description: e.target.value })}
              maxLength={MAX_TOOL_DESCRIPTION}
              placeholder="에이전트가 이 도구를 언제 사용해야 하는지 설명하세요"
              rows={3}
              className="block w-full resize-none bg-transparent px-4 py-3 text-[14px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none"
            />
          </div>
          <p className="mt-1 text-right text-[12px] text-zinc-400">
            {config.tool_description.length}/{MAX_TOOL_DESCRIPTION}
          </p>
        </div>
      </div>
    </div>
  );
};

export default RagConfigPanel;
