import { useState } from 'react';
import { useSearchHistory } from '@/hooks/useCollections';

interface SearchHistoryPanelProps {
  collectionName: string;
  onApply: (params: {
    query: string;
    topK: number;
    bm25Weight: number;
    vectorWeight: number;
  }) => void;
}

const formatRelativeTime = (isoDate: string): string => {
  const diff = Date.now() - new Date(isoDate).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '방금 전';
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  return `${days}일 전`;
};

const SearchHistoryPanel = ({ collectionName, onApply }: SearchHistoryPanelProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const historyQuery = useSearchHistory(collectionName, { limit: 10 });
  const histories = historyQuery.data?.histories ?? [];

  return (
    <div className="mt-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 text-[13px] font-medium text-zinc-500 transition-colors hover:text-zinc-700"
      >
        <svg
          className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={2}
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
        </svg>
        검색 히스토리
        {historyQuery.data && (
          <span className="rounded-full bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-500">
            {historyQuery.data.total}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="mt-3 overflow-hidden rounded-xl border border-zinc-200">
          {historyQuery.isLoading && (
            <div className="px-4 py-6 text-center text-[13px] text-zinc-400">로딩 중...</div>
          )}

          {!historyQuery.isLoading && histories.length === 0 && (
            <div className="px-4 py-6 text-center text-[13px] text-zinc-400">
              검색 히스토리가 없습니다
            </div>
          )}

          {histories.length > 0 && (
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b border-zinc-100 bg-zinc-50">
                  <th className="px-3 py-2 text-left font-medium text-zinc-500">쿼리</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500">BM25</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500">Vector</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500">Top K</th>
                  <th className="px-3 py-2 text-center font-medium text-zinc-500">결과</th>
                  <th className="px-3 py-2 text-right font-medium text-zinc-500">시간</th>
                </tr>
              </thead>
              <tbody>
                {histories.map((h) => (
                  <tr
                    key={h.id}
                    onClick={() =>
                      onApply({
                        query: h.query,
                        topK: h.top_k,
                        bm25Weight: h.bm25_weight,
                        vectorWeight: h.vector_weight,
                      })
                    }
                    className="cursor-pointer border-b border-zinc-50 transition-colors hover:bg-violet-50/50"
                  >
                    <td className="max-w-[200px] truncate px-3 py-2.5 text-zinc-700">
                      {h.query}
                    </td>
                    <td className="px-3 py-2.5 text-center text-zinc-500">{h.bm25_weight}</td>
                    <td className="px-3 py-2.5 text-center text-zinc-500">{h.vector_weight}</td>
                    <td className="px-3 py-2.5 text-center text-zinc-500">{h.top_k}</td>
                    <td className="px-3 py-2.5 text-center text-zinc-500">{h.result_count}건</td>
                    <td className="px-3 py-2.5 text-right text-zinc-400">
                      {formatRelativeTime(h.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

export default SearchHistoryPanel;
