import type { SourceChunk } from '@/types/chat';

interface SourceCitationProps {
  sources: SourceChunk[];
}

const SourceCitation = ({ sources }: SourceCitationProps) => {
  if (sources.length === 0) return null;

  return (
    <div className="mt-4 pt-3 border-t border-zinc-100">
      <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
        참고 문서
      </p>
      <div className="flex flex-wrap gap-2">
        {sources.map((source, idx) => (
          <button
            key={`${source.documentId}-${source.chunkIndex}`}
            className="group flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-[11.5px] text-zinc-600 shadow-sm transition-all hover:border-violet-300 hover:bg-violet-50 hover:shadow-md"
          >
            <span className="flex h-4 w-4 items-center justify-center rounded bg-zinc-100 text-[10px] font-bold text-zinc-500 group-hover:bg-violet-100 group-hover:text-violet-600">
              {idx + 1}
            </span>
            <span className="max-w-[140px] truncate">{source.documentName}</span>
            <span className="font-semibold text-violet-500">{Math.round(source.score * 100)}%</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default SourceCitation;
