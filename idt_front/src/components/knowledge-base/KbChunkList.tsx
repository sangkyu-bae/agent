import { useEffect, useState } from 'react';
import { useKbDocumentChunks } from '@/hooks/useKnowledgeBases';
import type {
  KbBrowseChunkDetail,
  KbStoreSource,
} from '@/types/knowledgeBase';
import KbPayloadMeta from './KbPayloadMeta';

interface KbChunkListProps {
  kbId: string;
  documentId: string;
  source: KbStoreSource;
}

const CARDS_PER_PAGE = 6;
const PREVIEW_LENGTH = 160;

const SEARCH_MODE_HINT: Record<string, string> = {
  match: '형태소 검색 (ES)',
  contains: '단순 포함 검색 (Qdrant)',
};

const ChunkContent = ({ content }: { content: string }) => {
  const [expanded, setExpanded] = useState(false);
  const isLong = content.length > PREVIEW_LENGTH;
  return (
    <div>
      <p className="whitespace-pre-wrap text-[13px] leading-[1.65] text-zinc-600">
        {expanded || !isLong ? content : `${content.slice(0, PREVIEW_LENGTH)}...`}
      </p>
      {isLong && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-[11.5px] font-medium text-violet-500 hover:text-violet-700"
        >
          {expanded ? '접기 ▲' : '펼치기 ▼'}
        </button>
      )}
    </div>
  );
};

const ChunkCard = ({
  chunk,
  indent = false,
}: {
  chunk: KbBrowseChunkDetail;
  indent?: boolean;
}) => (
  <div
    className={`rounded-xl border border-zinc-200 bg-white p-3.5 ${indent ? 'ml-6 border-l-2 border-l-sky-200' : ''}`}
  >
    <div className="mb-1.5 flex items-center gap-2">
      <span className="flex h-5 w-6 items-center justify-center rounded bg-zinc-100 text-[10.5px] font-bold text-zinc-500">
        {chunk.chunk_index}
      </span>
      <span
        className={`rounded px-1.5 py-0.5 text-[10.5px] font-semibold ${
          chunk.chunk_type === 'parent'
            ? 'bg-violet-50 text-violet-600'
            : 'bg-sky-50 text-sky-600'
        }`}
      >
        {chunk.chunk_type}
      </span>
    </div>
    <ChunkContent content={chunk.content} />
    <KbPayloadMeta metadata={chunk.metadata} />
  </div>
);

const KbChunkList = ({ kbId, documentId, source }: KbChunkListProps) => {
  const [searchInput, setSearchInput] = useState('');
  const [q, setQ] = useState<string | undefined>(undefined);
  const [includeParent, setIncludeParent] = useState(true);
  const [page, setPage] = useState(0);

  // 검색 입력 debounce 400ms (Design §5.3)
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(searchInput.trim() || undefined);
      setPage(0);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const chunksQuery = useKbDocumentChunks(kbId, documentId, {
    source,
    include_parent: includeParent,
    ...(q ? { q } : {}),
  });

  if (chunksQuery.isLoading) {
    return (
      <p className="py-8 text-center text-[14px] text-zinc-400">
        청크를 불러오는 중...
      </p>
    );
  }
  if (chunksQuery.isError) {
    return (
      <div className="py-8 text-center">
        <p className="text-[14px] text-red-500">청크를 불러오지 못했습니다</p>
        <button
          type="button"
          onClick={() => chunksQuery.refetch()}
          className="mt-3 rounded-xl border border-zinc-200 px-4 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-50"
        >
          다시 시도
        </button>
      </div>
    );
  }

  const data = chunksQuery.data;
  if (!data) return null;

  const isParentChild = data.chunk_strategy === 'parent_child';

  // 계층 응답은 parent+children 평탄화(들여쓰기 유지), flat 응답은 그대로
  const rows: { chunk: KbBrowseChunkDetail; indent: boolean }[] =
    data.parents !== null && data.parents !== undefined
      ? data.parents.flatMap((p) => [
          {
            chunk: {
              chunk_id: p.chunk_id,
              chunk_index: p.chunk_index,
              chunk_type: p.chunk_type,
              content: p.content,
              metadata: {},
            },
            indent: false,
          },
          ...p.children.map((c) => ({ chunk: c, indent: true })),
        ])
      : data.chunks.map((c) => ({ chunk: c, indent: false }));

  const totalPages = Math.ceil(rows.length / CARDS_PER_PAGE);
  const visible = rows.slice(
    page * CARDS_PER_PAGE,
    (page + 1) * CARDS_PER_PAGE,
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="청크 본문 키워드 검색"
          aria-label="청크 검색"
          className="w-64 rounded-xl border border-zinc-200 px-3.5 py-2 text-[13px] outline-none focus:border-violet-400"
        />
        {data.search_mode && (
          <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[11.5px] font-medium text-amber-600">
            {SEARCH_MODE_HINT[data.search_mode] ?? data.search_mode}
          </span>
        )}
        {isParentChild && (
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-zinc-600">
            <input
              type="checkbox"
              checked={includeParent}
              onChange={(e) => {
                setIncludeParent(e.target.checked);
                setPage(0);
              }}
              className="h-4 w-4 rounded accent-violet-600"
            />
            계층 구조 보기
          </label>
        )}
        <span className="text-[12px] text-zinc-400">
          총 {data.total_chunks}개
        </span>
      </div>

      {rows.length === 0 ? (
        <p className="py-8 text-center text-[14px] text-zinc-400">
          {q ? '검색 결과가 없습니다' : '저장된 청크가 없습니다'}
        </p>
      ) : (
        <>
          <div className="space-y-2.5">
            {visible.map(({ chunk, indent }) => (
              <ChunkCard key={chunk.chunk_id} chunk={chunk} indent={indent} />
            ))}
          </div>
          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[13px] text-zinc-500 disabled:opacity-40"
              >
                이전
              </button>
              <span className="text-[12px] text-zinc-400">
                {page + 1} / {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[13px] text-zinc-500 disabled:opacity-40"
              >
                다음
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default KbChunkList;
