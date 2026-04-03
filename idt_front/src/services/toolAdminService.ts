import apiClient from '@/services/api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  AdminTool,
  AdminToolCreateRequest,
  AdminToolUpdateRequest,
  AdminToolCreateResponse,
  AdminToolUpdateResponse,
  AdminToolDeleteResponse,
} from '@/types/toolAdmin';

const toolAdminService = {
  getTools: async (): Promise<AdminTool[]> => {
    const response = await apiClient.get<AdminTool[]>(API_ENDPOINTS.ADMIN_TOOLS);
    return response.data;
  },

  createTool: async (req: AdminToolCreateRequest): Promise<AdminToolCreateResponse> => {
    const response = await apiClient.post<AdminToolCreateResponse>(
      API_ENDPOINTS.ADMIN_TOOLS,
      req,
    );
    return response.data;
  },

  updateTool: async (toolId: string, req: AdminToolUpdateRequest): Promise<AdminToolUpdateResponse> => {
    const response = await apiClient.put<AdminToolUpdateResponse>(
      API_ENDPOINTS.ADMIN_TOOL_DETAIL(toolId),
      req,
    );
    return response.data;
  },

  deleteTool: async (toolId: string): Promise<AdminToolDeleteResponse> => {
    const response = await apiClient.delete<AdminToolDeleteResponse>(
      API_ENDPOINTS.ADMIN_TOOL_DETAIL(toolId),
    );
    return response.data;
  },
};

export default toolAdminService;
