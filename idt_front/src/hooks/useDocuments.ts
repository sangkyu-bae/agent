import { useQuery, useMutation } from '@tanstack/react-query';
import { ragService } from '@/services/ragService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type { UploadDocumentRequest, DocumentChunk, RetrievedChunk, RetrieveRequest } from '@/types/rag';
import type { PaginatedResponse } from '@/types/api';

/** VITE_USE_MOCK=true 이면 Mock 데이터 사용, false/미설정이면 실제 API */
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

/** Mock 데이터 동적 로드 (프로덕션 번들에 미포함) */
const loadMockDocuments = (): Promise<PaginatedResponse<import('@/types/rag').Document>> =>
  import('@/mocks/documentMocks').then((m) => m.mockDocumentList);

const loadMockChunks = (docId: string): Promise<DocumentChunk[]> =>
  import('@/mocks/documentMocks').then((m) => m.getMockChunks(docId));

const loadMockVectorSearch = (query: string, topK: number): Promise<RetrievedChunk[]> =>
  import('@/mocks/documentMocks').then((m) => m.getMockVectorSearch(query, topK));

/** 문서 목록 조회 */
export const useDocuments = () =>
  useQuery({
    queryKey: queryKeys.documents.list(),
    queryFn: async () => {
      if (USE_MOCK) return loadMockDocuments();
      return ragService.getDocuments().then((r) => r.data);
    },
  });

/** 특정 문서의 청킹 결과 조회 */
export const useDocumentChunks = (docId: string | null) =>
  useQuery({
    queryKey: queryKeys.documents.chunks(docId ?? '_disabled'),
    queryFn: async () => {
      if (USE_MOCK) return loadMockChunks(docId!);
      return ragService.getDocumentChunks(docId!).then((r) => r.data.data);
    },
    enabled: !!docId,
  });

/** 문서 업로드 뮤테이션 */
export const useUploadDocument = () =>
  useMutation({
    mutationFn: async ({ file, metadata }: UploadDocumentRequest) => {
      if (USE_MOCK) {
        // Mock: 업로드 성공 시뮬레이션 (500ms 지연)
        await new Promise((r) => setTimeout(r, 500));
        return { documentId: `doc-mock-${Date.now()}`, status: 'processing' as const };
      }
      return ragService.uploadDocument(file, metadata).then((r) => r.data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.list() });
    },
  });

/**
 * 벡터 검색 훅 — 쿼리를 전송하고 유사 청크 목록을 반환
 * useMutation: 사용자가 검색을 명시적으로 트리거할 때만 실행
 * TODO: 서버 연동 시 mock 분기 제거하고 ragService.retrieve() 직접 호출
 */
export const useVectorSearch = () =>
  useMutation<RetrievedChunk[], Error, RetrieveRequest>({
    mutationFn: async ({ query, topK = 5, documentIds }: RetrieveRequest) => {
      if (USE_MOCK) return loadMockVectorSearch(query, topK);
      return ragService.retrieve({ query, topK, documentIds }).then((r) => r.data.data);
    },
  });

/** 문서 삭제 뮤테이션 */
export const useDeleteDocument = () =>
  useMutation({
    mutationFn: async (docId: string) => {
      if (USE_MOCK) {
        // Mock: 삭제 성공 시뮬레이션 (300ms 지연)
        await new Promise((r) => setTimeout(r, 300));
        return;
      }
      return ragService.deleteDocument(docId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.list() });
    },
  });
