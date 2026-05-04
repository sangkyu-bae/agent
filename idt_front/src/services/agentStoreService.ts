import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  AgentListParams,
  AgentListResponse,
  AgentDetail,
  SubscribeResponse,
  UpdateSubscriptionRequest,
  ForkAgentRequest,
  ForkAgentResponse,
  MyAgentListParams,
  MyAgentListResponse,
  ForkStatsResponse,
  PublishAgentRequest,
} from '@/types/agentStore';

export const agentStoreService = {
  getAgents: (params: AgentListParams) =>
    authApiClient.get<AgentListResponse>(API_ENDPOINTS.AGENT_STORE_LIST, { params }),

  getAgent: (agentId: string) =>
    authApiClient.get<AgentDetail>(API_ENDPOINTS.AGENT_STORE_DETAIL(agentId)),

  subscribe: (agentId: string) =>
    authApiClient.post<SubscribeResponse>(API_ENDPOINTS.AGENT_STORE_SUBSCRIBE(agentId)),

  unsubscribe: (agentId: string) =>
    authApiClient.delete(API_ENDPOINTS.AGENT_STORE_SUBSCRIBE(agentId)),

  updateSubscription: (agentId: string, body: UpdateSubscriptionRequest) =>
    authApiClient.patch<SubscribeResponse>(API_ENDPOINTS.AGENT_STORE_SUBSCRIBE(agentId), body),

  fork: (agentId: string, body?: ForkAgentRequest) =>
    authApiClient.post<ForkAgentResponse>(API_ENDPOINTS.AGENT_STORE_FORK(agentId), body ?? {}),

  getMyAgents: (params: MyAgentListParams) =>
    authApiClient.get<MyAgentListResponse>(API_ENDPOINTS.AGENT_STORE_MY, { params }),

  getForkStats: (agentId: string) =>
    authApiClient.get<ForkStatsResponse>(API_ENDPOINTS.AGENT_STORE_FORK_STATS(agentId)),

  publishAgent: (agentId: string, body: PublishAgentRequest) =>
    authApiClient.patch(API_ENDPOINTS.AGENT_STORE_DETAIL(agentId), body),
};
