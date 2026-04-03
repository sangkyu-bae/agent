import apiClient from '@/services/api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { Tool, ToolToggleRequest, ToolToggleResponse } from '@/types/tool';

const toolService = {
  getTools: async (): Promise<Tool[]> => {
    const response = await apiClient.get<Tool[]>(API_ENDPOINTS.TOOLS);
    return response.data;
  },

  toggleTool: async (req: ToolToggleRequest): Promise<ToolToggleResponse> => {
    const response = await apiClient.patch<ToolToggleResponse>(
      API_ENDPOINTS.TOOL_TOGGLE(req.toolId),
      { enabled: req.enabled },
    );
    return response.data;
  },
};

export default toolService;
