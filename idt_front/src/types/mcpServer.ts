/**
 * MCP 서버 레지스트리 타입 — 백엔드 `src/application/mcp_registry/schemas.py` 매핑.
 *
 * 시크릿(auth_config·server_config)은 응답에서 '****'로 마스킹되어 온다.
 */

export type McpTransport = 'sse' | 'streamable_http';

/** 백엔드 MCPServerResponse 매핑 */
export interface McpServer {
  id: string;
  user_id: string;
  name: string;
  description: string;
  endpoint: string;
  transport: McpTransport;
  input_schema: Record<string, unknown> | null;
  is_active: boolean;
  tool_id: string;
  created_at: string;
  updated_at: string;
  auth_config: Record<string, unknown> | null; // masked
  server_config: Record<string, unknown> | null; // masked
}

/** 백엔드 ListMCPServersResponse 매핑 */
export interface McpServerListResponse {
  items: McpServer[];
  total: number;
}

/** 백엔드 RegisterMCPServerRequest 매핑 (user_id는 서비스에서 주입) */
export interface RegisterMcpServerRequest {
  user_id: string;
  name: string;
  description: string;
  endpoint: string;
  transport: McpTransport;
  input_schema?: Record<string, unknown> | null;
  auth_config?: Record<string, unknown> | null;
  server_config?: Record<string, unknown> | null;
}

/** 백엔드 UpdateMCPServerRequest 매핑 (모든 필드 optional) */
export interface UpdateMcpServerRequest {
  name?: string;
  description?: string;
  endpoint?: string;
  transport?: McpTransport;
  is_active?: boolean;
  input_schema?: Record<string, unknown> | null;
  auth_config?: Record<string, unknown> | null;
  server_config?: Record<string, unknown> | null;
}

/** 백엔드 MCPConnectionTestResponse 매핑 */
export interface McpConnectionTestResponse {
  ok: boolean;
  tools?: { name: string; description: string }[] | null;
  error?: string | null;
  elapsed_ms?: number | null;
}
