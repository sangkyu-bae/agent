// Design Ref: ui-redesign-chat §5.4 — 출처 칩. 위키 출처는 warning 톤, 문서 출처는 중립 톤 + hover brand.
import { useNavigate } from 'react-router-dom';
import { BookOpen } from 'lucide-react';

import type { DocumentSource } from '@/types/chat';

interface SourceCitationProps {
  sources: DocumentSource[];
}

const SourceCitation = ({ sources }: SourceCitationProps) => {
  const navigate = useNavigate();

  if (sources.length === 0) return null;

  return (
    <div className="mt-4 border-t border-border pt-3">
      <p className="mb-2 text-xs font-medium text-fg-subtle">참고 문서</p>
      <div className="flex flex-wrap gap-2">
        {sources.map((source, idx) =>
          source.source === 'wiki' ? (
            // wiki-user-facing: 위키 유래 출처 — chunk_id가 위키 문서 id
            <button
              key={source.chunk_id}
              type="button"
              onClick={() => navigate(`/knowledge/${source.chunk_id}`)}
              className="inline-flex items-center gap-1.5 rounded-full border border-warning-border bg-warning-bg px-2.5 py-1 text-xs text-warning transition-colors duration-150 hover:bg-warning-border/60"
            >
              <BookOpen className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
              <span>위키 근거</span>
              <span className="font-semibold">{Math.round(source.score * 100)}%</span>
            </button>
          ) : (
            <button
              key={source.chunk_id}
              type="button"
              className="group inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-muted px-2.5 py-1 text-xs text-fg-muted transition-colors duration-150 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
            >
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-surface-sunken text-xs font-semibold text-fg-subtle group-hover:bg-brand-100 group-hover:text-brand-700">
                {idx + 1}
              </span>
              <span className="max-w-36 truncate">{source.source}</span>
              <span className="font-semibold text-brand-600">{Math.round(source.score * 100)}%</span>
            </button>
          ),
        )}
      </div>
    </div>
  );
};

export default SourceCitation;
