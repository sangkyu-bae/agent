import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ComposeAgentRequest,
  ComposeAgentDraftResponse,
} from '@/types/agentComposer';

// fix-agent-composer: 자연어 → 에이전트 초안 조합 (무저장)
export const agentComposerService = {
  compose: (data: ComposeAgentRequest) =>
    authApiClient.post<ComposeAgentDraftResponse>(
      API_ENDPOINTS.AGENT_COMPOSE,
      data,
    ),
};
