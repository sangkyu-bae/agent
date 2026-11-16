// Design Ref: document-file-preview §5.3 — shadow DOM 호스트에 docx를 렌더한다 (Plan FR-08 스타일 격리).
import { useEffect, useRef } from 'react';

import { renderDocx } from '@/lib/docxRenderer';

interface DocxPreviewViewProps {
  blob: Blob;
  /** 렌더 완료. 부모가 useCallback으로 고정해 넘긴다 (identity가 바뀌면 다시 렌더된다) */
  onRendered: () => void;
  onFailed: (error: unknown) => void;
}

const DocxPreviewView = ({ blob, onRendered, onFailed }: DocxPreviewViewProps) => {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    // StrictMode 이중 실행에서 attachShadow 재호출은 예외이므로 기존 root를 재사용한다
    const root = host.shadowRoot ?? host.attachShadow({ mode: 'open' });

    // 취소된 렌더는 root를 건드리지 않게 상태를 넘긴다 (analysis G-04)
    renderDocx(blob, root, () => cancelled)
      .then(() => {
        if (!cancelled) onRendered();
      })
      .catch((error: unknown) => {
        if (!cancelled) onFailed(error);
      });

    return () => {
      cancelled = true;
    };
  }, [blob, onRendered, onFailed]);

  return (
    <div
      ref={hostRef}
      data-testid="docx-preview-host"
      className="max-h-[70vh] overflow-auto rounded-lg border border-border"
    />
  );
};

export default DocxPreviewView;
