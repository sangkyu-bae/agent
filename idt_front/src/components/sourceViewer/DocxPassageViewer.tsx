// Design Ref: source-passage-viewer §5.4·§7 — docx 원본 위 음영. 기존 renderDocx(shadow DOM 격리)를 재사용하고,
// 렌더된 텍스트에서 정규화 매칭으로 음영을 넣는다. 앱 CSS 가 shadow DOM 안에 닿지 않아 음영 스타일을 직접 넣는다.
import { useEffect, useRef, useState } from 'react';

import { renderDocx } from '@/lib/docxRenderer';
import type { SourceViewerPassage } from '@/types/sourceViewer';
import { highlightWithFocus, setCurrentWithFocus, type FocusHighlight } from '@/utils/domHighlight';

import MissingPassageNotice from './MissingPassageNotice';

interface DocxPassageViewerProps {
  blob: Blob;
  /** 안내 발췌용 (texts 와 같은 순서) */
  passages: SourceViewerPassage[];
  texts: string[];
  index: number;
  onFallback: (reason: 'render') => void;
  /** 위치를 못 찾은 구절 안내의 [텍스트로 보기] (FR-12) */
  onShowText?: () => void;
}

// CSS 변수는 shadow 경계를 넘어 상속되므로 디자인 토큰을 그대로 쓴다.
const MARK_CSS = `mark[data-spv-passage]{background:var(--color-warning-bg);color:inherit;border-radius:2px}
mark[data-spv-passage][aria-current]{background:var(--color-warning-border)}
mark[data-spv-focus]{background:var(--color-warning-border);font-weight:600}
mark[data-spv-focus][aria-current]{outline:2px solid var(--color-warning);outline-offset:1px}`;

const DocxPassageViewer = ({ blob, passages, texts, index, onFallback, onShowText }: DocxPassageViewerProps) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const [marks, setMarks] = useState<FocusHighlight | null>(null);
  // answer-citation-verification FR-14: 근거 문장(focus)도 같은 번에 칠한다
  const focusKey = JSON.stringify(passages.map((p) => p.focus ?? null));

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
        setMarks(highlightWithFocus(root, texts, JSON.parse(focusKey) as (string | null)[]));
      })
      .catch(() => {
        if (!cancelled) onFallback('render');
      });
    return () => {
      cancelled = true;
    };
  }, [blob, texts, focusKey, onFallback]);

  useEffect(() => {
    if (marks) {
      setCurrentWithFocus(marks.marks, marks.focusMarks, index)?.scrollIntoView?.({ block: 'center' });
    }
  }, [marks, index]);

  return (
    <div className="flex-1 overflow-y-auto">
      {marks !== null && marks.marks[index] === null && (
        <MissingPassageNotice excerpt={passages[index]?.excerpt} onShowText={onShowText} />
      )}
      <div ref={hostRef} data-testid="docx-passage-host" className="p-4" />
    </div>
  );
};

export default DocxPassageViewer;
