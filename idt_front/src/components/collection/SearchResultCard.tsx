import { useState } from 'react';
import { SEARCH_SOURCE_BADGE } from '@/types/collection';
import type { SearchResultItem } from '@/types/collection';

interface SearchResultCardProps {
  item: SearchResultItem;
  rank: number;
}

const SearchResultCard = ({ item, rank }: SearchResultCardProps) => {
  const [expanded, setExpanded] = useState(false);
  const shouldTruncate = item.content.split('\n').length > 3 || item.content.length > 200;
  const badge = SEARCH_SOURCE_BADGE[item.source];

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 transition-all duration-200 hover:border-zinc-300 hover:shadow-sm">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-100 text-[12px] font-bold text-violet-700">
            #{rank}
          </span>
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${badge.bg} ${badge.color}`}>
            {badge.label}
          </span>
        </div>
        <span className="text-[12px] font-medium text-zinc-500">
          Score: <span className="text-zinc-800">{item.score.toFixed(4)}</span>
        </span>
      </div>

      {/* Score details */}
      <div className="mb-3 flex gap-4 text-[12px] text-zinc-500">
        {item.bm25_rank !== null && (
          <span>
            BM25: rank #{item.bm25_rank}
            {item.bm25_score !== null && `, score ${item.bm25_score.toFixed(2)}`}
          </span>
        )}
        {item.vector_rank !== null && (
          <span>
            Vector: rank #{item.vector_rank}
            {item.vector_score !== null && `, score ${item.vector_score.toFixed(4)}`}
          </span>
        )}
      </div>

      <div className="mb-3 border-t border-zinc-100" />

      {/* Content */}
      <div>
        <p className={`whitespace-pre-wrap text-[13.5px] leading-relaxed text-zinc-700 ${!expanded && shouldTruncate ? 'line-clamp-3' : ''}`}>
          {item.content}
        </p>
        {shouldTruncate && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-1 text-[12px] font-medium text-violet-500 transition-colors hover:text-violet-700"
          >
            {expanded ? '접기' : '더보기'}
          </button>
        )}
      </div>

      {/* Metadata */}
      {item.metadata?.document_id ? (
        <div className="mt-2 flex items-center gap-1.5 text-[11px] text-zinc-400">
          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
          </svg>
          <span className="font-mono">{String(item.metadata.document_id).slice(0, 12)}...</span>
        </div>
      ) : null}
    </div>
  );
};

export default SearchResultCard;
