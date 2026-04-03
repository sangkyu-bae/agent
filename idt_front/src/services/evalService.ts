import apiClient from '@/services/api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { EvalDatasetResponse } from '@/types/eval';

const evalService = {
  extractDataset: async (file: File): Promise<EvalDatasetResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<EvalDatasetResponse>(
      API_ENDPOINTS.EVAL_DATASET_EXTRACT,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
  },
};

export default evalService;
