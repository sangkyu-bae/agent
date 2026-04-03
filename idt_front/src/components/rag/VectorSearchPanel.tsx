import { useState, useRef } from 'react';
import { Search, Loader2, ChevronDown } from 'lucide-react';
import { useVectorSearch } from '@/hooks/useDocuments';
import type { RetrievedChunk } from '@/types/rag';

// ─── Score Badge ─────────────────────────────────────────────────────────────

interface ScoreBadgeProps { score: number }

const ScoreBadge = ({ score }: ScoreBadgeProps) => {
  const pct = Math.round(score * 100);
  const style =
    score >= 0.80 ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
    score >= 0.60 ? 'bg-amber-50 text-amber-700 border-amber-200' :
                    'bg-red-50 text-red-600 border-red-200';
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold tabular-nums ${style}`}>
      {pct}%
    </span>
  );
};

// ─── Result Card ─────────────────────────────────────────────────────────────

interface ResultCardProps {
  rank: number;
  chunk: RetrievedChunk;
  query: string;
}

const highlightQuery = (text: string, query: string): React.ReactNode => {
  if (!query.trim()) return text;
  const keywords = query.trim().split(/\s+/).filter(Boolean);
  const pattern = new RegExp(`(${keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
  const parts = text.split(pattern);
  return parts.map((part, i) =>
    pattern.test(part)
      ? <mark key={i} className="rounded bg-violet-100 px-0.5 text-violet-800 not-italic">{part}</mark>
      : part
  );
};

const ResultCard = ({ rank, chunk, query }: ResultCardProps) => {
  const [expanded, setExpanded] = useState(false);
  const isLong = chunk.content.length > 200;
  const displayContent = !expanded && isLong ? chunk.content.slice(0, 200) + '...' : chunk.content;

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm transition-all duration-150 hover:border-violet-200 hover:shadow-md">
      {/* 상단: 랭크 + 문서 정보 + 점수 */}
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {/* 랭크 번호 */}
          <span
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold text-white"
            style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
          >
            {rank}
          </span>
          <div>
            <p className="text-[13px] font-semibold text-zinc-900 leading-snug">{chunk.documentName}</p>
            <p className="text-[11px] text-zinc-400">청크 #{chunk.chunkIndex}</p>
          </div>
        </div>
        <ScoreBadge score={chunk.score} />
      </div>

      {/* 내용 */}
      <div className="text-[13px] leading-[1.7] text-zinc-700">
        {highlightQuery(displayContent, query)}
      </div>

      {/* 더 보기 / 접기 */}
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 flex items-center gap-1 text-[11.5px] font-medium text-violet-500 hover:text-violet-700 transition-colors"
        >
          <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-150 ${expanded ? 'rotate-180' : ''}`} />
          {expanded ? '접기' : '전체 보기'}
        </button>
      )}

      {/* 유사도 바 */}
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-zinc-100">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${chunk.score * 100}%`,
            background: chunk.score >= 0.80
              ? 'linear-gradient(90deg, #10b981, #059669)'
              : chunk.score >= 0.60
              ? 'linear-gradient(90deg, #f59e0b, #d97706)'
              : 'linear-gradient(90deg, #ef4444, #dc2626)',
          }}
        />
      </div>
    </div>
  );
};

// ─── TopK Selector ───────────────────────────────────────────────────────────

const TOP_K_OPTIONS = [3, 5, 10] as const;
type TopKOption = (typeof TOP_K_OPTIONS)[number];

// ─── VectorSearchPanel ───────────────────────────────────────────────────────

