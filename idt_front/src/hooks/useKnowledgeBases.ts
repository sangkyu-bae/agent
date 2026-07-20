import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import knowledgeBaseService from '@/services/knowledgeBaseService';
import type {
  CreateKnowledgeBaseRequest,
  KbDocumentChunksParams,
  KbSearchRequest,
  KbStoreSource,
  SectionSummaryStatusResponse,
  UpdateKbChunkingRequest,
} from '@/types/knowledgeBase';

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

/** 청킹 설정 변경 (kb-custom-chunking D7) — 신규 업로드부터 적용 */
export const useUpdateKbChunking = (kbId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateKbChunkingRequest) =>
      knowledgeBaseService.updateKbChunking(kbId, body),
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

// ── KB 저장 내용 조회 (kb-content-browser Design §5.2) ──────────

export const useKbDocumentSummary = (
  kbId: string | undefined,
  documentId: string | undefined,
  source: KbStoreSource,
) =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.documentSummary(
      kbId ?? '',
      documentId ?? '',
      source,
    ),
    queryFn: () =>
      knowledgeBaseService.getKbDocumentSummary(
        kbId as string,
        documentId as string,
        source,
      ),
    enabled: !!kbId && !!documentId,
  });

export const useKbSectionSummaries = (
  kbId: string | undefined,
  documentId: string | undefined,
  source: KbStoreSource,
) =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.sectionSummaries(
      kbId ?? '',
      documentId ?? '',
      source,
    ),
    queryFn: () =>
      knowledgeBaseService.getKbSectionSummaries(
        kbId as string,
        documentId as string,
        source,
      ),
    enabled: !!kbId && !!documentId,
  });

export const useKbDocumentChunks = (
  kbId: string | undefined,
  documentId: string | undefined,
  params: KbDocumentChunksParams,
) =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.chunks(
      kbId ?? '',
      documentId ?? '',
      params,
    ),
    queryFn: () =>
      knowledgeBaseService.getKbDocumentChunks(
        kbId as string,
        documentId as string,
        params,
      ),
    enabled: !!kbId && !!documentId,
  });

/** 잡 미완료(pending/processing) 동안 5초 폴링 (Design D9).
 *  요약 비활성 프로파일 문서는 404 — retry 없이 조용히 종료. */
export const useSectionSummaryStatus = (
  kbId: string | undefined,
  documentId: string | undefined,
) =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.sectionSummaryStatus(
      kbId ?? '',
      documentId ?? '',
    ),
    queryFn: () =>
      knowledgeBaseService.getSectionSummaryStatus(
        kbId as string,
        documentId as string,
      ),
    enabled: !!kbId && !!documentId,
    retry: false,
    refetchInterval: (query) => {
      const status = (query.state.data as SectionSummaryStatusResponse | undefined)
        ?.status;
      return status === 'pending' || status === 'processing' ? 5000 : false;
    },
  });

export const useRetrySectionSummary = (kbId: string, documentId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      knowledgeBaseService.retrySectionSummary(kbId, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledgeBases.sectionSummaryStatus(
          kbId,
          documentId,
        ),
      });
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.knowledgeBases.all, 'sectionSummaries'],
      });
    },
  });
};

// ── KB 리트리버 테스트 (kb-retrieval-test) ─────────────────

export const useKbSearch = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ kbId, data }: { kbId: string; data: KbSearchRequest }) =>
      knowledgeBaseService.searchKb(kbId, data),
    onSuccess: (_, { kbId }) => {
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.knowledgeBases.all, 'searchHistory', kbId],
      });
    },
  });
};

export const useKbSearchHistory = (
  kbId: string | undefined,
  params?: { limit?: number; offset?: number },
) =>
  useQuery({
    queryKey: queryKeys.knowledgeBases.searchHistory(kbId ?? '', params),
    queryFn: () =>
      knowledgeBaseService.getKbSearchHistory(kbId as string, params),
    enabled: !!kbId,
  });

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
