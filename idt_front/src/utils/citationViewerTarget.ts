// Design Ref: answer-citation-verification §5.2 — 인용 번호 → 원문 뷰어 대상.
// 그 문서의 인용 구절만 번호 순으로 싣고(◀▶ 는 인용 순서), 근거 문장을 focus 로 넘긴다.
import type { SourceViewerPassage, SourceViewerTarget } from '@/types/sourceViewer';

import type { CitationRow } from './citationView';

export interface CitationViewerOpen {
  target: SourceViewerTarget;
  /** 누른 인용의 구절 위치 */
  index: number;
}

const toPassage = (row: CitationRow, known: SourceViewerPassage[]): SourceViewerPassage => {
  const base = known.find((p) => p.chunk_id === row.entry.chunk_id);
  return {
    chunk_id: base?.chunk_id ?? row.entry.chunk_id ?? '',
    parent_id: base?.parent_id ?? null,
    page: base?.page ?? row.entry.page,
    excerpt: base?.excerpt ?? row.entry.evidence ?? '',
    focus: row.entry.evidence,
  };
};

/** 원문 뷰어 정보(viewer)가 없는 문서이거나 번호가 없으면 null. */
export const citationViewerTarget = (rows: CitationRow[], no: number): CitationViewerOpen | null => {
  const clicked = rows.find((r) => r.no === no);
  const viewer = clicked?.source.viewer;
  if (!clicked || !viewer) return null;
  const docRows = rows.filter((r) => r.source === clicked.source);
  return {
    target: {
      viewer: { ...viewer, passages: docRows.map((r) => toPassage(r, viewer.passages)) },
      filename: clicked.source.source,
    },
    index: docRows.findIndex((r) => r.no === no),
  };
};
