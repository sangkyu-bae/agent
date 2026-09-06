import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  SetBuiltinResponse,
  SyncMcpToolsResponse,
  ToolCatalogResponse,
  ToolMetadataRequest,
  ToolMetadataResponse,
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
  // mcp-tool-category-routing FR-13: 분류·호출 상한 지정 (admin 전용).
  // 부분 갱신 — payload에 담은 필드만 서버에서 갱신된다.
  updateMetadata: (payload: ToolMetadataRequest) =>
    authApiClient.patch<ToolMetadataResponse>(
      API_ENDPOINTS.TOOL_CATALOG_METADATA,
      payload,
    ),
  // mcp-tool-auto-sync FR-11: 서버별 도구 재동기화 (admin 전용).
  // 등록/수정 시 자동 sync가 실패했을 때의 복구 경로이자,
  // MCP 서버 쪽 도구가 나중에 바뀐 경우의 재반영 수단이다.
  syncMcpTools: (mcpServerId: string) =>
    authApiClient.post<SyncMcpToolsResponse>(API_ENDPOINTS.TOOL_CATALOG_SYNC, {
      mcp_server_id: mcpServerId,
    }),
};
