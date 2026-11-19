// Design Ref: source-passage-viewer §5.4 — PDF 원본 위 음영. 구절의 쪽 ±1(쪽 정보 없으면 앞쪽 상한)만 렌더하고,
// 텍스트 레이어에서 정규화 매칭으로 음영을 넣는다. 못 찾으면 그 쪽으로 이동해 안내한다.
import { useEffect, useRef, useState } from 'react';

import { loadPdf } from '@/lib/pdfRenderer';
import type { SourceViewerPassage } from '@/types/sourceViewer';
import { highlightPassages, setCurrentPassage } from '@/utils/domHighlight';

interface PdfPassageViewerProps {
  blob: Blob;
  passages: SourceViewerPassage[];
  /** passages 와 같은 순서의 매칭 텍스트(청크 전문) */
  texts: string[];
  index: number;
  onFallback: (reason: 'render') => void;
}

/** 쪽 정보가 없는 구절이 있을 때 앞에서부터 렌더할 최대 쪽 수 */
const MAX_UNKNOWN_PAGES = 10;
const DEFAULT_WIDTH = 448;

const pagesToRender = (passagePages: (number | null)[], numPages: number): number[] => {
  const pages = new Set<number>();
  if (passagePages.some((p) => p == null)) {
    for (let n = 1; n <= Math.min(numPages, MAX_UNKNOWN_PAGES); n += 1) pages.add(n);
  }
  passagePages.forEach((page) => {
    if (page == null) return;
    for (const n of [page - 1, page, page + 1]) if (n >= 1 && n <= numPages) pages.add(n);
  });
  return [...pages].sort((a, b) => a - b);
};

type Marks = (HTMLElement[] | null)[];

const PdfPassageViewer = ({ blob, passages, texts, index, onFallback }: PdfPassageViewerProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [marks, setMarks] = useState<Marks | null>(null);
  // 배열 참조가 아니라 내용이 바뀔 때만 다시 렌더한다 — PDF 재로딩은 비싸다.
  const pagesKey = JSON.stringify(passages.map((p) => p.page));
  const textsKey = JSON.stringify(texts);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    let destroy: (() => void) | undefined;
    const run = async () => {
      const doc = await loadPdf(blob);
      destroy = doc.destroy;
      if (cancelled) return;
      container.replaceChildren();
      const width = Math.max(container.clientWidth - 32, 0) || DEFAULT_WIDTH;
      for (const n of pagesToRender(JSON.parse(pagesKey) as (number | null)[], doc.numPages)) {
        if (cancelled) return;
        await doc.renderPage(n, container, width);
      }
      if (!cancelled) setMarks(highlightPassages(container, JSON.parse(textsKey) as string[]));
    };
    run().catch(() => {
      if (!cancelled) onFallback('render');
    });
    return () => {
      cancelled = true;
      destroy?.();
    };
  }, [blob, pagesKey, textsKey, onFallback]);

  const current = passages[index];
  const missing = marks !== null && marks[index] === null;

  useEffect(() => {
    if (!marks) return;
    const first = setCurrentPassage(marks, index);
    const pageEl = current?.page != null
      ? containerRef.current?.querySelector(`[data-page="${current.page}"]`)
      : null;
    (first ?? pageEl)?.scrollIntoView?.({ block: 'center' });
  }, [marks, index, current]);

  return (
    <div className="flex-1 overflow-y-auto bg-surface-sunken">
      {missing && (
        <p role="status" className="m-4 rounded-md border border-warning-border bg-warning-bg p-3 text-sm text-warning">
          {current?.page != null
            ? `원문에서 정확한 위치를 찾지 못해 ${current.page}쪽을 보여 줍니다.`
            : '원문에서 정확한 위치를 찾지 못했습니다.'}
        </p>
      )}
      <div ref={containerRef} className="flex flex-col items-center gap-4 p-4" />
    </div>
  );
};

export default PdfPassageViewer;
