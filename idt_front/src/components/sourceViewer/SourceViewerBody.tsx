// Design Ref: source-passage-viewer §5.1·§5.4 — [텍스트|원본] 전환과 단계적 대체.
// 원본이 있으면 원본으로 열고, 원본 조회·렌더에 실패하면 텍스트로 바꾼 뒤 안내한다.
// 대상 문서가 바뀌면 부모가 key 로 다시 마운트해 모드를 초기화한다.
import { useCallback, useMemo, useState } from 'react';

import { useKbDocumentChunks } from '@/hooks/useKnowledgeBases';
import {
  SOURCE_VIEWER_CHUNK_PARAMS,
  VIEWER_MODE,
  type SourceViewerRef,
  type ViewerMode,
} from '@/types/sourceViewer';
import { passageTexts } from '@/utils/buildPassageDocument';
import { cn } from '@/utils/cn';

import OriginalPassageViewer from './OriginalPassageViewer';
import TextPassageViewer from './TextPassageViewer';

interface SourceViewerBodyProps {
  viewer: SourceViewerRef;
  index: number;
}

const FALLBACK_NOTICE = '원본 파일을 열 수 없어 텍스트로 보여 줍니다.';

const ModeButton = ({ label, active, disabled, onClick }: {
  label: string; active: boolean; disabled?: boolean; onClick: () => void;
}) => (
  <button
    type="button"
    aria-pressed={active}
    disabled={disabled}
    onClick={onClick}
    className={cn(
      'rounded-md px-2.5 py-1 text-xs transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50',
      active ? 'bg-surface text-fg shadow-sm' : 'text-fg-subtle hover:text-fg',
    )}
  >
    {label}
  </button>
);

const SourceViewerBody = ({ viewer, index }: SourceViewerBodyProps) => {
  const [mode, setMode] = useState<ViewerMode>(viewer.original ? VIEWER_MODE.ORIGINAL : VIEWER_MODE.TEXT);
  const [notice, setNotice] = useState<string | null>(null);
  const chunks = useKbDocumentChunks(viewer.kb_id, viewer.document_id, SOURCE_VIEWER_CHUNK_PARAMS);
  const texts = useMemo(() => passageTexts(chunks.data, viewer.passages), [chunks.data, viewer.passages]);
  const chunksSettled = chunks.isSuccess || chunks.isError;

  const fallback = useCallback(() => {
    setMode(VIEWER_MODE.TEXT);
    setNotice(FALLBACK_NOTICE);
  }, []);
  const choose = (next: ViewerMode) => {
    setNotice(null);
    setMode(next);
  };

  const showOriginal = mode === VIEWER_MODE.ORIGINAL && viewer.original !== null;
  return (
    <>
      <div className="flex items-center gap-1 border-b border-border bg-surface-muted px-4 py-1.5">
        <div className="inline-flex rounded-md bg-surface-sunken p-0.5" role="group" aria-label="보기 방식">
          <ModeButton label="텍스트" active={!showOriginal} onClick={() => choose(VIEWER_MODE.TEXT)} />
          <ModeButton
            label="원본"
            active={showOriginal}
            disabled={viewer.original === null}
            onClick={() => choose(VIEWER_MODE.ORIGINAL)}
          />
        </div>
      </div>
      {notice && (
        <p role="status" className="border-b border-warning-border bg-warning-bg px-4 py-2 text-xs text-warning">
          {notice}
        </p>
      )}
      {showOriginal && viewer.original !== null ? (
        chunksSettled ? (
          <OriginalPassageViewer
            viewer={viewer}
            kind={viewer.original}
            texts={texts}
            index={index}
            onFallback={fallback}
          />
        ) : (
          <p role="status" className="p-4 text-sm text-fg-secondary">원문을 불러오는 중입니다…</p>
        )
      ) : (
        <TextPassageViewer viewer={viewer} index={index} />
      )}
    </>
  );
};

export default SourceViewerBody;
