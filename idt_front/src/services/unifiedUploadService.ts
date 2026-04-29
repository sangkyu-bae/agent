import apiClient from '@/services/api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { UnifiedUploadParams, UnifiedUploadResponse } from '@/types/unifiedUpload';

const unifiedUploadService = {
  uploadDocument: async (
    file: File,
    params: UnifiedUploadParams,
  ): Promise<UnifiedUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<UnifiedUploadResponse>(
      API_ENDPOINTS.DOCUMENT_UPLOAD_ALL,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        params,
        timeout: 120_000,
      },
    );
    return response.data;
  },
};

export default unifiedUploadService;
