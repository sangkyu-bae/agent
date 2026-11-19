// Design Ref: source-passage-viewer §5.4 — 저장된 청크로 문서를 다시 만들고 인용 청크에 음영.
// 본문은 텍스트 노드로만 렌더한다(HTML·마크다운 미해석, SourceCitation 발췌와 같은 원칙).
import { useEffect, useMemo, useRef } from 'react';

import { useKbDocumentChunks } from '@/hooks/useKnowledgeBases';
import { ApiError } from '@/services/api/ApiError';
import { SOURCE_VIEWER_CHUNK_PARAMS, type SourceViewerRef } from '@/types/sourceViewer';
import { buildPassageDocument, toSegments } from '@/utils/buildPassageDocument';
import { cn } from '@/utils/cn';

interface TextPassageViewerProps {
  viewer: SourceViewerRef;
  index: number;
}

const errorMessage = (error: unknown) => {
  const status = error instanceof ApiError ? error.status : undefined;
  if (status === 403) return '이 문서를 볼 권한이 없습니다.';
  if (status === 404) return '문서를 찾을 수 없습니다. 삭제되었을 수 있습니다.';
  return '원문을 불러오지 못했습니다.';
};

const Notice = ({ children }: { children: string }) => (
  <p role="status" className="p-4 text-sm text-fg-secondary">{children}</p>
);

const TextPassageViewer = ({ viewer, index }: TextPassageViewerProps) => {
  const { data, isLoading, error } = useKbDocumentChunks(viewer.kb_id, viewer.document_id, SOURCE_VIEWER_CHUNK_PARAMS);
  const currentRef = useRef<HTMLElement>(null);
  const doc = useMemo(
    () => (data ? buildPassageDocument(data, viewer.passages) : null),
    [data, viewer.passages],
  );
  const segments = useMemo(() => (doc ? toSegments(doc.text, doc.ranges) : []), [doc]);

  useEffect(() => {
    currentRef.current?.scrollIntoView?.({ block: 'center' });
  }, [index, segments]);

  if (isLoading) return <Notice>원문을 불러오는 중입니다…</Notice>;
  if (error || !doc) return <Notice>{errorMessage(error)}</Notice>;

  const missing = doc.ranges[index] === null ? viewer.passages[index] : undefined;
  // 현재 구절의 첫 조각에만 스크롤 기준점을 단다.
  const anchor = segments.findIndex((s) => s.passages.includes(index));
  return (
    <div className="flex-1 overflow-y-auto">
      {missing && (
        <div className="m-4 rounded-md border border-warning-border bg-warning-bg p-3 text-sm text-fg-secondary">
          <p className="font-medium text-warning">원문에서 정확한 위치를 찾지 못했습니다.</p>
          {missing.excerpt && <p className="mt-2 whitespace-pre-wrap break-words">{missing.excerpt}</p>}
        </div>
      )}
      <p className="whitespace-pre-wrap break-words p-4 text-sm leading-[1.7] text-fg">
        {segments.map((seg, i) => {
          if (seg.passages.length === 0) return <span key={i}>{seg.text}</span>;
          const isCurrent = seg.passages.includes(index);
          return (
            <mark
              key={i}
              ref={i === anchor ? currentRef : undefined}
              aria-current={isCurrent ? 'true' : undefined}
              className={cn('rounded-sm text-fg', isCurrent ? 'bg-warning-border' : 'bg-warning-bg')}
            >
              {seg.text}
            </mark>
          );
        })}
      </p>
    </div>
  );
};

export default TextPassageViewer;
