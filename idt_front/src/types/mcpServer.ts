/**
 * MCP 서버 레지스트리 타입 — 백엔드 `src/application/mcp_registry/schemas.py` 매핑.
 *
 * 시크릿(auth_config·server_config)은 응답에서 '****'로 마스킹되어 온다.
 */

import type { ToolSyncResult } from '@/types/toolCatalog';

export type McpTransport = 'sse' | 'streamable_http';

/**
 * mcp-identity-header §3.1 — 신원 클레임 값을 꺼낼 사용자 속성.
 * 백엔드 ClaimSource(str Enum) 매핑.
 */
export const IDENTITY_CLAIM_SOURCES = {
  MAILBOX_UPN: 'mailbox_upn',
  EMAIL: 'email',
} as const;
export type IdentityClaimSource =
  (typeof IDENTITY_CLAIM_SOURCES)[keyof typeof IDENTITY_CLAIM_SOURCES];

/** 백엔드 IdentityHeaderConfig 기본값 (mcp-outlook-server 계약 §3) */
export const IDENTITY_DEFAULTS = {
  issuer: 'agent-builder',
  header_name: 'X-MCP-Identity',
  claim_name: 'preferred_username',
  claim_source: IDENTITY_CLAIM_SOURCES.MAILBOX_UPN,
  ttl_seconds: 300,
  min_secret_length: 32,
  max_ttl_seconds: 300,
} as const;

/** 응답용 — secret 은 항상 '****' 로 마스킹되어 온다 */
export interface McpIdentityConfig {
  audience: string;
  issuer: string;
  header_name: string;
  claim_name: string;
  claim_source: IdentityClaimSource;
  ttl_seconds: number;
  secret: string;
}

/**
 * 요청용 — secret 을 생략하면 수정 시 기존 비밀을 유지한다 (Design §4.2).
 * 등록/수정 요청의 identity_config: undefined=불변, null=해제, 객체=교체.
 */
export interface McpIdentityConfigRequest {
  audience: string;
  issuer: string;
  header_name: string;
  claim_name: string;
  claim_source: IdentityClaimSource;
  ttl_seconds: number;
  secret?: string;
}

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
  /**
   * approval-gate-phase2 D-07: 이 서버의 도구가 카탈로그에 처음 등록될 때
   * requires_approval 로 시작할지. 이미 동기화된 도구에는 소급하지 않는다.
   */
  default_requires_approval: boolean;
  tool_id: string;
  created_at: string;
  updated_at: string;
  auth_config: Record<string, unknown> | null; // masked
  server_config: Record<string, unknown> | null; // masked
  /** mcp-identity-header: 호출자 신원 헤더 설정 (secret 마스킹). null = 미사용 */
  identity_config?: McpIdentityConfig | null;
  /**
   * mcp-tool-auto-sync FR-09: 등록/수정 직후의 도구 동기화 결과.
   * 조회(GET) 응답에서는 항상 null — sync를 수행하지 않았다는 뜻이다.
   */
  tool_sync?: ToolSyncResult | null;
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
  default_requires_approval?: boolean;
  identity_config?: McpIdentityConfigRequest | null;
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
  default_requires_approval?: boolean;
  /** 3상태 — 키 없음=불변, null=해제, 객체=교체(secret 없으면 기존 유지) */
  identity_config?: McpIdentityConfigRequest | null;
}

/** 백엔드 MCPConnectionTestResponse 매핑 */
export interface McpConnectionTestResponse {
  ok: boolean;
  tools?: { name: string; description: string }[] | null;
  error?: string | null;
  elapsed_ms?: number | null;
}
