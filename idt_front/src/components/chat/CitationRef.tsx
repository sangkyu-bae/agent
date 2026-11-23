// Design Ref: answer-citation-verification §5.3 — 본문 위첨자 인용 번호.
// 원문 뷰어 정보가 있으면 누르면 그 인용 위치로 연다. 없으면 번호만(근거 문장은 title).
import { useSourceViewerStore } from '@/store/sourceViewerStore';
import type { CitationRow } from '@/utils/citationView';
import { citationViewerTarget } from '@/utils/citationViewerTarget';

interface CitationRefProps {
  no: number;
  rows: CitationRow[];
}

const CitationRef = ({ no, rows }: CitationRefProps) => {
  const open = useSourceViewerStore((s) => s.open);
  const opener = citationViewerTarget(rows, no);
  const evidence = rows.find((r) => r.no === no)?.entry.evidence ?? undefined;
  if (!opener) {
    return (
      <sup className="ml-0.5 text-xs font-semibold text-brand-700" title={evidence}>
        {no}
      </sup>
    );
  }
  return (
    <sup className="ml-0.5">
      <button
        type="button"
        aria-label={`근거 ${no} 원문 보기`}
        title={evidence}
        onClick={() => open(opener.target, opener.index)}
        className="rounded px-0.5 text-xs font-semibold text-brand-700 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-brand-500"
      >
        {no}
      </button>
    </sup>
  );
};

export default CitationRef;
