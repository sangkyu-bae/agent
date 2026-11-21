// Design Ref: answer-citation-verification §5.1·§5.4 — 인용 행(번호·파일·쪽·근거 문장·원문 보기).
// 근거 문장은 텍스트 노드로만 렌더한다(HTML 주입 없음, Design §7).
import { PanelRightOpen } from 'lucide-react';

import { useSourceViewerStore } from '@/store/sourceViewerStore';
import type { CitationRow } from '@/utils/citationView';
import { citationViewerTarget } from '@/utils/citationViewerTarget';

interface CitationListProps {
  rows: CitationRow[];
}

const CitationList = ({ rows }: CitationListProps) => {
  const open = useSourceViewerStore((s) => s.open);
  return (
    <ol aria-label="답변 근거" className="flex flex-col gap-2">
      {rows.map((row) => {
        const opener = citationViewerTarget(rows, row.no);
        const quote = row.entry.evidence ?? row.source.content;
        return (
          <li
            key={row.no}
            className="flex items-start gap-2 rounded-md border border-border bg-surface-muted px-3 py-2 text-xs"
          >
            <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">
              {row.no}
            </span>
            <div className="min-w-0 flex-1">
              <p className="flex min-w-0 items-center gap-1.5 text-fg-muted">
                <span className="truncate font-medium">{row.source.source}</span>
                {row.entry.page !== null && <span className="shrink-0">· {row.entry.page}쪽</span>}
              </p>
              <p className="mt-0.5 line-clamp-2 break-words text-fg-secondary">{quote}</p>
            </div>
            {opener && (
              <button
                type="button"
                aria-label={`근거 ${row.no} 원문 보기`}
                onClick={() => open(opener.target, opener.index)}
                className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5 text-fg-muted transition-colors duration-150 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
              >
                <PanelRightOpen className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                <span>원문 보기</span>
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
};

export default CitationList;
