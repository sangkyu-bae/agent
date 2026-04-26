import apiClient from './api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { EmbeddingModelListResponse } from '@/types/embeddingModel';

export const embeddingModelService = {
  getEmbeddingModels: async (): Promise<EmbeddingModelListResponse> => {
    const res = await apiClient.get<EmbeddingModelListResponse>(
      API_ENDPOINTS.EMBEDDING_MODELS,
    );
    return res.data;
  },
};
