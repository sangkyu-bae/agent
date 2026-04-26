import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { ToolCatalogResponse } from '@/types/toolCatalog';

export const toolCatalogService = {
  getToolCatalog: () =>
    authApiClient.get<ToolCatalogResponse>(API_ENDPOINTS.TOOL_CATALOG),
};
