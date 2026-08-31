// golden-sample-blueprint Design §4.1 — 9 엔드포인트. 컴포넌트는 이 서비스만 경유한다.
import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  BlueprintCreateRequest,
  BlueprintExtractResponse,
  BlueprintOptionsResponse,
  BlueprintResponse,
  BlueprintSummary,
  BlueprintUpdateRequest,
  FontsResponse,
} from '@/types/blueprint';

export const blueprintService = {
  extract: async (file: File, maxPages?: number): Promise<BlueprintExtractResponse> => {
    const form = new FormData();
    form.append('file', file);
    const { data } = await authApiClient.post<BlueprintExtractResponse>(
      API_ENDPOINTS.ADMIN_BLUEPRINTS_EXTRACT,
      form,
      {
        params: maxPages ? { max_pages: maxPages } : undefined,
        headers: { 'Content-Type': 'multipart/form-data' },
        // 비전 분류 N페이지 + 종합 — Plan NFR: 20페이지 ≤ 90s
        timeout: 300_000,
      }
    );
    return data;
  },

  list: async (includeInactive = true): Promise<BlueprintSummary[]> => {
    const { data } = await authApiClient.get<BlueprintSummary[]>(API_ENDPOINTS.ADMIN_BLUEPRINTS, {
      params: { include_inactive: includeInactive },
    });
    return data;
  },

  get: async (id: string): Promise<BlueprintResponse> => {
    const { data } = await authApiClient.get<BlueprintResponse>(
      API_ENDPOINTS.ADMIN_BLUEPRINT_DETAIL(id)
    );
    return data;
  },

  create: async (req: BlueprintCreateRequest): Promise<BlueprintResponse> => {
    const { data } = await authApiClient.post<BlueprintResponse>(
      API_ENDPOINTS.ADMIN_BLUEPRINTS,
      req
    );
    return data;
  },

  update: async (id: string, req: BlueprintUpdateRequest): Promise<BlueprintResponse> => {
    const { data } = await authApiClient.put<BlueprintResponse>(
      API_ENDPOINTS.ADMIN_BLUEPRINT_DETAIL(id),
      req
    );
    return data;
  },

  deactivate: async (id: string): Promise<BlueprintResponse> => {
    const { data } = await authApiClient.delete<BlueprintResponse>(
      API_ENDPOINTS.ADMIN_BLUEPRINT_DETAIL(id)
    );
    return data;
  },

  fonts: async (): Promise<FontsResponse> => {
    const { data } = await authApiClient.get<FontsResponse>(API_ENDPOINTS.ADMIN_BLUEPRINTS_FONTS);
    return data;
  },

  /** 에이전트 빌더 드롭다운 — active 만, 로그인 사용자 */
  options: async (): Promise<BlueprintOptionsResponse> => {
    const { data } = await authApiClient.get<BlueprintOptionsResponse>(
      API_ENDPOINTS.BLUEPRINT_OPTIONS
    );
    return data;
  },
};
