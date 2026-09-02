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

// mcp-tool-auto-sync FR-11: MCP 서버 도구 동기화 (POST /api/v1/tool-catalog/sync)
export interface SyncMcpToolsRequest {
  /** 생략 시 전체 서버 동기화. UI는 항상 서버 1개를 지정한다(Design D5). */
  mcp_server_id?: string;
}

export interface SyncMcpToolsResponse {
  synced_count: number;
}

/**
 * 백엔드 ToolSyncResultResponse 매핑 — 등록/수정 응답의 tool_sync 필드.
 *
 * 상위 필드가 null이면 "이번 응답은 sync를 수행하지 않았다"는 뜻으로,
 * `ok: false`(시도 후 실패)와 구분된다(Design §4.2).
 */
export interface ToolSyncResult {
  ok: boolean;
  synced_count: number;
  error_hint: string | null;
}
