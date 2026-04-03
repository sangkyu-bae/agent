export const TOOL_CATEGORY = {
  search: 'search',
  execution: 'execution',
  api: 'api',
  data: 'data',
} as const;

export type ToolCategory = (typeof TOOL_CATEGORY)[keyof typeof TOOL_CATEGORY];

export const TOOL_CATEGORY_LABEL: Record<ToolCategory, string> = {
  search: '검색',
  execution: '실행',
  api: 'API',
  data: '데이터',
};

export interface Tool {
  id: string;
  name: string;
  description: string;
  category: ToolCategory;
  icon: string;
  enabled: boolean;
  version?: string;
}

export interface ToolToggleRequest {
  toolId: string;
  enabled: boolean;
}

export interface ToolToggleResponse {
  toolId: string;
  enabled: boolean;
}
