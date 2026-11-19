// Design Ref: source-passage-viewer §2.2 — 원본 blob 을 받아 형식별 뷰어로 넘긴다.
// 조회 실패(404 ORIGINAL_NOT_AVAILABLE 포함)·렌더 실패는 onFallback 으로 텍스트 뷰어 전환을 요청한다.
import { useEffect } from 'react';

import { useSourceViewerOriginal } from '@/hooks/useSourceViewerOriginal';
import { ORIGINAL_KIND, type OriginalKind, type SourceViewerRef } from '@/types/sourceViewer';

import DocxPassageViewer from './DocxPassageViewer';
import PdfPassageViewer from './PdfPassageViewer';

interface OriginalPassageViewerProps {
  viewer: SourceViewerRef;
  kind: OriginalKind;
  texts: string[];
  index: number;
  onFallback: () => void;
}

const OriginalPassageViewer = ({ viewer, kind, texts, index, onFallback }: OriginalPassageViewerProps) => {
  const { data: blob, isError } = useSourceViewerOriginal(viewer.kb_id, viewer.document_id, true);

  useEffect(() => {
    if (isError) onFallback();
  }, [isError, onFallback]);

  if (!blob) {
    return <p role="status" className="p-4 text-sm text-fg-secondary">원본을 불러오는 중입니다…</p>;
  }
  if (kind === ORIGINAL_KIND.PDF) {
    return (
      <PdfPassageViewer blob={blob} passages={viewer.passages} texts={texts} index={index} onFallback={onFallback} />
    );
  }
  return <DocxPassageViewer blob={blob} texts={texts} index={index} onFallback={onFallback} />;
};

export default OriginalPassageViewer;
