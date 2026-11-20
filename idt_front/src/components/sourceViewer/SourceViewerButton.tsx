// Design Ref: source-passage-viewer §5.3, §11.2 F2 — viewer 가 있을 때만 그린다(서버 스위치 off = 버튼 없음).
import { PanelRightOpen } from 'lucide-react';

import { useSourceViewerStore } from '@/store/sourceViewerStore';
import type { DocumentSource } from '@/types/chat';

interface SourceViewerButtonProps {
  source: DocumentSource;
}

const SourceViewerButton = ({ source }: SourceViewerButtonProps) => {
  const open = useSourceViewerStore((s) => s.open);
  const viewer = source.viewer;
  if (!viewer) return null;
  return (
    <button
      type="button"
      aria-label={`${source.source} 원문 보기`}
      onClick={() => open({ viewer, filename: source.source })}
      className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-fg-muted transition-colors duration-150 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
    >
      <PanelRightOpen className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
      <span>원문 보기</span>
    </button>
  );
};

export default SourceViewerButton;
