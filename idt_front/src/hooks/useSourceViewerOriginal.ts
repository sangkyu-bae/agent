// Design Ref: source-passage-viewer §2.2 — 원본 blob 조회. 404(보관 안 된 문서)는 재시도하지 않고
// 호출 측이 텍스트 뷰어로 내려간다.
import { useQuery } from '@tanstack/react-query';

import { queryKeys } from '@/lib/queryKeys';
import { sourceViewerService } from '@/services/sourceViewerService';

export const useSourceViewerOriginal = (kbId: string, documentId: string, enabled: boolean) =>
  useQuery({
    queryKey: queryKeys.sourceViewer.original(kbId, documentId),
    queryFn: () => sourceViewerService.fetchOriginal(kbId, documentId),
    enabled,
    retry: false,
    staleTime: 5 * 60_000,
  });
