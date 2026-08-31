// multimodal-extractor Design §4.1 — 4 엔드포인트. 컴포넌트는 이 서비스만 경유한다.
import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ConnectionTestResponse,
  MultimodalPreviewResponse,
  MultimodalSettingsRequest,
  MultimodalSettingsResponse,
} from '@/types/multimodal';

export const multimodalService = {
  getSettings: async (): Promise<MultimodalSettingsResponse> => {
    const { data } = await authApiClient.get<MultimodalSettingsResponse>(
      API_ENDPOINTS.ADMIN_MULTIMODAL_SETTINGS
    );
    return data;
  },

  /** PUT 전체 교체 */
  updateSettings: async (
    req: MultimodalSettingsRequest
  ): Promise<MultimodalSettingsResponse> => {
    const { data } = await authApiClient.put<MultimodalSettingsResponse>(
      API_ENDPOINTS.ADMIN_MULTIMODAL_SETTINGS,
      req
    );
    return data;
  },

  /** image 생략 시 서버 내장 샘플 차트로 호출 */
  testConnection: async (image?: File | null): Promise<ConnectionTestResponse> => {
    const form = new FormData();
    if (image) form.append('image', image);
    const { data } = await authApiClient.post<ConnectionTestResponse>(
      API_ENDPOINTS.ADMIN_MULTIMODAL_TEST,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 }
    );
    return data;
  },

  preview: async (file: File, debug = false): Promise<MultimodalPreviewResponse> => {
    const form = new FormData();
    form.append('file', file);
    const { data } = await authApiClient.post<MultimodalPreviewResponse>(
      API_ENDPOINTS.PREVIEW_MULTIMODAL,
      form,
      {
        params: { debug },
        headers: { 'Content-Type': 'multipart/form-data' },
        // 비전 호출 N건 — Plan NFR: 20장·concurrency 4 기준 ≤ 90s
        timeout: 300_000,
      }
    );
    return data;
  },
};
