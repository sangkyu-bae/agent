import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { KnowledgeBaseInfo } from '@/types/ragToolConfig';
import type {
  CreateKnowledgeBaseRequest,
  KbCreateResponse,
  KbDocumentChunksParams,
  KbDocumentChunksResponse,
  KbDocumentListResponse,
  KbDocumentSummaryResponse,
  KbMessageResponse,
  KbSearchHistoryResponse,
  KbSearchRequest,
  KbSearchResponse,
  KbSectionSummaryListResponse,
  KbStoreSource,
  KbUploadResponse,
  SectionSummaryStatusResponse,
  UpdateKbChunkingRequest,
} from '@/types/knowledgeBase';

interface KnowledgeBasesResponse {
  knowledge_bases: KnowledgeBaseInfo[];
  total: number;
}

const knowledgeBaseService = {
  getKnowledgeBases: async (): Promise<KnowledgeBaseInfo[]> => {
    const { data } = await authApiClient.get<KnowledgeBasesResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASES,
    );
    return data.knowledge_bases;
  },

  getKnowledgeBase: async (kbId: string): Promise<KnowledgeBaseInfo> => {
    const { data } = await authApiClient.get<KnowledgeBaseInfo>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DETAIL(kbId),
    );
    return data;
  },

  createKnowledgeBase: async (
    body: CreateKnowledgeBaseRequest,
  ): Promise<KbCreateResponse> => {
    const { data } = await authApiClient.post<KbCreateResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASES,
      body,
    );
    return data;
  },

  // kb-custom-chunking D7: 청킹 설정 전체 교체 (신규 업로드부터 적용)
  updateKbChunking: async (
    kbId: string,
    body: UpdateKbChunkingRequest,
  ): Promise<KnowledgeBaseInfo> => {
    const { data } = await authApiClient.patch<KnowledgeBaseInfo>(
      API_ENDPOINTS.KNOWLEDGE_BASE_CHUNKING(kbId),
      body,
    );
    return data;
  },

  deleteKnowledgeBase: async (kbId: string): Promise<KbMessageResponse> => {
    const { data } = await authApiClient.delete<KbMessageResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DETAIL(kbId),
    );
    return data;
  },

  getKbDocuments: async (
    kbId: string,
    params?: { offset?: number; limit?: number },
  ): Promise<KbDocumentListResponse> => {
    const { data } = await authApiClient.get<KbDocumentListResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(kbId),
      { params },
    );
    return data;
  },

  // 동기 파싱+임베딩이라 수십 초 가능 — unifiedUploadService 선례의 timeout 상향(D6)
  uploadKbDocument: async (
    kbId: string,
    file: File,
  ): Promise<KbUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await authApiClient.post<KbUploadResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(kbId),
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120_000,
      },
    );
    return data;
  },

  // ── KB 저장 내용 조회 (kb-content-browser) ─────────────────

  getKbDocumentSummary: async (
    kbId: string,
    documentId: string,
    source: KbStoreSource,
  ): Promise<KbDocumentSummaryResponse> => {
    const { data } = await authApiClient.get<KbDocumentSummaryResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_SUMMARY(kbId, documentId),
      { params: { source } },
    );
    return data;
  },

  getKbSectionSummaries: async (
    kbId: string,
    documentId: string,
    source: KbStoreSource,
  ): Promise<KbSectionSummaryListResponse> => {
    const { data } = await authApiClient.get<KbSectionSummaryListResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARIES(kbId, documentId),
      { params: { source } },
    );
    return data;
  },

  getKbDocumentChunks: async (
    kbId: string,
    documentId: string,
    params: KbDocumentChunksParams,
  ): Promise<KbDocumentChunksResponse> => {
    const { data } = await authApiClient.get<KbDocumentChunksResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_CHUNKS(kbId, documentId),
      { params },
    );
    return data;
  },

  getSectionSummaryStatus: async (
    kbId: string,
    documentId: string,
  ): Promise<SectionSummaryStatusResponse> => {
    const { data } = await authApiClient.get<SectionSummaryStatusResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARY_STATUS(kbId, documentId),
    );
    return data;
  },

  // ── KB 리트리버 테스트 (kb-retrieval-test) ─────────────────

  searchKb: async (
    kbId: string,
    body: KbSearchRequest,
  ): Promise<KbSearchResponse> => {
    const { data } = await authApiClient.post<KbSearchResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SEARCH(kbId),
      body,
    );
    return data;
  },

  getKbSearchHistory: async (
    kbId: string,
    params?: { limit?: number; offset?: number },
  ): Promise<KbSearchHistoryResponse> => {
    const { data } = await authApiClient.get<KbSearchHistoryResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SEARCH_HISTORY(kbId),
      { params },
    );
    return data;
  },

  retrySectionSummary: async (
    kbId: string,
    documentId: string,
  ): Promise<SectionSummaryStatusResponse> => {
    const { data } = await authApiClient.post<SectionSummaryStatusResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARY_RETRY(kbId, documentId),
    );
    return data;
  },
};

export default knowledgeBaseService;
