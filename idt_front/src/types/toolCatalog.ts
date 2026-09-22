/** mcp-tool-category-routing §3.1: 백엔드 ToolCategoryPolicy.ALLOWED와 1:1 */
export const TOOL_CATEGORIES = ['search', 'collect', 'analysis', 'action'] as const;

export type ToolCategory = (typeof TOOL_CATEGORIES)[number];

/** 카테고리 표시 라벨 — 관리자 화면 셀렉트/배지 공용 */
export const TOOL_CATEGORY_LABELS: Record<ToolCategory, string> = {
  search: '검색',
  collect: '수집',
  analysis: '분석',
  action: '실행',
};

export const TOOL_CALL_LIMIT_MIN = 1;
export const TOOL_CALL_LIMIT_MAX = 20;

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
  /**
   * mcp-tool-category-routing: 워커 노드 분류.
   * null = 미분류 → 기존 react 경로. 관리자가 지정한 도구만 동작이 바뀐다.
   */
  category: ToolCategory | null;
  /** 워커 1회 실행당 도구 호출 상한. null이면 정책 기본값(2회) */
  max_tool_calls: number | null;
  /**
   * approval-gate Check G2: 이 도구 호출 전 사람 승인 필요 여부 (관리자 토글).
   * 게이트는 이 값과 에이전트별 승인 게이트 설정이 모두 켜져야 발동한다.
   */
  requires_approval?: boolean;
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

// mcp-tool-category-routing §4.2: 분류·호출 상한 지정 (PATCH /api/v1/tool-catalog/metadata)
// 필드를 생략하면 미변경, 명시적 null은 '미분류/기본값으로 되돌리기'다.
export interface ToolMetadataRequest {
  tool_id: string;
  category?: ToolCategory | null;
  max_tool_calls?: number | null;
  /** approval-gate Check G2: 생략하면 미변경. null 은 서버가 400 으로 거부 */
  requires_approval?: boolean;
}

export interface ToolMetadataResponse {
  tool_id: string;
  category: ToolCategory | null;
  max_tool_calls: number | null;
  requires_approval?: boolean;
}
