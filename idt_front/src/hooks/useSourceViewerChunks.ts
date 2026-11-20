// Design Ref: source-passage-viewer §12 M17 (module-7 실측) — 업로드가 partial(Qdrant 실패·ES 성공)이면
// Qdrant 청크가 비어 텍스트 뷰어가 빈 문서가 된다. Qdrant 가 비었을 때만 ES 로 한 번 더 조회한다.
import { useKbDocumentChunks } from '@/hooks/useKnowledgeBases';
import type { KbDocumentChunksResponse } from '@/types/knowledgeBase';
import { SOURCE_VIEWER_CHUNK_PARAMS, SOURCE_VIEWER_FALLBACK_CHUNK_PARAMS } from '@/types/sourceViewer';

const isEmpty = (data: KbDocumentChunksResponse) => data.chunks.length === 0 && !data.parents?.length;

export const useSourceViewerChunks = (kbId: string, documentId: string) => {
  const primary = useKbDocumentChunks(kbId, documentId, SOURCE_VIEWER_CHUNK_PARAMS);
  const needFallback = primary.isSuccess && isEmpty(primary.data);
  const fallback = useKbDocumentChunks(
    needFallback ? kbId : undefined,
    needFallback ? documentId : undefined,
    SOURCE_VIEWER_FALLBACK_CHUNK_PARAMS,
  );
  return needFallback ? fallback : primary;
};
