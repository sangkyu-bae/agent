import authApiClient from './api/authClient';
import { ApiError } from './api/ApiError';
import { API_ENDPOINTS } from '@/constants/api';
import type { AgentDocumentTemplateResponse } from '@/types/documentExtractor';
import type { AgentListResponse, AgentDetail } from '@/types/agentStore';
import type {
  CreateBuilderAgentRequest,
  CreateBuilderAgentResponse,
  UpdateBuilderAgentRequest,
  UpdateBuilderAgentResponse,
  AvailableSubAgentsResponse,
} from '@/types/agentBuilder';

export const agentBuilderService = {
  listMine: (params?: { search?: string; page?: number; size?: number }) =>
    authApiClient.get<AgentListResponse>(API_ENDPOINTS.AGENT_STORE_LIST, {
      params: { scope: 'mine', ...params },
    }),

  getDetail: (agentId: string) =>
    authApiClient.get<AgentDetail>(API_ENDPOINTS.AGENT_BUILDER_DETAIL(agentId)),

  create: (data: CreateBuilderAgentRequest) =>
    authApiClient.post<CreateBuilderAgentResponse>(
      API_ENDPOINTS.AGENT_BUILDER_CREATE,
      data,
    ),

  update: (agentId: string, data: UpdateBuilderAgentRequest) =>
    authApiClient.patch<UpdateBuilderAgentResponse>(
      API_ENDPOINTS.AGENT_BUILDER_UPDATE(agentId),
      data,
    ),

  delete: (agentId: string) =>
    authApiClient.delete(API_ENDPOINTS.AGENT_BUILDER_DELETE(agentId)),

  listAvailableSubAgents: () =>
    authApiClient.get<AvailableSubAgentsResponse>(
      API_ENDPOINTS.AGENT_AVAILABLE_SUB_AGENTS,
    ),

  /** extractor-template-preview §6: 404(양식 없음)는 null, 그 외 오류는 전파 */
  getDocumentTemplate: async (
    agentId: string,
  ): Promise<AgentDocumentTemplateResponse | null> => {
    try {
      const { data } = await authApiClient.get<AgentDocumentTemplateResponse>(
        API_ENDPOINTS.AGENT_DOCUMENT_TEMPLATE(agentId),
      );
      return data;
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },
};
