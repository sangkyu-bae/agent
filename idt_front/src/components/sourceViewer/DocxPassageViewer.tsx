// Design Ref: source-passage-viewer §5.4·§7 — docx 원본 위 음영. 기존 renderDocx(shadow DOM 격리)를 재사용하고,
// 렌더된 텍스트에서 정규화 매칭으로 음영을 넣는다. 앱 CSS 가 shadow DOM 안에 닿지 않아 음영 스타일을 직접 넣는다.
import { useEffect, useRef, useState } from 'react';

import { renderDocx } from '@/lib/docxRenderer';
import { highlightPassages, setCurrentPassage } from '@/utils/domHighlight';

interface DocxPassageViewerProps {
  blob: Blob;
  texts: string[];
  index: number;
  onFallback: (reason: 'render') => void;
}

// CSS 변수는 shadow 경계를 넘어 상속되므로 디자인 토큰을 그대로 쓴다.
const MARK_CSS = `mark[data-spv-passage]{background:var(--color-warning-bg);color:inherit;border-radius:2px}
mark[data-spv-passage][aria-current]{background:var(--color-warning-border)}`;

type Marks = (HTMLElement[] | null)[];

const DocxPassageViewer = ({ blob, texts, index, onFallback }: DocxPassageViewerProps) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const [marks, setMarks] = useState<Marks | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    const root = host.shadowRoot ?? host.attachShadow({ mode: 'open' });
    renderDocx(blob, root, () => cancelled)
      .then(() => {
        if (cancelled) return;
        const style = document.createElement('style');
        style.dataset.spv = '';
        style.textContent = MARK_CSS;
        root.appendChild(style);
        setMarks(highlightPassages(root, texts));
      })
      .catch(() => {
        if (!cancelled) onFallback('render');
      });
    return () => {
      cancelled = true;
    };
  }, [blob, texts, onFallback]);

  useEffect(() => {
    if (marks) setCurrentPassage(marks, index)?.scrollIntoView?.({ block: 'center' });
  }, [marks, index]);

  return (
    <div className="flex-1 overflow-y-auto">
      {marks !== null && marks[index] === null && (
        <p role="status" className="m-4 rounded-md border border-warning-border bg-warning-bg p-3 text-sm text-warning">
          원문에서 정확한 위치를 찾지 못했습니다.
        </p>
      )}
      <div ref={hostRef} data-testid="docx-passage-host" className="p-4" />
    </div>
  );
};

export default DocxPassageViewer;
