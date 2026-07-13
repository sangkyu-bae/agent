import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { KnowledgeBaseInfo } from '@/types/ragToolConfig';
import type {
  CreateKnowledgeBaseRequest,
  KbCreateResponse,
  KbDocumentListResponse,
  KbMessageResponse,
  KbUploadResponse,
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
};

export default knowledgeBaseService;