const VectorSearchPanel = () => {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState<TopKOption>(5);
  const [submittedQuery, setSubmittedQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const { mutate: search, data: results, isPending, isSuccess, reset } = useVectorSearch();

  const handleSubmit = () => {
    const q = query.trim();
    if (!q) return;
    setSubmittedQuery(q);
    search({ query: q, topK });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSubmit();
  };

  const handleClear = () => {
    setQuery('');
    setSubmittedQuery('');
    reset();
    inputRef.current?.focus();
  };

  return (
    <div className="mt-6 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
      {/* 섹션 헤더 */}
      <div className="border-b border-zinc-100 px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl"
            style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
          >
            <Search className="h-4 w-4 text-white" />
          </div>
          <div>
            <h2 className="text-[14px] font-semibold text-zinc-900">벡터 검색 테스트</h2>
            <p className="text-[11.5px] text-zinc-400">실제 RAG 쿼리에서 어떤 청크가 검색되는지 확인합니다</p>
          </div>
          {/* Mock 배지 */}
          <span className="ml-auto rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
            Mock
          </span>
        </div>
      </div>

      {/* 검색 입력 영역 */}
      <div className="px-5 py-4">
        <div className="flex items-center gap-2">
          {/* 검색창 */}
          <div className="flex flex-1 items-center overflow-hidden rounded-2xl border border-zinc-300 bg-white shadow-sm transition-all focus-within:border-violet-400 focus-within:shadow-violet-100/60 focus-within:shadow-md">
            <Search className="ml-4 h-4 w-4 shrink-0 text-zinc-400" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="검색 쿼리를 입력하세요 (예: 임베딩 벡터 검색 방법)"
              className="flex-1 bg-transparent px-3 py-3 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none"
            />
            {query && (
              <button
                onClick={handleClear}
                className="mr-2 rounded-lg p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 transition-all"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* TopK 선택 */}
          <div className="flex items-center gap-1 rounded-xl border border-zinc-200 bg-zinc-50 p-1">
            {TOP_K_OPTIONS.map((k) => (
              <button
                key={k}
                onClick={() => setTopK(k)}
                className={`rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition-all ${
                  topK === k
                    ? 'bg-violet-600 text-white shadow-sm'
                    : 'text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700'
                }`}
              >
                Top {k}
              </button>
            ))}
          </div>

          {/* 검색 버튼 */}
          <button
            onClick={handleSubmit}
            disabled={!query.trim() || isPending}
            className="flex items-center gap-2 rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isPending ? (
              <><Loader2 className="h-4 w-4 animate-spin" />검색 중</>
            ) : (
              <><Search className="h-4 w-4" />검색</>
            )}
          </button>
        </div>

        {/* 쿼리 힌트 */}
        {!isSuccess && !isPending && (
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="text-[11.5px] text-zinc-400">예시 쿼리:</span>
            {['임베딩 벡터 생성', '청킹 전략', 'API 엔드포인트', '재랭킹'].map((hint) => (
              <button
                key={hint}
                onClick={() => { setQuery(hint); inputRef.current?.focus(); }}
                className="rounded-lg border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[11.5px] text-zinc-500 hover:border-violet-300 hover:text-violet-600 transition-all"
              >
                {hint}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 검색 결과 */}
      {isPending && (
        <div className="flex items-center justify-center gap-2 border-t border-zinc-100 py-12 text-zinc-400">
          <Loader2 className="h-5 w-5 animate-spin text-violet-400" />
          <span className="text-[14px]">벡터 유사도 검색 중...</span>
        </div>
      )}

      {isSuccess && results && (
        <div className="border-t border-zinc-100 px-5 py-4">
          {/* 결과 헤더 */}
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <p className="text-[13px] font-semibold text-zinc-900">
                검색 결과
              </p>
              <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-[11px] font-semibold text-violet-700">
                {results.length}개
              </span>
            </div>
            <p className="text-[11.5px] text-zinc-400">
              쿼리: <span className="font-medium text-zinc-600">"{submittedQuery}"</span>
              <span className="ml-2 text-zinc-300">· Mock 점수 (실제 벡터 검색 아님)</span>
            </p>
          </div>

          {results.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-zinc-200 py-10 text-center text-zinc-400">
              <p className="text-[14px]">검색 결과가 없습니다</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {results.map((chunk, i) => (
                <ResultCard
                  key={`${chunk.documentId}-${chunk.chunkIndex}`}
                  rank={i + 1}
                  chunk={chunk}
                  query={submittedQuery}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default VectorSearchPanel;
