import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
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
};
