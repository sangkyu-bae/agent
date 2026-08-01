export interface CatalogTool {
  tool_id: string;
  source: 'internal' | 'mcp';
  name: string;
  description: string;
  mcp_server_id: string | null;
  mcp_server_name: string | null;
  requires_env: string[];
  /** builtin-tools: 에이전트 생성 시 자동 주입되는 빌트인 여부 (관리자 토글, 백엔드 상시 반환) */
  is_builtin: boolean;
}

export interface ToolCatalogResponse {
  tools: CatalogTool[];
}

// builtin-tools D3: 관리자 빌트인 토글 (PATCH /api/v1/tool-catalog/builtin)
export interface SetBuiltinRequest {
  tool_id: string;
  is_builtin: boolean;
}

export interface SetBuiltinResponse {
  tool_id: string;
  is_builtin: boolean;
}
