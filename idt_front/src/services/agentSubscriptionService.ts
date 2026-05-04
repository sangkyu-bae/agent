import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  MyAgentsParams,
  MyAgentsResponse,
  SubscriptionResponse,
  UpdateSubscriptionRequest,
  ForkAgentRequest,
  ForkAgentResponse,
  MyAgent,
} from '@/types/agent';
import type { AgentSummary } from '@/types/agent';

export const toAgentSummary = (agent: MyAgent): AgentSummary => ({
  id: agent.agent_id,
  name: agent.name,
  description: agent.description,
  category: agent.source_type,
  isDefault: false,
});

export const agentSubscriptionService = {
  getMyAgents: (params?: MyAgentsParams) =>
    authApiClient.get<MyAgentsResponse>(API_ENDPOINTS.AGENT_MY, { params }),

  subscribe: (agentId: string) =>
    authApiClient.post<SubscriptionResponse>(
      API_ENDPOINTS.AGENT_SUBSCRIBE(agentId),
    ),

  unsubscribe: (agentId: string) =>
    authApiClient.delete(API_ENDPOINTS.AGENT_SUBSCRIBE(agentId)),

  updateSubscription: (agentId: string, data: UpdateSubscriptionRequest) =>
    authApiClient.patch<SubscriptionResponse>(
      API_ENDPOINTS.AGENT_SUBSCRIBE(agentId),
      data,
    ),

  forkAgent: (agentId: string, data?: ForkAgentRequest) =>
    authApiClient.post<ForkAgentResponse>(
      API_ENDPOINTS.AGENT_FORK(agentId),
      data,
    ),
};
