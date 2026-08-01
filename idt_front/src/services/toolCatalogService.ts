import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  SetBuiltinResponse,
  ToolCatalogResponse,
} from '@/types/toolCatalog';

export const toolCatalogService = {
  getToolCatalog: () =>
    authApiClient.get<ToolCatalogResponse>(API_ENDPOINTS.TOOL_CATALOG),
  // builtin-tools D3: 관리자 전용 빌트인 등록/해제
  setBuiltin: (toolId: string, isBuiltin: boolean) =>
    authApiClient.patch<SetBuiltinResponse>(API_ENDPOINTS.TOOL_CATALOG_BUILTIN, {
      tool_id: toolId,
      is_builtin: isBuiltin,
    }),
};
