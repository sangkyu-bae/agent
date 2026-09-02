import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  SetBuiltinResponse,
  SyncMcpToolsResponse,
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
  // mcp-tool-auto-sync FR-11: 서버별 도구 재동기화 (admin 전용).
  // 등록/수정 시 자동 sync가 실패했을 때의 복구 경로이자,
  // MCP 서버 쪽 도구가 나중에 바뀐 경우의 재반영 수단이다.
  syncMcpTools: (mcpServerId: string) =>
    authApiClient.post<SyncMcpToolsResponse>(API_ENDPOINTS.TOOL_CATALOG_SYNC, {
      mcp_server_id: mcpServerId,
    }),
};
