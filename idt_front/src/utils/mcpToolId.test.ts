// MCP tool_id 판별·표시 헬퍼 — 백엔드 src/domain/tool_catalog/mcp_tool_id.py 대응
import { describe, it, expect } from 'vitest';
import { isMcpToolId, mcpToolLabel, parseMcpToolId } from './mcpToolId';

const UUID = '081c6fe7-e0bd-4aad-9a42-29b8bf073167';

describe('parseMcpToolId', () => {
  it('카탈로그 형식에서 서버ID와 도구명을 분리한다', () => {
    expect(parseMcpToolId(`mcp:${UUID}:create_issue`)).toEqual({
      serverId: UUID,
      toolName: 'create_issue',
    });
  });

  it('도구명에 콜론이 있어도 서버ID 뒤 전체가 도구명이다', () => {
    expect(parseMcpToolId(`mcp:${UUID}:ns:create`)).toEqual({
      serverId: UUID,
      toolName: 'ns:create',
    });
  });

  it('레거시 서버 단위 형식은 도구명이 null이다', () => {
    expect(parseMcpToolId(`mcp_${UUID}`)).toEqual({
      serverId: UUID,
      toolName: null,
    });
  });

  it.each(['internal:excel_export', 'excel_export', '', 'mcp:', `mcp:${UUID}`, 'mcp_'])(
    'MCP 형식이 아니면 null (%s)',
    (id) => {
      expect(parseMcpToolId(id)).toBeNull();
    },
  );
});

describe('isMcpToolId', () => {
  it('두 형식 모두 true', () => {
    expect(isMcpToolId(`mcp:${UUID}:x`)).toBe(true);
    expect(isMcpToolId(`mcp_${UUID}`)).toBe(true);
  });

  it('내부 도구는 false', () => {
    expect(isMcpToolId('internal:excel_export')).toBe(false);
  });
});

describe('mcpToolLabel', () => {
  it('개별 도구는 도구명만 보여준다 (UUID 노출 방지)', () => {
    expect(mcpToolLabel(`mcp:${UUID}:create_issue`)).toBe('create_issue');
  });

  it('레거시 서버 단위는 원본을 유지한다', () => {
    expect(mcpToolLabel(`mcp_${UUID}`)).toBe(`mcp_${UUID}`);
  });

  it('MCP가 아니면 원본을 유지한다', () => {
    expect(mcpToolLabel('excel_export')).toBe('excel_export');
  });
});
