import { describe, expect, it } from 'vitest';
import type { McpServer } from '@/types/mcpServer';
import {
  buildIdentityPayload,
  emptyIdentityForm,
  identityFormFromServer,
  validateIdentityForm,
} from './mcpIdentityForm';

// mcp-identity-header Design §4.2 / §5.1 — PUT 3상태 규칙:
// 필드 없음(undefined)=불변, null=해제, 객체=교체(secret 비면 기존 비밀 유지)

const SECRET = 's'.repeat(32);

const serverWith = (identity: McpServer['identity_config']): McpServer =>
  ({ id: 'srv-1', identity_config: identity }) as McpServer;

const enabledForm = (over: Partial<ReturnType<typeof emptyIdentityForm>> = {}) => ({
  ...emptyIdentityForm(),
  enabled: true,
  audience: 'mcp-outlook-server',
  secret: SECRET,
  ...over,
});

describe('identityFormFromServer', () => {
  it('신원 설정이 없으면 꺼진 기본 폼', () => {
    expect(identityFormFromServer(serverWith(null))).toEqual(emptyIdentityForm());
    expect(identityFormFromServer(null)).toEqual(emptyIdentityForm());
  });

  it('기존 설정을 켜진 상태로 불러오되 마스킹된 비밀은 비운다', () => {
    const form = identityFormFromServer(
      serverWith({
        audience: 'aud', issuer: 'iss', header_name: 'X-Id', claim_name: 'email',
        claim_source: 'email', ttl_seconds: 120, secret: '****',
      }),
    );
    expect(form).toMatchObject({
      enabled: true, audience: 'aud', issuer: 'iss', headerName: 'X-Id',
      claimName: 'email', claimSource: 'email', ttlSeconds: '120', secret: '',
    });
  });
});

describe('validateIdentityForm', () => {
  it('꺼져 있으면 검사하지 않는다', () => {
    expect(validateIdentityForm(emptyIdentityForm(), false)).toBeNull();
  });

  it('audience 는 필수', () => {
    expect(validateIdentityForm(enabledForm({ audience: '  ' }), false)).toMatch(/audience/);
  });

  it('새 설정이면 서명 비밀이 필수', () => {
    expect(validateIdentityForm(enabledForm({ secret: '' }), false)).toMatch(/서명 비밀/);
  });

  it('기존 설정이 있으면 비밀을 비워도 된다 (기존 유지)', () => {
    expect(validateIdentityForm(enabledForm({ secret: '' }), true)).toBeNull();
  });

  it('입력한 비밀은 32자 이상', () => {
    expect(validateIdentityForm(enabledForm({ secret: 's'.repeat(31) }), true)).toMatch(/32자/);
  });

  it.each(['0', '301', 'abc', '1.5'])('토큰 수명 %s 는 거부', (ttl) => {
    expect(validateIdentityForm(enabledForm({ ttlSeconds: ttl }), false)).toMatch(/수명/);
  });
});

describe('buildIdentityPayload', () => {
  it('꺼져 있고 기존 설정이 없으면 필드를 보내지 않는다', () => {
    expect(buildIdentityPayload(emptyIdentityForm(), false)).toBeUndefined();
  });

  it('꺼져 있고 기존 설정이 있으면 null — 해제', () => {
    expect(buildIdentityPayload(emptyIdentityForm(), true)).toBeNull();
  });

  it('켜져 있으면 전체 설정 객체를 만든다', () => {
    expect(buildIdentityPayload(enabledForm(), false)).toEqual({
      audience: 'mcp-outlook-server',
      secret: SECRET,
      issuer: 'agent-builder',
      header_name: 'X-MCP-Identity',
      claim_name: 'preferred_username',
      claim_source: 'mailbox_upn',
      ttl_seconds: 300,
    });
  });

  it('비밀을 비우면 secret 키 자체를 넣지 않는다 (기존 유지)', () => {
    const payload = buildIdentityPayload(enabledForm({ secret: '' }), true);
    expect(payload).not.toHaveProperty('secret');
    expect(payload).toMatchObject({ audience: 'mcp-outlook-server' });
  });

  it('값의 앞뒤 공백을 제거한다', () => {
    const payload = buildIdentityPayload(enabledForm({ audience: '  aud  ' }), false);
    expect(payload).toMatchObject({ audience: 'aud' });
  });
});
