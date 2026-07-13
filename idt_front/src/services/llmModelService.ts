import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CreateLlmModelRequest,
  LlmModel,
  LlmModelListResponse,
  UpdateLlmModelPricingRequest,
  UpdateLlmModelRequest,
} from '@/types/llmModel';

export const llmModelService = {
  getLlmModels: async (includeInactive = false): Promise<LlmModelListResponse> => {
    const { data } = await authApiClient.get<LlmModelListResponse>(
      API_ENDPOINTS.LLM_MODELS,
      { params: { include_inactive: includeInactive } }
    );
    return data;
  },

  getLlmModel: async (id: string): Promise<LlmModel> => {
    const { data } = await authApiClient.get<LlmModel>(
      API_ENDPOINTS.LLM_MODEL_DETAIL(id)
    );
    return data;
  },

  createLlmModel: async (req: CreateLlmModelRequest): Promise<LlmModel> => {
    const { data } = await authApiClient.post<LlmModel>(
      API_ENDPOINTS.LLM_MODELS,
      req
    );
    return data;
  },

  updateLlmModel: async (
    id: string,
    req: UpdateLlmModelRequest
  ): Promise<LlmModel> => {
    const { data } = await authApiClient.patch<LlmModel>(
      API_ENDPOINTS.LLM_MODEL_DETAIL(id),
      req
    );
    return data;
  },

  updateLlmModelPricing: async (
    id: string,
    req: UpdateLlmModelPricingRequest
  ): Promise<LlmModel> => {
    const { data } = await authApiClient.patch<LlmModel>(
      API_ENDPOINTS.LLM_MODEL_PRICING(id),
      req
    );
    return data;
  },

  deactivateLlmModel: async (id: string): Promise<LlmModel> => {
    const { data } = await authApiClient.delete<LlmModel>(
      API_ENDPOINTS.LLM_MODEL_DETAIL(id)
    );
    return data;
  },
};
