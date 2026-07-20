// LLM-WIKI-001: Wiki 관리 API 서비스. 모든 호출은 authApiClient(Bearer) 경유.
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CreateWikiRequest,
  DistillRequest,
  DistillResponse,
  ReviewActionRequest,
  UpdateWikiRequest,
  WikiArticle,
  WikiListResponse,
  WikiTreeResponse,
} from '@/types/wiki';

export const wikiService = {
  distill: async (data: DistillRequest): Promise<DistillResponse> => {
    const res = await authApiClient.post<DistillResponse>(
      API_ENDPOINTS.WIKI_DISTILL,
      data,
    );
    return res.data;
  },

  getArticles: async (params?: {
    agent_id?: string;
    status?: string;
  }): Promise<WikiListResponse> => {
    const res = await authApiClient.get<WikiListResponse>(
      API_ENDPOINTS.WIKI_LIST,
      { params },
    );
    return res.data;
  },

  getArticle: async (id: string): Promise<WikiArticle> => {
    const res = await authApiClient.get<WikiArticle>(
      API_ENDPOINTS.WIKI_DETAIL(id),
    );
    return res.data;
  },

  approve: async (
    id: string,
    data: ReviewActionRequest,
  ): Promise<WikiArticle> => {
    const res = await authApiClient.patch<WikiArticle>(
      API_ENDPOINTS.WIKI_APPROVE(id),
      data,
    );
    return res.data;
  },

  reject: async (id: string): Promise<WikiArticle> => {
    const res = await authApiClient.patch<WikiArticle>(
      API_ENDPOINTS.WIKI_REJECT(id),
    );
    return res.data;
  },

  deprecate: async (id: string): Promise<WikiArticle> => {
    const res = await authApiClient.patch<WikiArticle>(
      API_ENDPOINTS.WIKI_DEPRECATE(id),
    );
    return res.data;
  },

  restore: async (
    id: string,
    data: ReviewActionRequest,
  ): Promise<WikiArticle> => {
    const res = await authApiClient.patch<WikiArticle>(
      API_ENDPOINTS.WIKI_RESTORE(id),
      data,
    );
    return res.data;
  },

  update: async (id: string, data: UpdateWikiRequest): Promise<WikiArticle> => {
    const res = await authApiClient.put<WikiArticle>(
      API_ENDPOINTS.WIKI_UPDATE(id),
      data,
    );
    return res.data;
  },

  // wiki-user-facing: 소유자 직접 작성 + 지식 트리
  create: async (data: CreateWikiRequest): Promise<WikiArticle> => {
    const res = await authApiClient.post<WikiArticle>(
      API_ENDPOINTS.WIKI_CREATE,
      data,
    );
    return res.data;
  },

  getTree: async (agentId: string): Promise<WikiTreeResponse> => {
    const res = await authApiClient.get<WikiTreeResponse>(
      API_ENDPOINTS.WIKI_TREE,
      { params: { agent_id: agentId } },
    );
    return res.data;
  },
};
