import { useState } from 'react';
import HybridSearchPanel from '@/components/collection/HybridSearchPanel';
import SearchResultList from '@/components/collection/SearchResultList';
import KbSearchHistoryPanel from '@/components/knowledge-base/KbSearchHistoryPanel';
import { useKbSearch } from '@/hooks/useKnowledgeBases';
import type { KbSearchResponse } from '@/types/knowledgeBase';

interface KbSearchSectionProps {
  kbId: string;
  /** D10: 문서 단위 검색 스코프 — 드릴다운 선택과 독립 */
  scopeDoc: { document_id: string; filename: string } | null;
  onClearScope: () => void;
}

/** KB 리트리버 테스트 섹션 (kb-retrieval-test FR-08/09/10).
 *  컬렉션 문서 페이지의 하이브리드 검색 UI를 KB 범위로 재구성 —
 *  검색은 항상 이 KB 문서(kb_id payload)로 격리된다. */
const KbSearchSection = ({
  kbId,
  scopeDoc,
  onClearScope,
}: KbSearchSectionProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [topK, setTopK] = useState<number>(5);
  const [bm25Weight, setBm25Weight] = useState(0.5);
  const [vectorWeight, setVectorWeight] = useState(0.5);
  const [searchResult, setSearchResult] = useState<KbSearchResponse | null>(
    null,
  );

  const searchMutation = useKbSearch();

  const handleSearch = () => {
    if (!searchQuery.trim()) return;
    searchMutation.mutate(
      {
        kbId,
        data: {
          query: searchQuery.trim(),
          top_k: topK,
          bm25_weight: bm25Weight,
          vector_weight: vectorWeight,
          document_id: scopeDoc?.document_id,
        },
      },
      {
        onSuccess: (data) => setSearchResult(data),
      },
    );
  };

  const handleHistoryApply = (params: {
    query: string;
    topK: number;
    bm25Weight: number;
    vectorWeight: number;
  }) => {
    setSearchQuery(params.query);
    setTopK(params.topK);
    setBm25Weight(params.bm25Weight);
    setVectorWeight(params.vectorWeight);
  };

  return (
    <div className="mt-8 rounded-2xl border border-zinc-200 bg-white p-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-100">
            <svg className="h-5 w-5 text-violet-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
          </div>
          <div>
            <h3 className="text-[15px] font-semibold text-zinc-900">
              리트리버 테스트
            </h3>
            <p className="text-[12px] text-zinc-400">
              이 지식베이스 문서만 대상으로 BM25 + 벡터 하이브리드 검색을
              확인합니다
            </p>
          </div>
        </div>

        {/* 검색 스코프 배지 (FR-09) */}
        {scopeDoc ? (
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-violet-50 px-3 py-1.5 text-[12px] font-medium text-violet-700">
            {scopeDoc.filename}에서 검색
            <button
              aria-label="KB 전체 검색으로 전환"
              onClick={onClearScope}
              className="text-violet-400 transition-colors hover:text-violet-700"
            >
              ✕
            </button>
          </span>
        ) : (
          <span className="inline-flex items-center rounded-lg bg-zinc-100 px-3 py-1.5 text-[12px] font-medium text-zinc-500">
            KB 전체에서 검색
          </span>
        )}
      </div>

      {/* Search Input + Button */}
      <div className="flex gap-3">
        <div className="flex-1 overflow-hidden rounded-2xl border border-zinc-300 bg-white shadow-sm transition-all focus-within:border-violet-400 focus-within:shadow-violet-100/60">
          <div className="flex items-center px-4">
            <svg className="h-4 w-4 shrink-0 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="검색 쿼리를 입력하세요 (예: 여신 한도 기준)"
              className="block w-full bg-transparent px-3 py-3 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none"
            />
          </div>
        </div>

        <button
          onClick={handleSearch}
          disabled={!searchQuery.trim() || searchMutation.isPending}
          className={`flex items-center gap-2 rounded-2xl px-5 text-[13.5px] font-medium shadow-sm transition-all active:scale-95 ${
            searchQuery.trim() && !searchMutation.isPending
              ? 'bg-violet-600 text-white hover:bg-violet-700'
              : 'cursor-not-allowed bg-zinc-200 text-zinc-400'
          }`}
        >
          {searchMutation.isPending ? (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
          ) : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
          )}
          검색
        </button>
      </div>

      {/* Search Options Panel */}
      <div className="mt-4">
        <HybridSearchPanel
          bm25Weight={bm25Weight}
          vectorWeight={vectorWeight}
          topK={topK}
          onBm25WeightChange={setBm25Weight}
          onVectorWeightChange={setVectorWeight}
          onTopKChange={setTopK}
        />
      </div>

      {/* Search Results */}
      {searchMutation.isError && (
        <p className="mt-4 text-[13px] text-red-500">
          검색 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.
        </p>
      )}
      {(searchResult || searchMutation.isPending) && (
        <SearchResultList
          results={searchResult?.results}
          isLoading={searchMutation.isPending}
          isError={false}
          totalFound={searchResult?.total_found ?? 0}
          bm25Weight={searchResult?.bm25_weight ?? bm25Weight}
          vectorWeight={searchResult?.vector_weight ?? vectorWeight}
        />
      )}

      {/* Search History */}
      <KbSearchHistoryPanel kbId={kbId} onApply={handleHistoryApply} />
    </div>
  );
};

export default KbSearchSection;
