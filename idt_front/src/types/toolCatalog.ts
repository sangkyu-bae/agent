export interface CatalogTool {
  tool_id: string;
  source: 'internal' | 'mcp';
  name: string;
  description: string;
  mcp_server_id: string | null;
  mcp_server_name: string | null;
  requires_env: string[];
}

export interface ToolCatalogResponse {
  tools: CatalogTool[];
}
