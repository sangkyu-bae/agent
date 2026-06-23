import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  McpServer,
  McpServerListResponse,
  RegisterMcpServerRequest,
  UpdateMcpServerRequest,
  McpConnectionTestResponse,
} from '@/types/mcpServer';

export const mcpServerService = {
  /** 전체 활성 MCP 서버 목록 (user_id 미전달 → 전체 조회). */
  getServers: async (): Promise<McpServerListResponse> => {
    const { data } = await authApiClient.get<McpServerListResponse>(
      API_ENDPOINTS.MCP_SERVERS,
    );
    return data;
  },

  createServer: async (req: RegisterMcpServerRequest): Promise<McpServer> => {
    const { data } = await authApiClient.post<McpServer>(
      API_ENDPOINTS.MCP_SERVERS,
      req,
    );
    return data;
  },

  // 백엔드 라우터는 PUT (부서 관리의 patch와 다름)
  updateServer: async (
    id: string,
    req: UpdateMcpServerRequest,
  ): Promise<McpServer> => {
    const { data } = await authApiClient.put<McpServer>(
      API_ENDPOINTS.MCP_SERVER_DETAIL(id),
      req,
    );
    return data;
  },

  deleteServer: async (id: string): Promise<void> => {
    await authApiClient.delete(API_ENDPOINTS.MCP_SERVER_DETAIL(id));
  },

  /** 등록된 서버에 실제 연결해 도구 목록 확인. 실패는 ok:false 본문으로 옴. */
  testConnection: async (id: string): Promise<McpConnectionTestResponse> => {
    const { data } = await authApiClient.post<McpConnectionTestResponse>(
      API_ENDPOINTS.MCP_SERVER_TEST(id),
    );
    return data;
  },
};
