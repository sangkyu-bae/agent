import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { LlmModelListResponse } from '@/types/llmModel';

export const llmModelService = {
  getLlmModels: async (includeInactive = false): Promise<LlmModelListResponse> => {
    const { data } = await authApiClient.get<LlmModelListResponse>(
      API_ENDPOINTS.LLM_MODELS,
      { params: { include_inactive: includeInactive } }
    );
    return data;
  },
};
