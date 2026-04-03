import apiClient from './api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { AgentRun, RunAgentRequest, RunAgentResponse } from '@/types/agent';
import type { ApiResponse } from '@/types/api';

export const agentService = {
  run: (payload: RunAgentRequest) =>
    apiClient.post<ApiResponse<RunAgentResponse>>(API_ENDPOINTS.AGENT_RUN, payload),

  getRunStatus: (runId: string) =>
    apiClient.get<ApiResponse<AgentRun>>(API_ENDPOINTS.AGENT_RUN_STATUS(runId)),

  getStreamUrl: (runId: string) =>
    `${API_ENDPOINTS.AGENT_STREAM(runId)}`,
};
