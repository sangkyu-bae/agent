/**
 * MCP 서버 폼의 "호출자 신원 헤더" 섹션 — 순수 변환·검증 (mcp-identity-header §4.2, §5.1).
 *
 * 전송 3상태 (백엔드 UpdateMCPServerRequest.identity_config):
 * - undefined: 키를 보내지 않음 → 불변
 * - null: 해제
 * - 객체: 교체. secret 이 없으면 백엔드가 기존 비밀을 유지한다.
 */
import {
  IDENTITY_DEFAULTS,
  type IdentityClaimSource,
  type McpIdentityConfigRequest,
  type McpServer,
} from '@/types/mcpServer';

export interface IdentityFormState {
  enabled: boolean;
  audience: string;
  /** 응답은 마스킹되어 오므로 항상 빈 값으로 시작한다 (입력 시에만 교체) */
  secret: string;
  claimSource: IdentityClaimSource;
  headerName: string;
  claimName: string;
  issuer: string;
  /** 입력창 값 그대로 — 검증 후 정수로 변환한다 */
  ttlSeconds: string;
}

export const emptyIdentityForm = (): IdentityFormState => ({
  enabled: false,
  audience: '',
  secret: '',
  claimSource: IDENTITY_DEFAULTS.claim_source,
  headerName: IDENTITY_DEFAULTS.header_name,
  claimName: IDENTITY_DEFAULTS.claim_name,
  issuer: IDENTITY_DEFAULTS.issuer,
  ttlSeconds: String(IDENTITY_DEFAULTS.ttl_seconds),
});

export const identityFormFromServer = (server: McpServer | null): IdentityFormState => {
  const cfg = server?.identity_config;
  if (!cfg) return emptyIdentityForm();
  return {
    enabled: true,
    audience: cfg.audience,
    secret: '',
    claimSource: cfg.claim_source,
    headerName: cfg.header_name,
    claimName: cfg.claim_name,
    issuer: cfg.issuer,
    ttlSeconds: String(cfg.ttl_seconds),
  };
};

const parseTtl = (raw: string): number | null => {
  if (!/^\d+$/.test(raw.trim())) return null;
  const ttl = Number(raw.trim());
  return ttl >= 1 && ttl <= IDENTITY_DEFAULTS.max_ttl_seconds ? ttl : null;
};

/** 오류 문구를 돌려준다. 통과면 null. hasExisting: 서버에 이미 신원 설정이 있는가 */
export const validateIdentityForm = (
  state: IdentityFormState,
  hasExisting: boolean,
): string | null => {
  if (!state.enabled) return null;
  if (!state.audience.trim()) return '신원 헤더 audience는 필수입니다.';
  const secret = state.secret.trim();
  if (!secret && !hasExisting) return '서명 비밀은 필수입니다.';
  if (secret && secret.length < IDENTITY_DEFAULTS.min_secret_length) {
    return `서명 비밀은 ${IDENTITY_DEFAULTS.min_secret_length}자 이상이어야 합니다.`;
  }
  if (parseTtl(state.ttlSeconds) === null) {
    return `토큰 수명은 1~${IDENTITY_DEFAULTS.max_ttl_seconds}초 정수여야 합니다.`;
  }
  return null;
};

/** validateIdentityForm 통과 후 호출한다 */
export const buildIdentityPayload = (
  state: IdentityFormState,
  hasExisting: boolean,
): McpIdentityConfigRequest | null | undefined => {
  if (!state.enabled) return hasExisting ? null : undefined;
  const payload: McpIdentityConfigRequest = {
    audience: state.audience.trim(),
    issuer: state.issuer.trim() || IDENTITY_DEFAULTS.issuer,
    header_name: state.headerName.trim() || IDENTITY_DEFAULTS.header_name,
    claim_name: state.claimName.trim() || IDENTITY_DEFAULTS.claim_name,
    claim_source: state.claimSource,
    ttl_seconds: parseTtl(state.ttlSeconds) ?? IDENTITY_DEFAULTS.ttl_seconds,
  };
  const secret = state.secret.trim();
  if (secret) payload.secret = secret;
  return payload;
};
