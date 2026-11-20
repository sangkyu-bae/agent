// Design Ref: source-passage-viewer §5.1·§5.5 — 헤더·구절 이동·본문(텍스트/원본 전환은 SourceViewerBody).
import { ChevronLeft, ChevronRight } from 'lucide-react';

import IconButton from '@/components/ui/IconButton';
import { useSourceViewerStore } from '@/store/sourceViewerStore';

import SourceViewerBody from './SourceViewerBody';
import SourceViewerShell from './SourceViewerShell';

const SourceViewerPanel = () => {
  const target = useSourceViewerStore((s) => s.target);
  const index = useSourceViewerStore((s) => s.index);
  const { close, next, prev } = useSourceViewerStore.getState();
  if (!target) return null;

  const { passages } = target.viewer;
  const current = passages[index];
  return (
    <SourceViewerShell filename={target.filename} onClose={close}>
      <div className="flex items-center gap-1 border-b border-border px-4 py-2 text-xs text-fg-subtle">
        <span className="flex-1">
          {passages.length > 0 ? `구절 ${index + 1} / ${passages.length}` : '인용 구절 없음'}
        </span>
        {current?.page != null && <span className="mr-2">{`p.${current.page}`}</span>}
        <IconButton aria-label="이전 구절" size="sm" onClick={prev} disabled={index <= 0}>
          <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        </IconButton>
        <IconButton
          aria-label="다음 구절"
          size="sm"
          onClick={next}
          disabled={index >= passages.length - 1}
        >
          <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        </IconButton>
      </div>
      {/* 문서가 바뀌면 모드·대체 안내를 초기화한다 */}
      <SourceViewerBody key={target.viewer.document_id} viewer={target.viewer} index={index} />
    </SourceViewerShell>
  );
};

export default SourceViewerPanel;
