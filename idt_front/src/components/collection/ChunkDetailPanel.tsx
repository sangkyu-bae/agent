import { useState } from 'react';
import type { DocumentChunksResponse, ChunkDetail } from '@/types/collection';
import { CHUNK_STRATEGY_BADGE, CHUNK_TYPE_BADGE } from '@/types/collection';
import ChunkDetailModal from './ChunkDetailModal';

interface ChunkDetailPanelProps {
  data: DocumentChunksResponse | null;
  isLoading: boolean;
  showHierarchy?: boolean;
  onToggleHierarchy?: (value: boolean) => void;
}

const CARDS_PER_PAGE = 6;

const SkeletonCards = () => (
  <div className="grid grid-cols-3 gap-3">
    {[1, 2, 3, 4, 5, 6].map((i) => (
      <div key={i} className="h-36 animate-pulse rounded-xl bg-zinc-100" />
    ))}
  </div>
);

const ChunkDetailPanel = ({ data, isLoading, showHierarchy = false, onToggleHierarchy }: ChunkDetailPanelProps) => {
  const [chunkPage, setChunkPage] = useState(0);
  const [selectedChunk, setSelectedChunk] = useState<ChunkDetail | null>(null);

  if (isLoading || !data) {
    return (
      <div className="mt-6 rounded-2xl border border-zinc-200 bg-white p-5">
        <SkeletonCards />
      </div>
    );
  }

  const strategyBadge = CHUNK_STRATEGY_BADGE[data.chunk_strategy];
  const isParentChild = data.chunk_strategy === 'parent_child';

  const allChunks: ChunkDetail[] = showHierarchy && isParentChild && data.parents
    ? data.parents.flatMap((p) => [
        { chunk_id: p.chunk_id, chunk_index: p.chunk_index, chunk_type: p.chunk_type, content: p.content, metadata: {} },
        ...p.children,
      ])
    : data.chunks;

  const totalChunkPages = Math.ceil(allChunks.length / CARDS_PER_PAGE);
  const startIdx = chunkPage * CARDS_PER_PAGE;
  const visibleChunks = allChunks.slice(startIdx, startIdx + CARDS_PER_PAGE);

  return (
    <>
      <div className="mt-6 rounded-2xl border border-zinc-200 bg-white p-5">
        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="text-[15px] font-semibold text-zinc-900">
              {data.filename}
            </h3>
            <div className="mt-1 flex items-center gap-2">
              <span className={`rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${strategyBadge.bg} ${strategyBadge.color}`}>
                {strategyBadge.label}
              </span>
              <span className="text-[12px] text-zinc-400">
                총 {data.total_chunks}개 청크
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {isParentChild && (
              <label className="flex cursor-pointer items-center gap-2 text-[13px] text-zinc-600">
                <input
                  type="checkbox"
                  checked={showHierarchy}
                  onChange={(e) => {
                    onToggleHierarchy?.(e.target.checked);
                    setChunkPage(0);
                  }}
                  className="h-4 w-4 rounded accent-violet-600"
                />
                계층 구조 보기
              </label>
            )}
          </div>
        </div>

        {/* Chunk Cards Grid */}
        {allChunks.length === 0 ? (
          <p className="py-8 text-center text-[15px] text-zinc-400">
            청크가 없습니다
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {visibleChunks.map((chunk) => {
                const typeBadge = CHUNK_TYPE_BADGE[chunk.chunk_type];
                const preview = chunk.content.slice(0, 120);

                return (
                  <div
                    key={chunk.chunk_id}
                    onClick={() => setSelectedChunk(chunk)}
                    className="group relative cursor-pointer overflow-hidden rounded-xl border border-zinc-200 bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-violet-200 hover:shadow-lg"
                  >
                    {/* Card Header */}
                    <div className="mb-2 flex items-center gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded-md bg-zinc-100 text-[11px] font-bold text-zinc-500 transition-colors group-hover:bg-violet-100 group-hover:text-violet-600">
                        {chunk.chunk_index}
                      </span>
                      <span className={`rounded-md px-1.5 py-0.5 text-[10.5px] font-semibold ${typeBadge.bg} ${typeBadge.color}`}>
                        {typeBadge.label}
                      </span>
                    </div>

                    {/* Card Content Preview */}
                    <p className="line-clamp-4 text-[12.5px] leading-[1.6] text-zinc-600">
                      {preview}{chunk.content.length > 120 ? '...' : ''}
                    </p>

                    {/* Hover indicator */}
                    <div className="absolute bottom-2 right-2 opacity-0 transition-opacity group-hover:opacity-100">
                      <svg className="h-4 w-4 text-violet-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 19.5 15-15m0 0H8.25m11.25 0v11.25" />
                      </svg>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Pagination */}
            {totalChunkPages > 1 && (
              <div className="mt-4 flex items-center justify-center gap-3">
                <button
                  onClick={() => setChunkPage((p) => Math.max(0, p - 1))}
                  disabled={chunkPage === 0}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-500 transition-all hover:border-zinc-300 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
                  </svg>
                </button>
                <span className="text-[12px] text-zinc-400">
                  {chunkPage + 1} / {totalChunkPages}
                </span>
                <button
                  onClick={() => setChunkPage((p) => Math.min(totalChunkPages - 1, p + 1))}
                  disabled={chunkPage >= totalChunkPages - 1}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-500 transition-all hover:border-zinc-300 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                  </svg>
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Chunk Detail Modal */}
      {selectedChunk && (
        <ChunkDetailModal
          chunk={selectedChunk}
          onClose={() => setSelectedChunk(null)}
        />
      )}
    </>
  );
};

export default ChunkDetailPanel;
