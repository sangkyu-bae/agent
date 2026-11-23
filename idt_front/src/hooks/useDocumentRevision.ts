// Design Ref: document-revision §4.2 — 사전 점검·이력·되돌리기·연결·메타·재반영 훅.
// 상태를 바꾸는 mutation 은 성공 후 KB 캐시 전체(.all)를 무효화해 목록·이력·근거를 다시 읽는다.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import knowledgeBaseService from '@/services/knowledgeBaseService';
import type { RevisionMetaRequest, RollbackMode } from '@/types/knowledgeBase';

/** 업로드 전 사전 점검 — 상태를 바꾸지 않으므로 캐시 무효화 없음 */
export const useCheckKbRevision = (kbId: string) =>
  useMutation({
    mutationFn: (file: File) => knowledgeBaseService.checkKbRevision(kbId, file),
  });

export const useDocumentVersions = (
  kbId: string | undefined,
  documentId: string | undefined,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.versions(kbId ?? '', documentId ?? ''),
    queryFn: () =>
      knowledgeBaseService.getDocumentVersions(kbId as string, documentId as string),
    enabled: !!kbId && !!documentId && (options?.enabled ?? true),
  });

const useInvalidateKb = () => {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeBases.all });
};

export const useRollbackRevision = (kbId: string) => {
  const invalidate = useInvalidateKb();
  return useMutation({
    mutationFn: ({ documentId, mode }: { documentId: string; mode: RollbackMode }) =>
      knowledgeBaseService.rollbackRevision(kbId, documentId, mode),
    onSuccess: invalidate,
  });
};

export const useLinkRevision = (kbId: string) => {
  const invalidate = useInvalidateKb();
  return useMutation({
    mutationFn: ({
      documentId,
      supersedesDocumentId,
    }: {
      documentId: string;
      supersedesDocumentId: string;
    }) => knowledgeBaseService.linkRevision(kbId, documentId, supersedesDocumentId),
    onSuccess: invalidate,
  });
};

export const useUpdateRevisionMeta = (kbId: string) => {
  const invalidate = useInvalidateKb();
  return useMutation({
    mutationFn: ({ documentId, body }: { documentId: string; body: RevisionMetaRequest }) =>
      knowledgeBaseService.updateRevisionMeta(kbId, documentId, body),
    onSuccess: invalidate,
  });
};

export const useRetryRevisionSync = (kbId: string) => {
  const invalidate = useInvalidateKb();
  return useMutation({
    mutationFn: (documentId: string) =>
      knowledgeBaseService.retryRevisionSync(kbId, documentId),
    onSuccess: invalidate,
  });
};
