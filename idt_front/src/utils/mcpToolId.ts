// MCP tool_id 판별·표시 헬퍼.
// 백엔드 `src/domain/tool_catalog/mcp_tool_id.py`와 동일한 두 형식을 해석한다.
//   - `mcp:{serverId}:{toolName}` — 카탈로그 형식(정상). 개별 도구.
//   - `mcp_{serverId}`            — 레거시 서버 단위. 도구를 특정하지 못한다.

export interface McpToolRef {
  serverId: string;
  /** 레거시 서버 단위 형식이면 null */
  toolName: string | null;
}

const CATALOG_PREFIX = 'mcp:';
const LEGACY_PREFIX = 'mcp_';

export function parseMcpToolId(toolId: string): McpToolRef | null {
  if (!toolId) return null;

  if (toolId.startsWith(CATALOG_PREFIX)) {
    const rest = toolId.slice(CATALOG_PREFIX.length);
    const sep = rest.indexOf(':');
    if (sep <= 0) return null;
    const serverId = rest.slice(0, sep);
    // 도구명에 콜론이 들어갈 수 있으므로 첫 구분자 뒤 전체를 도구명으로 본다.
    const toolName = rest.slice(sep + 1);
    if (!serverId || !toolName) return null;
    return { serverId, toolName };
  }

  if (toolId.startsWith(LEGACY_PREFIX)) {
    const serverId = toolId.slice(LEGACY_PREFIX.length);
    return serverId ? { serverId, toolName: null } : null;
  }

  return null;
}

export function isMcpToolId(toolId: string): boolean {
  return parseMcpToolId(toolId) !== null;
}

/** 칩·목록에 보여줄 짧은 이름. UUID가 화면을 덮지 않게 한다. */
export function mcpToolLabel(toolId: string): string {
  return parseMcpToolId(toolId)?.toolName ?? toolId;
}
