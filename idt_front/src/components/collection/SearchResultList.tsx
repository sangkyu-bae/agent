import SearchResultCard from './SearchResultCard';
import type { SearchResultItem } from '@/types/collection';

interface SearchResultListProps {
  results: SearchResultItem[] | undefined;
  isLoading: boolean;
  isError: boolean;
  totalFound: number;
  bm25Weight: number;
  vectorWeight: number;
}

const SearchResultList = ({
  results,
  isLoading,
  isError,
  totalFound,
  bm25Weight,
  vectorWeight,
}: SearchResultListProps) => {
  return (
    <div className="mt-6 space-y-4">
      {isLoading && (
        <div className="flex flex-col items-center py-12">
          <div
            className="h-10 w-10 animate-spin rounded-full border-4 border-zinc-200"
            style={{ borderTopColor: '#7c3aed' }}
          />
          <p className="mt-3 text-[13px] text-zinc-400">검색 중...</p>
        </div>
      )}

      {isError && (
        <div className="rounded-2xl border border-red-200 bg-red-50/50 px-5 py-8 text-center">
          <p className="text-[14px] font-medium text-red-600">검색 중 오류가 발생했습니다</p>
          <p className="mt-1 text-[12px] text-red-400">잠시 후 다시 시도해주세요</p>
        </div>
      )}

      {!isLoading && !isError && results && results.length === 0 && (
        <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-5 py-8 text-center">
          <p className="text-[14px] font-medium text-zinc-500">검색 결과가 없습니다</p>
          <p className="mt-1 text-[12px] text-zinc-400">다른 쿼리나 가중치를 시도해보세요</p>
        </div>
      )}

      {!isLoading && !isError && results && results.length > 0 && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-[13px] text-zinc-500">
              총 <span className="font-semibold text-zinc-800">{totalFound}</span>건
            </p>
            <p className="text-[12px] text-zinc-400">
              BM25: {bm25Weight} / Vector: {vectorWeight}
            </p>
          </div>
          {results.map((item, idx) => (
            <SearchResultCard key={item.id} item={item} rank={idx + 1} />
          ))}
        </>
      )}
    </div>
  );
};

export default SearchResultList;
