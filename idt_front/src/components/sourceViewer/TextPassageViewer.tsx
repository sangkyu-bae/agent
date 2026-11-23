// Design Ref: source-passage-viewer §5.4 — 저장된 청크로 문서를 다시 만들고 인용 청크에 음영.
// 본문은 텍스트 노드로만 렌더한다(HTML·마크다운 미해석, SourceCitation 발췌와 같은 원칙).
import { useEffect, useMemo, useRef } from 'react';

import { useSourceViewerChunks } from '@/hooks/useSourceViewerChunks';
import { ApiError } from '@/services/api/ApiError';
import type { SourceViewerRef } from '@/types/sourceViewer';
import { buildPassageDocument, toSegments } from '@/utils/buildPassageDocument';
import { findPassage } from '@/utils/passageMatch';
import { cn } from '@/utils/cn';

import MissingPassageNotice from './MissingPassageNotice';

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
  const { data, isLoading, error } = useSourceViewerChunks(viewer.kb_id, viewer.document_id);
  const currentRef = useRef<HTMLElement>(null);
  const doc = useMemo(
    () => (data ? buildPassageDocument(data, viewer.passages) : null),
    [data, viewer.passages],
  );
  // answer-citation-verification FR-14: 근거 문장(focus) 범위 — 구절 번호 뒤(count + i)에 덧붙여 함께 자른다
  const count = viewer.passages.length;
  const focusRanges = useMemo(
    () => (doc ? viewer.passages.map((p) => (p.focus ? findPassage(doc.text, p.focus) : null)) : []),
    [doc, viewer.passages],
  );
  const segments = useMemo(
    () => (doc ? toSegments(doc.text, [...doc.ranges, ...focusRanges]) : []),
    [doc, focusRanges],
  );

  useEffect(() => {
    currentRef.current?.scrollIntoView?.({ block: 'center' });
  }, [index, segments]);

  if (isLoading) return <Notice>원문을 불러오는 중입니다…</Notice>;
  if (error || !doc) return <Notice>{errorMessage(error)}</Notice>;

  const missing = doc.ranges[index] === null ? viewer.passages[index] : undefined;
  // 근거 문장을 찾았으면 그 문장이 현재 위치(청크는 옅게), 아니면 기존처럼 청크 전체.
  const currentOwner = focusRanges[index] ? count + index : index;
  // 현재 구절의 첫 조각에만 스크롤 기준점을 단다.
  const anchor = segments.findIndex((s) => s.passages.includes(currentOwner));
  return (
    <div className="flex-1 overflow-y-auto">
      {missing && <MissingPassageNotice excerpt={missing.excerpt} />}
      <p className="whitespace-pre-wrap break-words p-4 text-sm leading-[1.7] text-fg">
        {segments.map((seg, i) => {
          if (seg.passages.length === 0) return <span key={i}>{seg.text}</span>;
          const isCurrent = seg.passages.includes(currentOwner);
          const isFocus = seg.passages.some((p) => p >= count);
          return (
            <mark
              key={i}
              ref={i === anchor ? currentRef : undefined}
              aria-current={isCurrent ? 'true' : undefined}
              data-spv-focus={isFocus ? 'true' : undefined}
              className={cn(
                'rounded-sm text-fg',
                isCurrent || isFocus ? 'bg-warning-border' : 'bg-warning-bg',
                isFocus && 'font-semibold',
                isFocus && isCurrent && 'outline-2 outline-warning',
              )}
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
