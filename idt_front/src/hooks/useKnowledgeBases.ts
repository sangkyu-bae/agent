import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import knowledgeBaseService from '@/services/knowledgeBaseService';
import type { CreateKnowledgeBaseRequest } from '@/types/knowledgeBase';

export const useKnowledgeBases = () =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.list(),
    queryFn: knowledgeBaseService.getKnowledgeBases,
    staleTime: 5 * 60 * 1000,
  });

export const useKnowledgeBase = (kbId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.detail(kbId ?? ''),
    queryFn: () => knowledgeBaseService.getKnowledgeBase(kbId as string),
    enabled: !!kbId,
  });

export const useKbDocuments = (
  kbId: string | undefined,
  params?: { offset?: number; limit?: number },
) =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.documents(kbId ?? '', params),
    queryFn: () =>
      knowledgeBaseService.getKbDocuments(kbId as string, params),
    enabled: !!kbId,
  });

/** 생성/삭제/업로드 성공 시 .all invalidate —
 *  agent-builder KB 드롭다운(FR-07)까지 자동 동기화 */
export const useCreateKnowledgeBase = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateKnowledgeBaseRequest) =>
      knowledgeBaseService.createKnowledgeBase(body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledgeBases.all,
      });
    },
  });
};

export const useDeleteKnowledgeBase = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (kbId: string) =>
      knowledgeBaseService.deleteKnowledgeBase(kbId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledgeBases.all,
      });
    },
  });
};

export const useUploadKbDocument = (kbId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      knowledgeBaseService.uploadKbDocument(kbId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledgeBases.all,
      });
    },
  });
};
